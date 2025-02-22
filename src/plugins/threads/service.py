import json
import os
import random
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import imgkit
from PIL import Image
from jinja2 import Environment, FileSystemLoader

from structlog import get_logger

log = get_logger(__name__)

WEEKDAY_NAMES = {0: "Пнд", 1: "Втр", 2: "Срд", 3: "Чтв", 4: "Птн", 5: "Суб", 6: "Вск"}
MONTH_NAMES = {1: "Янв", 2: "Фев", 3: "Мар", 4: "Апр", 5: "Май", 6: "Июн", 
               7: "Июл", 8: "Авг", 9: "Сен", 10: "Окт", 11: "Ноя", 12: "Дек"}

@dataclass
class BugurtResponse:
    story: str
    comments: List[str]

    @classmethod
    def from_json(cls, json_str: str) -> 'BugurtResponse':
        try:
            # Remove code block markers if present
            clean_json = json_str.strip().replace('```json', '').replace('```', '')
            data = json.loads(clean_json)
            return cls(
                story=data['story'],
                comments=data.get('2ch_comments', [])
            )
        except json.JSONDecodeError as e:
            log.error(f"Failed to parse JSON: {e}")
            raise
        except KeyError as e:
            log.error(f"Missing required field: {e}")
            raise

class ThreadImageGenerator:
    def __init__(self, template_dir: str = "bugurt"):
        self.template_dir = Path(f"src/plugins/threads/{template_dir}")
        self.template_path = self.template_dir / "template.html"
        self.css_path = self.template_dir / "default.css"
        self.images_dir = Path("assets/yoba" if template_dir == "bugurt" else "assets/pepe")
        self.has_external_css = template_dir == "bugurt"  # Only bugurt uses external CSS
        
        if not self.template_path.exists():
            raise FileNotFoundError(f"Template not found: {self.template_path}")
        if self.has_external_css and not self.css_path.exists():
            raise FileNotFoundError(f"CSS not found: {self.css_path}")
            
        self.jinja_env = Environment(loader=FileSystemLoader(str(self.template_dir)))
        self.imgkit_config = imgkit.config()
        
    def format_date(self, dt: datetime, use_russian: bool = True) -> str:
        """Format date in Russian or English style"""
        if use_russian:
            weekday = WEEKDAY_NAMES[dt.weekday()]
            month = MONTH_NAMES[dt.month]
            return f"{dt.day:02d} {month} {dt.year % 100:02d} {weekday} {dt.hour:02d}:{dt.minute:02d}:{dt.second:02d}"
        else:
            # English 4chan style: mm/dd/yy(day)HH:MM:SS
            weekday = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][dt.weekday()]
            return dt.strftime(f"%m/%d/%y({weekday})%H:%M:%S")

    def get_random_image(self) -> str:
        """Get random image path (kolobok for bugurt, pepe for greentext)"""
        if not self.images_dir.exists():
            log.warning(f"Images directory not found: {self.images_dir}")
            return ""
            
        image_files = list(self.images_dir.glob("*.jpg")) + list(self.images_dir.glob("*.png"))
        if not image_files:
            log.warning("No images found")
            return ""
            
        return str(random.choice(image_files))

    def format_story(self, text: str) -> str:
        """Format story text with proper separators"""
        if self.has_external_css:
            # Bugurt style with @ separators
            parts = [p.strip() for p in text.replace('\n', '@').split('@') if p.strip()]
            return '<br>@<br>'.join(parts)
        else:
            # Greentext style - make lines starting with > green
            lines = []
            for line in text.split('\n'):
                line = line.strip()
                if line:
                    if line.startswith('>') and not line.startswith('>>'):
                        line = f'<span class="quote">{line}</span>'
                    lines.append(line)
            return '<br>'.join(lines)

    def format_comment_text(self, text: str, thread_id: str) -> str:
        """Format comment text with post references and greentext"""
        # First handle post references
        ref_pattern = r">>([\d]+)"
        ref_template = f'<a href="#" class="post-reply-link" data-thread="{thread_id}" data-num="\\1">>>\\1</a>'
        text = re.sub(ref_pattern, ref_template, text)
        
        # Then handle greentext quotes (lines starting with >)
        lines = text.split('<br>')
        formatted_lines = []
        for line in lines:
            if line.strip().startswith('>') and not line.strip().startswith('>>'):
                line = f'<span class="unkfunc">{line}</span>'
            formatted_lines.append(line)
        
        return '<br>'.join(formatted_lines)

    def format_comments(self, comments: List[str], thread_id: str) -> List[Dict]:
        """Format comments with proper structure"""
        formatted = []
        current_time = datetime.now()
        
        for i, text in enumerate(comments):
            comment_id = str(int(thread_id) + i + 1)
            if not text.startswith(f">>{thread_id}"):
                text = f">>{thread_id}\n{text}"
                
            # First replace newlines with <br>, then apply formatting
            formatted_text = text.replace("\n", "<br>")
            formatted_text = self.format_comment_text(formatted_text, thread_id)
            
            formatted.append({
                "id": comment_id,
                "name": "Аноним" if self.has_external_css else "Anonymous",
                "date": self.format_date(current_time, use_russian=self.has_external_css),
                "text": formatted_text
            })
            
        return formatted

    def generate_image(self, story: str, comments: List[str]) -> Optional[bytes]:
        """Generate thread image from story and comments"""
        try:
            thread_id = str(int(datetime.now().timestamp()))
            image_path = self.get_random_image()
            
            # Get image details
            img_size = "0Кб, 0x0"
            img_url = ""
            if image_path:
                path = Path(image_path)
                if path.exists():
                    size_kb = path.stat().st_size // 1024
                    with Image.open(path) as img:
                        width, height = img.size
                    if self.has_external_css:
                        img_size = f"{size_kb}Кб, {width}x{height}"
                    else:
                        img_size = f"{size_kb}KB, {width}x{height}"
                    img_url = "file:///" + str(path.absolute()).replace('\\', '/')

            # Render template
            template = self.jinja_env.get_template(self.template_path.name)
            current_dt = datetime.now()
            use_russian = self.has_external_css  # Russian for bugurt, English for greentext
            current_time = self.format_date(current_dt, use_russian=use_russian)
            
            # Structure data differently based on template type
            if self.has_external_css:
                # Bugurt template
                html = template.render(
                    post_id=thread_id,
                    name="Аноним",
                    date=current_time,
                    image_path=img_url,
                    image_name="@not_salieri_bot",
                    image_size=img_size,
                    post_text=self.format_story(story),
                    comments=self.format_comments(comments, thread_id)
                )
            else:
                # Format comments for greentext with time offsets
                formatted_replies = []
                comment_dt = current_dt
                
                for i, text in enumerate(comments):
                    # Add time offset for each comment (2-5 minutes)
                    if i > 0:
                        comment_dt = comment_dt + timedelta(minutes=random.randint(2, 5))
                    
                    comment_id = str(int(thread_id) + i + 1)
                    
                    # Format the text
                    if not text.startswith(f">>{thread_id}"):
                        text = f">>{thread_id}\n{text}"
                        
                    # Split into lines and process each
                    lines = []
                    for line in text.split('\n'):
                        line = line.strip()
                        if line:
                            if line.startswith('>>'):
                                # Handle post reference
                                line = self.format_comment_text(line, thread_id)
                            elif line.startswith('>'):
                                # Handle greentext
                                line = f'<span class="quote">{line}</span>'
                            lines.append(line)
                    
                    formatted_text = "<br>".join(lines)
                    
                    formatted_replies.append({
                        "id": comment_id,
                        "name": "Anonymous",
                        "date": self.format_date(comment_dt, use_russian=False),
                        "text": formatted_text
                    })
                # Greentext template
                html = template.render(
                    thread_title="Greentext",
                    post={
                        "id": thread_id,
                        "subject": "",
                        "name": "Anonymous",
                        "datetime": self.format_date(current_dt, use_russian=False),
                        "datetime": current_time,
                        "has_image": bool(img_url),
                        "image_url": img_url,
                        "filename": "@not_salieri_bot",
                        "filesize": img_size,
                        "message": self.format_story(story)
                    },
                    replies=formatted_replies
                )

            # Create temp files
            temp_dir = Path.cwd() / ".temp"
            temp_dir.mkdir(exist_ok=True)
            
            temp_html = temp_dir / f"temp_{thread_id}.html"
            temp_png = temp_dir / f"temp_{thread_id}.png"
            
            # Write HTML
            temp_html.write_text(html, encoding='utf-8')
            
            # Generate image
            options = {
                "format": "png",
                "encoding": "UTF-8",
                "quality": 100,
                "enable-local-file-access": "",
            }
            
            if self.has_external_css:
                options["user-style-sheet"] = str(self.css_path)
            
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

@dataclass
class GreentextResponse:
    story: str
    comments: List[str]

    @classmethod
    def from_json(cls, json_str: str) -> 'GreentextResponse':
        try:
            # Remove code block markers if present
            clean_json = json_str.strip().replace('```json', '').replace('```', '')
            data = json.loads(clean_json)
            return cls(
                story=data['story'],
                comments=data.get('4ch_comments', [])
            )
        except json.JSONDecodeError as e:
            log.error(f"Failed to parse JSON: {e}")
            raise
        except KeyError as e:
            log.error(f"Missing required field: {e}")
            raise

def generate_bugurt_image(json_response: str, template_dir: str = "bugurt") -> Optional[bytes]:
    """Generate thread image from bugurt AI response"""
    try:
        # Parse response
        bugurt = BugurtResponse.from_json(json_response)
        
        # Generate image
        generator = ThreadImageGenerator(template_dir=template_dir)
        image_bytes = generator.generate_image(bugurt.story, bugurt.comments)
        
        if not image_bytes:
            log.error("Failed to generate bugurt image")
            return None
            
        return image_bytes

    except Exception as e:
        log.error(f"Failed to generate bugurt: {e}")
        return None

def generate_greentext_image(json_response: str, template_dir: str = "greentext") -> Optional[bytes]:
    """Generate thread image from greentext AI response"""
    try:
        # Parse response
        greentext = GreentextResponse.from_json(json_response)
        
        # Generate image
        generator = ThreadImageGenerator(template_dir=template_dir)
        image_bytes = generator.generate_image(greentext.story, greentext.comments)
        
        if not image_bytes:
            log.error("Failed to generate greentext image")
            return None
            
        return image_bytes

    except Exception as e:
        log.error(f"Failed to generate greentext: {e}")
        return None
