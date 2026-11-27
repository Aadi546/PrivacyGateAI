"""Permanent background replacement plus readable text, using a bundled font."""

from functools import lru_cache
from io import BytesIO

import fitz
import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFont

FONT_BYTES = fitz.Font("helv").buffer


class MaskingError(ValueError):
    pass


@lru_cache(maxsize=128)
def font(size):
    return ImageFont.truetype(BytesIO(FONT_BYTES), size=max(1, int(size)))


def union(rectangles):
    result = fitz.Rect(rectangles[0])
    for rectangle in rectangles[1:]:
        result |= fitz.Rect(rectangle)
    return list(result)


def clipped_rect(rectangle, image, padding=0):
    return (max(0, int(np.floor(rectangle[0])) - padding),
            max(0, int(np.floor(rectangle[1])) - padding),
            min(image.width, int(np.ceil(rectangle[2])) + padding),
            min(image.height, int(np.ceil(rectangle[3])) + padding))


def colors(image, rectangle, glyph_rectangle=None):
    """Require three agreeing clean edges; inspect the text area separately."""
    x0, y0, x1, y1 = clipped_rect(rectangle, image)
    ring = 3
    if x0 < ring or y0 < ring or x1 + ring > image.width or y1 + ring > image.height or x1 <= x0 or y1 <= y0:
        raise MaskingError("The selected text is too close to an edge for reliable clean masking.")
    pixels = np.asarray(image, dtype=np.int16)
    edges = [pixels[y0-ring:y0, x0:x1].reshape(-1, 3),
             pixels[y1:y1+ring, x0:x1].reshape(-1, 3),
             pixels[y0:y1, x0-ring:x0].reshape(-1, 3),
             pixels[y0:y1, x1:x1+ring].reshape(-1, 3)]
    candidates = [np.rint(np.median(edge, axis=0)).astype(int) for edge in edges]
    scores = [sum(np.quantile(np.max(np.abs(edge - candidate), axis=1), .95) <= 16 for edge in edges)
              for candidate in candidates]
    if max(scores) < 3:
        raise MaskingError("Clean masking needs a reliably uniform background around the selected text. Use a clearer sample; no output was generated.")
    background = candidates[int(np.argmax(scores))]
    gx0, gy0, gx1, gy1 = clipped_rect(glyph_rectangle or rectangle, image)
    interior_pixels = pixels[gy0:gy1, gx0:gx1]
    interior = interior_pixels.reshape(-1, 3)
    ink = interior[np.max(np.abs(interior - background), axis=1) > 50]
    if len(ink) < 4:
        raise MaskingError("The original text color could not be established reliably.")
    foreground = np.rint(np.median(ink, axis=0)).astype(int)
    # Anti-aliased glyphs lie on the foreground/background color segment.
    # A colored rule or pattern crossing the text area does not.
    direction = (foreground - background).astype(float)
    # Glyph strokes may be darker than the median ink color; that is not a pattern.
    fractions = np.maximum((interior - background) @ direction / max(float(direction @ direction), 1), 0)
    residual = np.max(np.abs(interior - (background + fractions[:, None] * direction)), axis=1)
    nonbackground = np.max(np.abs(interior_pixels - background), axis=2) > 40
    longest_run = 0
    for row in nonbackground:
        transitions = np.diff(np.r_[False, row, False].astype(int))
        runs = np.flatnonzero(transitions == -1) - np.flatnonzero(transitions == 1)
        longest_run = max(longest_run, int(runs.max()) if len(runs) else 0)
    if np.any(residual > 28) or longest_run > nonbackground.shape[1] * .9:
        raise MaskingError("A line or pattern crosses the selected text area. Clean masking is blocked to preserve nearby content.")
    return tuple(map(int, background)), tuple(map(int, foreground))


def safe_padding(image, bounds, requested, background, scale):
    """Grow through blank space only; exclude a nearby border from the fill."""
    core = clipped_rect([value * scale for value in bounds], image)
    target = clipped_rect([value * scale for value in requested], image)
    pixels = np.asarray(image, dtype=np.int16)
    x0, y0, x1, y1 = core
    limits = list(core)
    for side in range(4):
        steps = abs(core[side] - target[side])
        for step in range(1, steps + 1):
            if side == 0: strip = pixels[y0:y1, x0-step:x0-step+1]
            elif side == 1: strip = pixels[y0-step:y0-step+1, x0:x1]
            elif side == 2: strip = pixels[y0:y1, x1+step-1:x1+step]
            else: strip = pixels[y1+step-1:y1+step, x0:x1]
            occupied = np.max(np.abs(strip - np.array(background)), axis=2) > 16
            if float(occupied.mean()) >= .25:
                break
            limits[side] = core[side] + (-step if side < 2 else step)
    if limits == list(target):
        return requested
    return [value / scale for value in limits]


def plan(finding, image, pdf=False):
    """Coordinates remain in PDF points or orientation-corrected image pixels."""
    parts = []
    if finding["category"] == "aadhaar":
        groups = [(union(finding["rects"][:4]), "xxxx", finding["value"].replace(" ", "").replace("-", "")[:4]),
                  (union(finding["rects"][4:8]), "xxxx", finding["value"].replace(" ", "").replace("-", "")[4:8])]
    else:
        groups = [(union(finding["rects"]), finding["masked_value"], finding["value"])]
    scale = 2 if pdf else 1
    padding = .4 if pdf else 4
    for bounds, replacement, original in groups:
        rect = [bounds[0] - padding, bounds[1] - padding, bounds[2] + padding, bounds[3] + padding]
        sample_rect = [coordinate * scale for coordinate in rect]
        background, foreground = colors(image, sample_rect, [coordinate * scale for coordinate in bounds])
        rect = safe_padding(image, bounds, rect, background, scale)
        if pdf:
            style = finding["text_style"]
            size = style["size"]
            baseline = style["baseline"]
            color = style["color"]
            foreground = ((color >> 16) & 255, (color >> 8) & 255, color & 255)
            width = fitz.get_text_length(replacement, fontname="helv", fontsize=size)
            size = min(size, (bounds[2] - bounds[0]) * size / max(width, 1))
        else:
            reference = font(100).getbbox(original, anchor="ls")
            size = max(1, round((bounds[3] - bounds[1]) * 100 / max(reference[3] - reference[1], 1)))
            width = font(size).getlength(replacement)
            size = max(1, min(size, int((bounds[2] - bounds[0]) * size / max(width, 1))))
            reference = font(size).getbbox(original, anchor="ls")
            baseline = bounds[3] - reference[3]
        parts.append({"rect": rect, "text": replacement, "background": background,
                      "foreground": foreground, "size": size, "origin": [bounds[0], baseline]})
    return parts


def render(image, plans):
    """Overwrite source pixels first, then draw only the approved replacement."""
    result = image.copy()
    drawing = ImageDraw.Draw(result)
    for parts in plans.values():
        for part in parts:
            x0, y0, x1, y1 = clipped_rect(part["rect"], result)
            drawing.rectangle((x0, y0, x1 - 1, y1 - 1), fill=part["background"])
    for parts in plans.values():
        for part in parts:
            glyph_font = font(part["size"])
            ink_bounds = drawing.textbbox(tuple(part["origin"]), part["text"], font=glyph_font, anchor="ls")
            clear = clipped_rect(part["rect"], result)
            if ink_bounds[0] < clear[0] or ink_bounds[1] < clear[1] or ink_bounds[2] > clear[2] or ink_bounds[3] > clear[3]:
                raise MaskingError("Replacement text would overlap nearby content. No output was generated.")
            drawing.text(tuple(part["origin"]), part["text"], font=glyph_font, fill=part["foreground"], anchor="ls")
    return result


def raster_replacement_matches(actual, expected, parts):
    if actual.size != expected.size:
        return False
    return all(ImageChops.difference(actual.crop(clipped_rect(part["rect"], actual)),
                                     expected.crop(clipped_rect(part["rect"], expected))).getbbox() is None
               for part in parts)


def pdf_replacement_matches(page, parts):
    for part in parts:
        # Extract the replacement from its actual location, not elsewhere on the page.
        text = "".join(page.get_textbox(fitz.Rect(part["rect"])).split()).lower()
        if "".join(part["text"].split()).lower() not in text:
            return False
    return True
