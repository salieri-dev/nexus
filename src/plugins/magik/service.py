import uuid
from io import BytesIO

import magic
import numpy as np
import wand.color
import wand.drawing
import wand.image
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageSequence
from pyfiglet import figlet_format

from structlog import get_logger

log = get_logger(__name__)


class ImageService:
    def __init__(self):
        # Caching fonts and other constants for performance improvement
        self.font_cache = {}
        self.font_path = "path/to/font.ttf"  # Adjust as necessary

        # Cache formats and avoid recalculating mime if not necessary
        self.image_mimes = ["image/png", "image/pjpeg", "image/jpeg", "image/x-icon"]
        self.gif_mimes = ["image/gif"]
        log.info("ImageService initialized")

    def random_filename(self, image=False, ext: str = "png"):
        h = str(uuid.uuid4().hex)
        return f"{h}.{ext}" if image else h

    def get_font(self, size: int):
        """Cache fonts to avoid repetitive loading."""
        if size not in self.font_cache:
            self.font_cache[size] = ImageFont.truetype(self.font_path, size)
        return self.font_cache[size]

    def process_frames(self, image, process_func):
        """Common frame processor for GIFs."""
        frames = []
        for frame in image.sequence:
            with frame.clone() as img:
                img = process_func(img)
                frames.append(img.clone())
        return frames

    def save_gif(self, frames) -> BytesIO:
        """Helper for saving GIFs."""
        gif_output = BytesIO()
        with wand.image.Image() as gif:
            gif.sequence = frames
            gif.save(file=gif_output)
        gif_output.seek(0)
        return gif_output

    def save_image(self, image) -> BytesIO:
        """Helper for saving static images."""
        output = BytesIO()
        image.save(file=output)
        output.seek(0)
        return output

    # ---- Image Effect Functions ----

    def do_magik(self, scale, img_bytes, is_gif=False):
        """Logic for applying the 'magik' effect to images and GIFs."""
        img_bytes.seek(0)
        file_type = magic.from_buffer(img_bytes.getvalue(), mime=True)

        if file_type not in self.image_mimes + self.gif_mimes:
            log.error(f"Unsupported image format: {file_type}")
            raise ValueError(f"Unsupported image format: {file_type}")

        log.info(f"Applying magik effect with scale={scale}, is_gif={is_gif}")
        with wand.image.Image(blob=img_bytes.getvalue()) as original:
            if is_gif:
                frames = self.process_frames(original, lambda img: self.apply_magik_effect(img, scale))
                return self.save_gif(frames)
            else:
                with original.clone() as img:
                    img = self.apply_magik_effect(img, scale)
                    return self.save_image(img)

    def apply_magik_effect(self, image, scale):
        image.transform_colorspace("cmyk")
        image.transform(resize="800x800")
        image.liquid_rescale(
            width=int(image.width * 0.5),
            height=int(image.height * 0.5),
            delta_x=int(0.5 * scale) if scale else 1,
            rigidity=0,
        )
        image.liquid_rescale(
            width=int(image.width * 1.5),
            height=int(image.height * 1.5),
            delta_x=scale if scale else 2,
            rigidity=0,
        )
        return image

    def pixelate(self, img, pixels):
        """Helper to apply pixelation to both static frames and GIFs."""
        img = img.resize((int(img.size[0] / pixels), int(img.size[1] / pixels)), Image.NEAREST)
        img = img.resize((int(img.size[0] * pixels), int(img.size[1] * pixels)), Image.NEAREST)
        return img

    def make_pixel(self, b: BytesIO, pixels: int) -> BytesIO:
        log.info(f"Applying pixelation with pixels={pixels}")
        img = Image.open(b)
        pixelated_img = self.pixelate(img, pixels)

        final = BytesIO()
        pixelated_img.save(final, "png")
        final.seek(0)
        return final

    def make_pixel_gif(self, b, pixels):
        log.info(f"Applying pixelation to GIF with pixels={pixels}")
        img = Image.open(b)
        frames = [self.pixelate(frame.copy(), pixels) for frame in ImageSequence.Iterator(img)]

        final = BytesIO()
        frames[0].save(final, format="GIF", save_all=True, append_images=frames[1:], loop=0)
        final.seek(0)
        return final

    def transform_image(self, b, transform_func):
        """Generic image transformation (flip, flop, invert, etc.)."""
        img = Image.open(b)
        transformed = transform_func(img)

        final = BytesIO()
        transformed.save(final, "png")
        final.seek(0)
        return final

    def flip_image(self, b):
        log.info("Applying flip transformation")
        return self.transform_image(b, ImageOps.flip)

    def flop_image(self, b):
        log.info("Applying flop transformation")
        return self.transform_image(b, ImageOps.mirror)

    def invert_image(self, b):
        log.info("Applying invert transformation")
        return self.transform_image(b, lambda img: ImageOps.invert(img.convert("RGB")))

    def rotate_image(self, b, degrees):
        log.info(f"Rotating image by {degrees} degrees")
        img = Image.open(b).convert("RGBA")
        rotated = img.rotate(int(degrees))

        final = BytesIO()
        rotated.save(final, "png")
        final.seek(0)
        return final

    def do_ascii(self, text):
        """Generates ASCII art and an image."""
        try:
            log.info(f"Generating ASCII art for text: {text}")
            ascii_text = figlet_format(text, font="starwars")
            img = Image.new("RGB", (2000, 1000), color="black")
            draw = ImageDraw.Draw(img)
            font = self.get_font(20)  # Use cached font

            draw.text((20, 20), ascii_text, fill="green", font=font)
            bbox = draw.textbbox((0, 0), ascii_text, font=font)

            # Crop and save the image
            cropped_img = img.crop((0, 0, bbox[2] + 40, bbox[3] + 40))
            final = BytesIO()
            cropped_img.save(final, "PNG")
            final.seek(0)
            return final, ascii_text
        except Exception as e:
            log.error(f"Error making ASCII art: {e}")
            return None, None

    def mirror_side(self, img, side, axis_func):
        """Generic logic to apply side-mirroring effects (e.g., WAAW, HAAH)."""
        log.info(f"Applying mirror effect: side={side}, axis={axis_func}")
        dimension = int(img.width / 2) if side == "vertical" else int(img.height / 2)
        cropped_img = img.clone()

        crop_params = {
            ("east", "vertical"): dict(width=dimension, height=img.height, gravity="east"),
            ("west", "vertical"): dict(width=dimension, height=img.height, gravity="west"),
            ("north", "horizontal"): dict(width=img.width, height=dimension, gravity="north"),
            ("south", "horizontal"): dict(width=img.width, height=dimension, gravity="south"),
        }

        cropped_img.crop(**crop_params.get((axis_func, side)))

        opposite_half = cropped_img.clone()
        opposite_half.flip() if side == "horizontal" else opposite_half.flop()

        # Convert to PIL for merging
        half1_pil = Image.open(BytesIO(cropped_img.make_blob()))
        half2_pil = Image.open(BytesIO(opposite_half.make_blob()))

        imgs_comb = self.merge_images(half1_pil, half2_pil, side)

        final = BytesIO()
        imgs_comb.save(final, "png")
        final.seek(0)
        return final

    def merge_images(self, img1, img2, side):
        """Helper to merge two images either side-by-side or top-to-bottom."""
        if side == "vertical":
            imgs = [ImageOps.mirror(i) for i in [img1, img2]]
            min_shape = sorted([(np.sum(i.size), i.size) for i in imgs])[0][1]
            return Image.fromarray(np.hstack([np.asarray(i.resize(min_shape)) for i in imgs]))
        else:
            imgs = [img1, img2]
            min_shape = sorted([(np.sum(i.size), i.size) for i in imgs])[0][1]
            return Image.fromarray(np.vstack([np.asarray(i.resize(min_shape)) for i in imgs]))

    def do_waaw(self, b):
        log.info("Applying WAAW effect")
        img = wand.image.Image(file=b)
        try:
            return self.mirror_side(img, "vertical", "east")
        finally:
            img.close()

    def do_haah(self, b):
        log.info("Applying HAAH effect")
        img = wand.image.Image(file=b)
        try:
            return self.mirror_side(img, "vertical", "west")
        finally:
            img.close()

    def do_woow(self, b):
        log.info("Applying WOOW effect")
        img = wand.image.Image(file=b)
        try:
            return self.mirror_side(img, "horizontal", "north")
        finally:
            img.close()

    def do_hooh(self, b):
        log.info("Applying HOOH effect")
        img = wand.image.Image(file=b)
        try:
            return self.mirror_side(img, "horizontal", "south")
        finally:
            img.close()

    # ---- Special Image Manipulation Functions ----

    def watermark(self, b, mark=None, x=0, y=0, transparency=0):
        log.info(f"Adding watermark: mark={mark}, position=({x}, {y}), transparency={transparency}")
        img = Image.open(b).convert("RGBA")
        width, height = img.size

        # Create watermark overlay
        txt_img = Image.new("RGBA", img.size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(txt_img)

        if mark:
            font = self.get_font(30)  # Font size customizable or cached
            text_width, text_height = draw.textsize(mark, font=font)

            # Ensure watermark doesn't go out of bounds
            x = max(x, 0)
            y = max(y, 0)
            x = min(x, width - text_width)
            y = min(y, height - text_height)

            # Draw the watermark text with specified transparency
            draw.text((x, y), mark, fill=(255, 255, 255, int(255 * transparency)), font=font)

        # Combine watermark and original image
        watermarked = Image.alpha_composite(img, txt_img)

        # Save result
        final = BytesIO()
        watermarked.save(final, "PNG")
        final.seek(0)
        return final

    def jpeg(self, b, quality=1):
        """Applies 'JPEG' compression artifacts."""
        log.info(f"Applying JPEG compression with quality={quality}")
        img = Image.open(b)
        img_bytes = BytesIO()
        img.save(img_bytes, format="JPEG", quality=max(1, min(30, quality)))
        img_bytes.seek(0)

        jpeg_image = BytesIO()
        img.save(jpeg_image, format="PNG")
        jpeg_image.seek(0)
        return jpeg_image

    def do_vw(self, b, text: str):
        """Adds a vaporwave effect with text."""
        log.info(f"Applying vaporwave effect with text: {text}")
        # Placeholder vaporwave effect method (could add real vaporwave effect here)
        img = Image.open(b).convert("RGBA")

        draw = ImageDraw.Draw(img)
        font = self.get_font(20)  # Cached font for vaporwave effect

        # Add vaporwave text to the image
        draw.text((img.size[0] // 4, img.size[1] // 2), text, (255, 255, 255), font=font)

        final = BytesIO()
        img.save(final, "PNG")
        final.seek(0)
        return final
