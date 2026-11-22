import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

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


    def test_playbook_name_overrides_are_scoped_to_book_and_play(self):
        pbpl = [{"PLYL": "10", "SETL": "5", "name": "Master name", "PLYT": "1"}]
        setl = [{"SETL": "5", "name": "Set", "FORM": "1"}]
        pbai = [
            {"BOKL": "1", "PBPL": "10", "SETL": "5"},
            {"BOKL": "2", "PBPL": "10", "SETL": "5"},
        ]
        pppn = [
            {"BOKL": "1", "PLYL": "10", "PPPM": "Book One name"},
            {"BOKL": "2", "PLYL": "10", "PPPM": "Book Two name"},
        ]
        index, _ = build_index(pbpl, setl, pbai, pppn_rows=pppn)
        self.assertEqual(index["1"]["plays"][0]["playbook_name"], "Book One name")
        self.assertEqual(index["2"]["plays"][0]["playbook_name"], "Book Two name")
        self.assertEqual(index["1"]["plays"][0]["master_name"], "Master name")

    def test_play_set_and_ai_set_ids_are_both_retained(self):
        pbpl = [{"PLYL": "10", "SETL": "5", "name": "Play", "PLYT": "1"}]
        setl = [
            {"SETL": "5", "name": "Master set", "FORM": "1"},
            {"SETL": "6", "name": "AI row set", "FORM": "2"},
        ]
        pbai = [{"BOKL": "1", "PBPL": "10", "SETL": "6", "AIGR": "1", "prct": "50"}]
        index, diagnostics = build_index(
            pbpl, setl, pbai,
            form_rows=[{"FORM": "1", "name": "I Form"}, {"FORM": "2", "name": "Shotgun"}],
        )
        play = index["1"]["plays"][0]
        self.assertEqual(play["set_id"], 5)
        self.assertEqual(play["set_name"], "Master set")
        self.assertEqual(play["formation_name"], "I Form")
        self.assertEqual(play["pbai_set_ids"], [6])
        self.assertEqual(diagnostics["missing_setl"], [])
        self.assertEqual(diagnostics["pbai_set_mismatches"], [{
            "book_id": 1,
            "play_id": 10,
            "play_name": "Play",
            "master_set_id": 5,
            "master_set_name": "Master set",
            "pbai_sets": [{
                "set_id": 6,
                "set_name": "AI row set",
                "formation_id": 2,
                "formation_name": "Shotgun",
            }],
        }])

    def test_missing_formation_name_does_not_lose_set_or_play(self):
        index, diagnostics = build_index(
            [{"PLYL": "10", "SETL": "5", "name": "Play", "PLYT": "1"}],
            [{"SETL": "5", "name": "Set", "FORM": "999"}],
            [{"BOKL": "1", "PBPL": "10", "SETL": "5"}],
        )
        play = index["1"]["plays"][0]
        self.assertEqual(play["set_name"], "Set")
        self.assertEqual(play["formation_id"], 999)
        self.assertEqual(play["formation_name"], "")
        self.assertEqual(diagnostics["missing_setl"], [])

    def test_cli_writes_consistent_json_csv_and_diagnostics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            output = root / "out"
            source.mkdir()
            fixtures = {
                "pbpl_qkl_boot_40.csv": "PLYL,SETL,name,PLYT\n10,5,Inside Zone,1\n",
                "setl_qkl_boot_40.csv": "SETL,name,FORM\n5,Ace,1\n",
                "pbai_qkl_boot_40.csv": "BOKL,PBPL,SETL,AIGR,prct\n1,10,5,2,75\n",
                "form_qkl_boot_40.csv": "FORM,name\n1,I Form\n",
            }
            for name, content in fixtures.items():
                (source / name).write_text(content, encoding="utf-8")
            script = Path(__file__).resolve().parents[1] / "hc09_playbook_index.py"
            result = subprocess.run(
                [sys.executable, str(script), "--dir", str(source), "--out", str(output)],
                capture_output=True, text=True, check=True,
            )
            index = json.loads((output / "playbooks.json").read_text(encoding="utf-8"))
            diagnostics = json.loads((output / "diagnostics.json").read_text(encoding="utf-8"))
            with (output / "playbook_index.csv").open(newline="", encoding="utf-8-sig") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(index["1"]["plays"][0]["master_name"], "Inside Zone")
            self.assertEqual(rows[0]["formation_name"], "I Form")
            self.assertEqual(rows[0]["ai_groups"], "2")
            self.assertEqual(diagnostics["book_play_links"], 1)
            self.assertIn('"book_count": 1', result.stdout)

    def test_cli_rejects_missing_required_exports(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            script = Path(__file__).resolve().parents[1] / "hc09_playbook_index.py"
            result = subprocess.run(
                [sys.executable, str(script), "--dir", str(source), "--out", str(root / "out")],
                capture_output=True, text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("missing required table export(s)", result.stderr)


if __name__ == "__main__":
    unittest.main()
