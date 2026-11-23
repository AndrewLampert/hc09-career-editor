import unittest

import hc09_addplay


class FormationGroupTests(unittest.TestCase):
    def make_groups(self, book_groups):
        names = []
        links = []
        membership = []
        for group_id, name, count in book_groups:
            names.append({
                "PBFM": str(group_id), "name": name, "FTYP": "1",
                "ord_": str(group_id),
            })
            membership.append({"BOKL": "7", "PBFM": str(group_id)})
            for set_id in range(count):
                links.append({
                    "BOKL": str(100 + set_id), "SETL": str(group_id * 1000 + set_id),
                    "PBFM": str(group_id),
                })
        return hc09_addplay.FormationGroups(links, names, membership)

    def test_exact_stock_set_group_wins(self):
        groups = hc09_addplay.FormationGroups(
            [{"BOKL": "7", "SETL": "50", "PBFM": "3"}],
            [
                {"PBFM": "3", "name": "Goal Line", "FTYP": "1", "ord_": "1"},
                {"PBFM": "4", "name": "Splitbacks", "FTYP": "1", "ord_": "2"},
            ],
            [{"BOKL": "7", "PBFM": "3"}, {"BOKL": "7", "PBFM": "4"}],
        )
        self.assertEqual(groups.pick(7, 50), 3)

    def test_family_alias_maps_gun_to_shotgun(self):
        groups = hc09_addplay.FormationGroups(
            [{"BOKL": "20", "SETL": "50", "PBFM": "10"}],
            [
                {"PBFM": "8", "name": "Shotgun", "FTYP": "1", "ord_": "1"},
                {"PBFM": "9", "name": "Splitbacks", "FTYP": "1", "ord_": "2"},
                {"PBFM": "10", "name": "Gun", "FTYP": "1", "ord_": "3"},
            ],
            [{"BOKL": "7", "PBFM": "8"}, {"BOKL": "7", "PBFM": "9"}],
        )
        self.assertEqual(groups.pick(7, 50), 8)

    def test_special_teams_family_is_not_used_to_classify_a_normal_formation(self):
        groups = hc09_addplay.FormationGroups(
            [
                {"BOKL": "20", "SETL": "50", "PBFM": "8"},
                {"BOKL": "21", "SETL": "50", "PBFM": "8"},
            ],
            [
                {"PBFM": "8", "name": "Special Teams", "FTYP": "1", "ord_": "1"},
                {"PBFM": "9", "name": "Splitbacks", "FTYP": "1", "ord_": "2"},
            ],
            [{"BOKL": "7", "PBFM": "8"}, {"BOKL": "7", "PBFM": "9"}],
        )
        self.assertEqual(groups.pick(7, 50), 9)

    def test_fallback_uses_most_populated_non_special_group(self):
        groups = self.make_groups([
            (1, "Special Teams", 99),
            (2, "Splitbacks", 2),
            (3, "I Form", 7),
        ])
        self.assertEqual(groups.pick(7, 999), 3)

    def test_no_ordinary_group_means_no_placement_target(self):
        groups = self.make_groups([
            (1, "Special Teams", 99),
            (2, "Goal Line", 50),
            (3, "Hail Mary", 40),
        ])
        self.assertIsNone(groups.pick(7, 999))

    def test_non_offense_groups_are_never_placement_targets(self):
        groups = hc09_addplay.FormationGroups(
            [],
            [{"PBFM": "1", "name": "Splitbacks", "FTYP": "2", "ord_": "1"}],
            [{"BOKL": "7", "PBFM": "1"}],
        )
        self.assertIsNone(groups.pick(7, 50))


class EveryoneBooksTests(unittest.TestCase):
    class Library:
        books_of_play = {100: {7}, 200: {7}}

        @staticmethod
        def play_side(plyl):
            return {100: "offense", 200: "other"}[plyl]

    def test_special_teams_play_does_not_consume_offense_playbook_capacity(self):
        class Groups:
            @staticmethod
            def pick(_book, _like):
                return 4

        books, targets, left_out = hc09_addplay.everyone_books(
            self.Library(), [7], Groups(), 50, cap=2
        )
        self.assertEqual(books, [7])
        self.assertEqual(targets, {7: 4})
        self.assertEqual(left_out, [])

    def test_special_only_group_is_reported_as_no_placement_target(self):
        class Groups:
            @staticmethod
            def pick(_book, _like):
                return None

        books, targets, left_out = hc09_addplay.everyone_books(
            self.Library(), [7], Groups(), 50
        )
        self.assertEqual(books, [])
        self.assertEqual(targets, {})
        self.assertEqual(left_out, [(7, "it has no offense formation group to put the formation in")])


if __name__ == "__main__":
    unittest.main()
