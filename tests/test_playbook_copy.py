import unittest

import guiHC09


class PlaybookCopyFormationCategoryTests(unittest.TestCase):
    def make_data(self):
        game = {
            "plab": [
                {"PBGI": "1", "BGID": "1", "BOFF": "1", "BNAM": "Source", "BORD": "1"},
                {"PBGI": "2", "BGID": "2", "BOFF": "1", "BNAM": "Target", "BORD": "2"},
            ],
            "pbfm": [
                {"PBFM": "100", "name": "Kickoff"},
                {"PBFM": "101", "name": "Kick Return"},
                {"PBFM": "200", "name": "Split Backs"},
                {"PBFM": "201", "name": "I Form"},
            ],
            "setl": [
                {"SETL": "471", "name": "Onside Kick"},
                {"SETL": "50", "name": "I Form"},
            ],
            "pbpl": [
                {"SETL": "471", "PLYL": "6709", "name": "Onside Kick", "PLYT": "21"},
                {"SETL": "50", "PLYL": "500", "name": "Dive", "PLYT": "1"},
            ],
        }
        save = {
            "pgfm": [
                {"BOKL": "1", "PBFM": "100", "SRFM": "100"},
                {"BOKL": "1", "PBFM": "201", "SRFM": "201"},
                {"BOKL": "2", "PBFM": "101", "SRFM": "101"},
                {"BOKL": "2", "PBFM": "200", "SRFM": "200"},
            ],
            "pgsl": [
                {"BOKL": "1", "SETL": "471", "PBFM": "100"},
                {"BOKL": "1", "SETL": "50", "PBFM": "201"},
            ],
            "pgss": [
                {"BOKL": "1", "SETL": "471"},
                {"BOKL": "1", "SETL": "50"},
            ],
            "pgpl": [
                {"BOKL": "1", "SETL": "471", "PLYL": "6709", "PLTP": "21"},
                {"BOKL": "1", "SETL": "50", "PLYL": "500", "PLTP": "1"},
            ],
        }
        return guiHC09.PlaybookData(game, save, [])

    def test_copy_entire_kickoff_formation_preserves_special_teams_link(self):
        data = self.make_data()
        data.formation_sets[("1", "100")] = ["471"]
        plan = data.plan_copy("1", "2", "formation", "100")

        self.assertIsNone(plan["error"])
        self.assertEqual(plan["rows"]["PGFM"], [
            {"BOKL": "2", "PBFM": "100", "SRFM": "100"}
        ])
        self.assertEqual(plan["rows"]["PGSL"], [
            {"BOKL": "2", "SETL": "471", "PBFM": "100"}
        ])
        self.assertEqual(plan["rows"]["PGPL"], [
            {"BOKL": "2", "SETL": "471", "PLYL": "6709", "PLTP": "21"}
        ])

    def test_entire_formation_copy_rejects_wrong_category_override(self):
        data = self.make_data()
        data.formation_sets[("1", "100")] = ["471"]
        plan = data.plan_copy("1", "2", "formation", "100", into_formation="200")

        self.assertIn("special-teams set", plan["error"])
        self.assertIn("Split Backs", plan["error"])
        self.assertEqual(plan["rows"]["PGSL"], [])
        self.assertEqual(plan["rows"]["PGPL"], [])

    def test_mixed_source_formation_links_cannot_hide_special_teams_mismatch(self):
        data = self.make_data()
        # The same stock set has a valid Kickoff link and a bad Split Backs link.
        data.tables["PGSL"].append({"BOKL": "1", "SETL": "471", "PBFM": "200"})
        data._index_structure()

        plan = data.plan_copy("1", "2", "play", ("471", "6709"), into_formation="200")

        self.assertIn("special-teams set", plan["error"])
        self.assertIn("Split Backs", plan["error"])
        self.assertEqual(plan["rows"]["PGFM"], [])
        self.assertEqual(plan["rows"]["PGSS"], [])
        self.assertEqual(plan["rows"]["PGSL"], [])
        self.assertEqual(plan["rows"]["PGPL"], [])

    def test_copy_into_existing_mislinked_set_is_rejected_without_rows(self):
        data = self.make_data()
        # Target already owns this set, but has it linked to an ordinary formation.
        data.tables["PGSS"].append({"BOKL": "2", "SETL": "471"})
        data.tables["PGSL"].append({"BOKL": "2", "SETL": "471", "PBFM": "200"})
        data.tables["PGPL"].append({"BOKL": "2", "SETL": "471", "PLYL": "6709", "PLTP": "21"})
        data._index_structure()

        plan = data.plan_copy("1", "2", "play", ("471", "6709"))

        self.assertIn("source formation categories", plan["error"])
        self.assertIn("target's existing formation links", plan["error"])
        self.assertEqual(plan["rows"]["PGFM"], [])
        self.assertEqual(plan["rows"]["PGSS"], [])
        self.assertEqual(plan["rows"]["PGSL"], [])
        self.assertEqual(plan["rows"]["PGPL"], [])

    def test_copy_entire_ordinary_formation_maps_to_ordinary_target(self):
        data = self.make_data()
        data.formation_sets[("1", "201")] = ["50"]
        plan = data.plan_copy("1", "2", "formation", "201")

        self.assertIsNone(plan["error"])
        self.assertEqual(plan["rows"]["PGFM"], [
            {"BOKL": "2", "PBFM": "201", "SRFM": "201"}
        ])
        self.assertEqual(plan["rows"]["PGSL"], [
            {"BOKL": "2", "SETL": "50", "PBFM": "201"}
        ])
        self.assertEqual(plan["rows"]["PGPL"], [
            {"BOKL": "2", "SETL": "50", "PLYL": "500", "PLTP": "1"}
        ])

    def test_copy_entire_kick_return_formation_is_allowed(self):
        data = self.make_data()
        data.formation_sets[("1", "101")] = ["471"]
        plan = data.plan_copy("1", "2", "formation", "101")

        self.assertIsNone(plan["error"])
        self.assertEqual(plan["rows"]["PGSL"], [
            {"BOKL": "2", "SETL": "471", "PBFM": "101"}
        ])

    def test_stock_set_category_outlier_is_reported_read_only(self):
        data = self.make_data()
        for book in ("3", "4", "5"):
            data.book_side[book] = "Offense"
            data.book_names[book] = [f"Book {book}"]
            data.tables["PGFM"].append({"BOKL": book, "PBFM": "100", "SRFM": "100"})
            data.tables["PGSL"].append({"BOKL": book, "SETL": "471", "PBFM": "100"})
        data.tables["PGSL"].append({"BOKL": "2", "SETL": "471", "PBFM": "200"})
        data._index_structure()

        warnings = data.stock_set_category_warnings()

        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0]["book"], "2")
        self.assertEqual(warnings[0]["set"], "471")
        self.assertEqual(warnings[0]["expected"], "special-teams")
        self.assertEqual(warnings[0]["actual"], "ordinary")
        self.assertEqual(warnings[0]["formations"], ["Split Backs"])

    def test_special_teams_play_cannot_be_put_under_split_backs(self):
        data = self.make_data()
        plan = data.plan_copy("1", "2", "play", ("471", "6709"), into_formation="200")

        self.assertIn("special-teams set", plan["error"])
        self.assertIn('Split Backs', plan["error"])
        self.assertEqual(plan["rows"]["PGPL"], [])
        self.assertEqual(plan["rows"]["PGSL"], [])

    def test_special_teams_play_can_be_put_under_kick_return(self):
        data = self.make_data()
        plan = data.plan_copy("1", "2", "play", ("471", "6709"), into_formation="101")

        self.assertIsNone(plan["error"])
        self.assertEqual(plan["rows"]["PGSL"], [
            {"BOKL": "2", "SETL": "471", "PBFM": "101"}
        ])

    def test_ordinary_play_cannot_be_put_under_kickoff(self):
        data = self.make_data()
        plan = data.plan_copy("1", "2", "play", ("50", "500"), into_formation="101")

        self.assertIn("ordinary set", plan["error"])
        self.assertIn("Kick Return", plan["error"])
        self.assertEqual(plan["rows"]["PGPL"], [])

    def test_ordinary_play_can_be_put_under_split_backs(self):
        data = self.make_data()
        plan = data.plan_copy("1", "2", "play", ("50", "500"), into_formation="200")

        self.assertIsNone(plan["error"])
        self.assertEqual(plan["rows"]["PGSL"], [
            {"BOKL": "2", "SETL": "50", "PBFM": "200"}
        ])


if __name__ == "__main__":
    unittest.main()
