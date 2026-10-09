# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.
import base64
import os
import random
import struct
import string
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from powertoys_linux.core import apply_renames, rename_plan, resize_dimensions, transform_text
from powertoys_linux.images import resize_image
from gi.repository import GdkPixbuf, GLib


class RenameTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def file(self, name, data=b"original"):
        path = self.root / name
        path.write_bytes(data)
        return path

    def test_preview_apply_undo_preserves_content(self):
        files = [self.file("a photo.jpg"), self.file("a PHOTO.png")]
        plan = rename_plan(files, "photo", "picture")
        self.assertEqual([e.target.name for e in plan], ["a picture.jpg", "a picture.png"])
        self.assertTrue(all(p.exists() for p in files))
        undo = apply_renames(plan)
        self.assertTrue(all(not p.exists() for p in files))
        self.assertTrue(all(e.source.read_bytes() == b"original" for e in undo))
        apply_renames(undo)
        self.assertTrue(all(p.read_bytes() == b"original" for p in files))

    def test_literal_and_first_match(self):
        path = self.file("[x]-[x].txt")
        plan = rename_plan([path], "[x]", "\\1", all_matches=False)
        self.assertEqual(plan[0].target.name, "\\1-[x].txt")

    def test_extension_case_and_unchanged(self):
        path = self.file("file.TXT")
        self.assertEqual(rename_plan([path], "txt", "png"), [])
        self.assertEqual(rename_plan([path], "txt", "png", case_sensitive=True, stem_only=False), [])
        self.assertEqual(rename_plan([path], "txt", "png", stem_only=False)[0].target.name, "file.png")

    def test_collision_duplicate_and_symlink_are_rejected(self):
        path = self.file("cat.txt")
        target = self.file("dog.txt", b"keep")
        with self.assertRaises(FileExistsError):
            rename_plan([path], "cat", "dog")
        with self.assertRaises(ValueError):
            rename_plan([path, path], "cat", "bird")
        link = self.root / "link.txt"
        link.symlink_to(path)
        with self.assertRaises(ValueError):
            rename_plan([link], "link", "other")
        self.assertEqual(target.read_bytes(), b"keep")

    def test_duplicate_targets_rejected(self):
        files = [self.file("cat.txt"), self.file("CAT.txt")]
        with self.assertRaises(ValueError):
            rename_plan(files, "cat", "dog")

    def test_changed_source_or_new_target_after_preview(self):
        source = self.file("cat.txt")
        plan = rename_plan([source], "cat", "dog")
        source.write_bytes(b"changed")
        with self.assertRaises(ValueError):
            apply_renames(plan)
        plan = rename_plan([source], "cat", "dog")
        target = self.file("dog.txt", b"never overwrite")
        with self.assertRaises(FileExistsError):
            apply_renames(plan)
        self.assertEqual(target.read_bytes(), b"never overwrite")

    def test_link_failure_rolls_back_without_removing_sources(self):
        files = [self.file("cat1.txt"), self.file("cat2.txt")]
        plan = rename_plan(files, "cat", "dog")
        real_link = os.link
        def fail_second(source, target, **kwargs):
            if target.name == "dog2.txt":
                raise OSError("Simulated filesystem failure")
            real_link(source, target, **kwargs)
        with patch("powertoys_linux.core.os.link", side_effect=fail_second):
            with self.assertRaises(OSError):
                apply_renames(plan)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["cat1.txt", "cat2.txt"])

    def test_invalid_names(self):
        path = self.file("file")
        for search, replacement in (("", "x"), ("file", ""), ("file", ".."), ("file", "../escape"), ("file", "a\x00b"), ("file", "x" * 256)):
            with self.subTest(replacement=replacement), self.assertRaises(ValueError):
                rename_plan([path], search, replacement)

    def test_unlink_failure_keeps_all_file_data_at_new_names(self):
        files = [self.file("cat1.txt", b"one"), self.file("cat2.txt", b"two")]
        plan = rename_plan(files, "cat", "dog")
        real_unlink = Path.unlink
        def fail_second(path, **kwargs):
            if path.name == "cat2.txt":
                raise PermissionError("Simulated unlink failure")
            return real_unlink(path, **kwargs)
        with patch("pathlib.Path.unlink", new=fail_second):
            with self.assertRaisesRegex(OSError, "all files remain at their new names"):
                apply_renames(plan)
        self.assertEqual((self.root / "dog1.txt").read_bytes(), b"one")
        self.assertEqual((self.root / "dog2.txt").read_bytes(), b"two")
        self.assertEqual(files[1].read_bytes(), b"two")

    def test_fuzz_filename_input_and_rename_roundtrips(self):
        rng = random.Random(723)
        alphabet = string.ascii_letters + string.digits + " []-_.éλ"
        for index in range(400):
            name = f"item{index}_" + "".join(rng.choices(alphabet, k=rng.randrange(1, 50))) + ".txt"
            source = self.file(name, os.fsencode(name))
            replacement = "".join(rng.choices(alphabet + "/\x00", k=rng.randrange(0, 25)))
            try:
                plan = rename_plan([source], "item", replacement)
            except ValueError:
                self.assertTrue(source.exists())
                source.unlink()
                continue
            before = source.read_bytes()
            undo = apply_renames(plan)
            apply_renames(undo)
            self.assertEqual(source.read_bytes(), before)
            source.unlink()


class TextTests(unittest.TestCase):
    def test_json_and_base64(self):
        self.assertIn('"a": 1', transform_text('{"a":1}', "Format JSON"))
        text = "Hello λ\n🦊"
        self.assertEqual(transform_text(transform_text(text, "Base64 encode"), "Base64 decode"), text)

    def test_url_roundtrip_and_trim(self):
        text = "file:///a b?x=λ&y=1"
        self.assertEqual(transform_text(transform_text(text, "URL encode"), "URL decode"), text)
        self.assertEqual(transform_text(" a \n b ", "Trim lines"), "a\nb")

    def test_bad_input(self):
        for text, action in (("not json", "Format JSON"), ("!!!!", "Base64 decode"), (base64.b64encode(b"\xff").decode(), "Base64 decode"), ("x", "unknown"), ("x" * 2_000_001, "Uppercase")):
            with self.subTest(action=action), self.assertRaises((ValueError, UnicodeError)):
                transform_text(text, action)

    def test_fuzz_unicode_text(self):
        rng = random.Random(724)
        for _ in range(500):
            text = "".join(chr(rng.choice((rng.randrange(0, 0xD800), rng.randrange(0xE000, 0x110000)))) for _ in range(rng.randrange(0, 80)))
            for encode, decode in (("Base64 encode", "Base64 decode"), ("URL encode", "URL decode")):
                self.assertEqual(transform_text(transform_text(text, encode), decode), text)
            try:
                transform_text(text, "Format JSON")
            except (ValueError, UnicodeError):
                pass


class ImageTests(unittest.TestCase):
    def test_dimensions(self):
        self.assertEqual(resize_dimensions(200, 100, 100, 100), (100, 50))
        self.assertEqual(resize_dimensions(100, 200, 100, 100), (50, 100))
        self.assertEqual(resize_dimensions(10, 20, 100, 100), (10, 20))
        self.assertEqual(resize_dimensions(10, 20, 100, 100, False), (50, 100))
        with self.assertRaises(ValueError):
            resize_dimensions(0, 100, 100, 100)

    def test_image_output_and_existing_copy(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "image.png"
            pixbuf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, 200, 100)
            pixbuf.fill(0xff000080)
            pixbuf.savev(str(path), "png", [], [])
            original = path.read_bytes()
            first = resize_image(path, 100, 100)
            second = resize_image(path, 50, 50)
            self.assertNotEqual(first, second)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(GdkPixbuf.Pixbuf.get_file_info(str(first))[1:], (100, 50))
            self.assertEqual(GdkPixbuf.Pixbuf.get_file_info(str(second))[1:], (50, 25))
            output = GdkPixbuf.Pixbuf.new_from_file(str(first))
            self.assertTrue(output.get_has_alpha())

    def test_fuzz_invalid_image_headers(self):
        rng = random.Random(725)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bad.png"
            for _ in range(150):
                data = rng.randbytes(rng.randrange(0, 512))
                path.write_bytes(data)
                with self.assertRaises((ValueError, GLib.Error)):
                    resize_image(path, 100, 100)
                self.assertEqual(path.read_bytes(), data)
            self.assertEqual(len(list(Path(folder).iterdir())), 1)

    def test_jpeg_exif_orientation_is_applied_before_fitting(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "portrait.jpg"
            pixbuf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, 200, 100)
            pixbuf.fill(0xff0000ff)
            success, jpeg = pixbuf.save_to_bufferv("jpeg", [], [])
            self.assertTrue(success)
            # Minimal little-endian EXIF IFD: orientation tag = 6 (90 degrees).
            tiff = b"II" + struct.pack("<HIH", 42, 8, 1)
            tiff += struct.pack("<HHIHHI", 0x0112, 3, 1, 6, 0, 0)
            exif = b"Exif\x00\x00" + tiff
            path.write_bytes(jpeg[:2] + b"\xff\xe1" + struct.pack(">H", len(exif) + 2) + exif + jpeg[2:])
            target = resize_image(path, 100, 100)
            self.assertEqual(GdkPixbuf.Pixbuf.get_file_info(str(target))[1:], (50, 100))


if __name__ == "__main__":
    unittest.main()
