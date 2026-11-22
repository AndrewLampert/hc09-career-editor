import os
import tempfile
import unittest
from unittest import mock

import guiHC09


class FakeModel:
    def __init__(self):
        self.calls = []

    def run_bridge(self, args):
        self.calls.append(list(args))
        return {"results": [{"table": "PGPL", "status": "ok", "warnings": []}]}


class SaveBackupSafetyTests(unittest.TestCase):
    def setUp(self):
        guiHC09._OPENED_COPIES.clear()

    def tearDown(self):
        guiHC09._OPENED_COPIES.clear()

    def test_backup_failure_aborts_before_the_bridge_can_write(self):
        with tempfile.TemporaryDirectory() as folder:
            db = os.path.join(folder, "career.db")
            with open(db, "wb") as f:
                f.write(b"original-save")
            model = FakeModel()
            with mock.patch.object(guiHC09, "backup_save",
                                   side_effect=OSError("disk is full")):
                with self.assertRaisesRegex(OSError, "disk is full"):
                    guiHC09.write_tables_in_save(
                        model, db, folder, ["PGPL"],
                    )
            self.assertEqual(model.calls, [])
            with open(db, "rb") as f:
                self.assertEqual(f.read(), b"original-save")

    def test_failed_rollback_reports_where_the_recovery_copy_is(self):
        with tempfile.TemporaryDirectory() as folder:
            db = os.path.join(folder, "career.db")
            backup = os.path.join(folder, "career.bak")
            with open(db, "wb") as f:
                f.write(b"original-save")
            with open(backup, "wb") as f:
                f.write(b"original-save")
            model = FakeModel()

            with mock.patch.object(guiHC09, "backup_save", return_value=backup), \
                 mock.patch.object(guiHC09, "restore_backup",
                                   side_effect=RuntimeError("restore disk error")):
                with self.assertRaisesRegex(RuntimeError, "restore disk error"):
                    guiHC09.write_tables_in_save(
                        model, db, folder, ["PGPL"],
                    )
            self.assertEqual(model.calls[0][0], "import")


if __name__ == "__main__":
    unittest.main()
