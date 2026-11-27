"""Local Tesseract discovery and bounded OCR; no network or persistent files."""

import os
import shutil
from pathlib import Path

import cv2
import numpy as np
import pytesseract
from PIL import Image, ImageOps

OCR_TIMEOUT = 15
MIN_CONFIDENCE = 80


def find_tesseract():
    override = os.environ.get("TESSERACT_CMD")
    if override:
        candidate = shutil.which(override) or (override if Path(override).is_file() else None)
        if not candidate:
            raise RuntimeError("TESSERACT_CMD does not identify an executable. Correct it and restart.")
        return str(candidate)
    candidates = [shutil.which("tesseract"),
                  str(Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Tesseract-OCR" / "tesseract.exe"),
                  "/usr/local/bin/tesseract", "/opt/homebrew/bin/tesseract"]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(candidate)
    raise RuntimeError("Tesseract was not found. Install it, add it to PATH, or set TESSERACT_CMD. Checked Windows default and both Homebrew paths.")


def configure():
    pytesseract.pytesseract.tesseract_cmd = find_tesseract()


def health():
    try:
        configure()
        version = str(pytesseract.get_tesseract_version())
        if "eng" not in pytesseract.get_languages(config=""):
            return {"available": False, "error": "Tesseract English language data (eng) is missing."}
        return {"available": True, "version": version, "language": "eng"}
    except Exception as exc:
        return {"available": False, "error": str(exc) if isinstance(exc, RuntimeError) else "Tesseract could not run. Check installation and TESSERACT_CMD."}


def clean_image(image):
    # Fresh RGB pixels, corrected EXIF orientation, never copy metadata to output.
    corrected = ImageOps.exif_transpose(image)
    background = Image.new("RGB", corrected.size, "white")
    if corrected.mode == "RGBA":
        background.paste(corrected, mask=corrected.getchannel("A"))
    else:
        background.paste(corrected.convert("RGB"))
    return background


def qr_present(image):
    array = np.asarray(image.convert("RGB"))
    if max(image.size) > 1800:
        ratio = 1800 / max(image.size)
        array = cv2.resize(array, None, fx=ratio, fy=ratio, interpolation=cv2.INTER_AREA)
    detector = cv2.QRCodeDetector()
    found, _ = detector.detect(cv2.cvtColor(array, cv2.COLOR_RGB2GRAY))
    return bool(found)


def extract(image):
    """Match independently recognized character boxes to high-confidence OCR words."""
    configure()
    image = clean_image(image)
    gray = ImageOps.grayscale(image)
    data = pytesseract.image_to_data(gray, lang="eng", config="--psm 3", output_type=pytesseract.Output.DICT, timeout=OCR_TIMEOUT)
    box_data = pytesseract.image_to_boxes(gray, lang="eng", config="--psm 3", timeout=OCR_TIMEOUT)
    characters = []
    for row in box_data.splitlines():
        fields = row.split()
        if len(fields) != 6:
            continue
        char, left, bottom, right, top, _ = fields
        characters.append({"c": char, "bbox": [int(left), image.height - int(top), int(right), image.height - int(bottom)]})
    grouped = {}
    for index, word in enumerate(data["text"]):
        if not word.strip():
            continue
        key = (data["block_num"][index], data["par_num"][index], data["line_num"][index])
        left, top = data["left"][index], data["top"][index]
        right, bottom = left + data["width"][index], top + data["height"][index]
        selected = [char for char in characters if left - 1 <= (char["bbox"][0] + char["bbox"][2]) / 2 <= right + 1 and top - 1 <= (char["bbox"][1] + char["bbox"][3]) / 2 <= bottom + 1]
        selected.sort(key=lambda char: char["bbox"][0])
        precise = "".join(char["c"] for char in selected) == word and float(data["conf"][index]) >= MIN_CONFIDENCE
        if not precise:
            selected = [{"c": char, "bbox": [left, top, right, bottom]} for char in word]
        for char in selected:
            char["precise"] = precise
        grouped.setdefault(key, []).append((left, word, selected))
    lines = []
    for words in grouped.values():
        words.sort(key=lambda word: word[0])
        text, chars = "", []
        for _, word, boxes in words:
            if chars:
                text += " "
                chars.append({"c": " ", "bbox": boxes[0]["bbox"], "precise": True})
            text += word
            chars.extend(boxes)
        lines.append({"page": 0, "text": text, "chars": chars, "width": image.width, "height": image.height})
    return lines


def read_text(image):
    configure()
    return pytesseract.image_to_string(ImageOps.grayscale(image), lang="eng", config="--psm 3", timeout=OCR_TIMEOUT)
