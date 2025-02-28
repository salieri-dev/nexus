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
from src.plugins.nhentai.models import Images, NhentaiGallery, Tag, Title

log = get_logger(__name__)


class DownloadError(Exception):
    """Exception raised when image download fails"""
    pass


class NhentaiService:
    """Service for nhentai operations"""
    
    BASE_URL: str = "https://nhentai.net"
    
    @staticmethod
    async def get_blur_setting(chat_id: int, message: Message = None) -> bool:
        """Get nhentai_blur setting from peer_config"""
        from pyrogram.enums.chat_type import ChatType
        
        # Always disable blur (return False) in private chats
        if message and message.chat.type == ChatType.PRIVATE:
            return False

        # Otherwise use config value
        return await get_chat_setting(chat_id, "nhentai_blur", True)
    
    @staticmethod
    async def download_image(url: str, session: httpx.AsyncClient) -> io.BytesIO:
        """Download image from URL to BytesIO with fallback to alternative domains"""
        from src.plugins.nhentai.constants import NHENTAI_IMAGE_DOMAINS
        
        original_url = url
        tried_domains = set()
        
        # Extract the domain and path from the URL
        import re
        match = re.match(r'https?://([^/]+)(/.+)', url)
        if not match:
            log.error(f"Invalid URL format: {url}")
            raise DownloadError(f"Invalid URL format: {url}")
            
        domain, path = match.groups()
        
        # Try the original domain first
        domains_to_try = [domain] + [d for d in NHENTAI_IMAGE_DOMAINS if d != domain]
        
        for current_domain in domains_to_try:
            if current_domain in tried_domains:
                continue
                
            tried_domains.add(current_domain)
            current_url = f"https://{current_domain}{path}"
            
            try:
                proxy_enabled = bool(session._transport._pool._proxy_url) if hasattr(session._transport, "_pool") and hasattr(session._transport._pool, "_proxy_url") else False
                log.info("Downloading image", extra={"url": current_url, "proxy_enabled": proxy_enabled})

                response = await session.get(current_url)

                if response.status_code == 200:
                    content_length = len(response.content)
                    log.info("Image downloaded successfully", extra={"url": current_url, "content_length": content_length, "content_type": response.headers.get("content-type")})
                    return io.BytesIO(response.content)
                elif response.status_code == 404:
                    log.warning("Image not found", extra={"url": current_url, "status_code": 404, "response_headers": dict(response.headers)})
                    # Continue to next domain
                    continue
                else:
                    log.error("Failed to download image", extra={"url": current_url, "status_code": response.status_code, "response_headers": dict(response.headers), "response_text": response.text if response.headers.get("content-type", "").startswith("text") else None})
                    # Continue to next domain
                    continue

            except httpx.TimeoutException as e:
                log.error("Timeout while downloading image", extra={"url": current_url, "error": str(e), "timeout_seconds": session.timeout.read})
                # Continue to next domain
                continue
            except httpx.NetworkError as e:
                log.error("Network error while downloading image", extra={"url": current_url, "error": str(e)})
                # Continue to next domain
                continue
            except Exception as e:
                log.error("Unexpected error while downloading image", extra={"url": current_url, "error": str(e), "error_type": type(e).__name__})
                # Continue to next domain
                continue
        
        # If we get here, all domains failed
        log.error(f"All domains failed for image download: {original_url}")
        raise DownloadError(f"Failed to download image from all available domains. Original URL: {original_url}")
    
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
        
        link = f"https://nhentai.net/g/{media.id}"
        caption = f"<b>№{media.id}</b> | <a href='{link}'><b>{media.title.pretty}</b></a>\n\n"
        caption += f"<b>Pages:</b> {media.num_pages}\n<b>Favorites:</b> {media.num_favorites}\n\n"

        tag_dict: Dict[str, List[str]] = {category: [] for category in ["language", "artist", "group", "parody", "category", "tag"]}
        [tag_dict[tag.type].append(tag.name) for tag in media.tags if tag.type in tag_dict]

        for category, tags in tag_dict.items():
            if tags:
                caption += f"<b>{category.capitalize()}:</b> {', '.join(tags)}\n"

        from datetime import datetime
        timestamp_to_date = datetime.fromtimestamp(media.upload_date)
        caption += f"\n<b>Uploaded:</b> {timestamp_to_date.strftime('%Y-%m-%d')}"

        # Check if any blacklisted tags are present
        has_blacklisted_tag = any(tag in BLACKLIST_TAGS for tag in tag_dict["tag"])

        album = [InputMediaPhoto(media.images.pages[0], caption=caption, parse_mode=ParseMode.HTML)]
        total_pages = len(media.images.pages)
        album.extend([InputMediaPhoto(media.images.pages[min(total_pages - 1, max(1, round(total_pages * p / 100)))]) for p in [15, 30, 50, 70, 90] if total_pages >= len(album) + 1])

        return album, has_blacklisted_tag
    
    @staticmethod
    async def send_media_group(client, chat_id: int, album: List[InputMediaPhoto], message: Message, use_proxy: bool = False, blur: bool = False) -> Optional[str]:
        """Send media group and return error message if any"""
        try:
            # Check if blur should be applied based on settings
            should_blur = blur and await NhentaiService.get_blur_setting(chat_id, message)

            if not should_blur:
                await message.reply_media_group(media=album, quote=True)
            else:
                log.warning("Blacklisted tags detected. Downloading, blurring, and resending images...", extra={"proxy_url": PROXY_URL if use_proxy else None})

                client_config = {"timeout": httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0), "proxy": PROXY_URL if use_proxy else None, "follow_redirects": True}

                async with httpx.AsyncClient(**client_config) as session:
                    new_album = []
                    for media in album:
                        try:
                            image = await NhentaiService.download_image(media.media, session)
                            blurred_image = NhentaiService.blur_image(image)
                            new_media = InputMediaPhoto(blurred_image, caption=media.caption, parse_mode=media.parse_mode)
                            new_album.append(new_media)
                        except Exception as img_e:
                            log.error("Failed to process image", extra={"error": str(img_e), "media_url": media.media, "proxy_enabled": bool(use_proxy), "blur_enabled": blur})
                            raise

                await message.reply_media_group(media=new_album, quote=True)
            return None

        except Exception as e:
            error_msg = str(e)
            if "WEBPAGE" in error_msg:
                try:
                    log.warning("Failed to send images by URL. Downloading and resending...", extra={"error": error_msg, "album_size": len(album), "blur_enabled": blur})

                    client_config = {"timeout": httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0), "proxy": PROXY_URL if use_proxy else None, "follow_redirects": True}

                    async with httpx.AsyncClient(**client_config) as session:
                        new_album = []
                        for i, media in enumerate(album):
                            try:
                                image = await NhentaiService.download_image(media.media, session)
                                if blur and await NhentaiService.get_blur_setting(chat_id, message):
                                    image = NhentaiService.blur_image(image)
                                new_media = InputMediaPhoto(image, caption=media.caption, parse_mode=media.parse_mode)
                                new_album.append(new_media)
                            except Exception as img_e:
                                log.error(f"Failed to process image {i + 1}/{len(album)}", extra={"error": str(img_e), "media_url": media.media, "blur_enabled": blur})
                                raise

                    await message.reply_media_group(media=new_album, quote=True)
                    return None
                except Exception as download_e:
                    log.error("Failed to download and process images", extra={"error": str(download_e), "proxy_enabled": bool(use_proxy), "blur_enabled": blur})
                    return f"Failed to download and send images: {str(download_e)}"

            log.error("Failed to send media group", extra={"error": error_msg, "album_size": len(album), "proxy_enabled": bool(use_proxy), "blur_enabled": blur})
            return f"Failed to send media group: {error_msg}"
    
    @staticmethod
    def truncate_title(title: str, max_length: int = 40) -> str:
        """Truncate title to max length with ellipsis"""
        return (title[: max_length - 3] + "...") if len(title) > max_length else title


class NhentaiAPI:
    """API client for nhentai.net"""
    
    BASE_URL: str = "https://nhentai.net"
    PROXY_URL: Optional[str] = f"socks5://{os.getenv('PROXY_HOST')}:{os.getenv('PROXY_PORT')}" if os.getenv("USE_PROXY", "false").lower() == "true" else None

    def __init__(self, use_proxy: bool = None):
        """Initialize NhentaiAPI with optional proxy usage."""
        if use_proxy is None:
            # Use the environment variable to determine proxy usage if not provided
            use_proxy = os.getenv("USE_PROXY", "false").lower() == "true"
        self.use_proxy = use_proxy

    async def _make_request(self, endpoint: str, params: dict = None, retries: int = 3) -> dict:
        """Helper function to perform API requests with optional proxy support and retries."""
        client_kwargs = {"proxy": self.PROXY_URL} if self.use_proxy else {}
        url = f"{self.BASE_URL}/{endpoint}"

        for attempt in range(retries):
            try:
                async with httpx.AsyncClient(**client_kwargs, timeout=30.0) as client:
                    response = await client.get(url, params=params)
                    response.raise_for_status()
                    return response.json()
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                if attempt == retries - 1:
                    log.error(f"Failed to make request after {retries} attempts: {str(e)}")
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
        """Fetch detailed data of a gallery by ID from Nhentai API"""
        try:
            req = await self._make_request(f"api/gallery/{gallery_id}")
            return await self.convert_to_gallery(req)
        except Exception as e:
            log.error(f"Failed to fetch gallery {gallery_id}: {str(e)}")
            raise

    async def search(self, query: str, page: int = 1) -> List[NhentaiGallery]:
        """Query nhentai galleries based on search term and page"""
        try:
            params = {"query": query, "page": page}
            data = await self._make_request("api/galleries/search", params=params)
            return [await self.convert_to_gallery(item) for item in data["result"]]
        except Exception as e:
            log.error(f"Failed to search for query '{query}' on page {page}: {str(e)}")
            raise

    @staticmethod
    def parse_title(data: dict) -> Title:
        """Parse the title information from the API data"""
        return Title(**data["title"])

    @staticmethod
    def parse_tags(data: dict) -> List[Tag]:
        """Extract tag details of a gallery as a list of Tag objects"""
        return [Tag(**tag) for tag in data["tags"]]

    @staticmethod
    def parse_images(data: dict) -> Images:
        """Construct image URLs (pages, cover, thumbnail) for the given gallery"""
        from src.plugins.nhentai.constants import NHENTAI_IMAGE_DOMAINS, NHENTAI_THUMB_DOMAINS
        
        media_id = data["media_id"]
        # Use the first domain in the list for initial URLs
        image_domain = NHENTAI_IMAGE_DOMAINS[0]
        thumb_domain = NHENTAI_THUMB_DOMAINS[0]
        
        pages = [f"https://{image_domain}/galleries/{media_id}/{i + 1}.{NhentaiAPI.get_extension(page['t'])}" for i, page in enumerate(data["images"]["pages"])]

        # Use the appropriate format for cover and thumbnail
        # The format can be .jpg, .webp, or .webp.webp depending on the server
        cover_url = f"https://{thumb_domain}/galleries/{media_id}/cover.webp.webp"
        thumbnail_url = f"https://{thumb_domain}/galleries/{media_id}/thumb.webp.webp"
        
        log.info(f"Images: {len(pages)} pages, cover: {cover_url}, thumbnail: {thumbnail_url}")
        return Images(pages=pages, cover=cover_url, thumbnail=thumbnail_url)

    @staticmethod
    def get_extension(file_type: str) -> str:
        """Utility function to map file type to appropriate file extension"""
        return {"j": "jpg", "p": "png", "g": "gif"}.get(file_type, "jpg")

    async def convert_to_gallery(self, data: dict) -> NhentaiGallery:
        """Convert to NhentaiGallery object"""
        title = self.parse_title(data)
        tags = self.parse_tags(data)
        images = self.parse_images(data)

        return NhentaiGallery(id=data["id"], media_id=int(data["media_id"]), title=title, images=images, scanlator=data.get("scanlator", ""), upload_date=data["upload_date"], tags=tags, num_pages=data["num_pages"], num_favorites=data["num_favorites"])


class CollageCreator:
    """Creates collages of nhentai thumbnails"""
    
    def __init__(self, thumb_width=500, thumb_height=765, thumbnails_per_row=3, num_rows=4):
        self.thumb_width = thumb_width
        self.thumb_height = thumb_height
        self.thumbnails_per_row = thumbnails_per_row
        self.num_rows = num_rows
        self.collage_width = thumb_width * thumbnails_per_row
        self.collage_height = thumb_height * num_rows

        # Ensure font file exists
        font_path = os.path.join(os.path.dirname(__file__), "arial.ttf")
        if not os.path.exists(font_path):
            log.warning(f"Arial font not found at {font_path}, using default font")
            self.font_path = None
        else:
            self.font_path = font_path

    def get_font(self, size: int) -> ImageFont.FreeTypeFont:
        """Get font with fallback to default if arial.ttf is not available"""
        try:
            if self.font_path:
                return ImageFont.truetype(self.font_path, size)
            return ImageFont.load_default()
        except Exception as e:
            log.error(f"Failed to load font: {str(e)}")
            return ImageFont.load_default()

    def resize_and_pad(self, img, target_width, target_height, border_width=5):
        img = img.convert("RGB")
        aspect = img.width / img.height
        target_aspect = target_width / target_height

        if aspect > target_aspect:
            new_width = target_width - 2 * border_width
            new_height = int(new_width / aspect)
        else:
            new_height = target_height - 2 * border_width
            new_width = int(new_height * aspect)

        background = img.copy()
        background = background.resize((target_width, target_height), Image.LANCZOS)
        background = background.filter(ImageFilter.GaussianBlur(radius=20))

        img = img.resize((new_width, new_height), Image.LANCZOS)

        paste_x = (target_width - new_width) // 2
        paste_y = (target_height - new_height) // 2
        background.paste(img, (paste_x, paste_y))

        draw = ImageDraw.Draw(background)
        draw.rectangle([0, 0, target_width - 1, target_height - 1], outline=(0, 0, 0), width=border_width)

        return background

    def add_text_to_image(self, img, text):
        draw = ImageDraw.Draw(img)
        font = self.get_font(60)

        text_width = draw.textlength(text, font=font)
        text_height = 60
        position = (0, 0)

        background_shape = [(position[0], position[1]), (position[0] + text_width + 10, position[1] + text_height + 10)]
        draw.rectangle(background_shape, fill=(0, 0, 0, 128))

        draw.text(position, text, font=font, fill=(255, 255, 255))
        return img

    def draw_centered_text(self, img, text, font_size=60):
        draw = ImageDraw.Draw(img)
        font = self.get_font(font_size)
        text_width = draw.textlength(text, font=font)
        text_height = font_size
        position = ((self.thumb_width - text_width) // 2, (self.thumb_height - text_height) // 2)
        draw.text(position, text, font=font, fill=(0, 0, 0))
        return img

    async def create_collage(self, posts, start_index, end_index):
        collage = Image.new("RGB", (self.collage_width, self.collage_height), (255, 255, 255))

        async with httpx.AsyncClient() as client:
            tasks = [client.get(post.images.thumbnail) for post in posts[start_index:end_index]]
            responses = await asyncio.gather(*tasks, return_exceptions=True)

            for i, (post, response) in enumerate(zip(posts[start_index:end_index], responses)):
                if isinstance(response, Exception):
                    error_msg = f"Exception: {type(response).__name__}: {str(response)}"
                    log.error(f"Error fetching thumbnail for post {post.id}: {error_msg}")
                    img = Image.new("RGB", (self.thumb_width, self.thumb_height), (200, 200, 200))
                    img = self.draw_centered_text(img, "Error")
                    img = self.add_text_to_image(img, f"№ {post.id}")
                elif hasattr(response, 'status_code') and response.status_code == 404:
                    log.error(f"Error fetching thumbnail for post {post.id}: 404 Not Found")
                    img = Image.new("RGB", (self.thumb_width, self.thumb_height), (200, 200, 200))
                    img = self.draw_centered_text(img, "404")
                    img = self.add_text_to_image(img, f"№ {post.id}")
                else:
                    img = Image.open(BytesIO(response.content))
                    img = img.convert("RGB")
                    img = self.resize_and_pad(img, self.thumb_width, self.thumb_height)
                    img = self.add_text_to_image(img, f"№ {post.id}")

                x = (i % self.thumbnails_per_row) * self.thumb_width
                y = (i // self.thumbnails_per_row) * self.thumb_height
                collage.paste(img, (x, y))

        img_byte_arr = BytesIO()
        collage.save(img_byte_arr, format="JPEG", quality=95)
        img_byte_arr.seek(0)
        return img_byte_arr

    async def create_single_wide_collage(self, posts):
        log.info(f"Creating collage for {len(posts)} posts")

        # Calculate the number of columns needed for all posts
        total_posts = len(posts)
        num_columns = math.ceil(total_posts / self.num_rows)

        # Update collage width based on the number of columns
        self.collage_width = self.thumb_width * num_columns

        collage = Image.new("RGB", (self.collage_width, self.collage_height), (255, 255, 255))

        async with httpx.AsyncClient() as client:
            tasks = [client.get(post.images.thumbnail) for post in posts]
            responses = await asyncio.gather(*tasks, return_exceptions=True)

            for i, (post, response) in enumerate(zip(posts, responses)):
                if isinstance(response, Exception):
                    error_msg = f"Exception: {type(response).__name__}: {str(response)}"
                    log.error(f"Error fetching thumbnail for post {post.id}: {error_msg}")
                    img = Image.new("RGB", (self.thumb_width, self.thumb_height), (200, 200, 200))
                    img = self.draw_centered_text(img, "Error")
                    img = self.add_text_to_image(img, f"№ {post.id}")
                elif hasattr(response, 'status_code') and response.status_code == 404:
                    log.error(f"Error fetching thumbnail for post {post.id}: 404 Not Found")
                    img = Image.new("RGB", (self.thumb_width, self.thumb_height), (200, 200, 200))
                    img = self.draw_centered_text(img, "404")
                    img = self.add_text_to_image(img, f"№ {post.id}")
                else:
                    img = Image.open(BytesIO(response.content))
                    img = img.convert("RGB")
                    img = self.resize_and_pad(img, self.thumb_width, self.thumb_height)
                    img = self.add_text_to_image(img, f"№ {post.id}")

                # Add order number at the bottom of the tile
                img = self.add_order_number(img, i + 1)

                # Calculate x and y positions for horizontal order
                x = (i % num_columns) * self.thumb_width
                y = (i // num_columns) * self.thumb_height
                collage.paste(img, (x, y))

        img_byte_arr = BytesIO()
        collage.save(img_byte_arr, format="JPEG", quality=95)
        img_byte_arr.seek(0)
        return img_byte_arr

    def add_order_number(self, img, number):
        draw = ImageDraw.Draw(img)
        font = self.get_font(100)

        text = str(number)
        text_width = draw.textlength(text, font=font)
        text_height = 100

        # Position the number at the bottom-right corner
        position = (self.thumb_width - text_width - 10, self.thumb_height - text_height - 10)

        # Add a semi-transparent background for better visibility
        background_shape = [(position[0] - 5, position[1] - 5), (position[0] + text_width + 5, position[1] + text_height + 5)]
        draw.rectangle(background_shape, fill=(0, 0, 0, 128))

        # Draw the number
        draw.text(position, text, font=font, fill=(255, 255, 255))

        return img

    async def create_single_collage_as_bytesio(self, posts):
        return await self.create_single_wide_collage(posts)

    async def create_two_collages_as_bytesio(self, posts):
        log.info(f"Creating two collages for {len(posts)} posts")

        collage1 = await self.create_collage(posts, 0, 12)
        collage2 = await self.create_collage(posts, 12, 24)

        return collage1, collage2

    async def create_two_collages(self, posts):
        return await self.create_two_collages_as_bytesio(posts)
