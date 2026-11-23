import csv
import os
import tempfile
import unittest

import hc09_gamefiles as GF


def write_rows(folder, base, table, rows):
    path = os.path.join(folder, f"{table.lower()}_{base}.csv")
    fields = list(rows[0]) if rows else []
    with open(path, "w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def sample_changes(**overrides):
    changes = {
        "plyl": 200,
        "base": 200,
        "setl": 50,
        "name": None,
        "plys": {0: {"PSAL": 2}},
        "play": {},
        "plpd": {},
        "plrd": {},
        "plcm": {},
        "setp": {},
        "setg": {},
        "default_group": None,
        "shared_with": [],
        "playbooks": 1,
        "target_name": "Base Play",
    }
    changes.update(overrides)
    return changes


class GameFileTargetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.cache = self.temp.name
        self.master = {
            "ast": r"C:\\game\\qkl_boot.ast",
            "file": "qkl_boot.ast",
            "index": 40,
            "start": 4096,
            "size": 8192,
            "base": "boot_40",
            "tables": {"PLYS": 11, "PBPL": 1},
        }
        write_rows(self.cache, "boot_40", "PBPL", [{
            "PLYL": "200", "SETL": "50", "PLYT": "1", "PLF_": "0",
            "vpos": "0", "risk": "0", "motn": "0", "name": "Base Play",
        }])
        write_rows(self.cache, "boot_40", "PLYS", [
            {"PLYL": "200", "poso": str(pos), "PSAL": "1", "ARTL": "0", "PLRR": str(pos)}
            for pos in range(11)
        ])
        write_rows(self.cache, "boot_40", "PSLO", [
            {"PSAL": "1"}, {"PSAL": "2"},
        ])
        write_rows(self.cache, "boot_40", "ARTO", [{"ARTL": "0"}])

    def tearDown(self):
        self.temp.cleanup()

    def test_assignment_change_targets_master_row_with_expected_old_value(self):
        targets, report = GF.targets_for([self.master], self.cache, sample_changes())

        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0]["index"], 40)
        edit = next(e for e in targets[0]["edits"] if e["table"] == "PLYS")
        self.assertEqual(edit["match"], {"PLYL": 200, "poso": 0})
        self.assertEqual(edit["expect"], {"PSAL": 1})
        self.assertEqual(edit["set"], {"PSAL": 2})
        self.assertTrue(any("qkl_boot.ast #40" in item[0] for item in report))

    def test_assignment_is_not_written_when_master_lacks_the_requested_step_list(self):
        write_rows(self.cache, "boot_40", "PSLO", [{"PSAL": "1"}])

        targets, report = GF.targets_for([self.master], self.cache, sample_changes())

        self.assertEqual(targets, [])
        self.assertTrue(any("not written" in item[0] and "slot 0" in item[0] for item in report))

    def test_missing_play_in_master_is_rejected(self):
        write_rows(self.cache, "boot_40", "PBPL", [{
            "PLYL": "201", "SETL": "50", "PLYT": "1", "PLF_": "0",
            "vpos": "0", "risk": "0", "motn": "0", "name": "Other Play",
        }])

        with self.assertRaisesRegex(ValueError, "not in the master play database"):
            GF.targets_for([self.master], self.cache, sample_changes())

    def test_compact_copy_without_assignment_columns_is_not_given_a_bad_edit(self):
        compact = {
            "ast": r"C:\\game\\qkl_boot.ast",
            "file": "qkl_boot.ast",
            "index": 42,
            "start": 20000,
            "size": 4096,
            "base": "boot_42",
            "tables": {"PLYS": 1},
        }
        write_rows(self.cache, "boot_42", "PBPL", [{
            "PLYL": "200", "SETL": "50", "PLYT": "1", "PLF_": "0",
            "vpos": "0", "risk": "0", "motn": "0", "name": "Base Play",
        }])
        write_rows(self.cache, "boot_42", "PLYS", [{"PLYL": "200", "poso": "0"}])

        targets, _report = GF.targets_for(
            [self.master, compact], self.cache, sample_changes()
        )

        compact_targets = [target for target in targets if target["index"] == 42]
        self.assertEqual(compact_targets, [])
        self.assertEqual([target["index"] for target in targets], [40])


if __name__ == "__main__":
    unittest.main()
