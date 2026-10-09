# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.
"""Local Tesseract OCR with bounded images, process lifetime and output."""

import os
import math
import re
import shutil
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import gi

gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf

from .core import fingerprint


MAX_PIXELS = 20_000_000
MAX_FILE_BYTES = 50_000_000
MAX_TEXT_BYTES = 2_000_000
MODES = {"Automatic page": 3, "Text block": 6, "Single line": 7, "Scattered text": 11}
LANGUAGE = re.compile(r"[A-Za-z0-9_]+(?:[-/][A-Za-z0-9_]+)*\Z")


class OcrCancelled(Exception):
    pass


@dataclass(frozen=True)
class Engine:
    executable: Path
    runtime: Path | None = None

    def command(self, *arguments):
        result = [str(self.executable)]
        if self.runtime:
            folders = sorted((self.runtime / "usr/share/tesseract-ocr").glob("*/tessdata"))
            if not folders:
                raise RuntimeError("The local OCR runtime has no language data.")
            result.extend(("--tessdata-dir", str(folders[-1])))
        result.extend(arguments)
        return result

    def environment(self):
        context = dict(os.environ)
        context["OMP_THREAD_LIMIT"] = "2"
        if self.runtime:
            libraries = self.runtime / "usr/lib/x86_64-linux-gnu"
            context["LD_LIBRARY_PATH"] = str(libraries)
            context.pop("TESSDATA_PREFIX", None)
        return context


def local_runtime():
    data = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    return data / "powertoys-linux/ocr-runtime"


def find_engine():
    system = shutil.which("tesseract")
    if system:
        return Engine(Path(system).resolve())
    runtime = local_runtime()
    executable = runtime / "usr/bin/tesseract"
    if executable.is_file() and os.access(executable, os.X_OK):
        return Engine(executable, runtime)
    raise RuntimeError("OCR engine not installed. Install optional Tesseract support; see the OCR setup instructions.")


def list_languages(engine=None):
    engine = engine or find_engine()
    try:
        result = subprocess.run(engine.command("--list-langs"), env=engine.environment(),
                                capture_output=True, timeout=5, check=False)
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("OCR engine language discovery timed out.") from error
    if result.returncode:
        raise RuntimeError("OCR engine could not list languages: " + result.stderr.decode("utf-8", errors="replace")[:500])
    languages = sorted(set(line.strip() for line in result.stdout.decode("utf-8").splitlines()
                           if LANGUAGE.fullmatch(line.strip()) and line.strip() != "osd"))
    if not languages or len(languages) > 512:
        raise RuntimeError("No usable OCR language models are installed.")
    return languages


def load_image(path):
    source = Path(path)
    identity = fingerprint(source)
    if identity[2] > MAX_FILE_BYTES:
        raise ValueError("OCR images are limited to 50 MB.")
    image_format, width, height = GdkPixbuf.Pixbuf.get_file_info(str(source))
    if image_format is None or image_format.get_name() not in ("png", "jpeg") or width <= 0 or height <= 0:
        raise ValueError("Select a valid PNG or JPEG image.")
    if width * height > MAX_PIXELS:
        raise ValueError("OCR images are limited to 20 megapixels.")
    image = GdkPixbuf.Pixbuf.new_from_file(str(source)).apply_embedded_orientation()
    if fingerprint(source) != identity:
        raise ValueError("The source image changed while loading. Try again.")
    return image


def validate_crop(crop, width, height):
    if crop is None:
        return (0, 0, width, height)
    if not isinstance(crop, (tuple, list)) or len(crop) != 4 or any(type(value) is not int for value in crop):
        raise ValueError("The selected region must use integer pixel coordinates.")
    x, y, w, h = crop
    if min(x, y) < 0 or min(w, h) < 1 or x + w > width or y + h > height:
        raise ValueError("Select a non-empty region inside the image.")
    return tuple(crop)


def crop_from_drag(first, second, width, height, preview_width, preview_height):
    if (any(not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0
            for value in (width, height, preview_width, preview_height))
            or any(not isinstance(point, (tuple, list)) or len(point) != 2
                   or any(not isinstance(value, (int, float)) or not math.isfinite(value) for value in point)
                   for point in (first, second))):
        raise ValueError("Preview dimensions must be positive.")
    x1, x2 = sorted((min(width, max(0, round(point[0] * width / preview_width))) for point in (first, second)))
    y1, y2 = sorted((min(height, max(0, round(point[1] * height / preview_height))) for point in (first, second)))
    return validate_crop((x1, y1, x2 - x1, y2 - y1), width, height)


def stop_process(process):
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
    except ProcessLookupError:
        process.wait()


def recognize(image, language="eng", mode="Text block", crop=None, cancel=None, engine=None, timeout=30):
    if not isinstance(language, str) or not LANGUAGE.fullmatch(language) or not isinstance(mode, str) or mode not in MODES:
        raise ValueError("Choose a supported OCR language and recognition mode.")
    if cancel and cancel.is_set():
        raise OcrCancelled("OCR cancelled.")
    width, height = image.get_width(), image.get_height()
    if width * height > MAX_PIXELS:
        raise ValueError("OCR images are limited to 20 megapixels.")
    x, y, w, h = validate_crop(crop, width, height)
    engine = engine or find_engine()
    if language not in list_languages(engine):
        raise ValueError("The selected OCR language is not installed.")
    if cancel and cancel.is_set():
        raise OcrCancelled("OCR cancelled.")
    selection = image.new_subpixbuf(x, y, w, h)
    # Composite transparency on white so invisible background pixels do not
    # become black text when passed to the recognizer.
    prepared = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, w, h)
    prepared.fill(0xffffffff)
    selection.composite(prepared, 0, 0, w, h, 0, 0, 1, 1, GdkPixbuf.InterpType.BILINEAR, 255)
    with tempfile.TemporaryDirectory(prefix="powertoys-ocr-") as folder:
        source = Path(folder) / "input.png"
        prepared.savev(str(source), "png", [], [])
        with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
            process = subprocess.Popen(engine.command(str(source), "stdout", "-l", language, "--psm", str(MODES[mode])),
                                       env=engine.environment(), stdin=subprocess.DEVNULL, stdout=output,
                                       stderr=errors, start_new_session=True)
            deadline = time.monotonic() + timeout
            try:
                while process.poll() is None:
                    if cancel and cancel.is_set():
                        raise OcrCancelled("OCR cancelled.")
                    if time.monotonic() >= deadline:
                        raise TimeoutError("OCR exceeded its 30-second limit. Select a smaller region.")
                    if os.fstat(output.fileno()).st_size > MAX_TEXT_BYTES or os.fstat(errors.fileno()).st_size > 64_000:
                        raise ValueError("OCR output exceeded its size limit.")
                    time.sleep(0.05)
                output.seek(0)
                errors.seek(0)
                data = output.read(MAX_TEXT_BYTES + 1)
                if process.returncode:
                    raise RuntimeError("OCR failed: " + errors.read(4000).decode("utf-8", errors="replace").strip())
                if len(data) > MAX_TEXT_BYTES:
                    raise ValueError("OCR output exceeded its 2 MB limit.")
                text = data.decode("utf-8").strip()
                return " ".join(text.splitlines()) if mode == "Single line" else text
            finally:
                stop_process(process)
