#!/usr/bin/python3
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.
"""Real recognition accuracy smoke check; requires optional Tesseract + eng."""

import tempfile
from pathlib import Path

import cairo
from powertoys_linux import ocr


engine = ocr.find_engine()
assert "eng" in ocr.list_languages(engine), "Install the English language model."
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory) / "text.png"
    surface = cairo.ImageSurface(cairo.FORMAT_RGB24, 1000, 230)
    context = cairo.Context(surface)
    context.set_source_rgb(1, 1, 1)
    context.paint()
    context.set_source_rgb(0, 0, 0)
    context.select_font_face("DejaVu Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    context.set_font_size(45)
    context.move_to(30, 70)
    context.show_text("POWERTOYS LINUX OCR")
    context.move_to(30, 165)
    context.show_text("Invoice 12345")
    surface.write_to_png(str(path))
    before = path.read_bytes()
    image = ocr.load_image(path)
    result = ocr.recognize(image, engine=engine)
    assert "POWERTOYS LINUX OCR" in result, repr(result)
    assert "Invoice 12345" in result, repr(result)
    line = ocr.recognize(image, mode="Single line", crop=(0, 0, 1000, 95), engine=engine)
    assert line == "POWERTOYS LINUX OCR", repr(line)
    assert path.read_bytes() == before
print("Real Tesseract OCR passed: English multi-line text, cropped single line, unchanged source.")
