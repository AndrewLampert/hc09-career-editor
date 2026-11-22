import unittest

from hc09_playbook_index import build_index


class PlaybookIndexTests(unittest.TestCase):
    def test_joins_books_plays_sets_formations_and_name_overrides(self):
        pbpl = [
            {"PLYL": "101", "SETL": "7", "name": "Inside Zone", "PLYT": "1"},
            {"PLYL": "102", "SETL": "8", "name": "Four Verticals", "PLYT": "2"},
        ]
        setl = [
            {"SETL": "7", "name": "Ace", "FORM": "3"},
            {"SETL": "8", "name": "Trips", "FORM": "1"},
        ]
        pbai = [
            {"BOKL": "252", "PBPL": "101", "SETL": "7", "AIGR": "1", "prct": "40"},
            {"BOKL": "252", "PBPL": "101", "SETL": "7", "AIGR": "2", "prct": "25"},
            {"BOKL": "253", "PBPL": "102", "SETL": "8", "AIGR": "3", "prct": "10"},
        ]
        form = [{"FORM": "3", "name": "I Form"}, {"FORM": "1", "name": "Shotgun"}]
        pppn = [{"BOKL": "252", "PLYL": "101", "PPPM": "IZ Strong"}]

        index, diagnostics = build_index(pbpl, setl, pbai, form, pppn)

        play = index["252"]["plays"][0]
        self.assertEqual(play["master_name"], "Inside Zone")
        self.assertEqual(play["playbook_name"], "IZ Strong")
        self.assertEqual(play["formation_name"], "I Form")
        self.assertEqual(play["ai_rows"], [{"group": 1, "weight": 40}, {"group": 2, "weight": 25}])
        self.assertEqual(index["253"]["plays"][0]["formation_name"], "Shotgun")
        self.assertEqual(diagnostics["book_count"], 2)
        self.assertEqual(diagnostics["book_play_links"], 2)

    def test_reports_dangling_play_and_set_links(self):
        index, diagnostics = build_index(
            [{"PLYL": "10", "SETL": "99", "name": "Test", "PLYT": "1"}],
            [],
            [
                {"BOKL": "1", "PBPL": "404", "SETL": "0", "AIGR": "1", "prct": "5"},
                {"BOKL": "1", "PBPL": "10", "SETL": "99", "AIGR": "2", "prct": "6"},
            ],
        )
        self.assertEqual(index["1"]["play_count"], 1)
        self.assertEqual(len(diagnostics["missing_pbpl"]), 1)
        self.assertEqual(len(diagnostics["missing_setl"]), 1)

    def test_duplicate_book_play_rows_are_preserved_as_ai_rows(self):
        _, diagnostics = build_index(
            [{"PLYL": "10", "SETL": "5", "name": "Test", "PLYT": "1"}],
            [{"SETL": "5", "name": "Set", "FORM": "1"}],
            [
                {"BOKL": "1", "PBPL": "10", "SETL": "5", "AIGR": "1", "prct": "5"},
                {"BOKL": "1", "PBPL": "10", "SETL": "5", "AIGR": "1", "prct": "7"},
            ],
        )
        self.assertEqual(diagnostics["duplicate_book_play_rows"], 1)


if __name__ == "__main__":
    unittest.main()
