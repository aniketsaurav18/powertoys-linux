# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.
import os
import random
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from gi.repository import GdkPixbuf, GLib
from powertoys_linux import ocr


# A separate executable exercises the CLI protocol and actual process cleanup.
# It is a test double, not a recognition engine or an accuracy test.
ENGINE = '''#!/usr/bin/python3
import os, struct, sys, time
if "--list-langs" in sys.argv:
    print("List of available languages (3):\\neng\\nspa\\nosd")
    raise SystemExit(0)
mode = os.environ.get("TEST_OCR_MODE", "normal")
if mode == "hang":
    time.sleep(60)
if mode == "fail":
    print("bad image", file=sys.stderr)
    raise SystemExit(3)
if mode == "large":
    sys.stdout.write("x" * 2100000)
    raise SystemExit(0)
with open(sys.argv[1], "rb") as stream:
    header = stream.read(24)
assert struct.unpack(">II", header[16:24]) == (20, 10)
assert sys.argv[2:] == ["stdout", "-l", "eng", "--psm", os.environ.get("TEST_OCR_PSM", "6")]
print("Hello Linux\\n12345")
'''


class OcrTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        executable = self.root / "tesseract"
        executable.write_text(ENGINE)
        executable.chmod(0o700)
        self.engine = ocr.Engine(executable)
        self.image = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, 40, 30)
        self.image.fill(0xffffffff)

    def test_language_discovery(self):
        self.assertEqual(ocr.list_languages(self.engine), ["eng", "spa"])

    def test_crop_and_command_contract(self):
        self.assertEqual(ocr.recognize(self.image, crop=(5, 5, 20, 10), engine=self.engine), "Hello Linux\n12345")
        with patch.dict(os.environ, {"TEST_OCR_PSM": "7"}):
            self.assertEqual(ocr.recognize(self.image, mode="Single line", crop=(0, 0, 20, 10), engine=self.engine), "Hello Linux 12345")

    def test_engine_failure(self):
        with patch.dict(os.environ, {"TEST_OCR_MODE": "fail"}), self.assertRaisesRegex(RuntimeError, "bad image"):
            ocr.recognize(self.image, engine=self.engine)

    def test_output_limit(self):
        with patch.dict(os.environ, {"TEST_OCR_MODE": "large"}), self.assertRaisesRegex(ValueError, "limit"):
            ocr.recognize(self.image, engine=self.engine)

    def test_timeout_reaps_process(self):
        self.check_reaped(TimeoutError, timeout=0.1)

    def test_cancel_reaps_process(self):
        cancel = threading.Event()
        timer = threading.Timer(0.15, cancel.set)
        timer.start()
        try:
            self.check_reaped(ocr.OcrCancelled, cancel=cancel)
        finally:
            timer.cancel()
            timer.join()

    def check_reaped(self, error, **options):
        popen = ocr.subprocess.Popen
        processes = []

        def start(*args, **kwargs):
            process = popen(*args, **kwargs)
            processes.append(process)
            return process

        with patch.dict(os.environ, {"TEST_OCR_MODE": "hang"}), patch.object(ocr.subprocess, "Popen", side_effect=start):
            with self.assertRaises(error):
                ocr.recognize(self.image, engine=self.engine, **options)
        self.assertTrue(processes)
        self.assertTrue(all(process.poll() is not None for process in processes))

    def test_invalid_language_and_layout(self):
        for language in ("../eng", "eng;cmd", "eng+spa", "--help", None):
            with self.subTest(language=language), self.assertRaises(ValueError):
                ocr.recognize(self.image, language=language, engine=self.engine)
        with self.assertRaises(ValueError):
            ocr.recognize(self.image, mode=[], engine=self.engine)
        with self.assertRaises(ValueError):
            ocr.recognize(self.image, language="fra", engine=self.engine)

    def test_load_image_preserves_source_and_rejects_symlink(self):
        path = self.root / "input.png"
        self.image.savev(str(path), "png", [], [])
        before = path.read_bytes()
        loaded = ocr.load_image(path)
        self.assertEqual((loaded.get_width(), loaded.get_height()), (40, 30))
        self.assertEqual(path.read_bytes(), before)
        link = self.root / "link.png"
        link.symlink_to(path)
        with self.assertRaises(ValueError):
            ocr.load_image(link)

    def test_rejects_oversized_image_header(self):
        path = self.root / "large.png"
        self.image.savev(str(path), "png", [], [])
        with patch.object(GdkPixbuf.Pixbuf, "get_file_info", return_value=(GdkPixbuf.Pixbuf.get_file_info(str(path))[0], 10000, 10000)):
            with self.assertRaisesRegex(ValueError, "megapixels"):
                ocr.load_image(path)

    def test_crop_mapping_reversed_and_clamped(self):
        self.assertEqual(ocr.crop_from_drag((90, 40), (10, 5), 1000, 500, 100, 50), (100, 50, 800, 350))
        self.assertEqual(ocr.crop_from_drag((-3, -4), (120, 60), 1000, 500, 100, 50), (0, 0, 1000, 500))
        for crop in ((0, 0, 0, 4), (-1, 0, 1, 1), (0, 0, 101, 50), (True, 0, 3, 3), "abcd"):
            with self.assertRaises(ValueError):
                ocr.validate_crop(crop, 100, 50)
        with self.assertRaises(ValueError):
            ocr.crop_from_drag((float("nan"), 0), (10, 10), 100, 50, 100, 50)

    def test_fuzz_image_headers(self):
        rng = random.Random(902)
        path = self.root / "input.png"
        for _ in range(200):
            data = rng.randbytes(rng.randrange(0, 1024))
            path.write_bytes(data)
            with self.assertRaises((ValueError, GLib.Error)):
                ocr.load_image(path)
            self.assertEqual(path.read_bytes(), data)

    def test_fuzz_crop_coordinates(self):
        rng = random.Random(903)
        for _ in range(500):
            first, second = [tuple(rng.uniform(-100, 200) for _ in range(2)) for _ in range(2)]
            try:
                x, y, w, h = ocr.crop_from_drag(first, second, 1000, 500, 100, 50)
                self.assertGreaterEqual(min(x, y), 0)
                self.assertGreater(min(w, h), 0)
                self.assertLessEqual(x + w, 1000)
                self.assertLessEqual(y + h, 500)
            except ValueError:
                pass

    def test_local_runtime_command_and_environment(self):
        runtime = self.root / "runtime"
        (runtime / "usr/share/tesseract-ocr/5/tessdata").mkdir(parents=True)
        engine = ocr.Engine(runtime / "usr/bin/tesseract", runtime)
        self.assertIn("--tessdata-dir", engine.command("--list-langs"))
        context = engine.environment()
        self.assertEqual(context["OMP_THREAD_LIMIT"], "2")
        self.assertNotIn("TESSDATA_PREFIX", context)
