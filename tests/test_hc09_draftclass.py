import unittest

import guiHC09
import hc09_draftclass as dc


def row(pgid, dfcl, ppos, spd, spdx, **more):
    r = {"PGID": str(pgid), "DFCL": str(dfcl), "PPOS": str(ppos), "PSPD": str(spd), "PSDX": str(spdx)}
    r.update({k: str(v) for k, v in more.items()})
    return r


class StaticTablesTests(unittest.TestCase):
    def test_every_rating_has_the_maximum_column_the_editor_uses(self):
        for code, _label, mx in dc.RATINGS:
            self.assertEqual(guiHC09.PLAYER_MAX_HARDCODED[code], mx, code)

    def test_every_rating_label_is_the_editors(self):
        for code, label, _mx in dc.RATINGS:
            self.assertEqual(guiHC09.STAT_META[code][0], label, code)

    def test_position_names_are_the_editors(self):
        self.assertEqual({str(k): v for k, v in dc.POSITION_NAMES.items()}, guiHC09.POSITIONS)
        self.assertEqual(sorted(dc.POSITION_ORDER), sorted(dc.POSITION_NAMES))

    def test_export_fields_name_every_column_the_plan_reads(self):
        fields = set(dc.EXPORT_FIELDS.split(","))
        self.assertTrue({"PGID", "DFCL", "PPOS"} <= fields)
        for code, _label, mx in dc.RATINGS:
            self.assertIn(code, fields)
            self.assertIn(mx, fields)


class PlanTests(unittest.TestCase):
    def tables(self):
        return {
            "DPL1": [row(1, 1, 3, 70, 80), row(2, 2, 3, 60, 60)],
            "DPL2": [row(1, 1, 3, 70, 80), row(10, 19, 3, 90, 95), row(11, 19, 3, 98, 99), row(12, 19, 0, 50, 50), row(13, 19, 0, 3, 3)],
            "DPL3": [row(1, 1, 3, 70, 80), row(20, 32, 3, 70, 70)],
            "DPL4": [row(1, 1, 3, 70, 80)],
        }

    def test_same_change_for_the_rating_and_its_maximum(self):
        p = dc.plan(self.tables(), 19, {"PSPD": -5})
        by_id = {e["match"]["PGID"]: e for e in p["edits"]["DPL2"]}
        self.assertEqual(by_id[10], {"table": "DPL2", "match": {"PGID": 10, "DFCL": 19}, "expect": {"PSPD": 90, "PSDX": 95}, "set": {"PSPD": 85, "PSDX": 90}})
        self.assertEqual(p["tables"], ["DPL2"])
        self.assertEqual(p["players"], 4)
        self.assertEqual(p["values"], 8)

    def test_values_stay_between_0_and_99_and_the_maximum_never_falls_below_the_rating(self):
        p = dc.plan(self.tables(), 19, {"PSPD": 5})
        by_id = {e["match"]["PGID"]: e["set"] for e in p["edits"]["DPL2"]}
        self.assertEqual(by_id[11], {"PSPD": 99})                      # 98 -> 99 (clamped), the maximum was already 99
        down = dc.plan(self.tables(), 19, {"PSPD": -10})
        by_id = {e["match"]["PGID"]: e["set"] for e in down["edits"]["DPL2"]}
        self.assertEqual(by_id[13], {"PSPD": 0, "PSDX": 0})
        self.assertTrue(all(s["PSDX"] >= s["PSPD"] for s in by_id.values()))
        line = [ln for ln in p["ratings"][0]["lines"] if ln["ppos"] == 3][0]
        self.assertEqual(line["clamped"], 2)                           # 98 + 5 and 99 + 5 (max) hit 99

    def test_a_player_whose_values_do_not_change_gets_no_edit(self):
        p = dc.plan(self.tables(), 19, {"PSPD": 0})
        self.assertEqual(p["edits"]["DPL2"], [])
        self.assertEqual((p["players"], p["values"]), (0, 0))

    def test_per_position_changes(self):
        p = dc.plan(self.tables(), 19, {"PSPD": {3: -4}})
        ids = {e["match"]["PGID"] for e in p["edits"]["DPL2"]}
        self.assertEqual(ids, {10, 11})                                # the two WRs only; the QBs have no change
        line = p["ratings"][0]["lines"]
        self.assertEqual([ln["name"] for ln in line], ["QB", "WR"])
        wr = line[1]
        self.assertEqual((wr["players"], wr["old_mean"], wr["new_mean"], wr["changed"]), (2, 94.0, 90.0, 2))

    def test_class_one_goes_to_every_copy(self):
        p = dc.plan(self.tables(), 1, {"PSPD": 2})
        self.assertEqual(p["tables"], ["DPL1", "DPL2", "DPL3", "DPL4"])
        for t in p["tables"]:
            self.assertEqual([e["match"] for e in p["edits"][t]], [{"PGID": 1, "DFCL": 1}])
        self.assertEqual(p["players"], 1)

    def test_other_classes_only_touch_their_own_table(self):
        p = dc.plan(self.tables(), 32, {"PSPD": 1})
        self.assertEqual(p["tables"], ["DPL3"])
        self.assertEqual(list(p["edits"]), ["DPL3"])

    def test_refuses_what_it_does_not_know(self):
        with self.assertRaises(ValueError):
            dc.plan(self.tables(), 19, {"POVR": 1})
        with self.assertRaises(ValueError):
            dc.plan(self.tables(), 99, {"PSPD": 1})

    def test_a_player_without_a_readable_value_is_left_alone(self):
        tables = {"DPL2": [row(5, 19, 3, "", ""), row(6, 19, 3, 50, 60)]}
        p = dc.plan(tables, 19, {"PSPD": 3})
        self.assertEqual([e["match"]["PGID"] for e in p["edits"]["DPL2"]], [6])

    def test_several_ratings_in_one_plan(self):
        tables = {"DPL2": [row(5, 19, 3, 50, 60, PACC=70, PACX=75)]}
        p = dc.plan(tables, 19, {"PSPD": -1, "PACC": 2})
        self.assertEqual(p["edits"]["DPL2"][0]["set"], {"PSPD": 49, "PSDX": 59, "PACC": 72, "PACX": 77})
        self.assertEqual([r["rating"] for r in p["ratings"]], ["PSPD", "PACC"])

    def test_target_wraps_the_edits_for_the_bridge(self):
        t = dc.target_for({"ast": "a.ast", "index": 46, "start": 5, "size": 9, "extra": 1}, [{"table": "DPL2"}])
        self.assertEqual(t, {"ast": "a.ast", "index": 46, "start": 5, "size": 9, "edits": [{"table": "DPL2"}]})


class ReferenceTests(unittest.TestCase):
    def test_means_per_position(self):
        rows = [row(1, 19, 3, 80, 90), row(2, 19, 3, 70, 90), row(3, 19, 0, 50, 60), row(4, 19, 0, "", "")]
        self.assertEqual(dc.position_means(rows, "PSPD"), {3: (2, 75.0), 0: (1, 50.0)})

    def test_suggested_change_moves_the_mean_to_the_reference(self):
        rows = [row(1, 19, 3, 80, 90), row(2, 19, 3, 70, 90), row(3, 19, 0, 50, 60), row(9, 7, 3, 10, 10)]
        ref = {"PSPD": {3: 72.0, 0: 50.4, 16: 70.0}}
        self.assertEqual(dc.suggest_deltas(rows, 19, ref, ["PSPD"]), {"PSPD": {3: -3}})          # QB 0.4 rounds to 0 and is left out; no CBs in the class
        ref_up = {"PSPD": {3: 80.5}}
        self.assertEqual(dc.suggest_deltas(rows, 19, ref_up, ["PSPD"]), {"PSPD": {3: 6}})        # 5.5 rounds up

    def test_the_library_counts_class_one_once(self):
        tables = {t: [row(1, 1, 3, 70, 80)] for t in dc.TIERS}
        tables["DPL2"].append(row(10, 19, 3, 90, 95))
        rows = dc.library_rows(tables)
        self.assertEqual(sorted(r["PGID"] for r in rows), ["1", "10"])
        self.assertEqual(dc.reference_from_rows(rows, ["PSPD"]), {"PSPD": {3: 80.0}})

    def test_classes_and_tables(self):
        tables = {"DPL1": [row(1, 1, 3, 1, 1), row(2, 5, 3, 1, 1)], "DPL2": [row(1, 1, 3, 1, 1), row(3, 19, 3, 1, 1)]}
        self.assertEqual(dc.classes_in(tables), {"DPL1": {1: 1, 5: 1}, "DPL2": {1: 1, 19: 1}})
        self.assertEqual(dc.tables_holding(tables, 1), ["DPL1", "DPL2"])
        self.assertEqual(dc.tables_holding(tables, 19), ["DPL2"])
        self.assertEqual(dc.tables_holding(tables, 40), [])

    def test_class_label_names_the_first_class_of_new_careers(self):
        self.assertIn("first class of new careers", dc.class_label("DPL2", 19))
        self.assertNotIn("first class", dc.class_label("DPL3", 32))
        self.assertIn("all four tables", dc.class_label("DPL1", 1))

    def test_class_choices_list_the_first_class_first_and_class_one_once(self):
        tables = {"DPL1": [row(1, 1, 3, 1, 1), row(2, 5, 3, 1, 1)], "DPL2": [row(1, 1, 3, 1, 1), row(3, 19, 3, 1, 1), row(4, 17, 3, 1, 1)],
                  "DPL3": [row(1, 1, 3, 1, 1)], "DPL4": [row(1, 1, 3, 1, 1)]}
        got = [(t, c) for _l, t, c in dc.class_choices(tables)]
        self.assertEqual(got, [("DPL2", 19), ("DPL1", 1), ("DPL1", 5), ("DPL2", 17)])

    def test_the_four_tables_edits_go_into_one_list_and_the_restore_target_has_none(self):
        p = dc.plan({t: [row(1, 1, 3, 70, 80)] for t in dc.TIERS}, 1, {"PSPD": 1})
        self.assertEqual([e["table"] for e in dc.all_edits(p)], list(dc.TIERS))
        entry = {"ast": "a.ast", "index": 46, "start": 5, "size": 9}
        self.assertEqual(dc.restore_target_for(entry)["edits"], [])


if __name__ == "__main__":
    unittest.main()
