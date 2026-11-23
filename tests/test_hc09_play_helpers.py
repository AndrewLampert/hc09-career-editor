import unittest

import hc09_plays


class PlayDataHelperTests(unittest.TestCase):
    def test_signed_values_decode_twos_complement_boundaries(self):
        self.assertEqual(hc09_plays.signed(0, 8), 0)
        self.assertEqual(hc09_plays.signed(127, 8), 127)
        self.assertEqual(hc09_plays.signed(128, 8), -128)
        self.assertEqual(hc09_plays.signed(255, 8), -1)

    def test_float_bits_round_trip(self):
        for value in (0.0, 1.0, -2.5, 40.25):
            self.assertAlmostEqual(
                hc09_plays.float_bits(hc09_plays.bits_of_float(value)), value
            )

    def test_game_string_is_cut_at_first_control_character(self):
        self.assertEqual(hc09_plays.cut_at_control("Inside Zone\x00unused"), "Inside Zone")
        self.assertEqual(hc09_plays.cut_at_control("  Trips Right  "), "Trips Right")
        self.assertEqual(hc09_plays.cut_at_control(None), "")

    def test_motion_row_only_follows_coordinates_that_match_old_alignment(self):
        old = {"x___": "10", "y___": "20", "fx__": "30", "fy__": "40"}
        new = {"x___": "11", "y___": "21", "fx__": "31", "fy__": "41"}
        follows_both = {"x___": "10", "y___": "20", "fx__": "30", "fy__": "40"}
        moved_player = {"x___": "99", "y___": "98", "fx__": "30", "fy__": "40"}

        self.assertEqual(
            hc09_plays.motion_row_changes(old, new, follows_both),
            {"x___": "11", "y___": "21", "fx__": "31", "fy__": "41"},
        )
        self.assertEqual(
            hc09_plays.motion_row_changes(old, new, moved_player),
            {"fx__": "31", "fy__": "41"},
        )

    def test_motion_rows_skip_normal_group_and_unknown_slots(self):
        old_norm = {100: {"x___": "1", "y___": "2", "fx__": "3", "fy__": "4"}}
        new_norm = {100: {"x___": "5", "y___": "6", "fx__": "7", "fy__": "8"}}
        rows = [
            {"SETP": "100", "SGF_": "1", "x___": "1", "y___": "2", "fx__": "3", "fy__": "4"},
            {"SETP": "100", "SGF_": "2", "x___": "1", "y___": "2", "fx__": "3", "fy__": "4"},
            {"SETP": "101", "SGF_": "2", "x___": "1", "y___": "2", "fx__": "3", "fy__": "4"},
        ]

        changed = hc09_plays.carry_to_motion_rows(rows, old_norm, new_norm, 1)

        self.assertEqual(changed, 1)
        self.assertEqual(rows[0]["x___"], "1")
        self.assertEqual(rows[1]["x___"], "5")
        self.assertEqual(rows[2]["x___"], "1")

    def test_play_names_accept_printable_ascii_and_reject_invalid_values(self):
        self.assertEqual(hc09_plays.clean_play_name("  Trips Right  "), "Trips Right")
        for invalid in ("", " " * 2, "A" * 25, "Bad\nName", "Café"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    hc09_plays.clean_play_name(invalid)

    def test_cpu_groups_use_known_play_types_then_stock_frequency(self):
        self.assertEqual(hc09_plays.cpu_groups(4), (40, 20, 1))
        stock = [
            {"PLYT": "99", "AIGR": "8"},
            {"PLYT": "99", "AIGR": "8"},
            {"PLYT": "99", "AIGR": "4"},
            {"PLYT": "99", "AIGR": "4"},
            {"PLYT": "99", "AIGR": "4"},
            {"PLYT": "99", "AIGR": "2"},
            {"PLYT": "1", "AIGR": "100"},
        ]
        self.assertEqual(hc09_plays.cpu_groups(99, stock), (4, 8, 2))
        self.assertEqual(hc09_plays.cpu_groups(100, stock), (20, 7, 6))

    def test_missing_cpu_rows_follow_custom_playbook_parent_and_skip_unlinked_play(self):
        pbpl = [
            {"PLYL": "100", "name": "Linked", "PLYT": "4"},
            {"PLYL": "101", "name": "Unlinked", "PLYT": "4"},
        ]
        pgpl = [{"PLYL": "100", "BOKL": "252"}]
        plab = [{"PBGI": "252", "PBPR": "12"}]
        rows, skipped = hc09_plays.missing_cpu_rows(
            pbpl, [], pgpl, plab, stock_pbai=[]
        )

        self.assertEqual(len(rows), 3)
        self.assertEqual({row["BOKL"] for row in rows}, {12})
        self.assertEqual({row["PBPL"] for row in rows}, {100})
        self.assertEqual({row["AIGR"] for row in rows}, {40, 20, 1})
        self.assertEqual(skipped, [(101, "Unlinked", "it is in no playbook the computer can use")])

    def test_rename_rows_preserves_other_books_and_all_other_columns(self):
        source = [
            {"PLYL": "10", "SETL": "5", "name": "Old", "PLYT": "4"},
            {"PLYL": "10", "SETL": "6", "name": "Other copy", "PLYT": "4"},
        ]
        rows, renamed, skipped = hc09_plays.rename_rows(
            source, {10: "New"}, expect={10: 5}
        )

        self.assertEqual(renamed, 1)
        self.assertEqual(skipped, [10])
        self.assertEqual(rows[0]["name"], "New")
        self.assertEqual(rows[0]["PLYT"], "4")
        self.assertEqual(rows[1]["name"], "Other copy")


    def test_mounted_play_id_for_link_uses_set_and_play_ids_to_avoid_stock_collisions(self):
        custom = {
            100028: {"setl": 66, "plyl": 28, "name": "Custom A"},
            100029: {"setl": 67, "plyl": 28, "name": "Custom B"},
        }

        self.assertEqual(hc09_plays.mounted_play_id_for_link(custom, 66, 28), 100028)
        self.assertEqual(hc09_plays.mounted_play_id_for_link(custom, 67, 28), 100029)
        # A stock play may reuse PLYL 28; its different SETL must keep its stock id.
        self.assertEqual(hc09_plays.mounted_play_id_for_link(custom, 99, 28), 28)


    def test_original_play_id_for_mounted_returns_profile_id_for_custom_play(self):
        custom = {
            100028: {"setl": 66, "plyl": 28, "name": "HB DIRECT"},
        }

        self.assertEqual(hc09_plays.original_play_id_for_mounted(custom, 100028), 28)
        # Stock plays already use their career/game id and pass through unchanged.
        self.assertEqual(hc09_plays.original_play_id_for_mounted(custom, 28), 28)

    def test_custom_book_name_rows_adds_save_scoped_override_only_for_linked_play(self):
        pppn = [{"BOKL": "252", "PLYL": "10", "PPPM": "Stock name"}]
        pgpl = [{"BOKL": "3", "PLYL": "10"}, {"BOKL": "252", "PLYL": "10"}]

        rows, changed, created = hc09_plays.custom_book_name_rows(
            pppn, pgpl, 3, 10, "Custom book name"
        )

        self.assertTrue(changed)
        self.assertTrue(created)
        self.assertEqual(rows[0], pppn[0])
        self.assertEqual(rows[1], {
            "BOKL": "3", "PLYL": "10", "PPPM": "Custom book name"
        })

    def test_custom_book_name_rows_updates_existing_override_without_touching_stock_row(self):
        pppn = [
            {"BOKL": "252", "PLYL": "10", "PPPM": "Stock name"},
            {"BOKL": "3", "PLYL": "10", "PPPM": "Old custom name"},
        ]
        rows, changed, created = hc09_plays.custom_book_name_rows(
            pppn, [{"BOKL": "3", "PLYL": "10"}], 3, 10, "New custom name"
        )

        self.assertTrue(changed)
        self.assertFalse(created)
        self.assertEqual(rows[0]["PPPM"], "Stock name")
        self.assertEqual(rows[1]["PPPM"], "New custom name")

    def test_custom_book_name_rows_requires_custom_book_and_existing_link(self):
        with self.assertRaisesRegex(ValueError, "from 1 to 10"):
            hc09_plays.custom_book_name_rows([], [], 252, 10, "Name")
        with self.assertRaisesRegex(ValueError, "not linked"):
            hc09_plays.custom_book_name_rows([], [], 3, 10, "Name")

    def test_custom_book_name_rows_refuses_duplicate_override_rows(self):
        pppn = [
            {"BOKL": "3", "PLYL": "10", "PPPM": "First"},
            {"BOKL": "3", "PLYL": "10", "PPPM": "Second"},
        ]
        with self.assertRaisesRegex(ValueError, "duplicate PPPN"):
            hc09_plays.custom_book_name_rows(pppn, [{"BOKL": "3", "PLYL": "10"}], 3, 10, "New")


if __name__ == "__main__":
    unittest.main()
