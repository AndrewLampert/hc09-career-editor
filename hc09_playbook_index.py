#!/usr/bin/env python3
"""Build a read-only, per-playbook inventory from hc09-bridge CSV exports.

Expected input files use the bridge's play-sets-scan naming:
  pbpl_qkl_boot_40.csv, setl_qkl_boot_40.csv, pbai_qkl_boot_40.csv
Optional:
  form_qkl_boot_40.csv
  pppn.csv (exported separately from the shipped-name entry)

This tool does not modify archives or saves.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def as_int(row: dict[str, str], key: str, default: int = 0) -> int:
    value = row.get(key, "")
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def first_value(row: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def build_index(pbpl_rows, setl_rows, pbai_rows, form_rows=(), pppn_rows=()):
    """Return (book_index, diagnostics); all joins are by the game's numeric IDs."""
    plays = {as_int(row, "PLYL"): row for row in pbpl_rows if row.get("PLYL") not in (None, "")}
    sets = {as_int(row, "SETL"): row for row in setl_rows if row.get("SETL") not in (None, "")}
    formations = {as_int(row, "FORM"): first_value(row, "name", "NAME") for row in form_rows}
    overrides = {
        (as_int(row, "BOKL"), as_int(row, "PLYL")): first_value(row, "PPPM", "name", "NAME")
        for row in pppn_rows
    }

    books = defaultdict(dict)
    diagnostics = {
        "pbai_rows": len(pbai_rows),
        "unique_play_records": len(plays),
        "unique_set_records": len(sets),
        "missing_pbpl": [],
        "missing_setl": [],
        "duplicate_book_play_rows": 0,
    }
    seen_rows = set()

    for ai in pbai_rows:
        if ai.get("BOKL") in (None, "") or ai.get("PBPL") in (None, ""):
            continue
        book_id = as_int(ai, "BOKL")
        play_id = as_int(ai, "PBPL")
        play = plays.get(play_id)
        if play is None:
            diagnostics["missing_pbpl"].append({"book_id": book_id, "play_id": play_id})
            continue

        key = (book_id, play_id)
        if key in seen_rows:
            diagnostics["duplicate_book_play_rows"] += 1
        seen_rows.add(key)
        item = books[book_id].setdefault(play_id, {
            "book_id": book_id,
            "play_id": play_id,
            "master_name": first_value(play, "name", "NAME"),
            "playbook_name": overrides.get(key, ""),
            "play_type": as_int(play, "PLYT", -1),
            "set_id": as_int(play, "SETL", as_int(ai, "SETL", -1)),
            "set_name": "",
            "formation_id": -1,
            "formation_name": "",
            "ai_rows": [],
            "pbai_set_ids": [],
        })

        set_row = sets.get(item["set_id"])
        if set_row is None:
            diagnostics["missing_setl"].append({"book_id": book_id, "play_id": play_id, "set_id": item["set_id"]})
        else:
            item["set_name"] = first_value(set_row, "name", "NAME")
            item["formation_id"] = as_int(set_row, "FORM", -1)
            item["formation_name"] = formations.get(item["formation_id"], "")

        ai_set_id = as_int(ai, "SETL", -1)
        if ai_set_id not in item["pbai_set_ids"]:
            item["pbai_set_ids"].append(ai_set_id)
        item["ai_rows"].append({
            "group": as_int(ai, "AIGR", -1),
            "weight": as_int(ai, "prct", -1),
        })

    result = {}
    for book_id, play_map in sorted(books.items()):
        rows = []
        for play_id, item in sorted(play_map.items()):
            item["ai_rows"].sort(key=lambda row: (row["group"], row["weight"]))
            item["pbai_set_ids"].sort()
            rows.append(item)
        result[str(book_id)] = {"book_id": book_id, "play_count": len(rows), "plays": rows}
    diagnostics["book_count"] = len(result)
    diagnostics["book_play_links"] = sum(book["play_count"] for book in result.values())
    return result, diagnostics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", required=True, type=Path, help="directory written by play-sets-scan")
    parser.add_argument("--prefix", default="qkl_boot_40", help="archive/entry suffix, normally qkl_boot_40")
    parser.add_argument("--pppn", type=Path, help="optional PPPN CSV exported separately (BOKL,PLYL,PPPM)")
    parser.add_argument("--form-csv", type=Path, help="optional FORM CSV from a fe2ig copy (FORM,name)")
    parser.add_argument("--out", type=Path, default=Path("playbook-index"), help="output directory")
    args = parser.parse_args()

    def table(name):
        return read_csv(args.dir / f"{name.lower()}_{args.prefix}.csv")

    pbpl = table("PBPL")
    setl = table("SETL")
    pbai = table("PBAI")
    form = read_csv(args.form_csv) if args.form_csv else table("FORM")
    pppn = read_csv(args.pppn) if args.pppn else []

    missing = [name for name, rows in (("PBPL", pbpl), ("SETL", setl), ("PBAI", pbai)) if not rows]
    if missing:
        parser.error("missing required table export(s): " + ", ".join(missing))

    index, diagnostics = build_index(pbpl, setl, pbai, form, pppn)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "playbooks.json").write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    columns = ("book_id", "play_id", "playbook_name", "master_name", "formation_id", "formation_name",
               "set_id", "set_name", "play_type", "ai_groups", "ai_weights", "pbai_set_ids")
    with (args.out / "playbook_index.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for book in index.values():
            for play in book["plays"]:
                writer.writerow({
                    **{key: play[key] for key in columns if key in play},
                    "ai_groups": ";".join(str(row["group"]) for row in play["ai_rows"]),
                    "ai_weights": ";".join(str(row["weight"]) for row in play["ai_rows"]),
                    "pbai_set_ids": ";".join(str(value) for value in play["pbai_set_ids"]),
                })
    (args.out / "diagnostics.json").write_text(json.dumps(diagnostics, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(args.out), "diagnostics": diagnostics}, indent=2))


if __name__ == "__main__":
    main()
