"""Protect unrelated files when publishing documentation."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "docs_publisher", Path(__file__).parents[1] / "scripts" / "docs.py"
)
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)


class PublishingTests(unittest.TestCase):
    def test_repeat_publish_removes_stale_owned_files_only(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source"
            target = Path(folder) / "target"
            source.mkdir()
            (source / "old.html").write_text("old")
            publisher.sync_site(source, target)
            (target / "unrelated.txt").write_text("keep")
            (source / "old.html").unlink()
            (source / "index.html").write_text("new")
            publisher.sync_site(source, target)
            self.assertFalse((target / "old.html").exists())
            self.assertEqual((target / "unrelated.txt").read_text(), "keep")
            self.assertEqual((target / "index.html").read_text(), "new")

    def test_refuses_existing_unowned_file(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source"
            target = Path(folder) / "target"
            source.mkdir()
            target.mkdir()
            (source / "index.html").write_text("generated")
            (target / "index.html").write_text("existing")
            with self.assertRaises(ValueError):
                publisher.sync_site(source, target)
            self.assertEqual((target / "index.html").read_text(), "existing")

    def test_rejects_manifest_path_outside_destination(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source"
            target = Path(folder) / "target"
            source.mkdir()
            target.mkdir()
            outside = Path(folder) / "keep.txt"
            outside.write_text("keep")
            (target / publisher.MANIFEST).write_text(json.dumps(["../keep.txt"]))
            with self.assertRaises(ValueError):
                publisher.sync_site(source, target)
            self.assertTrue(outside.exists())
