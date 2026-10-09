# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.
import os
import random
import tempfile
import unittest
from pathlib import Path

from powertoys_linux.desktop import color_formats
from powertoys_linux.files import open_file_processes, text_preview


class FileTests(unittest.TestCase):
    def test_text_preview_and_truncation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "text.txt"
            path.write_text("Hello λ")
            self.assertEqual(text_preview(path), "Hello λ")
            path.write_bytes(b"a" * 199999 + "λ".encode())
            self.assertIn("Preview truncated", text_preview(path))
            path.write_bytes(b"a\x00b")
            with self.assertRaises(ValueError):
                text_preview(path)

    def test_open_descriptor_in_this_process(self):
        with tempfile.NamedTemporaryFile() as stream:
            matches, skipped = open_file_processes(stream.name)
            self.assertIn(os.getpid(), [pid for pid, name in matches])
            self.assertGreaterEqual(skipped, 0)

    def test_proc_fixture_deduplicates_descriptors(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "target"
            target.write_text("file")
            fd = root / "proc" / "123" / "fd"
            fd.mkdir(parents=True)
            (fd / "1").symlink_to(target)
            (fd / "2").symlink_to(target)
            (fd.parent / "comm").write_text("example\n")
            matches, skipped = open_file_processes(target, root / "proc")
            self.assertEqual(matches, [(123, "example")])
            self.assertEqual(skipped, 0)

    def test_fuzz_preview_bytes(self):
        rng = random.Random(726)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input"
            for _ in range(200):
                data = rng.randbytes(rng.randrange(0, 2000))
                path.write_bytes(data)
                try:
                    value = text_preview(path)
                    self.assertEqual(value.encode("utf-8"), data)
                except ValueError:
                    pass
                self.assertEqual(path.read_bytes(), data)


class ColorTests(unittest.TestCase):
    def test_color_formats(self):
        self.assertEqual(color_formats((1, 0, 0.5)), ("#FF0080", "rgb(255, 0, 128)"))
        self.assertEqual(color_formats((0, 0, 0))[0], "#000000")
        self.assertEqual(color_formats((1, 1, 1))[0], "#FFFFFF")

    def test_invalid_components(self):
        for color in ((0, 0), (float("nan"), 0, 0), (float("inf"), 0, 0), (-0.1, 0, 0), (1.01, 0, 0)):
            with self.subTest(color=color), self.assertRaises(ValueError):
                color_formats(color)

    def test_fuzz_color_components(self):
        rng = random.Random(727)
        for _ in range(300):
            color = tuple(rng.uniform(-2, 2) for _ in range(3))
            if all(0 <= c <= 1 for c in color):
                self.assertEqual(len(color_formats(color)[0]), 7)
            else:
                with self.assertRaises(ValueError):
                    color_formats(color)
