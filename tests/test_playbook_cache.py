import json
import os
import tempfile
import unittest
from unittest.mock import patch

import guiHC09


class PlaybookCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cache_dir = os.path.join(self.temp.name, "cache")
        os.makedirs(self.cache_dir)
        self.archive = os.path.join(self.temp.name, "qkl_boot.ast")
        with open(self.archive, "wb") as f:
            f.write(b"test archive revision A")
        self.app = guiHC09.App.__new__(guiHC09.App)
        self.app.ui_prefs = {"boot_ast_path": self.archive}
        self.cache_patch = patch.object(guiHC09, "PLAYBOOK_CACHE_DIR", self.cache_dir)
        self.cache_patch.start()
        self.addCleanup(self.cache_patch.stop)

    def write_stock_cache(self, stamp=None):
        for name in guiHC09.PLAYBOOK_NAME_FILES:
            with open(os.path.join(self.cache_dir, name), "w", encoding="utf-8") as f:
                f.write("header\nrow\n")
        if stamp is not None:
            with open(os.path.join(self.cache_dir, "playbook-source.json"), "w", encoding="utf-8") as f:
                json.dump(stamp, f)

    def test_cache_is_valid_for_same_archive_revision(self):
        stamp = guiHC09.App._playbook_source_stamp(self.archive)
        self.write_stock_cache(stamp)
        self.assertTrue(self.app._playbook_names_cached(self.archive))

    def test_cache_is_invalid_for_different_archive_path(self):
        stamp = guiHC09.App._playbook_source_stamp(self.archive)
        self.write_stock_cache(stamp)
        other = os.path.join(self.temp.name, "other_qkl_boot.ast")
        with open(other, "wb") as f:
            f.write(b"test archive revision A")
        self.assertFalse(self.app._playbook_names_cached(other))

    def test_cache_is_invalid_after_archive_changes(self):
        stamp = guiHC09.App._playbook_source_stamp(self.archive)
        self.write_stock_cache(stamp)
        with open(self.archive, "ab") as f:
            f.write(b" revision B")
        self.assertFalse(self.app._playbook_names_cached(self.archive))

    def test_cache_is_invalid_without_manifest(self):
        self.write_stock_cache()
        self.assertFalse(self.app._playbook_names_cached(self.archive))

    def test_cache_is_invalid_when_any_required_csv_is_missing(self):
        stamp = guiHC09.App._playbook_source_stamp(self.archive)
        self.write_stock_cache(stamp)
        os.remove(os.path.join(self.cache_dir, "pbpl.csv"))
        self.assertFalse(self.app._playbook_names_cached(self.archive))


if __name__ == "__main__":
    unittest.main()
