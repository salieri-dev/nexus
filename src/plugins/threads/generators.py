import os
import random
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import imgkit
from PIL import Image
from jinja2 import Environment, FileSystemLoader

from structlog import get_logger

log = get_logger(__name__)

# Russian date formatting constants
WEEKDAY_NAMES = {0: "Пнд", 1: "Втр", 2: "Срд", 3: "Чтв", 4: "Птн", 5: "Суб", 6: "Вск"}
MONTH_NAMES = {1: "Янв", 2: "Фев", 3: "Мар", 4: "Апр", 5: "Май", 6: "Июн",
               7: "Июл", 8: "Авг", 9: "Сен", 10: "Окт", 11: "Ноя", 12: "Дек"}


class BaseThreadGenerator(ABC):
    """Base class for thread image generators"""

    def __init__(self):
        self.template_dir = Path(f"src/plugins/threads/{self.get_template_name()}")
        self.template_path = self.template_dir / "template.html"
        self.images_dir = self.get_images_dir()

        if not self.template_path.exists():
            raise FileNotFoundError(f"Template not found: {self.template_path}")

        self.jinja_env = Environment(loader=FileSystemLoader(str(self.template_dir)))
        self.imgkit_config = imgkit.config()

    @abstractmethod
    def get_template_name(self) -> str:
        """Return the template directory name"""
        pass

    @abstractmethod
    def get_images_dir(self) -> Path:
        """Return the path to images directory"""
        pass

    @abstractmethod
    def format_story(self, text: str) -> str:
        """Format story text with proper styling"""
        pass

    @abstractmethod
    def format_comment_text(self, text: str, thread_id: str) -> str:
        """Format comment text with proper styling"""
        pass

    def format_date(self, dt: datetime, use_russian: bool = True) -> str:
        """Format date in Russian or English style"""
        if use_russian:
            weekday = WEEKDAY_NAMES[dt.weekday()]
            month = MONTH_NAMES[dt.month]
            return f"{dt.day:02d} {month} {dt.year % 100:02d} {weekday} {dt.hour:02d}:{dt.minute:02d}:{dt.second:02d}"
        else:
            weekday = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][dt.weekday()]
            return dt.strftime(f"%m/%d/%y({weekday})%H:%M:%S")

    def get_random_image(self) -> str:
        """Get random image path from the images directory"""
        if not self.images_dir.exists():
            log.warning(f"Images directory not found: {self.images_dir}")
            return ""

        image_files = list(self.images_dir.glob("*.jpg")) + list(self.images_dir.glob("*.png"))
        if not image_files:
            log.warning("No images found")
            return ""

        return str(random.choice(image_files))

    def format_comments(self, comments: List[str], thread_id: str) -> List[Dict]:
        """Format comments with proper structure"""
        formatted = []
        current_time = datetime.now()

        for i, text in enumerate(comments):
            comment_id = str(int(thread_id) + i + 1)
            if not text.startswith(f">>{thread_id}"):
                text = f">>{thread_id}\n{text}"

            formatted_text = self.format_comment_text(text, thread_id)

            formatted.append({
                "id": comment_id,
                "name": self.get_anon_name(),
                "date": self.format_date(current_time + timedelta(minutes=random.randint(2, 5)), self.use_russian),
                "text": formatted_text
            })

        return formatted

    @abstractmethod
    def get_anon_name(self) -> str:
        """Return anonymous poster name"""
        pass

    @property
    @abstractmethod
    def use_russian(self) -> bool:
        """Whether to use Russian language in formatting"""
        pass

    def generate_image(self, story: str, comments: List[str]) -> Optional[bytes]:
        """Generate thread image from story and comments"""
        try:
            thread_id = str(int(datetime.now().timestamp()))
            image_path = self.get_random_image()

            # Get image details
            img_size = "0Кб, 0x0" if self.use_russian else "0KB, 0x0"
            img_url = ""
            if image_path:
                path = Path(image_path)
                if path.exists():
                    size_kb = path.stat().st_size // 1024
                    with Image.open(path) as img:
                        width, height = img.size
                    img_size = f"{size_kb}{'Кб' if self.use_russian else 'KB'}, {width}x{height}"
                    img_url = "file:///" + str(path.absolute()).replace('\\', '/')

            # Prepare template data
            template_data = self.prepare_template_data(thread_id, story, comments, img_url, img_size)

            # Render template
            template = self.jinja_env.get_template(self.template_path.name)
            html = template.render(**template_data)

            # Create temp files
            temp_dir = Path.cwd() / ".temp"
            temp_dir.mkdir(exist_ok=True)

            temp_html = temp_dir / f"temp_{thread_id}.html"
            temp_png = temp_dir / f"temp_{thread_id}.png"

            # Write HTML
            temp_html.write_text(html, encoding='utf-8')

            # Generate image
            options = self.get_imgkit_options()
            imgkit.from_file(str(temp_html), str(temp_png), options=options, config=self.imgkit_config)

            # Read result
            image_bytes = temp_png.read_bytes()

            # Cleanup
            temp_html.unlink(missing_ok=True)
            temp_png.unlink(missing_ok=True)

            return image_bytes

        except Exception as e:
            log.error(f"Failed to generate image: {e}")
            return None

    @abstractmethod
    def prepare_template_data(self, thread_id: str, story: str, comments: List[str],
                              img_url: str, img_size: str) -> Dict:
        """Prepare data for template rendering"""
        pass

    @abstractmethod
    def get_imgkit_options(self) -> Dict:
        """Get options for imgkit"""
        pass


class BugurtGenerator(BaseThreadGenerator):
    """Generator for 2ch-style threads"""

    def get_template_name(self) -> str:
        return "bugurt"

    def get_images_dir(self) -> Path:
        return Path("assets/yoba")

    def format_story(self, text: str) -> str:
        parts = [p.strip() for p in text.replace('\n', '@').split('@') if p.strip()]
        formatted_parts = []
        for part in parts:
            if part.startswith('>'):
                part = f'<span class="unkfunc">{part}</span>'
            formatted_parts.append(part)
        return '<br>@<br>'.join(formatted_parts)

    def format_comment_text(self, text: str, thread_id: str) -> str:
        lines = text.split("\n")
        formatted_lines = []
        for line in lines:
            line = line.strip()
            if line:
                if line.startswith('>>'):
                    line = f'<a href="#" class="post-reply-link" data-thread="{thread_id}" data-num="{line[2:]}">{line}</a>'
                elif line.startswith('>'):
                    line = f'<span class="unkfunc">{line}</span>'
                formatted_lines.append(line)
        return "<br>".join(formatted_lines)

    def get_anon_name(self) -> str:
        return "Аноним"

    @property
    def use_russian(self) -> bool:
        return True

    def prepare_template_data(self, thread_id: str, story: str, comments: List[str],
                              img_url: str, img_size: str) -> Dict:
        current_time = self.format_date(datetime.now(), self.use_russian)
        return {
            "post_id": thread_id,
            "name": self.get_anon_name(),
            "date": current_time,
            "image_path": img_url,
            "image_name": "@not_salieri_bot",
            "image_size": img_size,
            "post_text": self.format_story(story),
            "comments": self.format_comments(comments, thread_id)
        }

    def get_imgkit_options(self) -> Dict:
        return {
            "format": "png",
            "encoding": "UTF-8",
            "quality": 100,
            "enable-local-file-access": "",
            "user-style-sheet": str(self.template_dir / "default.css")
        }


class GreentextGenerator(BaseThreadGenerator):
    """Generator for 4chan-style threads"""

    def get_template_name(self) -> str:
        return "greentext"

    def get_images_dir(self) -> Path:
        return Path("assets/pepe")

    def format_story(self, text: str) -> str:
        lines = []
        for line in text.split('\n'):
            line = line.strip()
            if line:
                if line.startswith('>') and not line.startswith('>>'):
                    line = f'<span class="quote">{line}</span>'
                lines.append(line)
        return '<br>'.join(lines)

    def format_comment_text(self, text: str, thread_id: str) -> str:
        lines = text.split('\n')
        formatted_lines = []
        for line in lines:
            line = line.strip()
            if line:
                if line.startswith('>>'):
                    line = f'<a href="#p{line[2:]}" class="quotelink">{line}</a>'
                elif line.startswith('>'):
                    line = f'<span class="quote">{line}</span>'
                formatted_lines.append(line)
        return '<br>'.join(formatted_lines)

    def get_anon_name(self) -> str:
        return "Anonymous"

    @property
    def use_russian(self) -> bool:
        return False

    def prepare_template_data(self, thread_id: str, story: str, comments: List[str],
                              img_url: str, img_size: str) -> Dict:
        current_time = self.format_date(datetime.now(), self.use_russian)
        return {
            "thread_title": "Greentext",
            "post": {
                "id": thread_id,
                "subject": "",
                "name": self.get_anon_name(),
                "datetime": current_time,
                "has_image": bool(img_url),
                "image_url": img_url,
                "filename": "@not_salieri_bot",
                "filesize": img_size,
                "message": self.format_story(story)
            },
            "replies": self.format_comments(comments, thread_id)
        }

    def get_imgkit_options(self) -> Dict:
        return {
            "format": "png",
            "encoding": "UTF-8",
            "quality": 100,
            "enable-local-file-access": ""
        }
