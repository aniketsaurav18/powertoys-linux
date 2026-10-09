# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.
import json
import random
import tempfile
import unittest
from pathlib import Path

from powertoys_linux.files import copy_template
from powertoys_linux import workspaces


class TemplateTests(unittest.TestCase):
    def test_copy_does_not_overwrite_and_preserves_template(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            source = folder / "source.txt"
            source.write_bytes(b"template\x00contents")
            target = copy_template(source, folder, "new.txt")
            self.assertEqual(target.read_bytes(), source.read_bytes())
            with self.assertRaises(FileExistsError):
                copy_template(source, folder, "new.txt")
            self.assertEqual(source.read_bytes(), b"template\x00contents")

    def test_fuzz_template_names(self):
        rng = random.Random(728)
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            source = folder / "source"
            source.write_text("original")
            for _ in range(200):
                name = "".join(rng.choices("abcé_/\x00", k=rng.randrange(0, 25)))
                try:
                    target = copy_template(source, folder, name)
                    self.assertEqual(target.read_text(), "original")
                    target.unlink()
                except (ValueError, FileExistsError):
                    pass
                self.assertEqual(source.read_text(), "original")


class WorkspaceTests(unittest.TestCase):
    def test_save_load_and_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config" / "workspaces.json"
            self.assertEqual(workspaces.load(path), {})
            groups = {"Development λ": ["editor.desktop", "terminal.desktop"]}
            workspaces.save(path, groups)
            self.assertEqual(workspaces.load(path), groups)
            workspaces.save(path, {})
            self.assertEqual(workspaces.load(path), {})
            self.assertEqual(list(path.parent.glob(".workspaces-*")), [])

    def test_reject_commands_and_invalid_configs(self):
        for groups in ({"": ["a.desktop"]}, {"Group": []}, {"Group": ["a.desktop", "a.desktop"]}, {"Group": ["/bin/sh"]}, {"Group": ["../evil.desktop"]}, {"Group": [123]}, []):
            with self.subTest(groups=groups), self.assertRaises(ValueError):
                workspaces.validate(groups)

    def test_preserve_invalid_existing_config(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "workspaces.json"
            path.write_text("broken data")
            with self.assertRaises(ValueError):
                workspaces.save(path, {"Group": ["app.desktop"]})
            self.assertEqual(path.read_text(), "broken data")

    def test_reject_oversize_save_before_creating_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "workspaces.json"
            groups = {f"Group {i}": [f"{j}_" + "a" * 240 + ".desktop" for j in range(50)] for i in range(100)}
            with self.assertRaises(ValueError):
                workspaces.save(path, groups)
            self.assertFalse(path.exists())

    def test_fuzz_workspace_config_bytes(self):
        rng = random.Random(729)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "workspaces.json"
            for _ in range(200):
                path.write_bytes(rng.randbytes(rng.randrange(0, 500)))
                with self.assertRaises(ValueError):
                    workspaces.load(path)
            for document in ({"version": 999, "groups": {}}, {"version": 1, "groups": None}, [], ["app.desktop"]):
                path.write_text(json.dumps(document))
                with self.assertRaises(ValueError):
                    workspaces.load(path)
