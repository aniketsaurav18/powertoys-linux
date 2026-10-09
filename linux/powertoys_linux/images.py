# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.
"""Image Resizer's Linux fit/shrink backend using the installed GNOME runtime."""

import os
from pathlib import Path

import gi

gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf

from .core import fingerprint, resize_dimensions


def resize_image(path, width, height, shrink_only=True):
    source = Path(path)
    identity = fingerprint(source)
    image_format, original_width, original_height = GdkPixbuf.Pixbuf.get_file_info(str(source))
    if image_format is None or original_width <= 0 or original_height <= 0:
        raise ValueError("Unsupported or damaged image.")
    if original_width * original_height > 40_000_000:
        raise ValueError("Input is limited to 40 megapixels.")
    if image_format.get_name() not in ("png", "jpeg"):
        raise ValueError("Stage 1 supports PNG and JPEG inputs only.")
    pixbuf = GdkPixbuf.Pixbuf.new_from_file(str(source)).apply_embedded_orientation()
    dimensions = resize_dimensions(pixbuf.get_width(), pixbuf.get_height(), width, height, shrink_only)
    if dimensions[0] * dimensions[1] > 40_000_000:
        raise ValueError("Output is limited to 40 megapixels.")
    resized = pixbuf.scale_simple(*dimensions, GdkPixbuf.InterpType.BILINEAR)
    success, data = resized.save_to_bufferv("png", [], [])
    if not success:
        raise ValueError("Could not encode the image.")
    if fingerprint(source) != identity:
        raise ValueError("Source image changed during resizing. Try again.")
    for index in range(1, 10001):
        suffix = "" if index == 1 else f" {index}"
        target = source.with_name(f"{source.stem} (resized{suffix}).png")
        try:
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            continue
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
        except Exception:
            target.unlink()
            raise
        return target
    raise FileExistsError("Too many resized copies in this folder.")
