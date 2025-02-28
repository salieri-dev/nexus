import asyncio
import math
import os
from io import BytesIO
from typing import List, Optional

import httpx
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from structlog import get_logger
from .models import Images, NhentaiGallery, Tag, Title

log = get_logger(__name__)


class NhentaiAPI:
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
        media_id = data["media_id"]
        pages = [f"https://i.nhentai.net/galleries/{media_id}/{i + 1}.{NhentaiAPI.get_extension(page['t'])}" for i, page in enumerate(data["images"]["pages"])]

        cover_url = f"https://i.nhentai.net/galleries/{media_id}/cover.jpg"
        thumbnail_url = f"https://t.nhentai.net/galleries/{media_id}/thumb.jpg"

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
                if isinstance(response, Exception) or response.status_code == 404:
                    log.error(f"Error fetching thumbnail for post {post.id}: {str(response)}")
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
                if isinstance(response, Exception) or response.status_code == 404:
                    log.error(f"Error fetching thumbnail for post {post.id}: {str(response)}")
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