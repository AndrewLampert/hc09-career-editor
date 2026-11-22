import csv
import json
import os
import tempfile
import unittest
from unittest import mock

import guiHC09


class FakeBridgeModel:
    def __init__(self, handler=None):
        self.handler = handler
        self.calls = []

    def run_bridge(self, args):
        self.calls.append(list(args))
        if self.handler:
            return self.handler(args)
        return {"results": [{"table": t, "status": "ok", "warnings": []}
                            for t in args[args.index("--tables") + 1].split(",")]}


def bare_app(model=None):
    app = guiHC09.App.__new__(guiHC09.App)
    app.model = model or FakeBridgeModel()
    return app


class CustomPlaySaveWriteTests(unittest.TestCase):
    def test_append_and_import_writes_existing_then_new_rows_in_header_order(self):
        with tempfile.TemporaryDirectory() as folder:
            db = os.path.join(folder, "career.db")
            headers = ["BOKL", "SETL", "PLYL", "PLTP"]
            old = [{"BOKL": 7, "SETL": 10, "PLYL": 20, "PLTP": 1}]
            added = [{"BOKL": 7, "SETL": 11, "PLYL": 21, "PLTP": 1}]
            captured = {}

            def bridge(args):
                captured["args"] = list(args)
                csv_path = os.path.join(args[args.index("--in") + 1], "pgpl.csv")
                with open(csv_path, newline="", encoding="utf-8") as f:
                    captured["rows"] = list(csv.reader(f))
                return {"results": [{"table": "PGPL", "status": "ok", "warnings": []}]}

            app = bare_app(FakeBridgeModel(bridge))
            result = app._append_and_import(
                db, {"PGPL": added}, {"PGPL": (headers, old)}
            )

            self.assertEqual(captured["rows"], [
                headers, ["7", "10", "20", "1"], ["7", "11", "21", "1"]
            ])
            self.assertIn("--allow-append", captured["args"])
            self.assertEqual(captured["args"][captured["args"].index("--allow-append") + 1], "PGPL")
            self.assertEqual(result["results"][0]["status"], "ok")

    def test_append_and_import_rejects_new_row_missing_a_column_before_bridge(self):
        app = bare_app()
        with tempfile.TemporaryDirectory() as folder:
            db = os.path.join(folder, "career.db")
            with self.assertRaisesRegex(RuntimeError, "lacks the columns"):
                app._append_and_import(
                    db, {"PGPL": [{"BOKL": 7}]},
                    {"PGPL": (["BOKL", "SETL"], [{"BOKL": 1, "SETL": 2}])},
                )
        self.assertEqual(app.model.calls, [])

    def test_append_and_import_rejects_bridge_warnings(self):
        app = bare_app(FakeBridgeModel(lambda _args: {
            "results": [{"table": "PGPL", "status": "ok", "warnings": ["row 1: wrong id"]}]
        }))
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(RuntimeError, "did not write every table"):
                app._append_and_import(
                    os.path.join(folder, "career.db"),
                    {"PGPL": [{"BOKL": 7, "SETL": 2}]},
                    {"PGPL": (["BOKL", "SETL"], [{"BOKL": 1, "SETL": 1}])},
                )

    def test_replace_and_import_writes_only_replacement_rows_without_append(self):
        captured = {}
        def bridge(args):
            captured["args"] = list(args)
            with open(os.path.join(args[args.index("--in") + 1], "pgpl.csv"),
                      newline="", encoding="utf-8") as f:
                captured["rows"] = list(csv.reader(f))
            return {"results": [{"table": "PGPL", "status": "ok", "warnings": []}]}

        app = bare_app(FakeBridgeModel(bridge))
        with tempfile.TemporaryDirectory() as folder:
            app._replace_and_import(
                os.path.join(folder, "profile.db"),
                {"PGPL": [{"BOKL": 7, "SETL": 3}]},
                {"PGPL": (["BOKL", "SETL"], [{"BOKL": 7, "SETL": 2}])},
            )
        self.assertEqual(captured["rows"], [["BOKL", "SETL"], ["7", "3"]])
        self.assertNotIn("--allow-append", captured["args"])
        self.assertNotIn("--allow-shrink", captured["args"])

    def test_copy_saves_for_custom_play_never_changes_the_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            profile = os.path.join(folder, "profile", "USR-DATA")
            career = os.path.join(folder, "career", "USR-DATA")
            os.makedirs(os.path.dirname(profile))
            os.makedirs(os.path.dirname(career))
            with open(profile, "wb") as f:
                f.write(b"profile-original")
            with open(career, "wb") as f:
                f.write(b"career-original")

            app = bare_app()
            out_profile, out_career = app._copy_saves_for_custom_play(
                profile, career, os.path.join(folder, "output")
            )

            with open(profile, "rb") as f:
                self.assertEqual(f.read(), b"profile-original")
            with open(career, "rb") as f:
                self.assertEqual(f.read(), b"career-original")
            with open(out_profile, "rb") as f:
                self.assertEqual(f.read(), b"profile-original")
            with open(out_career, "rb") as f:
                self.assertEqual(f.read(), b"career-original")

    def test_install_custom_play_replaces_both_files_and_keeps_preinstall_backups(self):
        with tempfile.TemporaryDirectory() as folder:
            profile = os.path.join(folder, "live", "profile.usr")
            career = os.path.join(folder, "live", "career.usr")
            new_profile = os.path.join(folder, "made", "profile.usr")
            new_career = os.path.join(folder, "made", "career.usr")
            for path, data in ((profile, b"profile-old"), (career, b"career-old"),
                               (new_profile, b"profile-new"), (new_career, b"career-new")):
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "wb") as f:
                    f.write(data)

            app = bare_app()
            app.TEST_BACKUP_DIR = os.path.join(folder, "backups")
            app.install_blocker = lambda _career: None
            app._reload_if_open = lambda _career: None
            backup = app.install_custom_play(
                {"profile": new_profile, "career": new_career, "name": "Test Play"},
                profile, career,
            )

            with open(profile, "rb") as f:
                self.assertEqual(f.read(), b"profile-new")
            with open(career, "rb") as f:
                self.assertEqual(f.read(), b"career-new")
            with open(os.path.join(backup, "profile", "USR-DATA"), "rb") as f:
                self.assertEqual(f.read(), b"profile-old")
            with open(os.path.join(backup, "career", "USR-DATA"), "rb") as f:
                self.assertEqual(f.read(), b"career-old")
            with open(os.path.join(backup, "info.json"), encoding="utf-8") as f:
                self.assertEqual(json.load(f)["play"], "Test Play")
            self.assertFalse(os.path.exists(profile + ".hc09-new"))
            self.assertFalse(os.path.exists(career + ".hc09-new"))

    def test_install_custom_play_rolls_back_first_file_if_second_replace_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            profile = os.path.join(folder, "live", "profile.usr")
            career = os.path.join(folder, "live", "career.usr")
            new_profile = os.path.join(folder, "made", "profile.usr")
            new_career = os.path.join(folder, "made", "career.usr")
            for path, data in ((profile, b"profile-old"), (career, b"career-old"),
                               (new_profile, b"profile-new"), (new_career, b"career-new")):
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "wb") as f:
                    f.write(data)

            app = bare_app()
            app.TEST_BACKUP_DIR = os.path.join(folder, "backups")
            app.install_blocker = lambda _career: None
            app._reload_if_open = lambda _career: None
            real_replace = os.replace
            calls = {"n": 0}

            def fail_second(src, dst):
                calls["n"] += 1
                if calls["n"] == 2:
                    raise OSError("simulated second-file failure")
                return real_replace(src, dst)

            with mock.patch.object(guiHC09.os, "replace", side_effect=fail_second):
                with self.assertRaisesRegex(RuntimeError, "put back"):
                    app.install_custom_play(
                        {"profile": new_profile, "career": new_career},
                        profile, career,
                    )

            with open(profile, "rb") as f:
                self.assertEqual(f.read(), b"profile-old")
            with open(career, "rb") as f:
                self.assertEqual(f.read(), b"career-old")
            self.assertFalse(os.path.exists(profile + ".hc09-new"))
            self.assertFalse(os.path.exists(career + ".hc09-new"))

    def test_install_custom_play_rejects_files_made_from_another_save_pair(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = []
            for name in ("profile", "career", "new_profile", "new_career"):
                p = os.path.join(folder, name)
                with open(p, "wb") as f:
                    f.write(name.encode())
                paths.append(p)
            profile, career, new_profile, new_career = paths
            app = bare_app()
            app.TEST_BACKUP_DIR = os.path.join(folder, "backups")
            app.install_blocker = lambda _career: None
            with self.assertRaisesRegex(RuntimeError, "made from another profile"):
                app.install_custom_play(
                    {"profile": new_profile, "career": new_career,
                     "made_sources": {"profile": os.path.join(folder, "other-profile")}},
                    profile, career,
                )
            self.assertFalse(os.path.exists(app.TEST_BACKUP_DIR))


if __name__ == "__main__":
    unittest.main()
