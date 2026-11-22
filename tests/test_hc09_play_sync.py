import copy
import unittest

import hc09_plays
from test_hc09_play_creation import make_library


def text_rows(rows):
    return {
        table: [{key: str(value) for key, value in row.items()} for row in items]
        for table, items in rows.items()
    }


def make_profile():
    lib = make_library()
    built, summary = hc09_plays.build_custom_play(
        lib, 200, "Saved Play", {}, profile={}
    )
    profile = text_rows(built)
    # Include the optional type-specific rows so synchronization covers every definition table.
    profile["PLPD"] = [{
        "PLYL": str(summary["plyl"]), "rcv1": "0", "per1": "50",
        "rcv2": "1", "per2": "25", "rcv3": "2", "per3": "15",
        "rcv4": "3", "per4": "5", "rcv5": "4", "per5": "5",
    }]
    profile["PLRD"] = [{"PLYL": str(summary["plyl"]), "hole": "3"}]
    profile["PLCM"] = [{"PLYL": str(summary["plyl"]), "decision": "1"}]
    return lib, profile, summary


class CustomPlaySyncTests(unittest.TestCase):
    def test_profile_custom_play_survives_mount_detail_and_remount(self):
        lib, profile, summary = make_profile()

        mounted = lib.mount_custom(profile)
        self.assertEqual(len(mounted), 1)
        detail = lib.detail(mounted[0])
        self.assertEqual(detail["play"]["name"], "Saved Play")
        self.assertEqual(len(detail["set"]["slots"]), 11)
        self.assertEqual(len(detail["slots"]), 11)

        lib.unmount_custom()
        self.assertNotIn(mounted[0], lib.plays)
        mounted_again = lib.mount_custom(profile)
        self.assertEqual(mounted_again, mounted)
        self.assertEqual(lib.detail(mounted_again[0])["play"]["name"], "Saved Play")
        self.assertEqual(summary["plyl"], hc09_plays.CUSTOM_OFFSETS["PLYL"] * 0 + summary["plyl"])

    def test_sync_updates_profile_values_in_career_copy_across_all_tables(self):
        _, profile, summary = make_profile()
        career = copy.deepcopy(profile)

        profile["PBPL"][0]["name"] = "Renamed Play"
        profile["SETL"][0]["name"] = "Renamed Set"
        profile["SETP"][0]["artx"] = "77"
        profile["SETG"][0]["x___"] = "123456"
        profile["SGFF"][0]["name"] = "Default Alignment"
        profile["PLYS"][0]["PSAL"] = "1"
        profile["PLPD"][0]["per1"] = "65"
        profile["PLRD"][0]["hole"] = "6"
        profile["PLCM"][0]["decision"] = "2"

        changed = hc09_plays.sync_play_definition(
            profile, career, summary["setl"], summary["plyl"]
        )

        self.assertEqual(
            set(changed),
            set(hc09_plays.DEFINITION_TABLES),
        )
        self.assertEqual(career["PBPL"][0]["name"], "Renamed Play")
        self.assertEqual(career["SETL"][0]["name"], "Renamed Set")
        self.assertEqual(career["SETP"][0]["artx"], "77")
        self.assertEqual(career["SETG"][0]["x___"], "123456")
        self.assertEqual(career["SGFF"][0]["name"], "Default Alignment")
        self.assertEqual(career["PLYS"][0]["PSAL"], "1")
        self.assertEqual(career["PLPD"][0]["per1"], "65")
        self.assertEqual(career["PLRD"][0]["hole"], "6")
        self.assertEqual(career["PLCM"][0]["decision"], "2")

    def test_sync_does_not_change_unrelated_play_rows(self):
        _, profile, summary = make_profile()
        career = copy.deepcopy(profile)
        other = {"SETL": "999", "PLYL": "998", "name": "Unrelated"}
        profile["PBPL"].append(dict(other))
        career["PBPL"].append(dict(other))
        profile["PBPL"][0]["name"] = "Updated"

        changed = hc09_plays.sync_play_definition(
            profile, career, summary["setl"], summary["plyl"]
        )

        self.assertEqual(career["PBPL"][0]["name"], "Updated")
        self.assertEqual(career["PBPL"][1], other)
        self.assertEqual(changed["PBPL"], career["PBPL"])

    def test_sync_returns_empty_when_career_has_no_definition_copy(self):
        _, profile, summary = make_profile()
        self.assertEqual(
            hc09_plays.sync_play_definition(
                profile, {}, summary["setl"], summary["plyl"]
            ),
            {},
        )

    def test_sync_rejects_missing_rows_instead_of_silently_rebuilding(self):
        _, profile, summary = make_profile()
        career = copy.deepcopy(profile)
        career["PLYS"].pop()

        with self.assertRaisesRegex(ValueError, "PLYS row"):
            hc09_plays.sync_play_definition(
                profile, career, summary["setl"], summary["plyl"]
            )

    def test_sync_rejects_rows_with_unmatched_ids(self):
        _, profile, summary = make_profile()
        career = copy.deepcopy(profile)
        career["SETP"][0]["SETP"] = "32000"

        with self.assertRaisesRegex(ValueError, "SETP row"):
            hc09_plays.sync_play_definition(
                profile, career, summary["setl"], summary["plyl"]
            )

    def test_missing_definitions_skips_colliding_slot_or_alignment_ids(self):
        _, profile, summary = make_profile()
        career = {
            "PGPL": [{
                "BOKL": "9", "SETL": str(summary["setl"]),
                "PLYL": str(summary["plyl"]),
            }],
            "SETP": [{"SETP": profile["SETP"][0]["SETP"]}],
        }

        additions, skipped = hc09_plays.missing_definitions(profile, career, 9)

        self.assertEqual(skipped, ["Saved Play"])
        self.assertTrue(all(not rows for rows in additions.values()))

    def test_missing_definitions_copies_profile_rows_without_mutating_source(self):
        _, profile, summary = make_profile()
        before = copy.deepcopy(profile)
        career = {
            "PGPL": [{
                "BOKL": "9", "SETL": str(summary["setl"]),
                "PLYL": str(summary["plyl"]),
            }]
        }

        additions, skipped = hc09_plays.missing_definitions(profile, career, 9)

        self.assertEqual(skipped, [])
        self.assertEqual(additions, profile)
        self.assertEqual(profile, before)
        self.assertIsNot(additions["PBPL"][0], profile["PBPL"][0])


if __name__ == "__main__":
    unittest.main()
