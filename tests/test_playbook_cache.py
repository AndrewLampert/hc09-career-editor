import json
import os
import tempfile
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace

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


    def test_cache_is_invalid_when_manifest_is_malformed(self):
        self.write_stock_cache()
        with open(os.path.join(self.cache_dir, "playbook-source.json"), "w", encoding="utf-8") as f:
            f.write("{not json")
        self.assertFalse(self.app._playbook_names_cached(self.archive))

    def test_pppn_cache_is_reused_only_for_matching_archive(self):
        stamp = guiHC09.App._playbook_source_stamp(self.archive)
        path = os.path.join(self.cache_dir, guiHC09.PLAYBOOK_PLAYNAMES_FILE)
        with open(path, "w", encoding="utf-8") as f:
            f.write("BOKL,PLYL,PPPM\\n" + ("1,2,Example play\\n" * 20))
        with open(os.path.join(self.cache_dir, "pppn-source.json"), "w", encoding="utf-8") as f:
            json.dump(stamp, f)
        self.app.model = SimpleNamespace(run_bridge=Mock())
        self.assertTrue(self.app._ensure_book_play_names(self.archive))
        self.app.model.run_bridge.assert_not_called()

    def test_pppn_export_failure_removes_stale_csv_and_manifest(self):
        path = os.path.join(self.cache_dir, guiHC09.PLAYBOOK_PLAYNAMES_FILE)
        marker = os.path.join(self.cache_dir, "pppn-source.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write("stale data" * 40)
        with open(marker, "w", encoding="utf-8") as f:
            json.dump(guiHC09.App._playbook_source_stamp(self.archive), f)
        self.app.model = SimpleNamespace(run_bridge=Mock(side_effect=RuntimeError("export failed")))
        self.assertFalse(self.app._ensure_book_play_names(self.archive))
        self.assertFalse(os.path.exists(path))
        self.assertFalse(os.path.exists(marker))
        self.assertIn("export failed", self.app._book_names_failure)

    def test_pppn_export_writes_source_manifest_after_success(self):
        path = os.path.join(self.cache_dir, guiHC09.PLAYBOOK_PLAYNAMES_FILE)

        def export(args):
            with open(path, "w", encoding="utf-8") as f:
                f.write("BOKL,PLYL,PPPM\\n" + ("1,2,Example play\\n" * 20))
            return {"records": 20}

        self.app.model = SimpleNamespace(run_bridge=Mock(side_effect=export))
        self.assertTrue(self.app._ensure_book_play_names(self.archive))
        self.assertTrue(os.path.isfile(os.path.join(self.cache_dir, "pppn-source.json")))
        self.assertTrue(self.app._playbook_cache_matches(self.archive, "pppn-source.json"))

    def test_stock_export_validates_tables_before_stamping_cache(self):
        outputs = {
            "PLAB": "PBGI,BNAM\\n1,Example book\\n",
            "PBFM,SETL,PBPL": (
                "pbfm.csv", "PBFM,name\\n1,Example formation\\n",
                "setl.csv", "SETL,name\\n1,Example set\\n",
                "pbpl.csv", "SETL,PLYL,name\\n1,2,Example play\\n",
            ),
        }

        def export(args):
            tables = args[args.index("--tables") + 1]
            if tables == "PLAB":
                with open(os.path.join(self.cache_dir, "plab.csv"), "w", encoding="utf-8") as f:
                    f.write(outputs["PLAB"])
            elif tables == "PBFM,SETL,PBPL":
                values = outputs[tables]
                for name, content in zip(values[::2], values[1::2]):
                    with open(os.path.join(self.cache_dir, name), "w", encoding="utf-8") as f:
                        f.write(content)
            elif tables == "PPPN":
                path = os.path.join(self.cache_dir, guiHC09.PLAYBOOK_PLAYNAMES_FILE)
                with open(path, "w", encoding="utf-8") as f:
                    f.write("BOKL,PLYL,PPPM\\n" + ("1,2,Example play\\n" * 20))
                return {"records": 20}
            return {"records": 1}

        self.app.model = SimpleNamespace(run_bridge=Mock(side_effect=export))
        self.app._extract_playbook_names(self.archive)
        self.assertTrue(self.app._playbook_names_cached(self.archive))
        self.assertTrue(self.app._playbook_cache_matches(self.archive, "pppn-source.json"))

    def test_stock_export_failure_does_not_stamp_cache(self):
        def export(args):
            tables = args[args.index("--tables") + 1]
            if tables == "PLAB":
                with open(os.path.join(self.cache_dir, "plab.csv"), "w", encoding="utf-8") as f:
                    f.write("PBGI,BNAM\\n1,Example book\\n")
            elif tables == "PBFM,SETL,PBPL":
                for name in ("pbfm.csv", "setl.csv", "pbpl.csv"):
                    with open(os.path.join(self.cache_dir, name), "w", encoding="utf-8") as f:
                        f.write("wrong,columns\\n1,Example\\n")
            return {"records": 1}

        self.app.model = SimpleNamespace(run_bridge=Mock(side_effect=export))
        with self.assertRaisesRegex(RuntimeError, "missing rows or required columns"):
            self.app._extract_playbook_names(self.archive)
        self.assertFalse(os.path.exists(os.path.join(self.cache_dir, "playbook-source.json")))

if __name__ == "__main__":
    unittest.main()
