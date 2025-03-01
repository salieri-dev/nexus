"""god forgive me for this"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from typing import Optional, Tuple, Union

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from structlog import get_logger

log = get_logger(__name__)


class ThxCumService:
    """Service for processing images with artistic effects"""

    def __init__(self, background_path: str, template_path: str, font_path: str):
        """Initialize the image processor with required assets"""
        try:
            self.background_img = self._load_image_cv2(background_path)
            self.template_path = template_path
            self.font_path = font_path
            self.thread_pool = ThreadPoolExecutor()
            log.info("ThxCumService initialized successfully")
        except Exception as e:
            log.error(f"Failed to initialize ThxCumService: {str(e)}")
            raise ValueError(f"Service initialization failed: {str(e)}")

    @staticmethod
    def _load_image_cv2(path: str) -> np.ndarray:
        """Load an image using OpenCV with error handling"""
        img = cv2.imread(path)
        if img is None:
            raise ValueError(f"Could not load image: {path}")
        return img

    @staticmethod
    def _bytes_to_cv2(image_bytes: bytes) -> np.ndarray:
        """Convert bytes to OpenCV image"""
        try:
            nparr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is None:
                raise ValueError("Failed to decode image bytes")
            return img
        except Exception as e:
            raise ValueError(f"Failed to convert bytes to image: {str(e)}")

    def _calculate_max_dimensions(self, image: np.ndarray, scale_factor: float = 0.6) -> Tuple[int, int]:
        """Calculate maximum dimensions that will fit in background"""
        aspect_ratio = image.shape[1] / image.shape[0]

        if aspect_ratio < 1:  # Tall image
            max_height = int(self.background_img.shape[0] * scale_factor * 1.2)
            max_width = int(max_height * aspect_ratio)
        else:  # Wide image
            max_width = int(self.background_img.shape[1] * scale_factor)
            max_height = int(self.background_img.shape[0] * scale_factor)

        return max_width, max_height

    def _resize_maintaining_aspect(self, image: np.ndarray, max_width: int, max_height: int) -> np.ndarray:
        """Resize image while maintaining aspect ratio"""
        try:
            width_ratio = max_width / image.shape[1]
            height_ratio = max_height / image.shape[0]

            scale = height_ratio if image.shape[0] > image.shape[1] else min(width_ratio, height_ratio)

            new_width = int(image.shape[1] * scale)
            new_height = int(image.shape[0] * scale)

            return cv2.resize(image, (new_width, new_height))
        except Exception as e:
            raise ValueError(f"Failed to resize image: {str(e)}")

    def _add_border_and_text(self, image: np.ndarray, border_width: int = 10) -> np.ndarray:
        """Add border and text overlay to image"""
        try:
            border_color = (27, 20, 13)  # BGR values for #0d141b
            text_color = (76, 96, 116)
            text = f"@not_salieri_bot ( {image.shape[1]}x{image.shape[0]} )"

            # Add border
            bordered = cv2.copyMakeBorder(image, top=border_width + 15, bottom=border_width, left=border_width, right=border_width, borderType=cv2.BORDER_CONSTANT, value=border_color)

            # Convert to PIL for text rendering
            pil_image = Image.fromarray(cv2.cvtColor(bordered, cv2.COLOR_BGR2RGB))
            draw = ImageDraw.Draw(pil_image)

            try:
                font = ImageFont.truetype(self.font_path, 15)
            except OSError:
                log.warning(f"Failed to load font from {self.font_path}, using default")
                font = ImageFont.load_default()

            # Center text
            text_bbox = draw.textbbox((0, 0), text, font=font)
            text_width = text_bbox[2] - text_bbox[0]
            text_x = (pil_image.width - text_width) // 2
            text_y = border_width - 7

            draw.text((text_x, text_y), text, font=font, fill=text_color)
            return cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
        except Exception as e:
            raise ValueError(f"Failed to add border and text: {str(e)}")

    def _add_film_grain(self, image: np.ndarray, intensity: float = 0.010) -> np.ndarray:
        """Add film grain effect"""
        try:
            h, w = image.shape[:2]
            noise = np.random.normal(0, intensity * 255, (h, w, 3)).astype(np.float32)
            noisy_img = cv2.add(image.astype(np.float32), noise)
            return np.clip(noisy_img, 0, 255).astype(np.uint8)
        except Exception as e:
            raise ValueError(f"Failed to add film grain: {str(e)}")

    def _apply_perspective_transform(self, image: np.ndarray, target_width: int = 2640) -> np.ndarray:
        """Apply perspective transformation"""
        try:
            scale_factor = target_width / image.shape[1]
            target_height = int(image.shape[0] * scale_factor)
            resized = cv2.resize(image, (target_width, target_height))

            src_points = np.float32([[0, 0], [target_width, 0], [target_width, target_height], [0, target_height]])

            dst_points = np.float32(
                [
                    [-200, 181],  # Top left
                    [2557, 280],  # Top right
                    [2430, 1784],  # Bottom right
                    [-200, 1724],  # Bottom left
                ]
            )

            matrix = cv2.getPerspectiveTransform(src_points, dst_points)
            return cv2.warpPerspective(resized, matrix, (2640, 1604), flags=cv2.INTER_LINEAR)
        except Exception as e:
            raise ValueError(f"Failed to apply perspective transform: {str(e)}")

    def _adjust_brightness(self, image: np.ndarray, factor: float = 0.9) -> np.ndarray:
        """Adjust image brightness"""
        try:
            return cv2.convertScaleAbs(image, alpha=factor, beta=0)
        except Exception as e:
            raise ValueError(f"Failed to adjust brightness: {str(e)}")

    def _create_final_composition(self, transformed: np.ndarray) -> Image.Image:
        """Create final composition with overlay"""
        try:
            # Add film grain
            transformed = self._add_film_grain(transformed)

            # Convert to PIL Image
            transformed_pil = Image.fromarray(cv2.cvtColor(transformed, cv2.COLOR_BGR2RGB)).convert("RGBA")

            # Create white background
            background = Image.new("RGBA", (2640, 1604), (255, 255, 255, 255))
            background.paste(transformed_pil, (0, 0), transformed_pil)

            # Add overlay
            overlay = Image.open(self.template_path).convert("RGBA")
            overlay_cv = cv2.cvtColor(np.array(overlay), cv2.COLOR_RGBA2BGRA)
            overlay_cv = self._adjust_brightness(overlay_cv, 1.2)
            overlay = Image.fromarray(cv2.cvtColor(overlay_cv, cv2.COLOR_BGRA2RGBA))

            return Image.alpha_composite(background, overlay)
        except Exception as e:
            raise ValueError(f"Failed to create final composition: {str(e)}")

    async def process_image(self, input_source: Union[str, bytes, BytesIO], output_path: Optional[str] = None, output_format: str = "PNG") -> Optional[BytesIO]:
        """
        Process an image with artistic effects

        Args:
            input_source: Image source (file path, bytes, or BytesIO)
            output_path: Optional path to save the result
            output_format: Output image format (default: PNG)

        Returns:
            BytesIO object containing the processed image if output_path is None,
            otherwise None (image is saved to file)

        Raises:
            ValueError: If any step of the processing fails
        """
        try:
            # Load input image
            if isinstance(input_source, str):
                input_to_paste = await asyncio.get_event_loop().run_in_executor(self.thread_pool, self._load_image_cv2, input_source)
            elif isinstance(input_source, (bytes, BytesIO)):
                if isinstance(input_source, BytesIO):
                    input_source = input_source.getvalue()
                input_to_paste = await asyncio.get_event_loop().run_in_executor(self.thread_pool, self._bytes_to_cv2, input_source)
            else:
                raise ValueError("input_source must be str, bytes, or BytesIO")

            # Process image using thread pool
            max_width, max_height = self._calculate_max_dimensions(input_to_paste)

            input_to_paste = await asyncio.get_event_loop().run_in_executor(self.thread_pool, self._resize_maintaining_aspect, input_to_paste, max_width, max_height)

            input_to_paste = await asyncio.get_event_loop().run_in_executor(self.thread_pool, self._add_border_and_text, input_to_paste)

            input_to_paste = await asyncio.get_event_loop().run_in_executor(self.thread_pool, self._add_film_grain, input_to_paste)

            # Center image on background with offset
            y_offset = (self.background_img.shape[0] - input_to_paste.shape[0]) // 2
            x_offset = (self.background_img.shape[1] - input_to_paste.shape[1]) // 2 + 400

            composition = self.background_img.copy()
            paste_height, paste_width = input_to_paste.shape[:2]

            # Handle boundary cases
            if y_offset + paste_height > composition.shape[0]:
                paste_height = composition.shape[0] - y_offset
            if x_offset + paste_width > composition.shape[1]:
                paste_width = composition.shape[1] - x_offset

            input_to_paste = input_to_paste[:paste_height, :paste_width]
            composition[y_offset : y_offset + paste_height, x_offset : x_offset + paste_width] = input_to_paste

            # Apply final transformations
            composition = await asyncio.get_event_loop().run_in_executor(self.thread_pool, self._add_film_grain, composition)

            transformed = await asyncio.get_event_loop().run_in_executor(self.thread_pool, self._apply_perspective_transform, composition)

            transformed = await asyncio.get_event_loop().run_in_executor(self.thread_pool, self._adjust_brightness, transformed, 0.89)

            final_image = await asyncio.get_event_loop().run_in_executor(self.thread_pool, self._create_final_composition, transformed)

            # Handle output
            if output_path:
                output_path = Path(output_path)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                await asyncio.get_event_loop().run_in_executor(self.thread_pool, final_image.save, str(output_path), output_format)
                return None
            else:
                img_byte_arr = BytesIO()
                await asyncio.get_event_loop().run_in_executor(self.thread_pool, final_image.save, img_byte_arr, output_format)
                img_byte_arr.seek(0)
                return img_byte_arr

        except Exception as e:
            log.error(f"Image processing failed: {str(e)}")
            raise ValueError(f"Failed to process image: {str(e)}")
