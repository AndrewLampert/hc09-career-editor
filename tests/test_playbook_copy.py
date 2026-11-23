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
