import unittest

import hc09_plays


def make_library():
    setl = [{"SETL": "50", "FORM": "1", "MOTN": "0", "SETT": "0", "SITT": "0", "name": "Test Set"}]
    setp = []
    setg = []
    plys = []
    for poso in range(11):
        setp.append({
            "SETL": "50", "SETP": str(100 + poso), "poso": str(poso),
            "EPos": str([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10][poso]),
            "DPos": "1", "artx": str(poso), "arty": "0", "fmtx": str(poso),
            "fmty": "0", "SGT_": "1", "arti": "4", "tabo": "0",
        })
        setg.append({
            "SETP": str(100 + poso), "SGF_": "700", "SF__": "0",
            "x___": "0", "y___": "0", "fx__": "0", "fy__": "0",
            "anm_": "0", "dir_": "0", "fanm": "0", "fdir": "0",
        })
        plys.append({"PLYL": "200", "poso": str(poso), "PSAL": "1", "ARTL": "0", "PLRR": str(poso)})
    tables = {
        "PBPL": [{"PLYL": "200", "SETL": "50", "PLYT": "1", "PLF_": "0", "name": "Base Play",
                  "risk": "0", "motn": "0", "vpos": "0", "SITT": "0"}],
        "SETL": setl, "SETP": setp, "SETG": setg,
        "SGFF": [{"SETL": "50", "SGF_": "700", "name": "Normal", "dflt": "1"}],
        "PLYS": plys,
        "PSLO": [{"PSAL": "1", "step": "0", "code": "14", "val1": "0", "val2": "0", "val3": "0"},
                 {"PSAL": "1", "step": "1", "code": "255", "val1": "0", "val2": "0", "val3": "0"}],
    }
    return hc09_plays.PlayLibrary(tables)


class PlayCreationTests(unittest.TestCase):
    def test_play_detail_contains_all_eleven_slots_and_slot_assignments(self):
        lib = make_library()
        detail = lib.detail(200)
        self.assertEqual(len(detail["set"]["slots"]), 11)
        self.assertEqual(len(detail["slots"]), 11)
        self.assertEqual([slot["poso"] for slot in detail["slots"]], list(range(11)))
        self.assertEqual([slot["psal"] for slot in detail["slots"]], [1] * 11)
        self.assertTrue(all(slot["text"] == "14" for slot in detail["slots"]))

    def test_custom_play_build_copies_eleven_slots_and_assignment_rows(self):
        lib = make_library()
        rows, summary = hc09_plays.build_custom_play(
            lib, 200, "Regression Play", {}, profile={}
        )
        self.assertEqual(summary["name"], "Regression Play")
        self.assertEqual(len(rows["SETP"]), 11)
        self.assertEqual(len(rows["PLYS"]), 11)
        self.assertEqual(len(rows["SETG"]), 11)
        self.assertEqual(len(rows["PBPL"]), 1)
        self.assertEqual(len({int(row["poso"]) for row in rows["PLYS"]}), 11)
        self.assertEqual({int(row["PSAL"]) for row in rows["PLYS"]}, {1})

    def test_custom_play_ids_avoid_stock_and_profile_ids(self):
        lib = make_library()
        profile = {
            "SETL": [{"SETL": "1"}],
            "PBPL": [{"SETL": "1", "PLYL": "1"}],
            "SETP": [{"SETP": "1"}],
            "SGFF": [{"SGF_": "1"}],
        }
        ids = hc09_plays.free_ids(lib, profile, avoid={
            "SETL": {2}, "PLYL": {2}, "SETP": {2}, "SGF_": {2}
        }, slots=2, groups=1)
        self.assertEqual(ids, {"SETL": 3, "PLYL": 3, "SETP": [3, 4], "SGF_": [3]})

    def test_career_link_rows_add_created_formation_only_once(self):
        first = hc09_plays.career_link_rows({}, 7, 20, 30, 1)
        self.assertIn("PGFM", first)
        self.assertEqual(first["PGPL"][0]["PLYL"], 30)
        self.assertEqual(first["PGSS"][0]["SETL"], 20)
        self.assertEqual(first["PGSL"][0]["PBFM"], hc09_plays.CREATED_FORMATION)
        career = {"PGFM": [{"BOKL": 7, "PBFM": hc09_plays.CREATED_FORMATION, "SRFM": hc09_plays.CREATED_FORMATION}]}
        second = hc09_plays.career_link_rows(career, 7, 21, 31, 1)
        self.assertNotIn("PGFM", second)
        self.assertEqual(second["PGPL"][0]["SETL"], 21)

    def test_missing_custom_definition_is_copied_once_into_career(self):
        lib = make_library()
        rows, summary = hc09_plays.build_custom_play(lib, 200, "New Play", {}, profile={})
        profile = {table: list(items) for table, items in rows.items()}
        career = {
            "PGPL": [{"BOKL": 9, "SETL": summary["setl"], "PLYL": summary["plyl"], "PLTP": 1}]
        }
        additions, skipped = hc09_plays.missing_definitions(profile, career, 9)
        self.assertEqual(skipped, [])
        self.assertEqual(len(additions["PBPL"]), 1)
        self.assertEqual(len(additions["SETP"]), 11)
        self.assertEqual(len(additions["PLYS"]), 11)
        self.assertEqual(len(additions["SETG"]), 11)
        career["PBPL"] = additions["PBPL"]
        career["SETL"] = additions["SETL"]
        career["SETP"] = additions["SETP"]
        career["SETG"] = additions["SETG"]
        career["SGFF"] = additions["SGFF"]
        career["PLYS"] = additions["PLYS"]
        career["PLPD"] = additions["PLPD"]
        career["PLRD"] = additions["PLRD"]
        career["PLCM"] = additions["PLCM"]
        again, skipped_again = hc09_plays.missing_definitions(profile, career, 9)
        self.assertEqual(skipped_again, [])
        self.assertTrue(all(not items for items in again.values()))

    def test_custom_definition_collision_is_reported_not_overwritten(self):
        lib = make_library()
        rows, summary = hc09_plays.build_custom_play(lib, 200, "Collision", {}, profile={})
        profile = {table: list(items) for table, items in rows.items()}
        career = {
            "PGPL": [{"BOKL": 9, "SETL": summary["setl"], "PLYL": summary["plyl"], "PLTP": 1}],
            "SETL": [{"SETL": summary["setl"]}],
        }
        additions, skipped = hc09_plays.missing_definitions(profile, career, 9)
        self.assertEqual(skipped, ["Collision"])
        self.assertTrue(all(not items for items in additions.values()))


if __name__ == "__main__":
    unittest.main()
