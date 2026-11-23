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


class PlaybookLinkIntegrityTests(unittest.TestCase):
    def test_valid_playbook_links_pass(self):
        tables = {
            "PGPL": [{"BOKL": "7", "SETL": "471", "PLYL": "6709"}],
            "PGSS": [{"BOKL": "7", "SETL": "471"}],
            "PGSL": [{"BOKL": "7", "SETL": "471", "PBFM": "26"}],
            "PGFM": [{"BOKL": "7", "PBFM": "26"}],
        }
        self.assertEqual(hc09_addplay.playbook_link_issues(tables), [])

    def test_stock_play_membership_does_not_require_pgsl_row(self):
        tables = {
            "PGPL": [{"BOKL": "7", "SETL": "471", "PLYL": "6709"}],
            "PGSS": [{"BOKL": "7", "SETL": "471"}],
            "PGSL": [],
            "PGFM": [{"BOKL": "7", "PBFM": "26"}],
        }
        self.assertEqual(hc09_addplay.playbook_link_issues(tables), [])

    def test_set_formation_missing_from_book_is_reported(self):
        tables = {
            "PGPL": [{"BOKL": "7", "SETL": "471", "PLYL": "6709"}],
            "PGSS": [{"BOKL": "7", "SETL": "471"}],
            "PGSL": [{"BOKL": "7", "SETL": "471", "PBFM": "26"}],
            "PGFM": [],
        }
        issues = hc09_addplay.playbook_link_issues(tables)
        self.assertEqual([x["kind"] for x in issues], ["formation_not_in_playbook"])
        self.assertEqual((issues[0]["book"], issues[0]["formation"]), (7, 26))

    def test_stock_play_membership_does_not_require_pgsl_row(self):
        tables = {
            "PGPL": [{"BOKL": "460", "SETL": "218", "PLYL": "6709"}],
            "PGSS": [], "PGSL": [], "PGFM": [{"BOKL": "460", "PBFM": "26"}],
        }
        self.assertEqual(hc09_addplay.playbook_link_issues(tables), [])
    def test_playbook_set_without_quick_sub_package_need_not_be_in_pgss(self):
        tables = {
            "PGPL": [{"BOKL": "7", "SETL": "471", "PLYL": "6709"}],
            "PGSS": [],
            "PGSL": [{"BOKL": "7", "SETL": "471", "PBFM": "26"}],
            "PGFM": [{"BOKL": "7", "PBFM": "26"}],
        }
        self.assertEqual(hc09_addplay.playbook_link_issues(tables), [])

    def test_one_set_can_legitimately_link_to_multiple_formations(self):
        tables = {
            "PGPL": [{"BOKL": "7", "SETL": "471", "PLYL": "6709"}],
            "PGSS": [{"BOKL": "7", "SETL": "471"}],
            "PGSL": [
                {"BOKL": "7", "SETL": "471", "PBFM": "26"},
                {"BOKL": "7", "SETL": "471", "PBFM": "27"},
            ],
            "PGFM": [
                {"BOKL": "7", "PBFM": "26"},
                {"BOKL": "7", "PBFM": "27"},
            ],
        }
        self.assertEqual(hc09_addplay.playbook_link_issues(tables), [])

    def test_same_formation_id_in_another_book_does_not_validate_link(self):
        tables = {
            "PGPL": [{"BOKL": "7", "SETL": "471", "PLYL": "6709"}],
            "PGSS": [{"BOKL": "7", "SETL": "471"}],
            "PGSL": [{"BOKL": "7", "SETL": "471", "PBFM": "26"}],
            "PGFM": [{"BOKL": "8", "PBFM": "26"}],
        }
        issues = hc09_addplay.playbook_link_issues(tables)
        self.assertEqual([x["kind"] for x in issues], ["formation_not_in_playbook"])


class ConvertMineSafetyTests(unittest.TestCase):
    def test_special_teams_play_is_rejected_before_formation_group_selection(self):
        class Library:
            plays = {6709: {"name": "Onside Kick"}}
            tables = {"PSLO": [], "ARTO": []}

            @staticmethod
            def detail(_base):
                return {"side": "other"}

        class Groups:
            def pick(self, *_args):
                raise AssertionError("special-teams plays must be rejected before group selection")

        plays, skipped = hc09_addplay.convert_mine(Library(), [6709], [252], Groups())
        self.assertEqual(plays, [])
        self.assertEqual(skipped, [(6709, "Only offensive plays can be converted for now.")])



class CustomPlayIntegrityTests(unittest.TestCase):
    @staticmethod
    def valid_tables():
        slots = [{"SETL": "5", "SETP": str(100 + i), "poso": str(i)} for i in range(11)]
        play_slots = [{"PLYL": "9", "poso": str(i)} for i in range(11)]
        return {
            "PBPL": [{"PLYL": "9", "SETL": "5"}],
            "SETL": [{"SETL": "5"}],
            "SETP": slots,
            "PLYS": play_slots,
            "SGFF": [{"SETL": "5", "SGF_": "20", "dflt": "1"}],
            "SETG": [{"SETP": str(100 + i), "SGF_": "20"} for i in range(11)],
            "PLPD": [], "PLRD": [], "PLCM": [],
        }

    def test_complete_custom_play_passes(self):
        self.assertEqual(hc09_addplay.custom_play_issues(self.valid_tables()), [])

    def test_missing_play_set_is_reported(self):
        tables = self.valid_tables()
        tables["PBPL"][0]["SETL"] = "77"
        issues = hc09_addplay.custom_play_issues(tables)
        self.assertIn("play_set_missing", [x["kind"] for x in issues])

    def test_incomplete_or_duplicate_slot_positions_are_reported(self):
        tables = self.valid_tables()
        tables["SETP"].pop()
        tables["PLYS"][-1]["poso"] = "9"
        kinds = [x["kind"] for x in hc09_addplay.custom_play_issues(tables)]
        self.assertIn("set_slots_invalid", kinds)
        self.assertIn("play_slots_invalid", kinds)

    def test_alignment_must_reference_a_slot_and_its_own_set_group(self):
        tables = self.valid_tables()
        tables["SETG"][0]["SETP"] = "999"
        kinds = [x["kind"] for x in hc09_addplay.custom_play_issues(tables)]
        self.assertIn("alignment_slot_missing", kinds)

    def test_detail_rows_must_reference_a_custom_play(self):
        tables = self.valid_tables()
        tables["PLPD"] = [{"PLYL": "88"}]
        issues = hc09_addplay.custom_play_issues(tables)
        self.assertIn("detail_play_missing", [x["kind"] for x in issues])

if __name__ == "__main__":
    unittest.main()
