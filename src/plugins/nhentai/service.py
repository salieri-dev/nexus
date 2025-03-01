"""Service layer for nhentai plugin"""

import asyncio
import io
import math
import os
from io import BytesIO
from typing import Dict, List, Optional, Tuple

import httpx
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from pyrogram.types import InputMediaPhoto, Message
from structlog import get_logger

from src.config.framework import get_chat_setting
from src.plugins.nhentai.constants import BLACKLIST_TAGS, PROXY_URL
from src.plugins.nhentai.constants import NHENTAI_IMAGE_DOMAINS, NHENTAI_THUMB_DOMAINS, MAX_RETRIES
from src.plugins.nhentai.models import Images, NhentaiGallery, Tag, Title

log = get_logger(__name__)


class DownloadError(Exception):
    """Exception raised when image download fails"""
    pass


class NhentaiService:
    """Service for nhentai operations"""

    BASE_URL = "https://nhentai.net"
    last_successful_domain = None

    @staticmethod
    async def get_blur_setting(chat_id: int, message: Message = None) -> bool:
        """Get nhentai_blur setting from peer_config or use default for private chats"""
        from pyrogram.enums.chat_type import ChatType

        # Always disable blur in private chats
        if message and message.chat.type == ChatType.PRIVATE:
            return False

        # Use config value for non-private chats
        return await get_chat_setting(chat_id, "nhentai_blur", True)

    @classmethod
    async def download_image(cls, url: str, session: httpx.AsyncClient) -> io.BytesIO:
        """Download image from URL with fallback to alternative domains"""
        import re

        # Extract domain and path from URL
        match = re.match(r"https?://([^/]+)(/.+)", url)
        if not match:
            log.error(f"Invalid URL format: {url}")
            raise DownloadError(f"Invalid URL format: {url}")

        domain, path = match.groups()
        is_thumbnail = "/thumb.webp" in path
        
        # Prioritize domains to try
        domains_to_try = []
        if cls.last_successful_domain:
            domains_to_try.append(cls.last_successful_domain)
        if domain != cls.last_successful_domain:
            domains_to_try.append(domain)
        domains_to_try.extend([d for d in NHENTAI_IMAGE_DOMAINS if d not in domains_to_try])
        
        # For thumbnails, prioritize i1.nhentai.net
        if is_thumbnail and "i1.nhentai.net" not in domains_to_try:
            domains_to_try.insert(0, "i1.nhentai.net")

        # Create URLs for all domains to try
        urls_to_try = [f"https://{d}{path}" for d in domains_to_try]
        
        # Try all domains in parallel
        async def try_url(url, domain):
            try:   
                response = await session.get(url)
                
                if response.status_code == 200:
                    cls.last_successful_domain = domain
                    return io.BytesIO(response.content)
                else:
                    return None
            except Exception as e:
                log.error(f"Error downloading: {url}, error: {str(e)}")
                return None

        tasks = [try_url(url, domains_to_try[i]) for i, url in enumerate(urls_to_try)]
        results = await asyncio.gather(*tasks)
        
        # Return first successful result
        for result in results:
            if result is not None:
                return result
        
        # Try fallbacks for thumbnails and alternative extensions
        if is_thumbnail:
            first_page = await cls._try_first_page_as_thumbnail(path, domains_to_try)
            if first_page:
                return first_page
                
        alternative = await cls._try_alternative_extension(url, domains_to_try)
        if alternative:
            return alternative

        # All attempts failed
        log.error(f"All domains failed for: {url}")
        raise DownloadError(f"Failed to download from all domains. URL: {url}")

    @classmethod
    async def _try_first_page_as_thumbnail(cls, path, domains_to_try):
        """Try using first page as thumbnail fallback"""
        import re
        
        gallery_match = re.search(r"/galleries/(\d+)/", path)
        if not gallery_match:
            return None
            
        gallery_id = gallery_match.group(1)
        # Try both jpg and webp extensions for the first page
        first_page_urls = []
        for d in domains_to_try:
            first_page_urls.append(f"https://{d}/galleries/{gallery_id}/1.jpg")
            first_page_urls.append(f"https://{d}/galleries/{gallery_id}/1.webp")
        
        # Try all first page URLs in parallel
        async def try_url(url, domain):
            try:
                async with httpx.AsyncClient(follow_redirects=True) as session:
                    log.info(f"HTTP Request: GET {url}")
                    response = await session.get(url)
                    if response.status_code == 200:
                        log.info(f"HTTP Request: GET {url} \"HTTP/1.1 200 OK\"")
                        cls.last_successful_domain = domain
                        return io.BytesIO(response.content)
                    else:
                        log.info(f"HTTP Request: GET {url} \"HTTP/1.1 {response.status_code} {response.reason_phrase}\"")
            except Exception as e:
                log.error(f"Error downloading: {url}, error: {str(e)}")
            return None
                
        tasks = [try_url(url, domains_to_try[i]) for i, url in enumerate(first_page_urls)]
        results = await asyncio.gather(*tasks)
        
        for result in results:
            if result is not None:
                return result
                
        return None

    @classmethod
    async def _try_alternative_extension(cls, url, domains_to_try):
        """Try alternative file extension if original failed"""
        import re
        
        if ".jpg" in url:
            alt_url = url.replace(".jpg", ".webp")
        elif ".webp" in url:
            alt_url = url.replace(".webp", ".jpg")
        else:
            return None
            
        match = re.match(r"https?://([^/]+)(/.+)", alt_url)
        if not match:
            return None
            
        domain, path = match.groups()
        alt_urls = [f"https://{d}{path}" for d in domains_to_try]
        
        async def try_url(url, domain):
            try:
                async with httpx.AsyncClient(follow_redirects=True) as session:
                    log.info(f"HTTP Request: GET {url}")
                    response = await session.get(url)
                    if response.status_code == 200:
                        log.info(f"HTTP Request: GET {url} \"HTTP/1.1 200 OK\"")
                        cls.last_successful_domain = domain
                        return io.BytesIO(response.content)
                    else:
                        log.info(f"HTTP Request: GET {url} \"HTTP/1.1 {response.status_code} {response.reason_phrase}\"")
            except Exception as e:
                log.error(f"Error downloading: {url}, error: {str(e)}")
            return None
                
        tasks = [try_url(url, domains_to_try[i]) for i, url in enumerate(alt_urls)]
        results = await asyncio.gather(*tasks)
        
        for result in results:
            if result is not None:
                return result
                
        return None

    @staticmethod
    def blur_image(image: io.BytesIO) -> io.BytesIO:
        """Apply blur effect to image"""
        with Image.open(image) as img:
            blurred_img = img.filter(ImageFilter.GaussianBlur(radius=30))
            output = io.BytesIO()
            blurred_img.save(output, format="JPEG")
            output.seek(0)
        return output

    @staticmethod
    def generate_output_message(media: NhentaiGallery, chat_id: int, message: Message = None) -> Tuple[List[InputMediaPhoto], bool]:
        """Generate output message with media and check for blacklisted tags"""
        from pyrogram.enums.parse_mode import ParseMode
        from datetime import datetime

        link = f"https://nhentai.net/g/{media.id}"
        caption = f"<b>№{media.id}</b> | <a href='{link}'><b>{media.title.pretty}</b></a>\n\n"
        caption += f"<b>Pages:</b> {media.num_pages}\n<b>Favorites:</b> {media.num_favorites}\n\n"

        # Organize tags by category
        tag_dict: Dict[str, List[str]] = {category: [] for category in ["language", "artist", "group", "parody", "category", "tag"]}
        [tag_dict[tag.type].append(tag.name) for tag in media.tags if tag.type in tag_dict]

        for category, tags in tag_dict.items():
            if tags:
                caption += f"<b>{category.capitalize()}:</b> {', '.join(tags)}\n"

        timestamp_to_date = datetime.fromtimestamp(media.upload_date)
        caption += f"\n<b>Uploaded:</b> {timestamp_to_date.strftime('%Y-%m-%d')}"

        # Check for blacklisted tags
        has_blacklisted_tag = any(tag in BLACKLIST_TAGS for tag in tag_dict["tag"])

        # Create album with cover and sample pages
        album = [InputMediaPhoto(media.images.pages[0], caption=caption, parse_mode=ParseMode.HTML)]
        
        # Add sample pages at different points in the gallery
        total_pages = len(media.images.pages)
        sample_percentages = [15, 30, 50, 70, 90]
        for percentage in sample_percentages:
            if total_pages >= len(album) + 1:
                page_index = min(total_pages - 1, max(1, round(total_pages * percentage / 100)))
                album.append(InputMediaPhoto(media.images.pages[page_index]))

        return album, has_blacklisted_tag

    @staticmethod
    async def send_media_group(client, chat_id: int, album: List[InputMediaPhoto], message: Message, use_proxy: bool = False, blur: bool = False) -> Optional[str]:
        """Send media group with optional blurring"""
        # Check if blur should be applied
        should_blur = blur and await NhentaiService.get_blur_setting(chat_id, message)

        try:
            # Try sending directly if no blur needed
            if not should_blur:
                await message.reply_media_group(media=album, quote=True)
                return None
                
            # Handle blurring
            log.warning("Blacklisted tags detected. Downloading and blurring images...")
            client_config = {
                "timeout": httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0),
                "proxy": PROXY_URL if use_proxy else None,
                "follow_redirects": True
            }
            
            async with httpx.AsyncClient(**client_config) as session:
                new_album = await NhentaiService._process_album_images(album, session, should_blur)
                await message.reply_media_group(media=new_album, quote=True)
                return None
                
        except Exception as e:
            error_msg = str(e)
            # Handle WEBPAGE errors by downloading images first
            if "WEBPAGE" in error_msg:
                try:
                    log.warning("Failed to send by URL. Downloading and resending...")
                    client_config = {
                        "timeout": httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0),
                        "proxy": PROXY_URL if use_proxy else None,
                        "follow_redirects": True
                    }
                    
                    async with httpx.AsyncClient(**client_config) as session:
                        new_album = await NhentaiService._process_album_images(
                            album, session, should_blur
                        )
                        await message.reply_media_group(media=new_album, quote=True)
                        return None
                except Exception as download_e:
                    log.error("Failed to download and process images", 
                             extra={"error": str(download_e)})
                    return f"Failed to download and send images: {str(download_e)}"
                    
            log.error("Failed to send media group", extra={"error": error_msg})
            return f"Failed to send media group: {error_msg}"

    @staticmethod
    async def _process_album_images(album, session, should_blur):
        """Download and optionally blur images in an album"""
        new_album = []
        for media in album:
            try:
                image = await NhentaiService.download_image(media.media, session)
                if should_blur:
                    image = NhentaiService.blur_image(image)
                new_media = InputMediaPhoto(
                    image, 
                    caption=media.caption, 
                    parse_mode=media.parse_mode
                )
                new_album.append(new_media)
            except Exception as img_e:
                log.error("Failed to process image", extra={"error": str(img_e)})
                raise
        return new_album

    @staticmethod
    def truncate_title(title: str, max_length: int = 40) -> str:
        """Truncate title to max length with ellipsis"""
        return (title[: max_length - 3] + "...") if len(title) > max_length else title


class NhentaiAPI:
    """API client for nhentai.net"""

    BASE_URL = "https://nhentai.net"
    PROXY_URL = f"socks5://{os.getenv('PROXY_HOST')}:{os.getenv('PROXY_PORT')}" if os.getenv("USE_PROXY", "false").lower() == "true" else None

    def __init__(self, use_proxy: bool = None):
        """Initialize with optional proxy usage."""
        self.use_proxy = use_proxy if use_proxy is not None else (os.getenv("USE_PROXY", "false").lower() == "true")
        log.info(f"Using {self.use_proxy} proxy")

    async def _make_request(self, endpoint: str, params: dict = None, retries: int = None) -> dict:
        """Make API requests with retry logic"""
        if retries is None:
            retries = MAX_RETRIES
            
        client_kwargs = {"proxy": self.PROXY_URL} if self.use_proxy else {}
        url = f"{self.BASE_URL}/{endpoint}"

        for attempt in range(retries):
            try:
                async with httpx.AsyncClient(**client_kwargs, timeout=10.0) as client:
                    response = await client.get(url, params=params)
                    response.raise_for_status()
                    return response.json()
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                if attempt == retries - 1:
                    log.error(f"Request failed after {retries} attempts: {str(e)}")
                    raise
                await asyncio.sleep(1 * (attempt + 1))  # Exponential backoff
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    raise
                if attempt == retries - 1:
                    log.error(f"HTTP error after {retries} attempts: {str(e)}")
                    raise
                await asyncio.sleep(1 * (attempt + 1))

    async def get_by_id(self, gallery_id: int) -> NhentaiGallery:
        """Fetch gallery by ID"""
        try:
            req = await self._make_request(f"api/gallery/{gallery_id}")
            return await self.convert_to_gallery(req)
        except Exception as e:
            log.error(f"Failed to fetch gallery {gallery_id}: {str(e)}")
            raise

    async def search(self, query: str, page: int = 1) -> List[NhentaiGallery]:
        """Search for galleries by query"""
        try:
            params = {"query": query, "page": page}
            data = await self._make_request("api/galleries/search", params=params)
            return [await self.convert_to_gallery(item) for item in data["result"]]
        except Exception as e:
            log.error(f"Failed to search for '{query}' on page {page}: {str(e)}")
            raise

    @staticmethod
    def parse_title(data: dict) -> Title:
        """Parse the title information"""
        return Title(**data["title"])

    @staticmethod
    def parse_tags(data: dict) -> List[Tag]:
        """Extract tag details as Tag objects"""
        return [Tag(**tag) for tag in data["tags"]]

    @classmethod
    def parse_images(cls, data: dict) -> Images:
        """Construct image URLs for the gallery"""
        media_id = data["media_id"]
        
        # Select domains based on availability
        image_domain = NhentaiService.last_successful_domain or NHENTAI_IMAGE_DOMAINS[0]
        
        # For thumbnails, use appropriate domain
        if NhentaiService.last_successful_domain:
            thumb_domain = NhentaiService.last_successful_domain
        elif image_domain.startswith("i"):
            # Convert i.nhentai.net to t.nhentai.net, etc.
            thumb_domain = "t" + image_domain[1:]
        else:
            thumb_domain = NHENTAI_THUMB_DOMAINS[0]

        # Create page URLs with correct extensions
        pages = []
        for i, page in enumerate(data["images"]["pages"]):
            extension = cls.get_extension(page['t'])
            page_url = f"https://{image_domain}/galleries/{media_id}/{i + 1}.{extension}"
            pages.append(page_url)

        # Create cover and thumbnail URLs using the correct extension
        cover_extension = cls.get_extension(data["images"]["cover"]["t"])
        thumbnail_extension = cls.get_extension(data["images"]["thumbnail"]["t"])
        
        cover_url = f"https://{thumb_domain}/galleries/{media_id}/cover.{cover_extension}"
        thumbnail_url = f"https://{thumb_domain}/galleries/{media_id}/thumb.{thumbnail_extension}"

        log.info(f"Images: {len(pages)} pages, cover: {cover_url}, thumbnail: {thumbnail_url}")
        return Images(pages=pages, cover=cover_url, thumbnail=thumbnail_url)

    @staticmethod
    def get_extension(file_type: str) -> str:
        """Map file type to extension"""
        if file_type == 'j':
            return "jpg"
        elif file_type == 'p':
            return "png"
        else:
            return "webp"

    async def convert_to_gallery(self, data: dict) -> NhentaiGallery:
        """Convert API data to NhentaiGallery object"""
        title = self.parse_title(data)
        tags = self.parse_tags(data)
        images = self.parse_images(data)

        return NhentaiGallery(
            id=data["id"], 
            media_id=int(data["media_id"]), 
            title=title, 
            images=images, 
            scanlator=data.get("scanlator", ""), 
            upload_date=data["upload_date"], 
            tags=tags, 
            num_pages=data["num_pages"], 
            num_favorites=data["num_favorites"]
        )


class CollageCreator:
    """Creates collages of nhentai thumbnails"""

    def __init__(self, thumb_width=500, thumb_height=765, thumbnails_per_row=3, num_rows=4):
        self.thumb_width = thumb_width
        self.thumb_height = thumb_height
        self.thumbnails_per_row = thumbnails_per_row
        self.num_rows = num_rows
        self.collage_width = thumb_width * thumbnails_per_row
        self.collage_height = thumb_height * num_rows

        # Load font
        font_path = os.path.join(os.path.dirname(__file__), "arial.ttf")
        self.font_path = font_path if os.path.exists(font_path) else None
        if not self.font_path:
            log.warning("Arial font not found, using default font")

    def get_font(self, size: int) -> ImageFont.FreeTypeFont:
        """Get font with fallback to default"""
        try:
            if self.font_path:
                return ImageFont.truetype(self.font_path, size)
            return ImageFont.load_default()
        except Exception as e:
            log.error(f"Failed to load font: {str(e)}")
            return ImageFont.load_default()

    def resize_and_pad(self, img, target_width, target_height, border_width=5):
        """Resize image, add background and border"""
        img = img.convert("RGB")
        aspect = img.width / img.height
        target_aspect = target_width / target_height

        # Determine new dimensions maintaining aspect ratio
        if aspect > target_aspect:
            new_width = target_width - 2 * border_width
            new_height = int(new_width / aspect)
        else:
            new_height = target_height - 2 * border_width
            new_width = int(new_height * aspect)

        # Create blurred background
        background = img.copy()
        background = background.resize((target_width, target_height), Image.LANCZOS)
        background = background.filter(ImageFilter.GaussianBlur(radius=20))

        # Resize main image
        img = img.resize((new_width, new_height), Image.LANCZOS)

        # Center image on background
        paste_x = (target_width - new_width) // 2
        paste_y = (target_height - new_height) // 2
        background.paste(img, (paste_x, paste_y))

        # Add border
        draw = ImageDraw.Draw(background)
        draw.rectangle(
            [0, 0, target_width - 1, target_height - 1], 
            outline=(0, 0, 0), 
            width=border_width
        )

        return background

    def add_text_to_image(self, img, text):
        """Add text overlay to image"""
        draw = ImageDraw.Draw(img)
        font = self.get_font(60)

        # Calculate text dimensions
        text_width = draw.textlength(text, font=font)
        text_height = 60
        position = (0, 0)

        # Add semi-transparent background
        background_shape = [
            (position[0], position[1]), 
            (position[0] + text_width + 10, position[1] + text_height + 10)
        ]
        draw.rectangle(background_shape, fill=(0, 0, 0, 128))

        # Draw text
        draw.text(position, text, font=font, fill=(255, 255, 255))
        return img

    def draw_centered_text(self, img, text, font_size=60):
        """Draw text centered on the image"""
        draw = ImageDraw.Draw(img)
        font = self.get_font(font_size)
        
        # Calculate text dimensions for centering
        text_width = draw.textlength(text, font=font)
        text_height = font_size
        
        # Calculate position to center the text
        position = (
            (self.thumb_width - text_width) // 2, 
            (self.thumb_height - text_height) // 2
        )
        
        # Draw text
        draw.text(position, text, font=font, fill=(0, 0, 0))
        return img

    def add_order_number(self, img, number):
        """Add order number to bottom right of image"""
        draw = ImageDraw.Draw(img)
        font = self.get_font(100)

        text = str(number)
        text_width = draw.textlength(text, font=font)
        text_height = 100

        # Position at bottom-right
        position = (
            self.thumb_width - text_width - 10, 
            self.thumb_height - text_height - 10
        )

        # Add background for better visibility
        background_shape = [
            (position[0] - 5, position[1] - 5), 
            (position[0] + text_width + 5, position[1] + text_height + 5)
        ]
        draw.rectangle(background_shape, fill=(0, 0, 0, 128))

        # Draw number
        draw.text(position, text, font=font, fill=(255, 255, 255))
        return img

    async def _process_thumbnails(self, posts, client):
        """Process thumbnails in parallel"""
        async def process_thumbnail(i, post):
            try:
                # Download thumbnail
                image_data = await NhentaiService.download_image(post.images.thumbnail, client)
                img = Image.open(image_data).convert("RGB")
                img = self.resize_and_pad(img, self.thumb_width, self.thumb_height)
                img = self.add_text_to_image(img, f"№ {post.id}")
                img = self.add_order_number(img, i + 1)
            except Exception as e:
                # Create error placeholder
                log.error(f"Error fetching thumbnail for post {post.id}: {e}")
                img = Image.new("RGB", (self.thumb_width, self.thumb_height), (200, 200, 200))
                img = self.draw_centered_text(img, "Error")
                img = self.add_text_to_image(img, f"№ {post.id}")
                img = self.add_order_number(img, i + 1)
            
            return i, img
        
        # Create tasks for all thumbnails
        tasks = [process_thumbnail(i, post) for i, post in enumerate(posts)]
        
        # Process all thumbnails in parallel
        return await asyncio.gather(*tasks)

    async def create_collage(self, posts, start_index, end_index):
        """Create a collage for a subset of posts"""
        collage = Image.new("RGB", (self.collage_width, self.collage_height), (255, 255, 255))
        
        # Create a client for downloading
        client_config = {
            "timeout": httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0), 
            "follow_redirects": True
        }
        
        async with httpx.AsyncClient(**client_config) as client:
            # Process thumbnails in parallel
            subset_posts = posts[start_index:end_index]
            results = await self._process_thumbnails(subset_posts, client)
            
            # Place images in the collage
            for i, img in results:
                x = (i % self.thumbnails_per_row) * self.thumb_width
                y = (i // self.thumbnails_per_row) * self.thumb_height
                collage.paste(img, (x, y))

        # Convert to BytesIO
        img_byte_arr = BytesIO()
        collage.save(img_byte_arr, format="JPEG", quality=95)
        img_byte_arr.seek(0)
        return img_byte_arr

    async def create_single_wide_collage(self, posts):
        """Create a single wide collage for all posts"""
        log.info(f"Creating collage for {len(posts)} posts")

        # Calculate dimensions based on number of posts
        total_posts = len(posts)
        num_columns = math.ceil(total_posts / self.num_rows)
        collage_width = self.thumb_width * num_columns

        collage = Image.new("RGB", (collage_width, self.collage_height), (255, 255, 255))

        # Create a client for downloading
        client_config = {
            "timeout": httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0), 
            "follow_redirects": True
        }
        
        async with httpx.AsyncClient(**client_config) as client:
            # Process thumbnails in parallel
            results = await self._process_thumbnails(posts, client)
            
            # Place images in the collage
            for i, img in results:
                # Calculate position (column, row)
                x = (i % num_columns) * self.thumb_width
                y = (i // num_columns) * self.thumb_height
                collage.paste(img, (x, y))

        # Convert to BytesIO
        img_byte_arr = BytesIO()
        collage.save(img_byte_arr, format="JPEG", quality=95)
        img_byte_arr.seek(0)
        return img_byte_arr

    async def create_single_collage_as_bytesio(self, posts):
        """Create a single collage as BytesIO"""
        return await self.create_single_wide_collage(posts)

    async def create_two_collages_as_bytesio(self, posts):
        """Create two separate collages as BytesIO objects"""
        log.info(f"Creating two collages for {len(posts)} posts")
        collage1 = await self.create_collage(posts, 0, 12)
        collage2 = await self.create_collage(posts, 12, 24)
        return collage1, collage2

    async def create_two_collages(self, posts):
        """Create two collages (alias method)"""
        return await self.create_two_collages_as_bytesio(posts)