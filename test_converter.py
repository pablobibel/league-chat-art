"""Image conversion checks using local synthetic fixtures only."""

from dataclasses import FrozenInstanceError
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image, features

from art_converter import ConversionOptions, convert_image


class ConverterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def save(self, image, filename="picture.png", **kwargs):
        path = self.directory / filename
        image.save(path, **kwargs)
        return path

    def test_contrasting_shape_preserves_rows_and_columns(self):
        image = Image.new("L", (4, 3), "white")
        for point in ((0, 0), (3, 0), (1, 1), (2, 1), (0, 2), (3, 2)):
            image.putpixel(point, 0)
        rows = convert_image(self.save(image), ConversionOptions(width=4, aspect=1))
        self.assertEqual(rows, ["l..l", ".ll.", "l..l"])

    def test_supported_formats_are_detected_from_contents(self):
        formats = ["PNG", "JPEG", "BMP"]
        if features.check("webp"):
            formats.append("WEBP")
        for image_format in formats:
            with self.subTest(format=image_format):
                path = self.save(Image.new("RGB", (4, 4), "black"), "misnamed.bin", format=image_format)
                self.assertEqual(convert_image(path, ConversionOptions(width=4, aspect=1)), ["llll"] * 4)

    def test_rgba_transparency_is_composited_on_white(self):
        image = Image.new("RGBA", (3, 1))
        image.putdata([(0, 0, 0, 0), (0, 0, 0, 255), (0, 0, 0, 64)])
        self.assertEqual(convert_image(self.save(image), ConversionOptions(width=3, aspect=1)), [".l."])

    def test_palette_transparency_is_composited_on_white(self):
        image = Image.new("P", (2, 1))
        image.putpalette([0, 0, 0, 0, 0, 0] + [0] * 762)
        image.putdata([0, 1])
        path = self.save(image, transparency=0)
        self.assertEqual(convert_image(path, ConversionOptions(width=2, aspect=1)), [".l"])

    def test_dimensions_preserve_aspect_and_respect_bounds(self):
        cases = [
            ((100, 100), ConversionOptions(), (48, 12)),
            ((200, 100), ConversionOptions(), (50, 6)),
            ((100, 400), ConversionOptions(), (12, 12)),
            ((1, 1000), ConversionOptions(), (1, 12)),
            ((1000, 1), ConversionOptions(), (50, 1)),
            ((1, 1), ConversionOptions(width=1, max_rows=1), (1, 1)),
            ((2, 3), ConversionOptions(width=10, max_rows=8, aspect=1), (5, 8)),
            ((1, 1), ConversionOptions(aspect=1e-308), (1, 12)),
            ((1, 1), ConversionOptions(aspect=1e308), (50, 1)),
        ]
        for size, options, expected in cases:
            with self.subTest(size=size, options=options):
                rows = convert_image(self.save(Image.new("L", size)), options)
                self.assertEqual((len(rows[0]), len(rows)), expected)
                self.assertTrue(all(len(row) == expected[0] for row in rows))

    def test_threshold_is_strict_and_invert_swaps_characters(self):
        image = Image.new("L", (4, 1))
        image.putdata([0, 127, 128, 255])
        path = self.save(image)
        self.assertEqual(convert_image(path, ConversionOptions(width=4, aspect=1)), ["ll.."])
        self.assertEqual(convert_image(path, ConversionOptions(width=4, aspect=1, invert=True)), ["..ll"])
        self.assertEqual(convert_image(path, ConversionOptions(width=4, aspect=1, threshold=0)), ["...."])
        self.assertEqual(convert_image(path, ConversionOptions(width=4, aspect=1, threshold=255)), ["lll."])

    def test_contrast_changes_threshold_classification(self):
        image = Image.new("L", (2, 1))
        image.putdata([100, 160])
        path = self.save(image)
        self.assertEqual(convert_image(path, ConversionOptions(width=2, aspect=1, threshold=90)), [".."])
        self.assertEqual(convert_image(path, ConversionOptions(width=2, aspect=1, threshold=90, contrast=2)), ["l."])

    def test_exif_orientation_applies_before_resizing(self):
        image = Image.new("RGB", (20, 40), "white")
        image.paste("black", (0, 0, 20, 20))
        exif = Image.Exif()
        exif[274] = 6  # Rotate 90 degrees clockwise for display.
        path = self.save(image, "rotated.jpg", exif=exif, quality=100)
        rows = convert_image(path, ConversionOptions(width=8, max_rows=20, aspect=1))
        self.assertEqual(rows, ["....llll"] * 4)

    def test_invalid_missing_truncated_and_unsupported_images(self):
        invalid = self.directory / "invalid.png"
        invalid.write_text("This is not an image.")
        truncated = self.save(Image.new("L", (10, 10)), "truncated.png")
        truncated.write_bytes(truncated.read_bytes()[:40])
        unsupported = self.save(Image.new("L", (3, 3)), "unsupported.png", format="GIF")
        for path in (self.directory / "missing.png", invalid, truncated, unsupported, self.directory):
            with self.subTest(path=path), self.assertRaises(ValueError):
                convert_image(path, ConversionOptions())

    def test_decompression_warning_and_error_are_clear_value_errors(self):
        path = self.save(Image.new("L", (10, 10)))
        for limit in (75, 20):
            with self.subTest(limit=limit), patch.object(Image, "MAX_IMAGE_PIXELS", limit):
                with self.assertRaisesRegex(ValueError, "safe decompression size limit"):
                    convert_image(path, ConversionOptions())

    def test_invalid_options_are_rejected(self):
        invalid_values = {
            "width": (0, -1, 1.5, True, "50"),
            "max_rows": (0, -2, 1.5, False),
            "aspect": (0, -1, float("nan"), float("inf"), True, "4", 10**400),
            "contrast": (0, -1, float("nan"), float("inf"), False, 10**400),
            "threshold": (-1, 256, 127.5, True),
            "invert": (1, "yes", None),
        }
        for name, values in invalid_values.items():
            for value in values:
                with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                    ConversionOptions(**{name: value})
        with self.assertRaises(FrozenInstanceError):
            ConversionOptions().width = 10


if __name__ == "__main__":
    unittest.main()
