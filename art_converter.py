"""Convert local images into small, two-character chat pictures."""

from dataclasses import dataclass
import math
from pathlib import Path
import warnings

from PIL import Image, ImageEnhance, ImageOps


@dataclass(frozen=True)
class ConversionOptions:
    width: int = 50
    max_rows: int = 12
    aspect: float = 4.0
    contrast: float = 1.0
    threshold: int = 128
    invert: bool = False

    def __post_init__(self) -> None:
        for name in ("width", "max_rows"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer.")
        for name in ("aspect", "contrast"):
            value = getattr(self, name)
            try:
                finite = isinstance(value, (int, float)) and math.isfinite(value)
            except OverflowError:
                finite = False
            if (
                isinstance(value, bool)
                or not finite
                or value <= 0
            ):
                raise ValueError(f"{name} must be a finite number greater than zero.")
        if (
            isinstance(self.threshold, bool)
            or not isinstance(self.threshold, int)
            or not 0 <= self.threshold <= 255
        ):
            raise ValueError("threshold must be an integer from 0 through 255.")
        if not isinstance(self.invert, bool):
            raise ValueError("invert must be true or false.")


def _output_size(size: tuple[int, int], options: ConversionOptions) -> tuple[int, int]:
    source_width, source_height = size
    rows_per_column = source_height / source_width / options.aspect
    if rows_per_column > options.max_rows / options.width:
        # Floor the scaled width so rounding cannot make the result wider than
        # its proportional row-constrained size. One column is the minimum.
        columns = max(1, math.floor(options.max_rows / rows_per_column))
        rows = options.max_rows
    else:
        columns = options.width
        rows = max(1, round(columns * rows_per_column))
    return columns, rows


def convert_image(path: str | Path, options: ConversionOptions) -> list[str]:
    """Return rows of ``l``/``.`` art, raising ValueError for invalid images.

    Width and max_rows bound the output. Aspect is the character-height to
    character-width correction; transparent pixels are composited onto white.
    Multi-frame images use their first frame.
    """
    if not isinstance(options, ConversionOptions):
        raise ValueError("options must be a ConversionOptions instance.")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as source:
                if source.format not in {"PNG", "JPEG", "WEBP", "BMP"}:
                    raise ValueError("Unsupported image format; use PNG, JPEG, WebP, or BMP.")
                source.load()
                oriented = ImageOps.exif_transpose(source)
                rgba = oriented.convert("RGBA")
                background = Image.new("RGBA", rgba.size, "white")
                gray = Image.alpha_composite(background, rgba).convert("L")
                gray = ImageEnhance.Contrast(gray).enhance(options.contrast)
                columns, rows = _output_size(gray.size, options)
                resized = gray.resize((columns, rows), Image.Resampling.LANCZOS)
                pixels = resized.tobytes()
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError("Image exceeds Pillow's safe decompression size limit.") from exc
    except (OSError, SyntaxError, TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"Cannot convert image '{path}': {exc}") from exc

    dark, light = (".", "l") if options.invert else ("l", ".")
    return [
        "".join(dark if pixel < options.threshold else light for pixel in pixels[start : start + columns])
        for start in range(0, len(pixels), columns)
    ]
