import unittest

import guiHC09


class ContractTotalsTests(unittest.TestCase):
    def test_the_bonus_total_goes_into_both_pvsb_and_psbo(self):
        got = guiHC09.contract_totals([1200, 100, 0, 0, 0, 0, 0], [500, 40, 0, 0, 0, 0, 0], 0)
        self.assertEqual(got, {"PCSA": 1700, "PTSA": 1840, "PVSB": 540, "PSBO": 540})

    def test_pcsa_is_the_current_year_and_the_year_index_is_kept_inside_the_contract(self):
        salaries, bonuses = [10, 20, 30, 40, 0, 0, 0], [1, 2, 3, 4, 0, 0, 0]
        self.assertEqual(guiHC09.contract_totals(salaries, bonuses, 2)["PCSA"], 33)
        self.assertEqual(guiHC09.contract_totals(salaries, bonuses, -3)["PCSA"], 11)
        self.assertEqual(guiHC09.contract_totals(salaries, bonuses, 99)["PCSA"], 0)

    def test_psbo_is_clamped_to_its_narrower_13_bit_field(self):
        got = guiHC09.contract_totals([0] * 7, [8191] * 7, 0)
        self.assertEqual((got["PVSB"], got["PSBO"]), (16383, 8191))
        self.assertEqual(got["PTSA"], 8191 * 7)
        self.assertEqual(guiHC09.PLAYER_PSBO_MAX_VALUE, (1 << 13) - 1)

    def test_folding_the_bonuses_writes_what_is_left_within_each_field(self):
        headers = [f"PSA{i}" for i in range(7)] + [f"PSB{i}" for i in range(7)] + ["PVSB", "PSBO"]
        row = {h: "0" for h in headers}
        row.update({"PSA0": "16000", "PSB0": "8000", "PSB1": "8000", "PSA1": "16300", "PVSB": "16000", "PSBO": "8000"})
        changed, overflowed = guiHC09.fold_bonuses_into_salary(row, headers)
        self.assertTrue(changed and overflowed)
        left = int(row["PSB0"]) + int(row["PSB1"])
        self.assertGreater(left, guiHC09.PLAYER_PSBO_MAX_VALUE)                 # the part that does not fit in a salary stays in the bonus
        self.assertEqual(row["PVSB"], str(min(left, 16383)))
        self.assertEqual(row["PSBO"], "8191")


if __name__ == "__main__":
    unittest.main()
