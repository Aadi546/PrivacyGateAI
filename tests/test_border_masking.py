"""Synthetic border regressions. Never use personal identity images here."""

from io import BytesIO
from pathlib import Path
import unittest

import fitz
import numpy as np
from PIL import Image, ImageDraw

from backend import engine, masking

RULES = {'formats': ['png', 'pdf'], 'max_bytes': 2097152, 'required_fields': []}


def border_fixture(line_y=271):
    with fitz.open(stream=engine.sample_document(), filetype='pdf') as doc:
        image = Image.open(BytesIO(doc[0].get_pixmap(alpha=False).tobytes('png'))).convert('RGB')
    ImageDraw.Draw(image).line((0, line_y, image.width-1, line_y), fill=(165, 25, 65), width=2)
    buffer = BytesIO()
    image.save(buffer, format='PNG')
    return image, buffer.getvalue()


class BorderMaskingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source, cls.data = border_fixture()
        cls.report = engine.analyze(cls.data, 'synthetic-border.png', RULES)
        cls.finding = next(f for f in cls.report['findings'] if f['category'] == 'aadhaar')

    def test_nearby_red_line_is_preserved_and_output_verified(self):
        self.assertTrue(self.finding['locatable'])
        output, verification = engine.redact(self.data, self.report, [self.finding['id']])
        self.assertEqual(verification['status'], 'passed_supported_checks')
        self.assertTrue(verification['preserved_last_four'])
        self.assertTrue(verification['checks'][0]['replacement_rendered'])
        actual = np.asarray(engine.raster_image(output))
        original = np.asarray(self.source)
        self.assertTrue(np.array_equal(actual[271:273], original[271:273]))
        allowed = np.zeros(original.shape[:2], dtype=bool)
        parts = masking.plan(self.finding, self.source)
        for part in parts:
            x0, y0, x1, y1 = masking.clipped_rect(part['rect'], self.source)
            allowed[y0:y1, x0:x1] = True
            self.assertLessEqual(y1, 271)
        self.assertTrue(np.array_equal(actual[~allowed], original[~allowed]))

    def test_colored_or_black_rule_crossing_digits_is_rejected(self):
        bounds = masking.union(self.finding['rects'][:4])
        y = int((bounds[1]+bounds[3])/2)
        for color in ((165,25,65), (30,30,30)):
            image = self.source.copy()
            ImageDraw.Draw(image).line((bounds[0]-10, y, bounds[2]+10, y), fill=color, width=2)
            with self.assertRaises(masking.MaskingError):
                masking.plan(self.finding, image)

    def test_pattern_crossing_replacement_area_is_rejected(self):
        image = self.source.copy()
        bounds = masking.union(self.finding['rects'][:4])
        draw = ImageDraw.Draw(image)
        for x in range(int(bounds[0]), int(bounds[2]), 6):
            draw.line((x,bounds[1],x,bounds[3]-1), fill=(20,120,180), width=1)
        with self.assertRaises(masking.MaskingError):
            masking.plan(self.finding, image)

    def test_different_grayscale_stroke_shades_are_not_a_pattern(self):
        pixels = np.array(self.source)
        bounds = masking.union(self.finding['rects'][:4])
        x0,y0,x1,y1 = masking.clipped_rect(bounds, self.source)
        region = pixels[y0:y1,x0:x1]
        ink = region.max(axis=2) < 180
        shades = np.broadcast_to(np.where(np.arange(x1-x0) % 2, 15, 65), ink.shape)
        region[ink] = np.repeat(shades[ink,None], 3, axis=1)
        parts = masking.plan(self.finding, Image.fromarray(pixels))
        self.assertEqual([part['text'] for part in parts], ['xxxx', 'xxxx'])

    def test_two_contaminated_edges_are_not_enough_for_background(self):
        image = self.source.copy()
        part = masking.plan(self.finding, image)[0]
        x0,y0,x1,y1 = masking.clipped_rect(part['rect'], image)
        draw = ImageDraw.Draw(image)
        draw.rectangle((x0,y0-3,x1-1,y0-1), fill=(20,100,180))
        draw.rectangle((x0-3,y0,x0-1,y1-1), fill=(20,100,180))
        with self.assertRaises(masking.MaskingError):
            masking.colors(image, part['rect'])


if __name__ == '__main__':
    unittest.main()
