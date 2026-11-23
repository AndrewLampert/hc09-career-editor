import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

import check_save


class CheckSaveReportTests(unittest.TestCase):
    def test_career_judge_distinguishes_missing_empty_and_populated_tables(self):
        rows = check_save.judge("career", {
            "DRPK": 448, "PGPL": 0, "PGSL": 1790, "PGSS": 1763,
        })
        by_table = {row["table"]: row for row in rows}
        self.assertEqual(by_table["DRPK"]["status"], "ok")
        self.assertEqual(by_table["PGPL"]["status"], "empty")
        self.assertEqual(by_table["PGSL"]["status"], "ok")
        self.assertEqual(by_table["PGFM"]["status"], "missing")
        self.assertEqual(by_table["PGFM"]["rows"], 0)

    def test_profile_judge_checks_each_custom_play_table(self):
        rows = check_save.judge("profile", {"PBPL": 2, "SETL": 1, "PLYS": 0})
        by_table = {row["table"]: row for row in rows}
        self.assertEqual(set(by_table), set(check_save.PROFILE_TABLES[i][0]
                                             for i in range(len(check_save.PROFILE_TABLES))))
        self.assertEqual(by_table["PBPL"]["status"], "ok")
        self.assertEqual(by_table["SETL"]["status"], "ok")
        self.assertEqual(by_table["PLYS"]["status"], "empty")
        self.assertEqual(by_table["PLCM"]["status"], "missing")

    def test_healthy_career_verdict_does_not_report_a_problem(self):
        counts = {code: 1 for code, *_rest in check_save.CAREER_TABLES}
        self.assertEqual(
            check_save.verdict("career", check_save.judge("career", counts)),
            ["Everything the Draft Picks and Playbooks tabs need is in this save."],
        )

    def test_career_verdict_names_missing_playbook_tables(self):
        rows = check_save.judge("career", {"DRPK": 448, "PGPL": 10, "PGSL": 10})
        verdict = "\n".join(check_save.verdict("career", rows))
        self.assertIn("PGSS (missing)", verdict)
        self.assertIn("PGFM (missing)", verdict)
        self.assertIn("The save, not the editor, lacks them.", verdict)

    def test_career_verdict_explains_empty_playbook_table(self):
        rows = check_save.judge("career", {
            "DRPK": 448, "PGPL": 0, "PGSL": 1, "PGSS": 1, "PGFM": 1,
        })
        verdict = "\n".join(check_save.verdict("career", rows))
        self.assertIn("PGPL (empty)", verdict)
        self.assertIn("cannot give the Playbooks tab", verdict)

    def test_profile_verdict_does_not_confuse_empty_custom_tables_with_missing(self):
        rows = check_save.judge("profile", {"PBPL": 0, "SETL": 0})
        verdict = "\n".join(check_save.verdict("profile", rows))
        self.assertIn("None of its custom play tables has rows", verdict)

    def test_saves_in_returns_a_single_file_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "career.usr")
            with open(path, "wb") as f:
                f.write(b"save")
            self.assertEqual(check_save.saves_in(path), [path])

    def test_saves_in_prefers_a_package_files_same_name(self):
        with tempfile.TemporaryDirectory() as folder:
            package = os.path.join(folder, "career")
            os.makedirs(package)
            expected = os.path.join(package, "career")
            other = os.path.join(package, "other.usr")
            for path in (expected, other):
                with open(path, "wb") as f:
                    f.write(b"save")
            self.assertEqual(check_save.saves_in(package), [expected])

    def test_table_counts_parses_bridge_inspection_output(self):
        completed = SimpleNamespace(
            returncode=0,
            stdout="Database tables:\n  PGPL: 9133 records\n  PGSL: 1790 records\n",
            stderr="",
        )
        with mock.patch.object(check_save, "find_node", return_value="node"), \
             mock.patch.object(check_save.os.path, "isfile", return_value=True), \
             mock.patch.object(check_save.subprocess, "run", return_value=completed):
            self.assertEqual(
                check_save.table_counts("career.usr"),
                {"PGPL": 9133, "PGSL": 1790},
            )

    def test_table_counts_reports_bridge_failure_as_check_error(self):
        completed = SimpleNamespace(
            returncode=1, stdout="", stderr="not a valid save\n at bridge.js:10",
        )
        with mock.patch.object(check_save, "find_node", return_value="node"), \
             mock.patch.object(check_save.os.path, "isfile", return_value=True), \
             mock.patch.object(check_save.subprocess, "run", return_value=completed):
            with self.assertRaisesRegex(check_save.CheckError, "not a valid save"):
                check_save.table_counts("broken.usr")


    def test_playbook_link_diagnostics_reports_clean_links(self):
        with tempfile.TemporaryDirectory() as folder:
            for name, rows in {
                "pgpl": "BOKL,SETL,PLYL\n7,471,6709\n",
                "pgss": "BOKL,SETL\n7,471\n",
                "pgsl": "BOKL,SETL,PBFM\n7,471,26\n",
                "pgfm": "BOKL,PBFM\n7,26\n",
            }.items():
                with open(os.path.join(folder, name + ".csv"), "w", encoding="utf-8") as f:
                    f.write(rows)
            completed = SimpleNamespace(returncode=0, stdout="", stderr="")
            with mock.patch.object(check_save.tempfile, "TemporaryDirectory") as tempdir, \
                 mock.patch.object(check_save.subprocess, "run", return_value=completed):
                tempdir.return_value.__enter__.return_value = folder
                tempdir.return_value.__exit__.return_value = False
                lines = check_save.playbook_link_diagnostics("career.usr",
                    {"PGPL": 1, "PGSL": 1, "PGSS": 1, "PGFM": 1}, "node")
            self.assertIn("no missing PGPL-to-PGSL or PGSL-to-PGFM links", lines[0])

    def test_playbook_link_diagnostics_reports_missing_link(self):
        with tempfile.TemporaryDirectory() as folder:
            for name, rows in {
                "pgpl": "BOKL,SETL,PLYL\n7,471,6709\n",
                "pgss": "BOKL,SETL\n7,471\n",
                "pgsl": "BOKL,SETL,PBFM\n",
                "pgfm": "BOKL,PBFM\n7,26\n",
            }.items():
                with open(os.path.join(folder, name + ".csv"), "w", encoding="utf-8") as f:
                    f.write(rows)
            completed = SimpleNamespace(returncode=0, stdout="", stderr="")
            with mock.patch.object(check_save.tempfile, "TemporaryDirectory") as tempdir, \
                 mock.patch.object(check_save.subprocess, "run", return_value=completed):
                tempdir.return_value.__enter__.return_value = folder
                tempdir.return_value.__exit__.return_value = False
                lines = check_save.playbook_link_diagnostics("career.usr",
                    {"PGPL": 1, "PGSL": 1, "PGSS": 1, "PGFM": 1}, "node")
            self.assertIn("1 broken reference(s) found", lines[0])
            self.assertIn("Book 7, set 471", lines[1])


if __name__ == "__main__":
    unittest.main()
