"""
HC09 / Franchise CSV Editor (GUI) - HC09 Safe Trade Edition
- Tkinter GUI (no external deps)
- Loads play.csv (players), optional drpk.csv (draft picks), optional slri.csv (salary cap), optional trvw.csv (trainers), optional coch.csv (coaches), optional gmvw.csv (GMs)
- Case-sensitive columns ON PURPOSE (we only normalize invisible junk like BOM/whitespace)
- Stat editor shows ONLY stats that have descriptions (STAT_META)
- MAX columns are HARD-CODED for YOUR export (no duplicates, no guessing)
- Name editor (PFNA/PLNA) is ON the Players + Stats screen (with sanitizing to avoid crashes)
- Raw Column Editor lets you edit ANY column for the selected player
- Trading:
    * "Trade Players (Safe Swap)": swaps player data across two teams WITHOUT
      changing TGID - the only confirmed-safe way to move a player between two
      REAL teams (a bare TGID overwrite crashes the game on day-advance, even
      with a perfectly consistent depth chart on both sides - see the comment
      above the toolbar buttons in App._build for the full test history).
    * "Sign Free Agent...": pulls a player out of Free Agents/the Secret pool
      onto a real team with a new contract - confirmed safe (pools aren't part
      of the same roster/depth-chart bookkeeping a real team is).

Run:
  python guiHC09.py
"""

import csv
import os
import re
from collections import Counter, defaultdict
import json
import random
import shutil
import tempfile
import threading
import time
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# -----------------------------
# Bridge (direct .db load/save, no more manual CSV export/import via HC09Editor)
# -----------------------------
NODE_EXE = "node"
BRIDGE_JS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hc09-bridge", "bridge.js")

# Recent-files list (QoL). Save files are always literally named "USR-DATA",
# so the useful distinguishing part to show is the parent save folder name
# (e.g. "BLUS30128-CAREER-TEST"), not the filename itself.
RECENT_FILES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".hc09_recent_files.json")
RECENT_FILES_MAX = 6

def load_recent_files():
    try:
        with open(RECENT_FILES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return [p for p in data if isinstance(p, str)]
    except Exception:
        pass
    return []

def save_recent_file(path):
    recents = [p for p in load_recent_files() if p != path]
    recents.insert(0, path)
    recents = recents[:RECENT_FILES_MAX]
    try:
        with open(RECENT_FILES_PATH, "w", encoding="utf-8") as f:
            json.dump(recents, f)
    except Exception:
        pass
    return recents

def remove_recent_file(path):
    recents = [p for p in load_recent_files() if p != path]
    try:
        with open(RECENT_FILES_PATH, "w", encoding="utf-8") as f:
            json.dump(recents, f)
    except Exception:
        pass
    return recents

def recent_file_display(path):
    """Show the save folder name (e.g. BLUS30128-CAREER-TEST) since every
    save file is literally named USR-DATA and wouldn't be distinguishable."""
    folder = os.path.basename(os.path.dirname(path))
    return folder or path

# -----------------------------
# Motivator Boost (replicates the in-game "Motivator" coach perk)
#
# Confirmed via controlled test (44 Falcons players, save BLUS30128-CAREER-TESTE,
# uniform potential baseline, varied headroom 0-50, varied ceiling 70/90, all
# checked against age/position/PLRN/dev-trait fields):
#   - Purchasing Motivator applies ONE random flat integer delta (observed
#     range 5-9, roughly uniform - chi2=4.64 on 44 samples, not significant
#     enough to prove weighting) to a player's potential.
#   - That SAME delta is added to every "X"-suffix potential/max stat field
#     for that player, EXCEPT Acceleration cap (PACX) and Stamina cap (PSAX),
#     which never moved for any of the 44 test subjects.
#   - Current stat values are never touched, even for players with zero
#     headroom (current == potential already).
#   - Clamped at 99 same as any other potential stat.
# This app-side reimplementation lets you apply that same boost to any
# player on demand, without needing to actually buy the perk in-game.
# State (mode preference + per-save boost history) is stored in a local app
# file, NOT written into the save file, per user request - so it survives
# closing/reopening the app but never touches game data on its own.
# -----------------------------
MOTIVATOR_STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".hc09_motivator_state.json")
MOTIVATOR_EXCLUDED_BASE_KEYS = {"PACC", "PSTA"}  # Acceleration / Stamina caps - never boosted in real testing
MOTIVATOR_RANDOM_MIN = 5
MOTIVATOR_RANDOM_MAX = 9
MOTIVATOR_MODE_RANDOM = "Random (5-9)"
MOTIVATOR_MODE_CUSTOM = "Custom amount"

def load_motivator_state():
    try:
        with open(MOTIVATOR_STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                data.setdefault("last_mode", MOTIVATOR_MODE_RANDOM)
                data.setdefault("last_custom_value", "10")
                data.setdefault("include_excluded_stats", False)
                data.setdefault("team_skip_already_boosted", True)
                data.setdefault("boosts", {})
                return data
    except Exception:
        pass
    return {
        "last_mode": MOTIVATOR_MODE_RANDOM, "last_custom_value": "10",
        "include_excluded_stats": False, "team_skip_already_boosted": True, "boosts": {},
    }

def save_motivator_state(state):
    try:
        with open(MOTIVATOR_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception:
        pass
DB_TABLE_FILES = {
    "PLAY": "play.csv",
    "DRPK": "drpk.csv",
    "SLRI": "slri.csv",
    "TRVW": "trvw.csv",
    "COCH": "coch.csv",
    "GMVW": "gmvw.csv",
    "GMSK": "gmsk.csv",
    "CSKL": "cskl.csv",
    "TEAM": "team.csv",
    "cINF": "cinf.csv",
    "TPHS": "tphs.csv",
}
# (table code, CSVModel rows attr, headers attr, path attr) - drives
# load_all_from_db/save_to_db/_finish_load's per-table wiring below, so
# adding a table only means adding one row here instead of touching all
# three functions by hand (a table added to DB_TABLE_FILES but missed in
# one of those three used to fail silently - see load_all_from_db).
DB_TABLE_ATTRS = [
    ("PLAY", "players", "player_headers", "play_path"),
    ("DRPK", "picks", "pick_headers", "drpk_path"),
    ("SLRI", "salaries", "salary_headers", "slri_path"),
    ("TRVW", "trainers", "trainer_headers", "trainer_path"),
    ("COCH", "coaches", "coach_headers", "coach_path"),
    ("GMVW", "gms", "gm_headers", "gm_path"),
    ("GMSK", "gmsk", "gmsk_headers", "gmsk_path"),
    ("CSKL", "cskl", "cskl_headers", "cskl_path"),
    ("TEAM", "team", "team_headers", "team_path"),
    ("cINF", "cinf", "cinf_headers", "cinf_path"),
    ("TPHS", "tphs", "tphs_headers", "tphs_path"),
]

# cINF (1 row, global/save-level state) has a SEYR field ("Season Year" per
# the reference spreadsheet). DISPROVEN as a live "current season" indicator:
# initially looked confirmed (one save, confirmed in-game as showing 2008,
# had SEYR=255, and SEYR+1753=2008) - but a SECOND save, independently
# confirmed in-game as showing 2009, ALSO has SEYR=255. It isn't dynamically
# tracking the season the way it first appeared to; that first match was a
# coincidence. NOT used anywhere anymore (see refresh_picks's comment) - left
# defined only in case cINF's real meaning gets solved later.
CINF_SEASON_YEAR_OFFSET = 1753  # UNRELIABLE - do not use for a "current year" display, see comment above

# TMSA (Team Salary Cap, on the TEAM table, keyed by TGID): confirmed via a
# live test - editing a player's contract updates their own displayed cap hit
# correctly, but the team-wide "Team Salary Cap" / "Salary Cap Room" numbers
# on the Team Roadmap screen do NOT update to match unless TMSA is updated too
# (confirmed: bumped Keith Brooking's (Falcons LB) cap hit by +$3.0M in-game,
# his own card correctly showed the new number after a restart, but Team
# Salary Cap stayed frozen at the old value). TMSA is in units of $10,000
# (confirmed: TMSA=4953 for the Falcons matches the displayed "$49.53M").
# "Salary Cap Room" is NOT separately stored - it's NFL cap (SCAD, in the
# SLRI table, raw dollars, e.g. 116000000) minus TMSA*10000, computed live
# (confirmed: 11600 - 4953 = 6647, matching the displayed "$66.47M" exactly).
TEAM_SALARY_CAP_FIELD = "TMSA"
TEAM_SALARY_CAP_UNIT = 10000  # 1 TMSA unit = $10,000
TEAM_SALARY_CAP_MAX_VALUE = 524287  # TMSA is a 19-bit field (2^19 - 1), confirmed via bridge.js fields

def format_cap_dollars(raw_units):
    """Format a raw PSA/PSB/TMSA-style unit value (1 unit = $10,000) as a
    plain comma-separated dollar amount, e.g. 40 -> '$400,000'."""
    try:
        dollars = int(raw_units) * TEAM_SALARY_CAP_UNIT
    except (TypeError, ValueError):
        return "?"
    return f"${dollars:,}"

# PPGR ("Position Skill Map") is a literal position-bucket code stored on each
# row of the GMSK and CSKL tables - NOT a row-storage-order convention. Cracked
# via a community reference spreadsheet (Discord: NFL Head Coach modding
# server, "HC EDITOR TRANSLATE.xlsx" -> VALUE TRANSLATION sheet's own
# PPGR/TRANS code columns), then independently confirmed: cross-referencing
# Jim Andrews' (Bears GM) GMSK PPGR values against his already-confirmed
# Potential Evaluation bucket order reproduced the exact same 0-9 mapping the
# spreadsheet documents. Further confirmed live (custom "New Coach" PNid 977 +
# Falcons GM PNid 2061, save BLUS30128-CAREER-TEST): writing a distinct
# 1-2-3-4-5-repeating pattern to every PPGR row across all 3 Coach Development
# categories and both GM GMSK stats landed on exactly the right position on
# every screen after a full RPCS3 restart (including confirming the game
# clamps a displayed "current" down to "max" whenever current > max, which is
# exactly what showed up on the rows deliberately set that way). Row STORAGE
# order is NOT consistent between records (confirmed: Jauron's CSKL rows and
# Andrews' GMSK rows were ordered differently despite both using this same
# PPGR scheme) - always look up by each row's own PPGR field, never assume a
# fixed position ordering.
PPGR_TO_POSITION = {
    "0": "QB", "1": "RB", "2": "WR", "3": "TE", "4": "OL",
    "5": "DL", "6": "LB", "7": "DB", "8": "K", "9": "P",
}

# GM "Potential Evaluation" scouting skill, confirmed in-game (see conversation
# history for the verification): lives in the separate GMSK table, joined to
# GMVW via PNid. SKRE = current value, SKRM = max. Each GM has a fixed block of
# 10 GMSK rows (one per position bucket, identified via PPGR - see above).
# Some GMs (freshly appointed, never invested in this skill) have zero rows.
GM_POTENTIAL_EVAL_BUCKETS = ["DB", "DL", "K", "LB", "OL", "P", "QB", "RB", "TE", "WR"]
GM_POTENTIAL_EVAL_CUR_FIELD = "SKRE"
GM_POTENTIAL_EVAL_MAX_FIELD = "SKRM"
GM_POTENTIAL_EVAL_MIN_VALUE = 1
GM_POTENTIAL_EVAL_MAX_VALUE = 5

# GM "Rookie Scouting" - a SEPARATE stat from Potential Evaluation (confirmed:
# they can differ, e.g. WR showed 5 vs 4 in one save). Lives in the same GMSK
# table/row-block as Potential Evaluation. Field pairing was originally coded
# backwards (SKSX assumed current, SKSC assumed max) - corrected per the same
# community reference spreadsheet that cracked PPGR (see above) and confirmed
# live on the Falcons GM (PNid 2061): SKSC = current, SKSX = potential/max.
# The row-to-bucket order question that used to block per-bucket editing is
# moot now - PPGR gives the bucket directly (see PPGR_TO_POSITION).
GM_ROOKIE_SCOUTING_CUR_FIELD = "SKSC"
GM_ROOKIE_SCOUTING_MAX_FIELD = "SKSX"
GM_ROOKIE_SCOUTING_MIN_VALUE = 1
GM_ROOKIE_SCOUTING_MAX_VALUE = 5

# Synthetic (not real file field codes) tree column keys for the GM tab's
# Potential Evaluation and Rookie Scouting cur/max columns, one pair per
# position bucket.
GM_POTENTIAL_EVAL_COLUMNS = []
GM_ROOKIE_SCOUTING_COLUMNS = []
for _b in GM_POTENTIAL_EVAL_BUCKETS:
    GM_POTENTIAL_EVAL_COLUMNS.append(f"PE_{_b}_C")
    GM_POTENTIAL_EVAL_COLUMNS.append(f"PE_{_b}_M")
    GM_ROOKIE_SCOUTING_COLUMNS.append(f"RS_{_b}_C")
    GM_ROOKIE_SCOUTING_COLUMNS.append(f"RS_{_b}_M")
del _b

def parse_pe_column(colname):
    """Return (bucket, is_max) for a synthetic PE_xx_C/PE_xx_M column, else None."""
    if not colname.startswith("PE_"):
        return None
    parts = colname.split("_")
    if len(parts) != 3 or parts[1] not in GM_POTENTIAL_EVAL_BUCKETS or parts[2] not in ("C", "M"):
        return None
    return parts[1], parts[2] == "M"

def parse_rs_column(colname):
    """Return (bucket, is_max) for a synthetic RS_xx_C/RS_xx_M column, else None."""
    if not colname.startswith("RS_"):
        return None
    parts = colname.split("_")
    if len(parts) != 3 or parts[1] not in GM_POTENTIAL_EVAL_BUCKETS or parts[2] not in ("C", "M"):
        return None
    return parts[1], parts[2] == "M"

# Coach "Development" skills (Physical/Intangible/Learning), 3 categories x 10
# position buckets, confirmed in-game via the same PPGR-keyed CSKL table used
# by GM's Potential Evaluation/Rookie Scouting. Field pairs per the community
# reference spreadsheet, confirmed live (custom "New Coach", PNid 977): a
# distinct value pattern written to every position row across all 3
# categories matched exactly in-game after a full restart, including the
# current>max clamping behavior on the rows deliberately set that way.
COACH_DEV_CATEGORIES = {
    # 2-letter code -> (current field, max/potential field, display name)
    "PH": ("SKPD", "SKPM", "Physical"),
    "IN": ("SKID", "SKIM", "Intangible"),
    "LR": ("SKLD", "SKLM", "Learning"),
}
COACH_DEV_MIN_VALUE = 1
COACH_DEV_MAX_VALUE = 5

# Synthetic tree column keys for the Coach tab's Development columns:
# DV_<cat>_<bucket>_C / DV_<cat>_<bucket>_M, one pair per category per bucket.
COACH_DEV_COLUMNS = []
for _cat in COACH_DEV_CATEGORIES:
    for _b in GM_POTENTIAL_EVAL_BUCKETS:
        COACH_DEV_COLUMNS.append(f"DV_{_cat}_{_b}_C")
        COACH_DEV_COLUMNS.append(f"DV_{_cat}_{_b}_M")
del _cat, _b

def parse_dev_column(colname):
    """Return (cat, bucket, is_max) for a synthetic DV_xx_yy_C/M column, else None."""
    if not colname.startswith("DV_"):
        return None
    parts = colname.split("_")
    if len(parts) != 4 or parts[1] not in COACH_DEV_CATEGORIES or parts[2] not in GM_POTENTIAL_EVAL_BUCKETS or parts[3] not in ("C", "M"):
        return None
    return parts[1], parts[2], parts[3] == "M"

# -----------------------------
# CONSTANTS / METADATA
# -----------------------------
TEAM_NAMES = {
    "1": "Bears (Chicago)", "2": "Bengals (Cincinnati)", "3": "Bills (Buffalo)", "4": "Broncos (Denver)",
    "5": "Browns (Cleveland)", "6": "Buccaneers (Tampa Bay)", "7": "Cardinals (Arizona)", "8": "Chargers (Los Angeles)",
    "9": "Chiefs (Kansas City)", "10": "Colts (Indianapolis)", "11": "Cowboys (Dallas)", "12": "Dolphins (Miami)",
    "13": "Eagles (Philadelphia)", "14": "Falcons (Atlanta)", "15": "49ers (San Francisco)", "16": "Giants (New York)",
    "17": "Jaguars (Jacksonville)", "18": "Jets (New York)", "19": "Lions (Detroit)", "20": "Packers (Green Bay)",
    "21": "Panthers (Carolina)", "22": "Patriots (New England)", "23": "Raiders (Las Vegas)", "24": "Rams (Los Angeles)",
    "25": "Ravens (Baltimore)", "26": "Commanders (Washington)", "27": "Saints (New Orleans)", "28": "Seahawks (Seattle)",
    "29": "Steelers (Pittsburgh)", "30": "Titans (Tennessee)", "31": "Vikings (Minnesota)", "32": "Texans (Houston)",
    # Free Agents was wrongly coded as TGID 33 - confirmed against real save data
    # (checked via the community reference spreadsheet's own team table, then
    # cross-verified in the actual save file: 412 real players carry TGID 1009,
    # zero carry 33). Fixed to the real value.
    "1009": "Free Agents", "1015": "Draft Class",
    # "SECRET" per the same spreadsheet's team table - confirmed 15 real players
    # sit in this pool in the test save. Per the user (NFL Head Coach 09 player,
    # not independently verified in-game by us): these are "Game Changers" -
    # special unlockable players that are meant to show up in-game with a
    # distinct visual treatment, separate from the normal Free Agents pool.
    # Signing one via Sign Free Agent is confirmed to work (safe, same as any
    # other free agent) - whether the special "Game Changers" presentation
    # still shows correctly for a signed one hasn't specifically been checked.
    "1013": "Game Changer Players",
}

# PSXP ("Portrait ID" per the reference spreadsheet) is the player's face/photo.
# Confirmed by the user: PSXP=0 displays as a plain grey silhouette in-game (not
# an error/missing state) - this is what every Game Changer Players pool player
# has (see TEAM_NAMES "1013" comment). NOT otherwise investigated - a future
# feature idea is custom portraits (uploading your own, or reassigning one of
# the game's existing in-game portraits to a player) via this field, but the ID
# space/lookup mechanism (what values are valid, where the actual images live)
# hasn't been explored at all yet.
PLAYER_PORTRAIT_CODE = "PSXP"

PLAYER_FIRST_NAME_CODE = "PFNA"
PLAYER_LAST_NAME_CODE = "PLNA"
PLAYER_POS_CODE = "PPOS"
PREFERRED_TEAM_COLS = ["TID", "TEAM", "TMID", "TGID"]  # TGID last as fallback

# DRPK field meanings, per the NFL Head Coach modding Discord (independently
# corroborated: someone else there changed DPID directly and got their picks
# back successfully, the same approach used here):
#   DPID = current owning team, DPOD = ORIGINAL owning team, DPNM/DPIX
#   together are described as the pick's "ID". DPNM is confirmed 0-indexed
#   for the CURRENT year only (1st overall = 0, 45th = 44); for FUTURE years
#   it's not a pick number at all (see refresh_picks's comment). DPYO = year
#   offset (0 = current year, matching PPGR-style small-int-offset fields
#   elsewhere in this file).
#   CONFIRMED UNSAFE, per the same Discord thread's own caution ("might mess
#   up the game later since the trade details are in [a separate] list") and
#   directly reproduced: writing DPID alone crashed the user's game on
#   day-advance. See the investigation log above _build_picks_tab for the
#   full writeup - pick reassignment was removed, the tab is view-only.
#   DPOD (see DRAFT_PICK_ORIGINAL_TEAM) is display-only, never written.
DRAFT_PICK_ID = "DPID"
DRAFT_PICK_ORIGINAL_TEAM = "DPOD"
DRAFT_PICK_NUM = "DPNM"
DRAFT_PICK_YEAR = "DPYO"

SALARY_CAP_KEY = "SCAD"
PLAYER_CONTRACT_COLS = [f"PSA{i}" for i in range(7)]
PLAYER_BONUS_COLS = [f"PSB{i}" for i in range(7)]
PLAYER_SALARY_MAX_VALUE = 16383
PLAYER_BONUS_MAX_VALUE = 8191
# PCSA/PTSA/PVSB are derived (summed) fields, not directly entered - their own
# bit-widths (14/16/14, confirmed via bridge.js fields) are each narrower than
# what per-field-valid PSA/PSB sums can add up to, so they need their own clamp.
PLAYER_PCSA_MAX_VALUE = 16383
PLAYER_PTSA_MAX_VALUE = 65535
PLAYER_PVSB_MAX_VALUE = 16383


def fold_bonuses_into_salary(row, headers):
    """Move each contract year's bonus (PSBn) into that same year's salary
    (PSAn) and zero the bonus, so every year's cap hit stays exactly the same
    while the guaranteed money (the part that turns into a cap penalty when a
    player is cut or traded) goes away. PCSA/PTSA are sums of salary+bonus per
    year, so they're unchanged by this; PVSB and PSBO (identical in every
    player in a real save checked, and the signing-bonus total the sign dialog
    already derives from the PSB sum) are rewritten to match what's left.

    Salary is a narrower field than salary+bonus can reach (at least one real
    player already has a combined year over the limit), so if a year's total
    doesn't fit, the salary is filled to its max and the remainder stays in
    that year's bonus rather than being silently dropped - the cap hit is
    preserved either way. Returns (changed, overflowed)."""
    changed = False
    overflowed = False
    has_bonus_cols = False
    for sal_col, bon_col in zip(PLAYER_CONTRACT_COLS, PLAYER_BONUS_COLS):
        if bon_col not in headers:
            continue
        has_bonus_cols = True
        bonus = safe_int(row.get(bon_col, "")) or 0
        if bonus <= 0 or sal_col not in headers:
            continue
        salary = safe_int(row.get(sal_col, "")) or 0
        combined = salary + bonus
        new_salary = min(combined, PLAYER_SALARY_MAX_VALUE)
        new_bonus = combined - new_salary
        row[sal_col] = str(new_salary)
        row[bon_col] = str(new_bonus)
        changed = True
        if new_bonus:
            overflowed = True
    if has_bonus_cols:
        remaining = sum(safe_int(row.get(c, "")) or 0 for c in PLAYER_BONUS_COLS if c in headers)
        for col in ("PVSB", "PSBO"):
            if col in headers:
                new_val = str(min(remaining, PLAYER_PVSB_MAX_VALUE))
                if row.get(col, "") != new_val:
                    row[col] = new_val
                    changed = True
    return changed, overflowed


def sort_table_cells(rows, reverse):
    """rows: list of (cell_text, iid). Plain numbers - or text that starts with
    one, like the "11: Cowboys (Dallas)" team display - sort numerically;
    everything else (names, "-", "N/A", blanks) sorts as case-insensitive text
    after all the numbers, in both directions, so missing values never end up
    at the top of a descending sort. Cells with the same number are ordered by
    their text (so "3-2-6" comes before "3-4 Pressure"); identical cells keep
    their previous relative order, since Python's sort is stable."""
    numeric, other = [], []
    for text, iid in rows:
        v = (text or "").strip()
        num = None
        try:
            num = float(v)
        except ValueError:
            m = re.match(r"^-?\d+(\.\d+)?", v)
            if m:
                num = float(m.group(0))
        if num is not None:
            numeric.append((num, v.lower(), iid))
        else:
            other.append((v.lower(), iid))
    numeric.sort(key=lambda r: (r[0], r[1]), reverse=reverse)
    other.sort(key=lambda r: r[0], reverse=reverse)
    return [r[2] for r in numeric] + [iid for _, iid in other]


PLAYER_LIST_SORT_OPTIONS = ["Position", "Name", "OVR (high first)", "Age (oldest first)", "Salary (highest first)"]


STAFF_SKPT_MAX_VALUE = 131071
AGE_COL = "PAGE"
YEARS_COL = "PYRP"

# -----------------------------
# Personality (PTId, present on both PLAY and COCH with identical encoding -
# confirmed via controlled test: PTId equals the 17-personality-type index,
# cross-checked against known in-game personalities on save
# BLUS30128-CAREER-DOLPHINS2 with zero mismatches across 20+ players/coaches).
# Reference data (52 traits x 17 types, each trait's real gameplay effects)
# is community-compiled (ebongreen, Operation Sports), not dev-confirmed.
# -----------------------------
PERSONALITY_DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "personality_traits_reference.json")

def load_personality_data():
    try:
        with open(PERSONALITY_DATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

PERSONALITY_DATA = load_personality_data()
PERSONALITY_PTID_TO_NAME = {}
PERSONALITY_NAME_TO_PTID = {}
if PERSONALITY_DATA and "save_field_ptid_mapping" in PERSONALITY_DATA:
    for _k, _v in PERSONALITY_DATA["save_field_ptid_mapping"]["ptid_to_personality"].items():
        PERSONALITY_PTID_TO_NAME[int(_k)] = _v
        PERSONALITY_NAME_TO_PTID[_v] = int(_k)

POSITIONS = {
    "0": "QB", "1": "HB", "2": "FB", "3": "WR", "4": "TE",
    "5": "LT", "6": "LG", "7": "C", "8": "RG", "9": "RT",
    "10": "LE", "11": "RE", "12": "DT", "13": "LOLB", "14": "MLB",
    "15": "ROLB", "16": "CB", "17": "FS", "18": "SS", "19": "K", "20": "P"
}

# Position display order (QB, HB, FB, WR, TE, OL, DL, LB, CB, FS, SS, K, P)
POSITION_ORDER = {
    "0": 0,    # QB
    "1": 1,    # HB
    "2": 2,    # FB
    "3": 3,    # WR
    "4": 4,    # TE
    "5": 5,    # LT
    "6": 6,    # LG
    "7": 7,    # C
    "8": 8,    # RG
    "9": 9,    # RT
    "10": 10,  # LE
    "12": 11,  # DT
    "11": 12,  # RE
    "13": 13,  # LOLB
    "14": 14,  # MLB
    "15": 15,  # ROLB
    "16": 16,  # CB
    "17": 17,  # FS
    "18": 18,  # SS
    "19": 19,  # K
    "20": 20,  # P
}

STAT_MAX_VALUE = 99

# -----------------------------
# Stat descriptions (only these appear in the Stat Editor)
# -----------------------------
STAT_META = {
    "PSPD": ("Speed", "Top-end running speed"),
    "PAGI": ("Agility", "Change of direction / lateral movement"),
    "PACC": ("Acceleration", "Burst to top speed"),
    "PSTR": ("Strength", "Power of player (blocking/tackling)"),
    "PAWR": ("Awareness", "Football IQ and reaction time"),
    "PSTA": ("Stamina", "Fatigue resistance"),
    "PINJ": ("Injury", "Durability / injury resistance"),
    "PLTR": ("Trucking", "Run through tackles / power after contact"),
    "PTGH": ("Toughness", "Plays through hits / durability vs big contact"),
    "PELU": ("Elusiveness", "Jukes and evasive moves"),
    "PBCV": ("Vision", "Ball carrier vision / cutbacks"),
    "PLSA": ("Stiff Arm", "Stiff-arm effectiveness"),
    "PLSM": ("Spin Move", "Spin move success"),
    "PLJM": ("Juke Move", "Juke effectiveness"),
    "PCAR": ("Carrying", "Ball security"),
    "PTHP": ("Throw Power", "QB arm strength"),
    "PTHA": ("Throw Accuracy", "Overall QB accuracy"),
    "PCTH": ("Catching", "Catch reliability"),
    "PLSC": ("Spectacular Catch", "Aggressive catches"),
    "PLCI": ("Catch In Traffic", "Catches through contact"),
    "PLRR": ("Route Running", "Route precision"),
    "PLRL": ("Release", "Beating press coverage"),
    "PJMP": ("Jump", "Vertical leap"),
    "PPBK": ("Pass Block", "Pass protection"),
    "PPBS": ("Pass Block Power", "Anchor vs power rush"),
    "PPBF": ("Pass Block Finesse", "Mirror finesse rush"),
    "PRBK": ("Run Block", "Run blocking"),
    "PRBS": ("Run Block Strength", "Run blocking strength / anchor"),
    "PLIB": ("Impact Blocking", "Dominant run-game blocks"),
    "PTAK": ("Tackling", "Tackle success"),
    "PLHT": ("Hit Power", "Big hit strength"),
    "PRBF": ("Run Block Finesse", "Footwork/finesse in run blocking (RunBlockFinesseRating)"),
    "PLPm": ("Power Move", "DL power pass rush move"),
    "PFMS": ("Finesse Move", "DL finesse pass rush move"),
    "PBSG": ("Block Shed", "Shedding blockers"),
    "PLPU": ("Pursuit", "Closing speed & angles"),
    "PLPR": ("Play Recognition", "Reads plays faster"),
    "PLMC": ("Man Coverage", "Man-to-man coverage"),
    "PLZC": ("Zone Coverage", "Zone awareness"),
    "PLPE": ("Press", "Jam WRs at line"),
    "PKPR": ("Kick Power", "Kicker leg strength"),
    "PKAC": ("Kick Accuracy", "FG accuracy"),
    "PKRT": ("Kick Return", "Return ability"),
    "PLRN": ("Learning", "Development speed"),
    # Found via a community reference spreadsheet (Discord: NFL Head Coach modding
    # server, "HC09_DB_AttributeMapping_2.xlsx"), NOT yet independently in-game
    # verified the way everything above was. Both are documented as "calculated"
    # values (Morale from PLYR_EGO, Importance not documented) rather than plain
    # stored ratings like the others - editing them may get silently overwritten
    # by the game's own recalculation rather than sticking. Try at your own risk.
    "PMOR": ("Morale", "Calculated from ego - editing may not persist, unverified"),
    "PIMP": ("Importance", "Formula undocumented - editing may not persist, unverified"),
}

# -----------------------------
# Staff skill fields (confirmed in-game against Bills GM/Trainer skill screens).
# Each is a (current_field, max_field) pair; in-game "Level" = both values equal
# once "Potential Reached". Range observed 1-5.
# -----------------------------
GM_SKILL_META = {
    "SKTD": ("Trade Negotiation", "SKTM"),
    "SKNG": ("Contract Negotiation", "SKNM"),
}
TRAINER_SKILL_META = {
    "TSIE": ("Injury Evaluation", "TSIM"),
    "TSRH": ("Rehabilitation", "TSRM"),
    "TSFR": ("Fatigue Recovery", "TSFM"),
}
STAFF_SKILL_MIN_VALUE = 1
STAFF_SKILL_MAX_VALUE = 5

# GM per-position "xxMP" fields in the GMVW table. Initially suspected to be
# the "Potential Evaluation" scouting skill (QBMP=1 happened to match
# "Potential Evaluation QB Level 1" for the same GM), but DISPROVEN by a
# direct in-game test: writing 18 distinct values (1-5) across these fields
# and doing a full RPCS3 restart still showed the original, unchanged
# Potential Evaluation numbers in-game. These fields are NOT what drives that
# UI. What they actually do is unknown - left here unlabeled/unmaxed rather
# than removed, since they're still real, safely-editable fields in the file;
# just don't assume the position-name guesses below mean anything.
GM_SCOUTING_FIELDS = [
    "CBMP", "FBMP", "HBMP", "QBMP", "GDMP", "DEMP", "TEMP", "KKMP", "TKMP",
    "MLMP", "OLMP", "KPMP", "CRMP", "WRMP", "FSMP", "GSMP", "SSMP", "DTMP",
]
GM_SCOUTING_MIN_VALUE = 0
GM_SCOUTING_MAX_VALUE = 5  # range observed in-game to be valid for this table's fields generally

# All staff numeric fields editable via double-click in the Trainer/Coach/GM
# tables, with their valid (min, max) range.
STAFF_NUMERIC_FIELDS = {
    "SKPT": (0, 131071),
    # Coach: all 4 named skills confirmed directly editable via in-game testing
    # (see the investigation log above COACH_MAXABLE_SKILL_FIELDS for the full
    # history). CSPC/CSPA/CSPF and CHEM were false leads, disproven/nonexistent.
    # SKPC=Play Call, SKST=Strategy, SKCR=Team Chemistry: each directly editable.
    # SKPA/SKPF: NOT independently meaningful - they're the two inputs to
    # Performance's real formula (Performance = MIN(SKPA, SKPF)).
    "SKPC": (1, 5), "SKPA": (1, 5), "SKPF": (1, 5), "SKST": (1, 5), "SKCR": (1, 5),
    # SKPX/SKSM/SKCM: the "potential"/max partners for Play Call/Strategy/Team
    # Chemistry - previously unknown to exist (the UI just showed a flat 5 for
    # max on these 3). Found via the same community reference spreadsheet that
    # cracked PPGR/CSKL/Rookie Scouting (see PPGR_TO_POSITION comment above).
    # Not yet independently in-game verified the way the Development stats and
    # Rookie Scouting were (no test round run on these specifically), but the
    # naming pattern is identical to every other confirmed SK-prefixed pair.
    "SKPX": (1, 5), "SKSM": (1, 5), "SKCM": (1, 5),
    # POVS (Overall): confirmed on COCH specifically - custom "New Coach" (PNid
    # 977, save BLUS30128-CAREER-TEST), writing 64 showed as 64 on the coach's
    # screen, range 0-99. POVS also exists as a column on GMVW/TRVW, but a live
    # "Max Selected" test showed GM's and Trainer's Overall did NOT respond to
    # writing/maxing it there - only added to COACH_MAXABLE_SKILL_FIELDS /
    # refresh_coach's columns, deliberately left out of GM/Trainer's (see those
    # lists' comments). The other 14 fields from the same "Coach Ratings" screen
    # group in a third-party editor's config (CCHM/CKNW/CMOT/COFF/CDEF plus 9
    # per-position CRxx ratings) were written in the same COCH test but NOT
    # visibly confirmed on any screen checked - inconclusive, not disproven
    # (could be AI-only backend inputs with no UI surface). Not implemented.
    "POVS": (0, 99),
    "SKTD": (STAFF_SKILL_MIN_VALUE, STAFF_SKILL_MAX_VALUE), "SKTM": (STAFF_SKILL_MIN_VALUE, STAFF_SKILL_MAX_VALUE),
    "SKNG": (STAFF_SKILL_MIN_VALUE, STAFF_SKILL_MAX_VALUE), "SKNM": (STAFF_SKILL_MIN_VALUE, STAFF_SKILL_MAX_VALUE),
    "TSIE": (STAFF_SKILL_MIN_VALUE, STAFF_SKILL_MAX_VALUE), "TSIM": (STAFF_SKILL_MIN_VALUE, STAFF_SKILL_MAX_VALUE),
    "TSRH": (STAFF_SKILL_MIN_VALUE, STAFF_SKILL_MAX_VALUE), "TSRM": (STAFF_SKILL_MIN_VALUE, STAFF_SKILL_MAX_VALUE),
    "TSFR": (STAFF_SKILL_MIN_VALUE, STAFF_SKILL_MAX_VALUE), "TSFM": (STAFF_SKILL_MIN_VALUE, STAFF_SKILL_MAX_VALUE),
    **{f: (GM_SCOUTING_MIN_VALUE, GM_SCOUTING_MAX_VALUE) for f in GM_SCOUTING_FIELDS},
}

# Skill fields maxed out per staff type when "Set to Max" is clicked (besides SKPT).
# GM_SCOUTING_FIELDS deliberately excluded - their in-game effect is unknown (see note above).
# POVS (Overall) is confirmed directly stored/displayed on COCH (see below), but
# a live "Max Selected" test showed GM's and Trainer's Overall did NOT change in
# response to writing/maxing POVS on their rows - it's evidently computed from
# their other skills there instead of being a plain stored value like on COCH.
# So POVS is Coach-only; deliberately excluded here.
GM_MAXABLE_SKILL_FIELDS = ["SKTD", "SKTM", "SKNG", "SKNM"]
TRAINER_MAXABLE_SKILL_FIELDS = ["TSIE", "TSIM", "TSRH", "TSRM", "TSFR", "TSFM"]
# Maxing SKPA and SKPF to 5 also maxes Performance (MIN(SKPA,SKPF) = 5).
# SKPX/SKSM/SKCM included alongside their current-value partners so maxing a
# coach also raises the cap on Play Call/Strategy/Chemistry, not just the
# current value (see STAFF_NUMERIC_FIELDS note above on their unverified status).
COACH_MAXABLE_SKILL_FIELDS = ["SKPC", "SKPX", "SKPA", "SKPF", "SKST", "SKSM", "SKCR", "SKCM", "POVS"]

# ======================================================================

# COACH SKILL INVESTIGATION LOG - ALL 4 NAMED SKILLS NOW CONFIRMED
# =============================================================================
# The COCH table has ~200 fields and no obvious names for a coach's skills -
# the field->skill mapping below was reverse-engineered by writing test values
# to a save and checking the in-game "Staff Skills Selection" screen after a
# FULL RPCS3 restart (a soft in-game reload does NOT pick up file changes -
# confirmed the hard way multiple times). Testing used two disposable test
# saves under dev_hdd0/.../savedata/: BLUS30128-CAREER-TEST (Bears GM Jim
# Andrews, PNid 2048; Bills coach Dick Jauron, PNid 0) and
# BLUS30128-CAREER-COACHTEST (a custom "New Coach", TGID 3 / Bills, PNid 977,
# SKPT=50000, all skills started at 1 - useful because ANY field showing "1"
# for him was a viable untested candidate). The hc09-bridge CLI (bridge.js)
# has an `inspect` command to list all tables/fields/record-counts, a `fields`
# command to dump a table's raw field offsets/bit-widths (used to rule out a
# bit-packing bug as an explanation for one contradictory result early on),
# and `export`/`import` for reading/writing values via CSV round-trip.
#
# CONFIRMED (every field below uses the "SK" prefix - a real, consistent
# naming pattern once discovered; every "CS"-prefixed sibling field tried
# turned out to be an unrelated red herring, see DISPROVEN below):
#   - Play Call = SKPC directly (whatever value you write is exactly what
#     shows in-game). Max always displays as a fixed 5.
#   - Strategy = SKST directly. Confirmed across 2 rounds with different
#     values (SKST=4 -> Strategy showed 4; SKST=1 -> Strategy showed 1).
#   - Team Chemistry = SKCR directly. Confirmed by process of elimination
#     across 3 rounds against other "value stayed at 1 for a fresh coach"
#     candidates (DMPP, CCYT were both briefly plausible but disproven when
#     changing them independently didn't move Chemistry; SKCR did, twice).
#   - Performance is NOT a stored field - it's computed as MIN(SKPA, SKPF).
#     Verified across 5 separate rounds with different SKPA/SKPF values every
#     time; the lower of the two matched the displayed current value in EVERY
#     round. (The displayed "max" side was inconsistent - sometimes a fixed 5,
#     sometimes mirrored current - not solved, but doesn't block maxing it:
#     setting both SKPA=5 and SKPF=5 reliably shows Performance as 5/5.)
#
# DISPROVEN (tried, ruled out by direct in-game testing - don't re-try these):
#   - CSPC, CSPA, CSPF: each sits right next to its SKPx counterpart (CSPA is
#     next to SKPA, etc.) and LOOKED like an obvious current/max pair, but
#     writing to them never changed anything on any screen. CSPA briefly
#     seemed to match Strategy in one round (coincidence - a follow-up round
#     disproved it). Bit-layout check (`node bridge.js fields --db <save>
#     --table COCH`) showed CSPA/CSPF are both 13-bit fields (0-8191 range)
#     while their SKPx partners are 3-bit (0-7) - i.e. CSPA/CSPF were never a
#     1-5 skill value to begin with, they're something else entirely (unknown
#     what, and no longer relevant since SKPA/SKPF/SKPC/SKST/SKCR cover all 4
#     named skills).
#   - "CHEM" (used in earlier versions of this script for Team Chemistry):
#     doesn't exist as a real column in COCH at all. Was silently a no-op.
#   - PH/FS/HS-suffix field groups in COCH (e.g. QBPH/QBFS/QBHS, one set of
#     10 position-coded fields each): zero effect in-game.
#   - CPSE and PSSK tables (also PNid-linked): New Coach has zero rows in
#     either, can't even be tested against him.
#   - CFDA, CFFA, CFUC, CFRE, CFDP, CFRP, CFFR, CFRR, CFEX: turned out to be
#     1-bit boolean flags (writing 2-5 silently truncated to 0/1), ruling them
#     out as 1-5 skill values entirely.
#   - DMPP, CCYT (Chemistry candidates), NHPP, BZPP, CDVP (Strategy
#     candidates): all briefly plausible (matched a "1" baseline, held values
#     2-5 correctly), all individually disproven once SKCR/SKST were isolated
#     as the real answer via unique-value elimination rounds.
#
# PHYSICAL/INTANGIBLE/LEARNING DEVELOPMENT - SOLVED (was "exhaustively
# searched and not found" via COCH field scanning; the real answer was in
# CSKL all along, just paired wrong in the first attempt):
#   - The original CSKL test paired SKID (Intangible Development current)
#     with SKLM (Learning Development *potential*) as a supposed unique
#     current/max pair - two different stats' fields mismatched. Writing to a
#     nonsense pairing like that produces exactly the kind of "zero visible
#     effect" result that was observed, without CSKL itself being wrong.
#   - Cracked via a community reference spreadsheet (Discord: NFL Head Coach
#     modding server, "HC EDITOR TRANSLATE.xlsx"), which gives CSKL's real
#     field layout: SKPD/SKPM (Physical current/max), SKID/SKIM (Intangible
#     current/max), SKLD/SKLM (Learning current/max), plus PPGR (a literal
#     position-bucket code, see PPGR_TO_POSITION above) and PNid.
#   - CONFIRMED live: custom "New Coach" (PNid 977, save
#     BLUS30128-CAREER-TEST), a distinct 1-2-3-4-5-repeating value pattern
#     written identically across all 3 categories for every PPGR row (0-9)
#     matched exactly on the in-game Development screens after a full RPCS3
#     restart - including confirming the game clamps a displayed "current"
#     down to "max" whenever current > max (exactly what showed up on the
#     rows deliberately set that way: TE/OL/K/P).
#   - See COACH_DEV_CATEGORIES / get_coach_development_rows for the
#     implementation.
#
# COACH RATINGS (from a "Coach Ratings" screen grouping found in a third-party
# editor's own config file, not the community spreadsheet): CCHM (Coach
# Chemistry), CKNW (Knowledge), CMOT (Motivation), POVS (Overall), COFF/CDEF
# (Off/Def ratings), and 9 per-position CRxx ratings (CRQB/CRRB/CRWR/CROL/
# CRDL/CRLB/CRDB/CRKS/CRPS - the same CRxx group already disproven above as a
# Development candidate, evidently because that was the wrong screen to check
# against, not because the fields don't do anything at all).
#   - Tested live on New Coach (PNid 977): only POVS confirmed visible
#     in-game (writing 64 showed as 64, range 0-99). The other 14 were written
#     successfully to the file but not visibly confirmed on any screen
#     checked - inconclusive, NOT disproven (could be backend/AI-only inputs
#     with no UI surface, e.g. affecting CPU coach hiring/performance
#     simulation rather than anything a human GM sees). Only POVS is
#     implemented in the UI; the other 14 are left alone pending further
#     investigation if picked back up.
#   - POVS also exists as a column on GMVW and TRVW (GM/Trainer), but "Max
#     Selected" was tried on both live and their displayed Overall did NOT
#     change - unlike COCH, it's evidently computed from their other skills
#     rather than a plain stored/displayed value there. POVS is Coach-only
#     in the UI (COACH_MAXABLE_SKILL_FIELDS / refresh_coach) for this reason.
# =============================================================================

# Friendly column headers for the raw field codes above.
STAFF_FIELD_LABELS = {
    "SKTD": "Trade Cur", "SKTM": "Trade Max",
    "SKNG": "Contract Cur", "SKNM": "Contract Max",
    "TSIE": "Injury Eval Cur", "TSIM": "Injury Eval Max",
    "TSRH": "Rehab Cur", "TSRM": "Rehab Max",
    "TSFR": "Fatigue Rec Cur", "TSFM": "Fatigue Rec Max",
    "SKPC": "Play Call Cur", "SKST": "Strategy Cur", "SKCR": "Chemistry Cur",
    "SKPX": "Play Call Max", "SKSM": "Strategy Max", "SKCM": "Chemistry Max",
    "POVS": "Overall",  # POVS also appears on GMVW/TRVW rows, not just COCH
    "SKPA": "Perf. Input A", "SKPF": "Perf. Input B",
    "COPS": "Position",
    # GM_SCOUTING_FIELDS (CBMP, FBMP, etc.) intentionally have NO label here -
    # disproven as "Potential Evaluation" (see comment above), true purpose
    # unknown. Shown by raw field code via the STAFF_FIELD_LABELS.get(h, h)
    # fallback wherever they're displayed.
}
# Confirmed Potential Evaluation + Rookie Scouting columns (from GMSK).
for _b in GM_POTENTIAL_EVAL_BUCKETS:
    STAFF_FIELD_LABELS[f"PE_{_b}_C"] = f"{_b} PE Cur"
    STAFF_FIELD_LABELS[f"PE_{_b}_M"] = f"{_b} PE Max"
    STAFF_FIELD_LABELS[f"RS_{_b}_C"] = f"{_b} RS Cur"
    STAFF_FIELD_LABELS[f"RS_{_b}_M"] = f"{_b} RS Max"
del _b
# Confirmed Coach Development columns (from CSKL).
for _cat, (_cur, _mx, _catname) in COACH_DEV_CATEGORIES.items():
    for _b in GM_POTENTIAL_EVAL_BUCKETS:
        STAFF_FIELD_LABELS[f"DV_{_cat}_{_b}_C"] = f"{_b} {_catname[:3]} Cur"
        STAFF_FIELD_LABELS[f"DV_{_cat}_{_b}_M"] = f"{_b} {_catname[:3]} Max"
del _cat, _cur, _mx, _catname, _b

# COPS = which staff "slot" a coach fills on their team (Head Coach, Offensive
# Coordinator, etc.). Sourced from a community report (Discord: NFL Head Coach
# modding server) matching the order these appear under the in-game Develop
# Staff screen, except DBC and DLC which are swapped from that on-screen
# order; the same report confirmed in-game that swapping a coach's position
# (e.g. HC <-> LBC) via this field works. Edited via the double-click dropdown
# in the Coach tab (see is_cops_column in _on_tree_double_click), not the
# generic numeric entry box, since it's a fixed set of labeled codes rather
# than an arbitrary integer.
COACH_POSITION_LABELS = {
    "0": "HC", "1": "OC", "2": "DC", "3": "STC", "4": "QBC", "5": "RBC",
    "6": "WRC", "7": "OLC", "8": "LBC", "9": "DLC", "10": "DBC",
}

# Team philosophy: the schemes and philosophies the game's Team Philosophy screen
# shows, stored per team in the TPHS table (the same field codes also appear on each
# coach row, COCH, but that screen does not read those). Value names come from the
# community HC09 config (docs/hc09_field_reference.md); the number is what is stored
# in the save. CHECKED IN THE GAME'S Team Philosophy screen, both ways (changed in
# game and read back from the save; written by the editor and read off the screen):
# NHPP 0 Heavily / 1 Balanced / 2 Rarely; OPPP 0 Head Coach / 1 Offensive Coordinator;
# OSPP 0 West Coast Normal / 2 Vertical Passing / 3 Spread / 4 Power Running (the
# config says "Speed" for 3); DSPP 0 3-4; DPPP 1 Defensive Coordinator; BZPP 0 Heavy;
# CVPP 2 Zone; DMPP 0 Aggressive; QBPP 0 Mobile/Speed; CBPP 61 Man; KKPP 75 Power (the
# game words the position ones in full, e.g. "Man Coverage/Ballhawk CB", "Big Foot/
# Distance K"); FS 67, SS 74 and punter 79 match what the screen shows. The other names
# in each list are the config's and have not been checked.
PHILOSOPHY_VALUES = {
    "OSPP": {0: "West Coast Normal", 1: "West Coast Heavy Pass", 2: "Vertical Passing", 3: "Spread", 4: "Power Running"},
    "OPPP": {0: "Head Coach", 1: "Offensive Coordinator"},
    "NHPP": {0: "Heavily", 1: "Balanced", 2: "Rarely"},
    "DSPP": {0: "3-4", 1: "4-3", 2: "4-6"},
    "DPPP": {0: "Head Coach", 1: "Defensive Coordinator"},
    "BZPP": {0: "Heavy", 1: "Normal", 2: "Light"},
    "CVPP": {0: "Man", 1: "Cover 2", 2: "Zone"},
    "DMPP": {0: "Aggressive", 1: "Conservative", 2: "Balanced"},
    "QBPP": {0: "Mobile/Speed", 1: "Strong Arm/Tools", 2: "Pure Passer", 3: "Field General", 4: "Balanced"},
    "HBPP": {5: "Speed", 6: "Moves", 7: "Power", 8: "Receiving", 9: "Workhorse", 10: "Balanced"},
    "FBPP": {11: "Ball Carrier", 12: "Blocking", 13: "Receiving", 14: "Balanced"},
    "WRPP": {15: "Strong", 16: "Tall", 17: "Speed", 18: "Route-Runner", 19: "Balanced"},
    "TEPP": {20: "Playmaker", 21: "H-Back", 22: "Balanced", 23: "Soft Hands", 24: "Blocking"},
    "TKPP": {25: "Size", 26: "Run Block", 27: "Pass Block", 28: "Zone Block", 29: "Balanced"},
    "GDPP": {30: "Size", 31: "Run Block", 32: "Pass Block", 33: "Zone Block", 34: "Balanced"},
    "CRPP": {35: "Size", 36: "Run Block", 37: "Pass Block", 38: "Zone Block", 39: "Balanced"},
    "DEPP": {40: "Balanced", 41: "Prototype", 42: "Speed", 43: "Run Stopper", 44: "3-4"},
    "DTPP": {45: "Balanced", 46: "Prototype", 47: "One-Gap", 48: "Run Stopper", 49: "3-4"},
    "OLPP": {50: "Balanced", 51: "Cover 2", 52: "Run Stopper", 53: "3-4 Pass Rush", 54: "Prototype"},
    "MLPP": {55: "Balanced", 56: "Coverage", 57: "Power", 58: "Tackler", 59: "Prototype"},
    "CBPP": {60: "Balanced", 61: "Man Coverage/Ballhawk", 62: "Strong/Press/Run Support", 63: "Prototype", 64: "Cover 2"},
    "FSPP": {65: "Balanced", 66: "Man Coverage", 67: "Centerfielder", 68: "Prototype", 69: "Run Support/Blitzer"},
    "SsPP": {70: "Balanced", 71: "Coverage", 72: "Prototype", 73: "Run Support/Big Hitter", 74: "Smart/Productive"},
    "KKPP": {75: "Big Foot/Distance", 76: "Accuracy", 77: "Balanced"},
    "KPPP": {78: "Power", 79: "Pinpoint Accuracy", 80: "Balanced"},
}

PHILOSOPHY_TABS = [
    ("Game plan", [
        ("Offense", [("OSPP", "Offensive scheme"), ("OPPP", "Offensive playbook control"), ("NHPP", "No-huddle philosophy")]),
        ("Defense", [("DSPP", "Defensive scheme"), ("DPPP", "Defensive playbook control"),
                     ("BZPP", "Blitzing"), ("CVPP", "Coverage")]),
        ("Game management", [("DMPP", "Defining moments")]),
    ]),
    ("Position philosophies", [
        ("Offense", [("QBPP", "QB"), ("HBPP", "HB"), ("FBPP", "FB"), ("WRPP", "WR"), ("TEPP", "TE"),
                     ("TKPP", "Tackle"), ("GDPP", "Guard"), ("CRPP", "Center")]),
        ("Defense", [("DEPP", "DE"), ("DTPP", "DT"), ("OLPP", "OLB"), ("MLPP", "MLB"), ("CBPP", "CB"), ("FSPP", "FS"), ("SsPP", "SS")]),
        ("Kicking", [("KKPP", "Kicker"), ("KPPP", "Punter")]),
    ]),
]

# -----------------------------
# HARD-CODED MAX columns (matches YOUR header dump)
# Case-sensitive.
# -----------------------------
PLAYER_MAX_HARDCODED = {
    "PSPD": "PSDX",
    "PAGI": "PAGX",
    "PACC": "PACX",
    "PSTR": "PSTX",
    "PAWR": "PAWX",
    "PSTA": "PSAX",
    "PINJ": "PINX",
    "PLTR": "PLTX",
    "PTGH": "PTGX",
    "PELU": "PELX",
    "PBCV": "PBCX",
    "PLSA": "PLSX",
    "PLSM": "PSMx",   # lowercase x in your file
    "PLJM": "PLJX",
    "PCAR": "PCAX",
    "PTHP": "PTPX",
    "PTHA": "PTAX",
    "PCTH": "PCTX",
    "PLSC": "PSCX",
    "PLCI": "PLCX",
    "PLRR": "PRRX",
    "PLRL": "PRLX",
    "PJMP": "PJMX",
    "PPBK": "PPBX",
    "PPBS": "PPSX",
    "PPBF": "PPFX",
    "PRBK": "PRBX",
    "PRBS": "PRSX",
    "PLIB": "PIBX",
    "PTAK": "PTKX",
    "PLHT": "PLHX",
    "PRBF": "PRFX",
    "PLPm": "PPMX",
    "PFMS": "PFMX",
    "PBSG": "PBSX",
    "PLPU": "PPUX",
    "PLPR": "PPRX",
    "PLMC": "PLMX",
    "PLZC": "PLZX",
    "PLPE": "PPEX",
    "PKPR": "PKPX",
    "PKAC": "PKAX",
    "PKRT": "PKRX",
    "PLRN": "PLRX",
    "PMOR": "PMOX",  # documented as fixed at 99 for everyone
    "PIMP": "PIMX",
}

# -----------------------------
# HC09-safe trade: do NOT swap these keys
# Add more here if you discover crashy fields in your file.
# -----------------------------
IMMUTABLE_KEYS = {
    "TGID",  # team ownership in your export
    "PGID",  # player global ID
    "POID",  # often a portrait / appearance / internal reference
}

# -----------------------------
# Utilities
# -----------------------------
def _norm_key(s: str) -> str:
    """Keep case EXACT. Only remove invisible junk that breaks exact matches."""
    if s is None:
        return s
    return (
        s.replace("\ufeff", "")
         .replace("\xa0", " ")
         .replace("\r", "")
         .replace("\n", "")
         .replace("\t", " ")
         .strip()
    )

def clamp_stat(v: int) -> int:
    return max(0, min(STAT_MAX_VALUE, v))

def safe_int(s):
    try:
        if s is None:
            return None
        s = str(s).strip()
        if s == "":
            return None
        return int(s)
    except Exception:
        return None

# -----------------------------
# Player Type Fit: how well a player's ratings suit one of the game's team position philosophies.
#
# The presets on the game's Team Philosophy screen (five each for CB, FS and SS, three for K and P, ...) are the
# team position philosophies: the TPHS xxPP values 0-80 (PHILOSOPHY_VALUES). The game's own files carry what each
# one values: PEAW (athletic ratings) and PEIW (skill ratings) have one row per philosophy, keyed by GMPP = the
# philosophy's value, with a weight for each rating. Checked on the five CB presets: Man Coverage weights man
# coverage 31 and zone coverage 0, Cover 2 the reverse, Strong/Press weights tackling, pursuit and press, and
# Prototype is high everywhere. Their siblings PEOW, PEDW and PESW (scouting-factor, durability and height/weight
# weights) are not used here, and RNSW is zero for every philosophy.
#
# The fit score is the weighted average of a player's ratings with those weights. It ranks who suits a preset;
# it is NOT the game's overall, whose exact formula has not been reproduced. This replaces an earlier version
# built on PLYT, the game's 37 player-generation archetypes, which are not what the game offers as presets.
# -----------------------------
PHILOSOPHY_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".hc09_gamedata_cache", "philosophies")
PHILOSOPHY_WEIGHT_TABLES = ("PEAW", "PEIW")
BOOT_AST_FILENAME = "qkl_boot.ast"
# weight column -> the player rating it weighs. Matched by name and checked against which position groups use
# each weight (e.g. HPWW, hit power, is heavy for MLB / SS / OLB; RORW, route running, for WR / TE).
PHILOSOPHY_WEIGHT_ATTR = {
    # PEAW
    "ACCW": "PACC", "SPDW": "PSPD", "AGLW": "PAGI", "FIMW": "PFMS", "SPMW": "PLSM", "THPW": "PTHP", "JMPW": "PJMP",
    "STRW": "PSTR", "RBSW": "PRBS", "ELUW": "PELU", "JMVW": "PLJM", "HPWW": "PLHT", "KPWW": "PKPR", "PBSw": "PPBS",
    # PEIW
    "THAW": "PTHA", "STAW": "PSTA", "IMBW": "PLIB", "RNBW": "PRBK", "KACW": "PKAC", "TACW": "PTAK", "SPCW": "PLSC",
    "PBFW": "PPBF", "RBFW": "PRBF", "PRGW": "PLPR", "TGHW": "PTGH", "INJW": "PINJ", "PBKW": "PPBK", "TRKW": "PLTR",
    "RELW": "PLRL", "STMW": "PLSA", "PWMW": "PLPm", "LRNW": "PLRN", "IMPW": "PIMP", "MORW": "PMOR", "RORW": "PLRR",
    "PURW": "PLPU", "AWRW": "PAWR", "BKSW": "PBSG", "CATW": "PCTH", "CITW": "PLCI", "KRTW": "PKRT", "BCVW": "PBCV",
    "MCVW": "PLMC", "ZCVW": "PLZC", "CARw": "PCAR", "PRSw": "PLPE",
}
# (label, the team philosophy field that holds the preset, the PPOS values of the players it applies to)
PHILOSOPHY_GROUPS = [
    ("QB", "QBPP", {"0"}), ("HB", "HBPP", {"1"}), ("FB", "FBPP", {"2"}), ("WR", "WRPP", {"3"}), ("TE", "TEPP", {"4"}),
    ("OT (LT / RT)", "TKPP", {"5", "9"}), ("OG (LG / RG)", "GDPP", {"6", "8"}), ("C", "CRPP", {"7"}),
    ("DE (LE / RE)", "DEPP", {"10", "11"}), ("DT", "DTPP", {"12"}), ("OLB (LOLB / ROLB)", "OLPP", {"13", "15"}),
    ("MLB", "MLPP", {"14"}), ("CB", "CBPP", {"16"}), ("FS", "FSPP", {"17"}), ("SS", "SsPP", {"18"}),
    ("K", "KKPP", {"19"}), ("P", "KPPP", {"20"}),
]


def load_philosophy_weights():
    """{philosophy value: {player rating column: weight}} from the cached PEAW and PEIW tables, or {} if they
    have not been extracted from the game files yet."""
    out = {}
    for table in PHILOSOPHY_WEIGHT_TABLES:
        try:
            with open(os.path.join(PHILOSOPHY_CACHE_DIR, table.lower() + ".csv"), newline="", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    gid = safe_int(r.get("GMPP", ""))
                    if gid is None:
                        continue
                    weights = out.setdefault(gid, {})
                    for col, attr in PHILOSOPHY_WEIGHT_ATTR.items():
                        try:
                            w = float(r.get(col) or 0)
                        except ValueError:
                            continue
                        if w > 0 and col in r:
                            weights[attr] = w
        except OSError:
            return {}
    return out


PHILOSOPHY_WEIGHTS = load_philosophy_weights()


def compute_philosophy_fit(row, weights):
    """Weighted average of the player's ratings (0-99) with the philosophy's weights; None if none apply."""
    num = den = 0.0
    for attr, w in weights.items():
        v = safe_int(row.get(attr, ""))
        if v is not None:
            num += w * v
            den += w
    return num / den if den else None


def philosophy_key_ratings(weights, n=8):
    """The ratings a philosophy weights most, as 'Man Coverage 31, Speed 31, ...'."""
    top = sorted(weights.items(), key=lambda kv: (-kv[1], kv[0]))[:n]
    return ", ".join(f"{STAT_META.get(a, (a,))[0]} {w:g}" for a, w in top)


def detect_team_col_case_sensitive(headers):
    hs = set(headers or [])
    for c in PREFERRED_TEAM_COLS:
        if c in hs:
            return c
    return None

def build_player_max_map(headers):
    """Use ONLY hard-coded mapping that exists in THIS file's headers."""
    hs = set(headers or [])
    out = {}
    for base, mx in PLAYER_MAX_HARDCODED.items():
        if base in STAT_META and mx in hs:
            out[base] = mx
    return out

def sanitize_name(raw: str, max_len: int = 15) -> str:
    """
    HC09 can crash on weird chars / long strings.
    - Keep letters, space, apostrophe, hyphen, period
    - Collapse spaces
    - Trim length
    """
    if raw is None:
        return ""
    s = raw.strip()
    s = re.sub(r"[^A-Za-z\.\'\-\s]", "", s)  # drop weird chars
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) > max_len:
        s = s[:max_len].strip()
    return s

def swap_players_safe(p1: dict, p2: dict, immutable_keys: set):
    """
    HC09-safe swap:
    swap all values for keys that exist in BOTH dicts, except immutable keys.
    """
    # only swap keys shared by both rows
    shared_keys = set(p1.keys()) & set(p2.keys())
    for k in shared_keys:
        if k in immutable_keys:
            continue
        p1[k], p2[k] = p2[k], p1[k]

# -----------------------------
# CSV model
# -----------------------------
class CSVModel:
    def __init__(self):
        self.play_path = ""
        self.drpk_path = ""
        self.slri_path = ""
        # Optional staff CSVs
        self.trainer_path = ""
        self.coach_path = ""
        self.gm_path = ""

        self.players = []          # list[dict]
        self.player_headers = []   # list[str]
        self.picks = []            # list[dict]
        self.pick_headers = []     # list[str]
        self.salaries = []         # list[dict]
        self.salary_headers = []   # list[str]

        self.trainers = []         # list[dict]
        self.trainer_headers = []  # list[str]
        self.coaches = []          # list[dict]
        self.coach_headers = []    # list[str]
        self.gms = []              # list[dict]
        self.gm_headers = []       # list[str]
        self.gmsk = []              # list[dict] - GM "Potential Evaluation"/"Rookie Scouting" rows (joined via PNid)
        self.gmsk_headers = []      # list[str]
        self.gmsk_path = ""
        self.cskl = []              # list[dict] - Coach "Development" (Physical/Intangible/Learning) rows (joined via PNid)
        self.cskl_headers = []      # list[str]
        self.cskl_path = ""
        self.team = []              # list[dict] - one row per team (real teams + Free Agents/Secret/Draft/etc pools), keyed by TGID
        self.team_headers = []      # list[str]
        self.team_path = ""
        self.cinf = []               # list[dict] - single global row, has SEYR (current season year, see CINF_SEASON_YEAR_OFFSET)
        self.cinf_headers = []       # list[str]
        self.cinf_path = ""
        self.tphs = []               # list[dict] - one row per team: the Team Philosophy screen (keyed by TGID)
        self.tphs_headers = []       # list[str]
        self.tphs_path = ""

        self.team_col = None
        self.max_map = {}
        self.csv_formats = {}

        self.db_path = ""       # path to the .db / USR-DATA save file
        # Playbook tables edited in the Playbooks tab and not yet saved:
        # {"PGPL": [row dicts, whole table], ...}. Written (with row appending
        # enabled for just these tables) by save_to_db, then dropped.
        self.pb_pending = {}
        self.load_serial = 0

    # ---------- Bridge (node bridge.js) ----------
    def run_bridge(self, args):
        """Run hc09-bridge/bridge.js with the given args, return parsed JSON stdout."""
        cmd = [NODE_EXE, BRIDGE_JS] + args
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, check=True
            )
        except FileNotFoundError:
            raise RuntimeError(
                "Could not find 'node'. Install Node.js and make sure it's on your PATH."
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"bridge.js failed:\n{e.stderr or e.stdout}")

        try:
            return json.loads(result.stdout)
        except (json.JSONDecodeError, ValueError):
            raise RuntimeError(f"bridge.js returned unexpected output:\n{result.stdout}")

    def load_all_from_db(self, db_path):
        """Export all tables from the .db save file straight into memory (no manual CSV steps)."""
        if not db_path or not os.path.isfile(db_path):
            raise ValueError("Select a valid .db / USR-DATA save file.")

        self.pb_pending = {}   # unsaved playbook edits belong to the file being replaced
        self.load_serial += 1  # lets the Playbooks tab notice a reload even when the file's mtime is unchanged
        tmp_dir = tempfile.mkdtemp(prefix="hc09_bridge_load_")
        try:
            self.run_bridge(["export", "--db", db_path, "--out", tmp_dir])

            self.db_path = db_path

            for code, _rows_attr, _headers_attr, path_attr in DB_TABLE_ATTRS:
                setattr(self, path_attr, os.path.join(tmp_dir, DB_TABLE_FILES[code]))

            self._finish_load()
        finally:
            # _finish_load() reads every CSV into memory before returning, so
            # nothing downstream ever touches this directory again - clean it
            # up now (rather than never, as before) regardless of whether the
            # load succeeded.
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def save_to_db(self):
        """Write current in-memory tables straight back into the .db save file."""
        if not self.db_path:
            raise ValueError("No save file loaded.")

        tmp_dir = tempfile.mkdtemp(prefix="hc09_bridge_save_")
        pending = {t: rows for t, rows in self.pb_pending.items() if t in PLAYBOOK_TABLE_HEADERS}
        try:
            for code, rows_attr, headers_attr, _path_attr in DB_TABLE_ATTRS:
                rows = getattr(self, rows_attr)
                if rows:
                    self._write_csv(os.path.join(tmp_dir, DB_TABLE_FILES[code]), rows, getattr(self, headers_attr))
            for table, rows in pending.items():
                self._write_csv(os.path.join(tmp_dir, table.lower() + ".csv"), rows, PLAYBOOK_TABLE_HEADERS[table])

            backup_path = self.db_path + ".bak"
            shutil.copy2(self.db_path, backup_path)

            # No --out: save in place. (Passing --out equal to --db would hit a
            # clone-to-self race in HC09Helper.save() and corrupt the file.)
            args = ["import", "--db", self.db_path, "--in", tmp_dir]
            if pending:
                # Playbook edits add rows, which an ordinary import never does, so
                # growing is enabled for exactly the edited tables.
                args += ["--tables", ",".join([c for c, *_ in DB_TABLE_ATTRS] + list(pending)),
                         "--allow-append", ",".join(pending)]
            if pending:
                try:
                    result = self.run_bridge(args)
                except Exception as e:
                    # The import may have died partway through writing the file.
                    shutil.copy2(backup_path, self.db_path)
                    raise RuntimeError(
                        "The playbook edits could not be saved, so your save was restored from its backup. "
                        f"Details: {e}") from e
                self._check_playbook_save(result, pending, backup_path)
            else:
                self.run_bridge(args)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        if pending:
            self.pb_pending = {}
        return backup_path

    def _check_playbook_save(self, import_result, pending, backup_path):
        """After a save that grew playbook tables: every pending table must have
        been written, and the file must pass the bridge's structure check
        (every table header checksum, the checksum chain, row counts). If not,
        put the backup back rather than leave a save the game might reject."""
        by_table = {r.get("table"): r for r in (import_result or {}).get("results", [])}
        problems = [f"{t}: {by_table.get(t, {}).get('status', 'missing')}" for t in pending
                    if by_table.get(t, {}).get("status") != "ok"]
        if not problems:
            try:
                check = self.run_bridge(["verify-db", "--db", self.db_path])
                if not check.get("ok"):
                    problems = check.get("issues") or ["structure check failed"]
            except Exception as e:
                # A file the checker can't even open or parse is not a file to keep.
                problems = [f"the structure check could not run ({e})"]
        if problems:
            shutil.copy2(backup_path, self.db_path)
            raise RuntimeError(
                "The playbook edits could not be saved safely, so your save was restored from its backup. "
                "Details: " + "; ".join(str(p) for p in problems[:4]))

    def _write_csv(self, path, rows, headers):
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=headers, lineterminator="\r\n")
            w.writeheader()
            for r in rows:
                w.writerow(r)

    def load_csv(self, path):
        if not path or not os.path.isfile(path):
            return [], []
        raw = open(path, "rb").read()
        has_bom = raw.startswith(b"\xef\xbb\xbf")
        if b"\r\n" in raw:
            lineterminator = "\r\n"
        else:
            lineterminator = "\n"
        self.csv_formats[path] = {
            "encoding": "utf-8-sig" if has_bom else "utf-8",
            "lineterminator": lineterminator,
        }
        with open(path, "r", newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            raw_headers = reader.fieldnames or []
            headers = [_norm_key(h) for h in raw_headers]
            rows = []
            for row in reader:
                cleaned = {}
                for k, v in row.items():
                    nk = _norm_key(k)
                    cleaned[nk] = v
                rows.append(cleaned)
        return rows, headers

    def save_csv(self, rows, headers, original_file):
        if not original_file:
            raise ValueError("No original file path to save.")
        base, ext = os.path.splitext(original_file)
        out = f"{base}_modified{ext}"
        n = 1
        while os.path.exists(out):
            out = f"{base}_modified_{n}{ext}"
            n += 1
        fmt = self.csv_formats.get(original_file, {"encoding": "utf-8-sig", "lineterminator": "\n"})
        with open(out, "w", newline="", encoding=fmt["encoding"]) as f:
            w = csv.DictWriter(f, fieldnames=headers, lineterminator=fmt["lineterminator"])
            w.writeheader()
            for r in rows:
                w.writerow(r)
        return out

    def load_all(self, play_path, drpk_path="", slri_path="", trainer_path="", coach_path="", gm_path=""):
        self.play_path = play_path or ""
        self.drpk_path = drpk_path or ""
        self.slri_path = slri_path or ""
        self.trainer_path = trainer_path or ""
        self.coach_path = coach_path or ""
        self.gm_path = gm_path or ""

        self._finish_load()

    def _finish_load(self):
        for _code, rows_attr, headers_attr, path_attr in DB_TABLE_ATTRS:
            path = getattr(self, path_attr, "")
            rows, headers = self.load_csv(path) if path else ([], [])
            setattr(self, rows_attr, rows)
            setattr(self, headers_attr, headers)

        if not self.players:
            raise ValueError("play.csv loaded 0 players/rows.")

        # Ensure coach extra fields exist in headers and set defaults
        coach_extra = ["CSPC", "SKPC", "SKPA", "SKPF", "CHEM"]
        if self.coach_headers is None:
            self.coach_headers = []
        coach_header_set = set(self.coach_headers)
        for f in coach_extra:
            if f not in coach_header_set:
                continue
        # Ensure each existing coach numeric field has a default
        for r in self.coaches:
            for f in coach_extra:
                if f not in coach_header_set:
                    continue
                if (r.get(f, "") or "").strip() == "":
                    r[f] = "1"

        self.team_col = detect_team_col_case_sensitive(self.player_headers)
        self.max_map = build_player_max_map(self.player_headers)

    def player_name(self, row):
        fn = (row.get(PLAYER_FIRST_NAME_CODE, "") or "").strip()
        ln = (row.get(PLAYER_LAST_NAME_CODE, "") or "").strip()
        nm = f"{fn} {ln}".strip()
        return nm if nm else "(No Name)"

    def player_pos(self, row):
        code = (row.get(PLAYER_POS_CODE, "") or "").strip()
        return POSITIONS.get(code, "UNK")

    def player_team_id(self, row):
        if not self.team_col:
            return ""
        return (row.get(self.team_col, "") or "").strip()

    def set_player_team_id(self, row, tid):
        """Returns False (no-op) if the team column wasn't detected for this
        save - callers should check this before assuming the move happened."""
        if not self.team_col:
            return False
        row[self.team_col] = str(tid)
        return True

    def _rows_by_position(self, table_rows, pnid):
        """Return {position_bucket: row} for a PPGR-linked table (GMSK or CSKL),
        keyed by each row's own PPGR field (see PPGR_TO_POSITION) - NOT by
        file/insertion order, which is confirmed inconsistent between records
        (e.g. Jauron's CSKL rows and Andrews' GMSK rows were stored in
        different physical orders despite using the same PPGR scheme)."""
        if not pnid:
            return {}
        # Memoized by table identity (self.gmsk/self.cskl) so repeated calls -
        # one per coach/GM row rendered, over a league-wide 300+ row table -
        # don't each re-scan the whole table linearly. Naturally invalidated
        # when _finish_load reassigns a fresh list: that's a new id(), so the
        # old cache entry is simply never looked up again.
        cache = getattr(self, "_pos_index_cache", None)
        if cache is None:
            cache = self._pos_index_cache = {}
        key = id(table_rows)
        index = cache.get(key)
        if index is None:
            index = {}
            for r in table_rows:
                row_pnid = (r.get("PNid", "") or "").strip()
                if not row_pnid:
                    continue
                bucket = PPGR_TO_POSITION.get((r.get("PPGR", "") or "").strip())
                if bucket:
                    index.setdefault(row_pnid, {})[bucket] = r
            cache[key] = index
        return index.get(str(pnid), {})

    def get_gm_potential_eval_rows(self, pnid):
        """Return {bucket: GMSK row} for this GM's Potential Evaluation + Rookie
        Scouting data (both stats live on the same GMSK rows), or {} if this GM
        has no rows populated yet (freshly appointed GMs can have none)."""
        rows = self._rows_by_position(self.gmsk, pnid)
        if len(rows) != len(GM_POTENTIAL_EVAL_BUCKETS):
            return {}
        return rows

    def get_coach_development_rows(self, pnid):
        """Return {bucket: CSKL row} for this coach's Physical/Intangible/Learning
        Development data, or {} if not populated (see get_gm_potential_eval_rows)."""
        rows = self._rows_by_position(self.cskl, pnid)
        if len(rows) != len(GM_POTENTIAL_EVAL_BUCKETS):
            return {}
        return rows

    def get_team_row(self, tgid):
        """Return the TEAM table row for this TGID (holds TMSA, the team's
        stored salary cap total - see TEAM_SALARY_CAP_FIELD), or None."""
        if not tgid:
            return None
        for r in self.team:
            if (r.get("TGID", "") or "").strip() == str(tgid):
                return r
        return None

    def adjust_team_salary_cap(self, tgid, delta_units):
        """Add delta_units (same $10,000 units as TMSA/PCSA/PTSA) to a team's
        stored cap total, clamped at 0. No-op if the TEAM table isn't loaded
        or this TGID has no row (e.g. TEAM table wasn't in the export)."""
        row = self.get_team_row(tgid)
        if row is None:
            return False
        cur = safe_int(row.get(TEAM_SALARY_CAP_FIELD, "0")) or 0
        row[TEAM_SALARY_CAP_FIELD] = str(max(0, min(TEAM_SALARY_CAP_MAX_VALUE, cur + delta_units)))
        return True

    def get_current_season_year(self):
        """UNRELIABLE - see CINF_SEASON_YEAR_OFFSET. Disproven as a live
        "current season" indicator (two saves independently confirmed as
        different in-game years both have the same raw SEYR value). Not
        called anywhere; kept only in case cINF's real meaning is solved
        later."""
        if not self.cinf:
            return None
        seyr = safe_int(self.cinf[0].get("SEYR", ""))
        if seyr is None:
            return None
        return seyr + CINF_SEASON_YEAR_OFFSET

class TeamAutocompleteCombo:
    """A ttk.Combobox with type-to-filter team selection, backed by a custom
    floating suggestion popup instead of the native ttk dropdown - opening the
    real dropdown (via <Down> or Post) steals keyboard focus into its own
    listbox, which blocks further typing in the entry. This popup never takes
    focus, so you can keep typing continuously to narrow the list. Up/Down
    move a highlighted suggestion, Enter/Tab confirm it (Tab still moves
    focus on afterward, unlike Enter), clicking a row confirms it, hovering
    highlights it, clicking away and back preserves the current filter, and
    clicking/focusing the entry selects all its text (like a browser address
    bar) so typing immediately replaces it.

    Extracted from the Sign Free Agent dialog (where this exact behavior was
    built and tuned against real user feedback) so the Draft Picks tab (and
    anywhere else that needs "type or pick a team") doesn't duplicate it.
    """
    def __init__(self, parent, options, width=26, initial_tid=None):
        self.options = list(options)  # [(tid, name), ...]
        self.all_values = [f"{tid}: {name}" for tid, name in self.options]

        self.combo = ttk.Combobox(parent, width=width)
        self.combo["values"] = self.all_values
        if initial_tid is not None:
            self.set_tid(initial_tid)
        elif self.all_values:
            self.combo.current(0)

        self._popup = None
        self._popup_list = None
        self._popup_active_idx = -1

        self.combo.bind("<KeyRelease>", self._on_typed)
        self.combo.bind("<FocusIn>", self._select_all)
        self.combo.bind("<Button-1>", self._select_all)
        self.combo.bind("<FocusOut>", lambda e: self.combo.after(150, self._hide_popup))
        # Bound directly (not via <KeyRelease>) and return "break" when the
        # popup is open, so these move the highlighted suggestion instead of
        # the native Combobox's default Up/Down/Return handling running too.
        self.combo.bind("<Down>", lambda e: self._on_arrow(1))
        self.combo.bind("<Up>", lambda e: self._on_arrow(-1))
        self.combo.bind("<Return>", self._on_return)
        self.combo.bind("<Tab>", self._on_tab)

    def pack(self, **kw):
        self.combo.pack(**kw)
        return self

    def get_tid(self):
        """Resolve whatever's typed/selected to a TID: exact 'id: name' match
        first (picking from the dropdown), else a case-insensitive substring
        match against team names (typing "falcons" and not picking from the
        list), else None."""
        typed = self.combo.get().strip()
        if not typed:
            return None
        exact = typed.split(":", 1)[0].strip() if ":" in typed else typed
        if any(tid == exact for tid, _name in self.options):
            return exact
        typed_lower = typed.lower()
        for tid, name in self.options:
            if typed_lower in name.lower():
                return tid
        return None

    def set_tid(self, tid):
        for i, label in enumerate(self.combo["values"]):
            if str(label).startswith(str(tid) + ":"):
                self.combo.current(i)
                return
        if self.combo["values"]:
            self.combo.current(0)

    def destroy_popup(self):
        """Call from the owning window's destroy()/close handler - the popup
        is a separate Toplevel, not a child of the normal widget tree, so it
        won't be torn down automatically."""
        if self._popup is not None:
            self._popup.destroy()
            self._popup = None

    def _select_all(self, event):
        widget = event.widget
        widget.after(1, lambda: (widget.selection_range(0, tk.END), widget.icursor(tk.END)))
        self._refresh_popup_from_text()

    def _refresh_popup_from_text(self):
        typed = self.combo.get().strip().lower()
        self.combo["values"] = self.all_values
        if not typed:
            self._hide_popup()
            return
        matches = [v for v in self.all_values if typed in v.lower()]
        self._show_popup(matches)

    def _on_typed(self, event):
        if event.keysym in ("Up", "Down", "Return", "Escape", "Tab"):
            if event.keysym == "Escape":
                self._hide_popup()
            return
        self._refresh_popup_from_text()

    def _on_arrow(self, direction):
        if self._popup is None or str(self._popup.state()) != "normal":
            return None  # popup not showing - let the key behave normally
        size = self._popup_list.size()
        if size == 0:
            return "break"
        self._popup_active_idx = max(0, min(size - 1, self._popup_active_idx + direction))
        self._highlight_popup_row(self._popup_active_idx)
        return "break"

    def _on_return(self, event):
        if self._popup is None or str(self._popup.state()) != "normal":
            return None
        if 0 <= self._popup_active_idx < self._popup_list.size():
            self._pick_value(self._popup_list.get(self._popup_active_idx))
            return "break"
        return None

    def _on_tab(self, event):
        if self._popup is not None and str(self._popup.state()) == "normal":
            if 0 <= self._popup_active_idx < self._popup_list.size():
                self._pick_value(self._popup_list.get(self._popup_active_idx))
        return None

    def _highlight_popup_row(self, idx):
        self._popup_list.selection_clear(0, tk.END)
        if 0 <= idx < self._popup_list.size():
            self._popup_list.selection_set(idx)
            self._popup_list.activate(idx)
            self._popup_list.see(idx)
        self._popup_active_idx = idx

    def _show_popup(self, matches):
        if not matches:
            self._hide_popup()
            return
        if self._popup is None:
            self._popup = tk.Toplevel(self.combo)
            self._popup.overrideredirect(True)
            self._popup.attributes("-topmost", True)
            self._popup_list = tk.Listbox(self._popup, exportselection=False, activestyle="none")
            self._popup_list.pack(fill="both", expand=True)
            self._popup_list.bind("<Button-1>", self._on_popup_click)
            self._popup_list.bind("<Motion>", self._on_popup_hover)
            self._popup_active_idx = -1

        shown = matches[:10]
        self._popup_list.delete(0, tk.END)
        for m in shown:
            self._popup_list.insert(tk.END, m)
        self._popup_active_idx = -1

        x = self.combo.winfo_rootx()
        y = self.combo.winfo_rooty() + self.combo.winfo_height()
        w = max(self.combo.winfo_width(), 220)
        h = min(20 * len(shown) + 4, 200)
        self._popup.geometry(f"{w}x{h}+{x}+{y}")
        self._popup.deiconify()
        self.combo.focus_set()  # keep typing focus on the entry, never the popup

    def _hide_popup(self):
        if self._popup is not None:
            self._popup.withdraw()
            self._popup_active_idx = -1

    def _on_popup_hover(self, event):
        idx = self._popup_list.nearest(event.y)
        if 0 <= idx < self._popup_list.size():
            self._highlight_popup_row(idx)

    def _on_popup_click(self, event):
        idx = self._popup_list.nearest(event.y)
        if idx < 0 or idx >= self._popup_list.size():
            return
        self._pick_value(self._popup_list.get(idx))

    def _pick_value(self, value):
        self.combo.delete(0, tk.END)
        self.combo.insert(0, value)
        self._hide_popup()
        self.combo.focus_set()

# =============================================================================
# "MOVE PLAYER -> SELECTED TEAM" INVESTIGATION LOG - REMOVED, CONFIRMED UNSAFE
# =============================================================================
# This used to be a toolbar button that moved the selected player to whichever
# team was highlighted in the Teams list, by directly overwriting their TGID
# field (and nothing else) - a simpler one-click alternative to Trade Players
# (Safe Swap). It was ALREADY hard-blocked for TGID-only files (this project's
# actual file format) before this investigation even started, with a warning
# telling the user to use Safe Swap instead. That block looked like leftover
# caution from before the direct-DB-write bridge existed - it turned out to be
# a correctly-founded safety rail, confirmed the hard way:
#
# CONFIRMED (via live in-game testing, save BLUS30128-CAREER-TEST):
#   - A bare TGID overwrite (Calvin Johnson, Lions WR, PGID 27903, moved to
#     the Falcons) displays PERFECTLY FINE immediately - shows up correctly on
#     the new team's roster, cap page, and Evaluate Roster screen, with his
#     existing contract intact. The game CRASHES the moment you advance to the
#     next day. Reproduced twice.
#   - Ruled out roster headcount: did a reciprocal two-way move (Calvin to the
#     Falcons AND a Falcons player to the Lions simultaneously, via the same
#     bare-TGID method) so neither team's roster size actually changed. Still
#     crashed at the same point.
#   - Found the DCHT table (2897 records, fields PGID/TGID/DCLK/PPOS/ddep) -
#     a depth chart, completely separate from PLAY.TGID. Directly confirmed
#     (captured live, before any revert) that after the bare TGID move, DCHT
#     still listed Calvin under the Lions (TGID=19) as their starting WR
#     (ddep=1) even though PLAY said Falcons - a real, proven stale reference.
#   - Ruled out depth-chart staleness alone: updated just his DCHT row's TGID
#     to match (14). Still crashed.
#   - Ruled out depth-chart slot conflicts/gaps: did a full reciprocal swap
#     with a real Falcons WR (Michael Jenkins, PGID 17320) who was already
#     sitting at the exact slot (ddep=1) that Calvin would occupy - swapped
#     both players' TGID AND their DCHT row's TGID, so each team's WR depth
#     chart stayed perfectly sequential (0-5) on both sides with zero gaps or
#     duplicates the whole time (independently verified: the in-game Depth
#     Chart screen for both teams matched the raw DCHT data exactly). STILL
#     crashed, at the same point, every time.
#   - Checked every other table found containing both a PGID and TGID field
#     (AWPL, PFTA, PSAC, ACAG, DPLP, DRPP, INJY, PSRC, PSRG, PSRS, RPGR - 11
#     tables, one with 11,550 records) for any row referencing Calvin
#     Johnson's PGID (27903). NONE of them did.
#
# CONCLUSION: whatever actually causes the crash was not found via any
# save-file diffing/inspection approach tried (3 separate ruled-out
# hypotheses, 13 tables checked total including DCHT). It may be something
# computed at load time rather than stored in any single field, a caching/
# GameFlow issue, or something else that would need live RPCS3 memory
# inspection to find - a fundamentally heavier investigation than everything
# else in this file, which was all done via save-file edits. Given this,
# "Trade Players (Safe Swap)" (which never touches TGID at all - it swaps
# player DATA between two rows while both stay in their own team's slot) is
# the ONLY confirmed-safe way to move a player between two REAL teams. Sign
# Free Agent remains safe (confirmed via the same day-advance test) because
# it only ever pulls a player OUT of a pool (Free Agents/Secret, TGID 1009/
# 1013) - those pools are never listed on any real team's DCHT depth chart,
# so there's no stale reference to leave behind on the source side, unlike a
# real team-to-team move.
#
# FOLLOW-UP (via a real in-game player-for-picks trade, before/after diffed
# directly - Joe Thomas, Browns to Texans, for 2 draft picks, save
# BLUS30128-CAREER-QQETBROWNS): confirms WHY the earlier DCHT-sync attempt
# (giving Calvin Johnson's own DCHT row the correct new TGID) still crashed.
# A real trade doesn't just update the moved player's own DCHT row - it
# CASCADES across the losing team's entire affected position group (70 DCHT
# rows changed, all still TGID=5/Browns, spanning multiple PPOS values -
# likely the whole O-line, not just Joe Thomas's own LT slot), reshuffling
# who's promoted into which depth-chart slot to backfill the vacancy. That's
# a full depth-chart recalculation, not a single-row edit - a fundamentally
# bigger operation than anything attempted in the Calvin Johnson test.
# Also confirmed: a real trade updates TEAM.TMSA on BOTH sides (Browns
# 10127->9709, Texans 13488->13906, matching Joe Thomas's cap hit moving
# from one team to the other) - something no player-moving feature in this
# file currently does (Sign Free Agent only ever adds to one team's TMSA,
# since it pulls from a pool with no real cap to lose). If a "trade a player
# for picks" feature is ever attempted, both of these would need solving:
# the depth-chart reshuffle algorithm (not yet reverse-engineered - unclear
# if it's as simple as "shift everyone below up one slot" or something more
# position-specific) and dual-team TMSA adjustment.
# =============================================================================

# -----------------------------
# GUI
# -----------------------------
class SwapTradeDialog(tk.Toplevel):
    """
    HC09-safe swap trade dialog:
    pick Team 1 -> player, Team 2 -> player, then swap (without changing TGID/IDs).
    """
    def __init__(self, parent, model: CSVModel):
        super().__init__(parent)
        self.title("Trade Players (Safe Swap - does not change TGID)")
        self.geometry("980x520")
        self.minsize(900, 480)
        self.resizable(True, True)
        self.parent = parent
        self.model = model

        self.team1 = tk.StringVar(value="1009")
        self.team2 = tk.StringVar(value="1")

        self.idx1 = None  # real index into model.players
        self.idx2 = None

        self._build()

    def _build(self):
        top = ttk.Frame(self)
        top.pack(fill="x", padx=12, pady=10)

        warn = (
            "This trade swaps player DATA between two roster rows, but keeps TGID/IDs unchanged.\n"
            "That is the safest method when TGID is the only team column."
        )
        ttk.Label(top, text=warn).pack(anchor="w")

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, padx=12, pady=(0, 10))

        left = ttk.LabelFrame(body, text="Team 1 (choose player to send)")
        right = ttk.LabelFrame(body, text="Team 2 (choose player to send)")

        left.pack(side="left", fill="both", expand=True, padx=(0, 8))
        right.pack(side="left", fill="both", expand=True, padx=(8, 0))

        # Team dropdowns
        self.cmb_t1 = ttk.Combobox(left, state="readonly", width=28)
        self.cmb_t2 = ttk.Combobox(right, state="readonly", width=28)

        team_vals = [f"{tid}: {name}" for tid, name in TEAM_NAMES.items()]
        self.cmb_t1["values"] = team_vals
        self.cmb_t2["values"] = team_vals

        # default selections
        self._set_combo_to_tid(self.cmb_t1, "1009")
        self._set_combo_to_tid(self.cmb_t2, "1")

        self.cmb_t1.pack(anchor="w", padx=10, pady=(10, 6))
        self.cmb_t2.pack(anchor="w", padx=10, pady=(10, 6))

        self.cmb_t1.bind("<<ComboboxSelected>>", lambda e: self._refresh_roster(1))
        self.cmb_t2.bind("<<ComboboxSelected>>", lambda e: self._refresh_roster(2))

        # Rosters
        self.lst1 = tk.Listbox(left, exportselection=False)
        self.lst2 = tk.Listbox(right, exportselection=False)
        self.lst1.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.lst2.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.lst1.bind("<<ListboxSelect>>", lambda e: self._on_pick_player(1))
        self.lst2.bind("<<ListboxSelect>>", lambda e: self._on_pick_player(2))

        # bottom controls
        bottom = ttk.Frame(self)
        bottom.pack(fill="x", padx=12, pady=(0, 10))

        ttk.Label(bottom, text="Immutable keys not swapped: " + ", ".join(sorted(IMMUTABLE_KEYS))).pack(side="left")

        ttk.Button(bottom, text="Swap (HC09-safe trade)", command=self._do_swap).pack(side="right")
        ttk.Button(bottom, text="Close", command=self.destroy).pack(side="right", padx=(0, 8))

        self._refresh_roster(1)
        self._refresh_roster(2)

    def _set_combo_to_tid(self, cmb, tid):
        for i, label in enumerate(cmb["values"]):
            if str(label).startswith(str(tid) + ":"):
                cmb.current(i)
                return
        if cmb["values"]:
            cmb.current(0)

    def _combo_tid(self, cmb):
        v = cmb.get()
        if ":" in v:
            return v.split(":", 1)[0].strip()
        return v.strip()

    def _refresh_roster(self, which):
        tid = self._combo_tid(self.cmb_t1 if which == 1 else self.cmb_t2)
        lst = self.lst1 if which == 1 else self.lst2

        lst.delete(0, tk.END)
        mapping = []

        team_col = self.model.team_col
        if not team_col:
            # if somehow no team col, show all
            filtered = list(enumerate(self.model.players))
        else:
            filtered = [(i, r) for i, r in enumerate(self.model.players)
                        if (r.get(team_col, "") or "").strip() == tid]

        for i, r in filtered:
            pos = self.model.player_pos(r)
            name = self.model.player_name(r)
            mapping.append(i)
            lst.insert(tk.END, f"{pos}  {name}   (row#{i})")

        if which == 1:
            self.map1 = mapping
            self.idx1 = None
        else:
            self.map2 = mapping
            self.idx2 = None

        # auto-select first
        if lst.size() > 0:
            lst.selection_set(0)
            lst.activate(0)
            self._on_pick_player(which)

    def _on_pick_player(self, which):
        lst = self.lst1 if which == 1 else self.lst2
        sel = lst.curselection()
        if not sel:
            return
        lb_idx = sel[0]
        if which == 1:
            if lb_idx < len(self.map1):
                self.idx1 = self.map1[lb_idx]
        else:
            if lb_idx < len(self.map2):
                self.idx2 = self.map2[lb_idx]

    def _do_swap(self):
        if self.idx1 is None or self.idx2 is None:
            messagebox.showwarning("Pick players", "Select one player on each side.")
            return
        if self.idx1 == self.idx2:
            messagebox.showwarning("Same row", "You selected the same row on both sides.")
            return

        p1 = self.model.players[self.idx1]
        p2 = self.model.players[self.idx2]

        n1 = self.model.player_name(p1)
        n2 = self.model.player_name(p2)

        swap_players_safe(p1, p2, IMMUTABLE_KEYS)
        self.parent.mark_dirty()

        messagebox.showinfo("Trade complete", f"✅ TRADE COMPLETED (Safe Swap)\n\n{n1}  ⇄  {n2}")

        # Refresh the parent's views
        self.parent.refresh_players_for_team()
        self.parent.refresh_stats_for_player()
        self.parent.refresh_picks()


# Source pools for signing - deliberately NOT the full 34-entry TEAM_NAMES list.
# Moving a player directly between two REAL teams via raw TGID write is a
# different, untested scenario (stale contract data, roster-size effects, etc.)
# - this dialog is scoped to exactly what was confirmed: pulling a player out
# of Free Agents/the Secret pool onto a real team, mirroring the exact fields
# a real in-game "cut" reverses (see SIGN_CONTRACT_FIELDS comment below).
SIGN_SOURCE_POOLS = [("1009", "Free Agents"), ("1013", "Game Changer Players")]
SIGN_DEST_TEAMS = [(tid, name) for tid, name in TEAM_NAMES.items() if tid not in ("1009", "1013", "1015")]


class SignFreeAgentDialog(tk.Toplevel):
    """
    Sign a player out of Free Agents / the Secret pool onto a real team with a
    new contract - the reverse of an in-game "cut", confirmed field-for-field
    two ways:
      1. A live before/after diff (cut Jason Snelling, PGID 28126, in-game,
         compared play.csv before vs after) confirmed the core fields: TGID
         (team -> 1009 Free Agents), PPTI ("Acquired From" -> the releasing
         team, i.e. it records who most recently let the player go), PCON
         (contract length -> 0), PCYL (years left -> 0), and the used PSA
         salary slots -> 0.
      2. PCSA/PTSA/PVSB's exact formulas were reverse-engineered from a real
         mid-contract player's data (Keith Brooking, Falcons LB: PCON=7,
         PCYL=2). PCSA (649) exactly equals PSA[5]+PSB[5], where 5 =
         PCON-PCYL (i.e. the CURRENT year's salary+bonus combined, not
         always year 0 - a player mid-contract is past year 0). PTSA (3640)
         exactly equals sum(all 7 PSA)+sum(all 7 PSB) - full contract value
         including bonus, not just salary as the reference spreadsheet's
         description implied. PVSB (1050) exactly equals sum(all 7 PSB).
         For a BRAND NEW signing specifically, PCON==PCYL so the current-year
         index is always 0 - which is exactly what this dialog writes to
         PSA0/PSB0, so the "current year" formulas above reduce to using
         index 0 here.
    Bonus (PSB0-6) wasn't populated on the Snelling cut test (his contract had
    none) so bullet 1 doesn't directly prove PSB also zeroes on a cut, but
    it's assumed to follow the same per-year pattern as PSA (same field
    layout/naming, same 7-year slot structure).
    Signing reverses every one of the confirmed fields using the years/
    salary/bonus you enter, and sets PPTI to the source pool's ID (mirroring
    "acquired from"). NOT yet tested: whether the game's own cap-usage
    display picks this up automatically (TEAM table has no obvious "cap
    used" field - only TCP0/TCP1, the SEPARATE dead-cap-penalty mechanic -
    suggesting cap usage is computed dynamically from active salaries, but
    this needs an in-game check before relying on it for cap purposes).
    """
    # Remembers the last-used source pool / destination team across dialog
    # opens within the same running session (class attributes, not instance -
    # each "Sign Free Agent..." click creates a fresh Toplevel, so instance
    # state wouldn't survive between opens).
    _last_src_tid = SIGN_SOURCE_POOLS[0][0]
    _last_dest_tid = SIGN_DEST_TEAMS[0][0]

    def __init__(self, parent, model: CSVModel):
        super().__init__(parent)
        self.title("Sign Free Agent / Pool Player")
        # 640 tall used to clip the Sign Player/Close buttons below the
        # visible window (confirmed by actually opening it) - 720 was
        # verified to show the full contract grid + buttons with no resize.
        self.geometry("640x720")
        self.minsize(600, 640)
        self.resizable(True, True)
        self.parent = parent
        self.model = model
        self.idx_player = None
        self.idx_players = []  # all currently-selected source rows (ctrl/shift-click multi-select)
        self.year_rows = []  # list of dicts: {salary_var, bonus_var, salary_lbl, bonus_lbl}

        # If a player was already selected on the Players tab and they're
        # sitting in Free Agents/the Secret pool, preselect them here instead
        # of defaulting to the first row of the last-used pool.
        self._preselect_row_idx = None
        self._preselect_src_tid = None
        sel_idx = getattr(parent, "selected_player_index", None)
        if sel_idx is not None and 0 <= sel_idx < len(model.players):
            ptid = model.player_team_id(model.players[sel_idx])
            if ptid in dict(SIGN_SOURCE_POOLS):
                self._preselect_row_idx = sel_idx
                self._preselect_src_tid = ptid

        self._build()

    def _build(self):
        top = ttk.Frame(self)
        top.pack(fill="x", padx=12, pady=10)
        ttk.Label(
            top,
            text="Reverses an in-game 'cut' - confirmed field-for-field via a live before/after test.",
            wraplength=600, justify="left",
        ).pack(anchor="w")

        src_frame = ttk.LabelFrame(self, text="Source pool")
        src_frame.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        self.cmb_src = ttk.Combobox(src_frame, state="readonly", width=30)
        self.cmb_src["values"] = [f"{tid}: {name}" for tid, name in SIGN_SOURCE_POOLS]
        self._set_combo_to_tid(self.cmb_src, self._preselect_src_tid or SignFreeAgentDialog._last_src_tid)
        self.cmb_src.pack(anchor="w", padx=10, pady=(10, 6))
        self.cmb_src.bind("<<ComboboxSelected>>", lambda e: self._refresh_roster())

        # EXTENDED selectmode: ctrl-click to add/remove individual players,
        # shift-click for a range - lets you sign several players at once
        # with the same contract terms.
        self.lst_src = tk.Listbox(src_frame, exportselection=False, selectmode=tk.EXTENDED)
        self.lst_src.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.lst_src.bind("<<ListboxSelect>>", lambda e: self._on_pick_player())

        contract = ttk.LabelFrame(self, text="New contract")
        contract.pack(fill="x", padx=12, pady=(0, 8))

        self.lbl_signing = ttk.Label(contract, text="No player selected", font=("TkDefaultFont", 10, "bold"))
        self.lbl_signing.pack(anchor="w", padx=10, pady=(8, 4))

        row1 = ttk.Frame(contract)
        row1.pack(fill="x", padx=10, pady=6)
        ttk.Label(row1, text="Sign to team:").pack(side="left")
        self.dest_combo = TeamAutocompleteCombo(
            row1, SIGN_DEST_TEAMS, width=26, initial_tid=SignFreeAgentDialog._last_dest_tid
        ).pack(side="left", padx=(6, 0))

        row2 = ttk.Frame(contract)
        row2.pack(fill="x", padx=10, pady=6)
        ttk.Label(row2, text="Contract years:").pack(side="left")
        self.years_var = tk.StringVar(value="4")
        self.spn_years = ttk.Spinbox(
            row2, from_=1, to=7, width=4, textvariable=self.years_var,
            state="readonly", command=self._rebuild_year_rows,
        )
        self.spn_years.pack(side="left", padx=(6, 16))
        ttk.Button(row2, text="Reset", command=self._rebuild_year_rows).pack(side="left")

        ttk.Label(
            contract,
            text=f"1 unit = $10,000 (max salary {PLAYER_SALARY_MAX_VALUE} = {format_cap_dollars(PLAYER_SALARY_MAX_VALUE)}, "
                 f"max bonus {PLAYER_BONUS_MAX_VALUE} = {format_cap_dollars(PLAYER_BONUS_MAX_VALUE)})",
            foreground="gray",
        ).pack(anchor="w", padx=10)

        self.years_frame = ttk.Frame(contract)
        self.years_frame.pack(fill="x", padx=10, pady=(4, 8))

        self.lbl_total = ttk.Label(contract, text="", foreground="gray")
        self.lbl_total.pack(anchor="w", padx=10, pady=(0, 6))

        bottom = ttk.Frame(self)
        bottom.pack(fill="x", padx=12, pady=(0, 10))
        ttk.Button(bottom, text="Sign Player", command=self._do_sign).pack(side="right")
        ttk.Button(bottom, text="Close", command=self.destroy).pack(side="right", padx=(0, 8))

        self._rebuild_year_rows()
        self._refresh_roster()

    def destroy(self):
        # The team combo's suggestion popup is a separate Toplevel, not a
        # child of this dialog's normal widget tree, so it needs explicit
        # cleanup. Covers both the "Close" button and the window's X button.
        self.dest_combo.destroy_popup()
        super().destroy()

    def _combo_tid(self, cmb):
        v = cmb.get()
        return v.split(":", 1)[0].strip() if ":" in v else v.strip()

    def _set_combo_to_tid(self, cmb, tid):
        for i, label in enumerate(cmb["values"]):
            if str(label).startswith(str(tid) + ":"):
                cmb.current(i)
                return
        if cmb["values"]:
            cmb.current(0)

    def _rebuild_year_rows(self):
        """Rebuild the per-year salary/bonus entry rows to match the current
        'Contract years' spinner value, each with a live-updating formatted
        dollar amount so it's unambiguous whether a number means $10K, $100K,
        $1M, etc."""
        for child in self.years_frame.winfo_children():
            child.destroy()
        self.year_rows = []

        try:
            years = int(self.years_var.get())
        except Exception:
            years = 4
        years = max(1, min(7, years))

        ttk.Label(self.years_frame, text="Year", foreground="gray").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Label(self.years_frame, text="Salary", foreground="gray").grid(row=0, column=1, sticky="w")
        ttk.Label(self.years_frame, text="= $", foreground="gray").grid(row=0, column=2, sticky="w", padx=(6, 0))
        ttk.Label(self.years_frame, text="Bonus", foreground="gray").grid(row=0, column=3, sticky="w", padx=(16, 0))
        ttk.Label(self.years_frame, text="= $", foreground="gray").grid(row=0, column=4, sticky="w", padx=(6, 0))

        for y in range(years):
            r = y + 1
            ttk.Label(self.years_frame, text=f"{y + 1}").grid(row=r, column=0, sticky="w", padx=(0, 8), pady=2)

            salary_var = tk.StringVar(value="40")
            salary_ent = ttk.Entry(self.years_frame, width=8, textvariable=salary_var)
            salary_ent.grid(row=r, column=1, sticky="w", pady=2)
            salary_lbl = ttk.Label(self.years_frame, text=format_cap_dollars(40), width=14)
            salary_lbl.grid(row=r, column=2, sticky="w", padx=(6, 0), pady=2)

            bonus_var = tk.StringVar(value="0")
            bonus_ent = ttk.Entry(self.years_frame, width=8, textvariable=bonus_var)
            bonus_ent.grid(row=r, column=3, sticky="w", padx=(16, 0), pady=2)
            bonus_lbl = ttk.Label(self.years_frame, text=format_cap_dollars(0), width=14)
            bonus_lbl.grid(row=r, column=4, sticky="w", padx=(6, 0), pady=2)

            entry = {"salary_var": salary_var, "bonus_var": bonus_var, "salary_lbl": salary_lbl, "bonus_lbl": bonus_lbl}
            salary_var.trace_add("write", lambda *_a, e=entry: self._on_year_value_changed(e))
            bonus_var.trace_add("write", lambda *_a, e=entry: self._on_year_value_changed(e))
            self.year_rows.append(entry)

            if y == 0 and years > 1:
                ttk.Button(
                    self.years_frame, text="Copy to rest →", command=self._copy_year1_to_rest,
                ).grid(row=r, column=5, sticky="w", padx=(16, 0), pady=2)

        self._update_total_label()

    def _copy_year1_to_rest(self):
        """Flat-contract shortcut (like OOTP's contract negotiation screen):
        copy Year 1's salary/bonus to every other year in one click."""
        if len(self.year_rows) < 2:
            return
        salary1 = self.year_rows[0]["salary_var"].get()
        bonus1 = self.year_rows[0]["bonus_var"].get()
        for entry in self.year_rows[1:]:
            entry["salary_var"].set(salary1)
            entry["bonus_var"].set(bonus1)

    def _on_year_value_changed(self, entry):
        entry["salary_lbl"].configure(text=format_cap_dollars(safe_int(entry["salary_var"].get()) or 0))
        entry["bonus_lbl"].configure(text=format_cap_dollars(safe_int(entry["bonus_var"].get()) or 0))
        self._update_total_label()

    def _update_total_label(self):
        total_units = sum(
            (safe_int(e["salary_var"].get()) or 0) + (safe_int(e["bonus_var"].get()) or 0)
            for e in self.year_rows
        )
        self.lbl_total.configure(text=f"Total contract value: {format_cap_dollars(total_units)}")

    def _refresh_roster(self):
        tid = self._combo_tid(self.cmb_src)
        self.lst_src.delete(0, tk.END)
        self.map_src = []
        self.idx_player = None

        team_col = self.model.team_col or "TGID"
        filtered = [(i, r) for i, r in enumerate(self.model.players)
                    if (r.get(team_col, "") or "").strip() == tid]
        filtered.sort(key=lambda ir: POSITION_ORDER.get((ir[1].get(PLAYER_POS_CODE, "") or "").strip(), 999))

        for i, r in filtered:
            pos = self.model.player_pos(r)
            name = self.model.player_name(r)
            ovr = (r.get("POVR", "") or "").strip()
            self.map_src.append(i)
            self.lst_src.insert(tk.END, f"{pos}  {name}  (OVR {ovr})  (row#{i})")

        if self.lst_src.size() > 0:
            lb_idx = 0
            if self._preselect_row_idx is not None and self._preselect_row_idx in self.map_src:
                lb_idx = self.map_src.index(self._preselect_row_idx)
            self._preselect_row_idx = None  # only honor it on the first refresh
            self.lst_src.selection_set(lb_idx)
            self.lst_src.activate(lb_idx)
            self.lst_src.see(lb_idx)
            self._on_pick_player()

    def _on_pick_player(self):
        """Refresh self.idx_players from the listbox's current selection
        (ctrl/shift-click for multiple). self.idx_player stays the FIRST
        selected one, for backward-compat call sites and the signing label."""
        sel = self.lst_src.curselection()
        self.idx_players = [self.map_src[i] for i in sel if i < len(self.map_src)]
        self.idx_player = self.idx_players[0] if self.idx_players else None
        self._update_signing_label()

    def _update_signing_label(self):
        if not hasattr(self, "lbl_signing"):
            return
        if not self.idx_players:
            self.lbl_signing.configure(text="No player selected")
            return
        if len(self.idx_players) == 1:
            row = self.model.players[self.idx_players[0]]
            pos = self.model.player_pos(row)
            name = self.model.player_name(row)
            ovr = (row.get("POVR", "") or "").strip()
            self.lbl_signing.configure(text=f"Signing: {name} ({pos}, OVR {ovr})")
        else:
            names = ", ".join(self.model.player_name(self.model.players[i]) for i in self.idx_players)
            self.lbl_signing.configure(text=f"Signing {len(self.idx_players)} players: {names}")

    def _do_sign(self):
        # Re-derive from the listbox's own current selection rather than
        # trusting cached state, so clicking player(s) and then immediately
        # clicking "Sign Player" always targets whoever is actually
        # highlighted, with no risk of stale state in between.
        self._on_pick_player()
        if not self.idx_players:
            messagebox.showwarning("Pick a player", "Select one or more players from the source pool first.")
            return

        src_tid_pool = self._combo_tid(self.cmb_src)
        dest_tid = self.dest_combo.get_tid()
        if not dest_tid:
            messagebox.showerror("Unknown team", f"'{self.dest_combo.combo.get()}' doesn't match any team.")
            return

        years = len(self.year_rows)
        salaries, bonuses = [], []
        for i, e in enumerate(self.year_rows):
            s = safe_int(e["salary_var"].get())
            b = safe_int(e["bonus_var"].get())
            if s is None or b is None:
                messagebox.showerror("Invalid contract", f"Year {i + 1}: salary/bonus must be whole numbers.")
                return
            if not (0 <= s <= PLAYER_SALARY_MAX_VALUE):
                messagebox.showerror("Invalid contract", f"Year {i + 1} salary must be 0-{PLAYER_SALARY_MAX_VALUE}.")
                return
            if not (0 <= b <= PLAYER_BONUS_MAX_VALUE):
                messagebox.showerror("Invalid contract", f"Year {i + 1} bonus must be 0-{PLAYER_BONUS_MAX_VALUE}.")
                return
            salaries.append(s)
            bonuses.append(b)

        # Everyone selected gets the SAME contract terms (years/salary/bonus
        # per year) - each signed independently, and the destination team's
        # cap total accumulates all of them together.
        signed_names = []
        total_cap_hit = 0
        for idx in self.idx_players:
            row = self.model.players[idx]
            src_tid = self.model.player_team_id(row)
            signed_names.append(self.model.player_name(row))

            for i, col in enumerate(PLAYER_CONTRACT_COLS):
                row[col] = str(salaries[i]) if i < years else "0"
            for i, col in enumerate(PLAYER_BONUS_COLS):
                row[col] = str(bonuses[i]) if i < years else "0"

            # PCSA/PTSA/PVSB formulas found by decoding a real mid-contract
            # player (Keith Brooking, Falcons LB, PCON=7/PCYL=2: PCSA=649
            # exactly equals PSA[5]+PSB[5] where 5=PCON-PCYL, i.e. the CURRENT
            # year's salary+bonus combined - and PTSA=3640 exactly equals
            # sum(all PSA)+sum(all PSB)). For a brand-new signing, PCON==PCYL
            # so the current-year index is 0, which is exactly what this
            # dialog just wrote to PSA0/PSB0 - i.e. year 1's entered
            # salary/bonus.
            total_salary = sum(int(row.get(c, "0") or "0") for c in PLAYER_CONTRACT_COLS)
            total_bonus = sum(int(row.get(c, "0") or "0") for c in PLAYER_BONUS_COLS)
            year1_cap_hit = salaries[0] + bonuses[0]

            team_moved = self.model.set_player_team_id(row, dest_tid)
            if not team_moved:
                messagebox.showwarning(
                    "Team not changed",
                    f"{self.model.player_name(row)}'s contract was updated, but the team column "
                    "wasn't detected for this save, so they weren't actually moved to the new team."
                )
            row["PCON"] = str(years)
            row["PCYL"] = str(years)
            # PCSA/PTSA/PVSB are sums of already-validated per-year values, but
            # their own fields are narrower than what those sums can reach -
            # clamp to each field's real max instead of letting it silently
            # overflow/wrap on write (see PLAYER_PCSA_MAX_VALUE etc. above).
            row["PCSA"] = str(min(year1_cap_hit, PLAYER_PCSA_MAX_VALUE))
            row["PTSA"] = str(min(total_salary + total_bonus, PLAYER_PTSA_MAX_VALUE))
            row["PVSB"] = str(min(total_bonus, PLAYER_PVSB_MAX_VALUE))
            row["PPTI"] = str(src_tid)
            total_cap_hit += year1_cap_hit

        # Team-wide "Team Salary Cap" (TMSA) is a separately stored total, NOT
        # dynamically computed from the roster - confirmed live (bumping a
        # player's cap hit updated their own card correctly but left the
        # Team Roadmap's cap number frozen until TMSA itself was updated).
        # Each signed player's cap hit is exactly year 1's salary+bonus (same
        # units as TMSA), so the sum across everyone signed gets added.
        cap_updated = self.model.adjust_team_salary_cap(dest_tid, total_cap_hit)

        self.parent.mark_dirty()
        SignFreeAgentDialog._last_src_tid = src_tid_pool
        SignFreeAgentDialog._last_dest_tid = dest_tid
        dest_name = TEAM_NAMES.get(dest_tid, dest_tid)
        cap_note = "" if cap_updated else "\n\n(Team cap total not found/updated - load a save with the TEAM table.)"
        who = signed_names[0] if len(signed_names) == 1 else f"{len(signed_names)} players ({', '.join(signed_names)})"
        messagebox.showinfo(
            "Player(s) signed",
            f"{who} signed to {dest_tid}: {dest_name}\n"
            f"{years} year(s) each, {format_cap_dollars(salaries[0] + bonuses[0])}/yr year 1.{cap_note}"
        )

        self.parent.refresh_players_for_team()
        self.parent.refresh_stats_for_player()
        self._refresh_roster()


BASE_TITLE = "HC09 CSV Editor (GUI) - Safe Trades"

# -----------------------------
# Visual theme (cosmetic only - no functional change).
# Applied via App._apply_theme() using ttk.Style + the Tk option database, so
# plain tk widgets (Listbox/Text, still used in several places for
# performance/simplicity) pick up matching colors/fonts without having to
# edit every widget construction site individually. Light/dark are both full
# palettes so the "Dark Mode" toggle can just swap which one is active.
# -----------------------------
UI_FONT_FAMILY = "Segoe UI"

UI_PALETTE_LIGHT = {
    "bg": "#f4f6fb", "surface": "#ffffff", "text": "#1c2430", "subtle": "#68707d",
    "border": "#d7dbe3", "accent": "#2f6fed", "accent_hover": "#255ed1",
    "accent_text": "#ffffff", "header_bg": "#eef1f7",
}
UI_PALETTE_DARK = {
    "bg": "#191c20", "surface": "#23262c", "text": "#f2f4f8", "subtle": "#aab0bb",
    "border": "#42474f", "accent": "#5b9bff", "accent_hover": "#7cadff",
    "accent_text": "#0b0e12", "header_bg": "#2c3038",
}

UI_PREFS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".hc09_ui_prefs.json")

def load_ui_prefs():
    try:
        with open(UI_PREFS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                data.setdefault("mode", "light")
                data.setdefault("facelift_enabled", True)
                return data
    except Exception:
        pass
    return {"mode": "light", "facelift_enabled": True}

def save_ui_prefs(prefs):
    try:
        with open(UI_PREFS_PATH, "w", encoding="utf-8") as f:
            json.dump(prefs, f, indent=2)
    except Exception:
        pass

# -----------------------------
# Portrait support (qkl_fe2ig.ast player/coach headshots)
# -----------------------------
# See docs/hc09_photo_customization findings: top-level AST entry 1777 is a
# nested archive of ~3580 player headshots keyed by shortId, which PSXP
# equals directly. Coach portraits (entry 1775) use the same mechanism but
# the coach-side ID field hasn't been independently confirmed yet.
PORTRAIT_TOP_INDEX = {"player": 1777, "coach": 1775}
PORTRAIT_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".hc09_portrait_cache")
PORTRAIT_ARCHIVE_FILENAME = {"player": "player_portraits.bin", "coach": "coach_portraits.bin"}

# Auto-detected first: the RPCS3 install location the archive was originally
# found at. If it's not there (different machine/install), on_locate_game_files
# still lets you point at it manually.
KNOWN_GAME_AST_CANDIDATES = [
    r"C:\Emulators\Emulator stuff\Rpcs3\NFL Head Coach 09 (USA)\NFL Head Coach 09 (USA)\PS3_GAME\USRDIR\qkl_fe2ig.ast",
]


class PlayerContractDialog(tk.Toplevel):
    """Contract editor for an existing player - same all-years grid style as
    SignFreeAgentDialog's contract section, but pre-filled with the player's
    actual current PSA0-6/PSB0-6 values instead of defaults for a brand-new
    signing. Opened from the Players + Stats tab's 'Edit Contract...' button,
    replacing what used to be an always-expanded inline grid on that screen."""

    def __init__(self, parent, model: CSVModel, player_index: int):
        super().__init__(parent)
        p = getattr(parent, "_ui_palette", None)
        if p:
            self.configure(background=p["bg"])
        self.title("Edit Contract")
        # No explicit geometry - let it size itself snugly to its actual
        # content instead of guessing a fixed height (a hardcoded 640px left
        # a large empty gap below the buttons on most players' contracts).
        # Locked non-resizable since that snug fit is the whole point - a
        # fixed grid of contract years, nothing here benefits from more room.
        self.resizable(False, False)
        self.minsize(420, 460)
        self.transient(parent)
        self.grab_set()

        self.parent = parent
        self.model = model
        self.player_index = player_index
        self.rows = []  # [{salary_var, bonus_var, salary_lbl, bonus_lbl, salary_col, bonus_col}]

        row = self.model.players[player_index]
        name = self.model.player_name(row) if hasattr(self.model, "player_name") else ""
        ttk.Label(self, text=f"Player: {name}", font=("", 10, "bold"), padding=(12, 12, 12, 4)).pack(anchor="w")

        ttk.Label(
            self,
            text=f"1 unit = $10,000 (max salary {PLAYER_SALARY_MAX_VALUE} = {format_cap_dollars(PLAYER_SALARY_MAX_VALUE)}, "
                 f"max bonus {PLAYER_BONUS_MAX_VALUE} = {format_cap_dollars(PLAYER_BONUS_MAX_VALUE)})",
            foreground="gray", wraplength=420, justify="left",
        ).pack(anchor="w", padx=12)

        years_frame = ttk.Frame(self)
        years_frame.pack(fill="x", padx=12, pady=(8, 4))

        ttk.Label(years_frame, text="Year", foreground="gray").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Label(years_frame, text="Salary", foreground="gray").grid(row=0, column=1, sticky="w")
        ttk.Label(years_frame, text="= $", foreground="gray").grid(row=0, column=2, sticky="w", padx=(6, 0))
        ttk.Label(years_frame, text="Bonus", foreground="gray").grid(row=0, column=3, sticky="w", padx=(16, 0))
        ttk.Label(years_frame, text="= $", foreground="gray").grid(row=0, column=4, sticky="w", padx=(6, 0))

        for y in range(7):
            r = y + 1
            salary_col, bonus_col = f"PSA{y}", f"PSB{y}"
            salary_now = safe_int(row.get(salary_col, "")) or 0
            bonus_now = safe_int(row.get(bonus_col, "")) or 0

            ttk.Label(years_frame, text=f"{y}").grid(row=r, column=0, sticky="w", padx=(0, 8), pady=2)

            salary_var = tk.StringVar(value=str(salary_now))
            ttk.Entry(years_frame, width=8, textvariable=salary_var).grid(row=r, column=1, sticky="w", pady=2)
            salary_lbl = ttk.Label(years_frame, text=format_cap_dollars(salary_now), width=14)
            salary_lbl.grid(row=r, column=2, sticky="w", padx=(6, 0), pady=2)

            bonus_var = tk.StringVar(value=str(bonus_now))
            ttk.Entry(years_frame, width=8, textvariable=bonus_var).grid(row=r, column=3, sticky="w", padx=(16, 0), pady=2)
            bonus_lbl = ttk.Label(years_frame, text=format_cap_dollars(bonus_now), width=14)
            bonus_lbl.grid(row=r, column=4, sticky="w", padx=(6, 0), pady=2)

            entry = {
                "salary_var": salary_var, "bonus_var": bonus_var,
                "salary_lbl": salary_lbl, "bonus_lbl": bonus_lbl,
                "salary_col": salary_col, "bonus_col": bonus_col,
            }
            salary_var.trace_add("write", lambda *_a, e=entry: self._on_row_changed(e))
            bonus_var.trace_add("write", lambda *_a, e=entry: self._on_row_changed(e))
            self.rows.append(entry)

            if y == 0:
                ttk.Button(years_frame, text="Copy to rest →", command=self._copy_year0_to_rest).grid(
                    row=r, column=5, sticky="w", padx=(16, 0), pady=2
                )

        self.lbl_total = ttk.Label(self, text="", foreground="gray")
        self.lbl_total.pack(anchor="w", padx=12, pady=(4, 8))
        self._update_total_label()

        min_btns = ttk.Frame(self)
        min_btns.pack(fill="x", padx=12, pady=(0, 4))
        ttk.Button(min_btns, text="Set All Salary Min", command=self._set_salary_min).pack(side="left")
        ttk.Button(min_btns, text="Set All Bonus Min", command=self._set_bonus_min).pack(side="left", padx=(8, 0))

        bottom = ttk.Frame(self)
        bottom.pack(fill="x", padx=12, pady=(8, 12), side="bottom")
        ttk.Button(bottom, text="Apply", style="Accent.TButton", command=self._on_apply).pack(side="right")
        ttk.Button(bottom, text="Close", command=self.destroy).pack(side="right", padx=(0, 8))

    def _on_row_changed(self, entry):
        entry["salary_lbl"].configure(text=format_cap_dollars(safe_int(entry["salary_var"].get()) or 0))
        entry["bonus_lbl"].configure(text=format_cap_dollars(safe_int(entry["bonus_var"].get()) or 0))
        self._update_total_label()

    def _update_total_label(self):
        total_units = sum(
            (safe_int(e["salary_var"].get()) or 0) + (safe_int(e["bonus_var"].get()) or 0)
            for e in self.rows
        )
        self.lbl_total.configure(text=f"Total contract value (all 7 years): {format_cap_dollars(total_units)}")

    def _copy_year0_to_rest(self):
        salary0 = self.rows[0]["salary_var"].get()
        bonus0 = self.rows[0]["bonus_var"].get()
        for entry in self.rows[1:]:
            entry["salary_var"].set(salary0)
            entry["bonus_var"].set(bonus0)

    def _set_salary_min(self):
        # 1 (the lowest non-zero unit, $10,000/yr) rather than 0 - some
        # in-game behavior around a literal $0 salary is untested/unclear,
        # so defaulting to the lowest non-zero value avoids the risk.
        for entry in self.rows:
            entry["salary_var"].set("1")

    def _set_bonus_min(self):
        for entry in self.rows:
            entry["bonus_var"].set("0")

    def _on_apply(self):
        row = self.model.players[self.player_index]
        headers = set(self.model.player_headers or [])
        try:
            updates = 0
            for entry in self.rows:
                salary_col, bonus_col = entry["salary_col"], entry["bonus_col"]
                if salary_col in headers:
                    salary_val = max(0, min(PLAYER_SALARY_MAX_VALUE, int(entry["salary_var"].get() or "0")))
                    row[salary_col] = str(salary_val)
                    updates += 1
                if bonus_col in headers:
                    bonus_val = max(0, min(PLAYER_BONUS_MAX_VALUE, int(entry["bonus_var"].get() or "0")))
                    row[bonus_col] = str(bonus_val)
                    updates += 1
            self.parent.mark_dirty()
            self.parent.refresh_players_for_team(preselect_model_idx=self.player_index)
            self.parent.refresh_stats_for_player()
            messagebox.showinfo("Contract updated", f"Updated {updates} field(s) across all 7 years.")
            self.destroy()
        except Exception as e:
            messagebox.showerror("Contract Error", str(e))


class PersonalityDialog(tk.Toplevel):
    """Personality (PTId) viewer/editor - works identically for a PLAY row or
    a COCH row, since both tables use the same PTId field/encoding. Shows the
    current personality's traits (community-compiled effects reference) and
    lets you pick a different one of the 17 real personality types."""

    def __init__(self, parent, rows_list, row_index, subject_label, refresh_callback, subject_kind="player"):
        super().__init__(parent)
        p = getattr(parent, "_ui_palette", None)
        if p:
            self.configure(background=p["bg"])
        self.title("Personality")
        self.minsize(460, 520)
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()

        self.parent = parent
        self.rows_list = rows_list
        self.row_index = row_index
        self.refresh_callback = refresh_callback
        # Easy/Hard to Sign and Easy/Hard to Please are about contract
        # negotiation with a PLAYER - not meaningful for a coach's own
        # personality, so those measurements are left out entirely in that
        # context (both the compare table and the per-trait tag list below).
        self.is_coach = (subject_kind == "coach")

        row = rows_list[row_index]
        current_ptid = safe_int(row.get("PTId", ""))
        current_name = PERSONALITY_PTID_TO_NAME.get(current_ptid, f"Unknown (PTId={current_ptid})")

        ttk.Label(self, text=subject_label, font=("", 10, "bold"), padding=(12, 12, 12, 0)).pack(anchor="w")

        if not PERSONALITY_DATA:
            ttk.Label(
                self, foreground="gray", wraplength=420, justify="left",
                text=f"Current PTId: {current_ptid} ({current_name})\n\n"
                     f"docs/personality_traits_reference.json not found next to guiHC09.py - "
                     f"trait details and the name<->PTId picker aren't available without it.",
            ).pack(anchor="w", padx=12, pady=12)
            ttk.Button(self, text="Close", command=self.destroy).pack(anchor="e", padx=12, pady=(0, 12))
            return

        self.minsize(620, 640)

        row_frm = ttk.Frame(self)
        row_frm.pack(fill="x", padx=12, pady=(6, 4))
        ttk.Label(row_frm, text="Personality:").pack(side="left")
        self.personality_var = tk.StringVar(value=current_name)
        names_sorted = sorted(PERSONALITY_NAME_TO_PTID.keys())
        cmb = ttk.Combobox(row_frm, state="readonly", width=20, textvariable=self.personality_var, values=names_sorted)
        cmb.pack(side="left", padx=(8, 0))
        cmb.bind("<<ComboboxSelected>>", lambda e: self._on_personality_picked())

        # Compare table: every personality's trait counts across the same six
        # measurements shown on the reference spreadsheet - click a column
        # header to sort by it, to find the type that best matches what
        # you're looking for (e.g. sort by "Easy to Sign" descending).
        ttk.Label(
            self, foreground="gray",
            text="Click a column to sort, or set target counts below and find the closest match - "
                 "if no personality hits your targets exactly, the nearest ones rank first instead of nothing.",
            wraplength=580, justify="left",
        ).pack(anchor="w", padx=12, pady=(2, 2))

        target_frm = ttk.Frame(self)
        target_frm.pack(fill="x", padx=12, pady=(2, 4))
        ttk.Label(target_frm, text="Target counts (blank = don't care):").pack(side="left")
        self.target_vars = {}
        if self.is_coach:
            target_cols = ["quiet", "loud"]
        else:
            target_cols = ["easy_sign", "hard_sign", "easy_please", "hard_please", "quiet", "loud"]
        target_labels = {
            "easy_sign": "Easy Sign", "hard_sign": "Hard Sign", "easy_please": "Easy Please",
            "hard_please": "Hard Please", "quiet": "Quiet", "loud": "Loud",
        }
        target_choices = [""] + [str(n) for n in range(0, 8)]
        for c in target_cols:
            ttk.Label(target_frm, text=target_labels[c] + ":").pack(side="left", padx=(8, 2))
            var = tk.StringVar(value="")
            ttk.Combobox(
                target_frm, state="readonly", width=2, textvariable=var, values=target_choices,
            ).pack(side="left")
            self.target_vars[c] = var
        ttk.Button(target_frm, text="Find Closest Match", command=self._find_closest_match).pack(side="left", padx=(10, 0))
        ttk.Button(target_frm, text="Clear", command=self._clear_targets).pack(side="left", padx=(4, 0))

        table_frm = ttk.Frame(self)
        table_frm.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        if self.is_coach:
            cols = ("name", "quiet", "loud", "match_score")
        else:
            cols = ("name", "easy_sign", "hard_sign", "easy_please", "hard_please", "quiet", "loud", "match_score")
        headers = {
            "name": "Personality", "easy_sign": "Easy to Sign", "hard_sign": "Hard to Sign",
            "easy_please": "Easy to Please", "hard_please": "Hard to Please", "quiet": "Quiet", "loud": "Loud",
            "match_score": "Match",
        }
        self.compare_cols = cols
        self.compare_tree = ttk.Treeview(table_frm, columns=cols, show="headings", height=8)
        for c in cols:
            self.compare_tree.heading(c, text=headers[c], command=lambda c=c: self._sort_compare_table(c))
            self.compare_tree.column(c, width=70 if c != "name" else 110, anchor="center" if c != "name" else "w", stretch=False)
        xscroll = ttk.Scrollbar(table_frm, orient="horizontal", command=self.compare_tree.xview)
        self.compare_tree.configure(xscrollcommand=xscroll.set)
        self.compare_tree.pack(fill="both", expand=True)
        xscroll.pack(fill="x")
        self.compare_tree.bind("<<TreeviewSelect>>", self._on_compare_row_selected)
        self._compare_sort_state = {}
        self._populate_compare_table()

        ttk.Label(self, text="Traits for the selected personality (community-compiled, not dev-confirmed):",
                  foreground="gray").pack(anchor="w", padx=12, pady=(6, 0))

        text_frm = ttk.Frame(self)
        text_frm.pack(fill="both", expand=True, padx=12, pady=(4, 8))
        self.traits_text = tk.Text(text_frm, height=10, wrap="word", relief="flat", borderwidth=1)
        if p:
            self.traits_text.configure(background=p["surface"], foreground=p["text"], highlightbackground=p["border"])
        scroll = ttk.Scrollbar(text_frm, orient="vertical", command=self.traits_text.yview)
        self.traits_text.configure(yscrollcommand=scroll.set)
        self.traits_text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        btn_frm = ttk.Frame(self)
        btn_frm.pack(fill="x", padx=12, pady=(0, 12))
        apply_btn_kwargs = {"style": "Accent.TButton"} if p else {}
        ttk.Button(btn_frm, text="Apply", command=self._apply, **apply_btn_kwargs).pack(side="right")
        ttk.Button(btn_frm, text="Close", command=self.destroy).pack(side="right", padx=(0, 8))

        self._refresh_traits_display()
        self._select_compare_row(current_name)

    _COL_TO_SUMMARY_KEY = {
        "easy_sign": "Easy to Sign", "hard_sign": "Hard to Sign",
        "easy_please": "Easy to Please", "hard_please": "Hard to Please",
        "quiet": "Quiet", "loud": "Loud",
    }

    def _populate_compare_table(self):
        for iid in self.compare_tree.get_children():
            self.compare_tree.delete(iid)
        for name in sorted(PERSONALITY_NAME_TO_PTID.keys()):
            info = PERSONALITY_DATA.get("type_summary", {}).get(name, {})
            values = []
            for col in self.compare_cols:
                if col == "name":
                    values.append(name)
                elif col == "match_score":
                    values.append("")
                else:
                    values.append(int(info.get(self._COL_TO_SUMMARY_KEY[col], 0)))
            self.compare_tree.insert("", tk.END, iid=name, values=tuple(values))

    def _clear_targets(self):
        for var in self.target_vars.values():
            var.set("")
        for iid in self.compare_tree.get_children():
            self.compare_tree.set(iid, "match_score", "")

    def _find_closest_match(self):
        """Ranks every personality by total distance from the target counts
        you set (ignoring blank fields). If nothing hits your targets
        exactly, the closest ones simply sort to the top instead of the
        table coming up empty - there's no hard filtering-out here."""
        targets = {}
        for col, var in self.target_vars.items():
            raw = var.get().strip()
            if raw != "":
                try:
                    targets[col] = float(raw)
                except ValueError:
                    messagebox.showwarning("Invalid target", f"'{raw}' isn't a number.")
                    return

        if not targets:
            messagebox.showinfo("No targets set", "Enter at least one target count to find the closest match.")
            return

        col_to_key = self._COL_TO_SUMMARY_KEY
        scored = []
        for name in PERSONALITY_NAME_TO_PTID.keys():
            info = PERSONALITY_DATA.get("type_summary", {}).get(name, {})
            distance = sum(abs(float(info.get(col_to_key[col], 0)) - target) for col, target in targets.items())
            scored.append((distance, name))
        scored.sort(key=lambda x: x[0])

        for distance, name in scored:
            self.compare_tree.set(name, "match_score", f"{distance:g}")
        for index, (_, name) in enumerate(scored):
            self.compare_tree.move(name, "", index)

        self._compare_sort_state = {}
        best_name = scored[0][1]
        self.personality_var.set(best_name)
        self._select_compare_row(best_name)
        self._refresh_traits_display()

    def _sort_compare_table(self, col):
        reverse = self._compare_sort_state.get(col, False)
        rows = [(self.compare_tree.set(iid, col), iid) for iid in self.compare_tree.get_children()]
        try:
            rows.sort(key=lambda r: float(r[0]), reverse=reverse)
        except ValueError:
            rows.sort(key=lambda r: r[0], reverse=reverse)
        for index, (_, iid) in enumerate(rows):
            self.compare_tree.move(iid, "", index)
        self._compare_sort_state[col] = not reverse

    def _select_compare_row(self, name):
        if name in self.compare_tree.get_children():
            self.compare_tree.selection_set(name)
            self.compare_tree.see(name)

    def _on_compare_row_selected(self, event=None):
        sel = self.compare_tree.selection()
        if not sel:
            return
        self.personality_var.set(sel[0])
        self._refresh_traits_display()

    def _on_personality_picked(self):
        self._select_compare_row(self.personality_var.get())
        self._refresh_traits_display()

    def _refresh_traits_display(self):
        name = self.personality_var.get()
        type_info = PERSONALITY_DATA.get("type_summary", {}).get(name, {})
        trait_names = type_info.get("traits", [])

        lines = []
        for t in trait_names:
            tinfo = PERSONALITY_DATA.get("traits", {}).get(t, {})
            tags = []
            if not self.is_coach:
                if tinfo.get("easy_to_sign"):
                    tags.append("Easy to Sign")
                if tinfo.get("hard_to_sign"):
                    tags.append("Hard to Sign")
                if tinfo.get("easy_to_please"):
                    tags.append("Easy to Please")
                if tinfo.get("hard_to_please"):
                    tags.append("Hard to Please")
            if tinfo.get("quiet"):
                tags.append("Quiet")
            if tinfo.get("loud"):
                tags.append("Loud")
            tag_str = f" [{', '.join(tags)}]" if tags else ""
            lines.append(f"• {t}{tag_str}\n   {tinfo.get('description', '')}")

        self.traits_text.configure(state="normal")
        self.traits_text.delete("1.0", tk.END)
        self.traits_text.insert("1.0", "\n\n".join(lines) if lines else "No trait data for this type.")
        self.traits_text.configure(state="disabled")

    def _apply(self):
        name = self.personality_var.get()
        ptid = PERSONALITY_NAME_TO_PTID.get(name)
        if ptid is None:
            messagebox.showerror("Personality Error", f"No known PTId for '{name}'.")
            return

        row = self.rows_list[self.row_index]
        row["PTId"] = str(ptid)
        self.parent.mark_dirty()
        if self.refresh_callback:
            self.refresh_callback()

        messagebox.showinfo("Personality updated", f"Set to {name} (PTId={ptid}).")
        self.destroy()


class AssignPortraitDialog(tk.Toplevel):
    """Reassign one of the game's ~3580 existing in-game portraits to a
    player - no game-file modification needed, since PSXP (the player's
    portrait ID) is a plain save field and the portrait itself is read from
    the untouched game disc. Browse by shortId (Prev/Next/Random/jump-to),
    preview, Apply writes PSXP. Uploading a genuinely custom photo would
    require repacking the archive on disk - separate, unsolved problem."""

    def __init__(self, parent, row, row_name, refresh_callback):
        super().__init__(parent)
        p = getattr(parent, "_ui_palette", None)
        if p:
            self.configure(background=p["bg"])
        self.title("Assign Existing Photo")
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)

        self.parent = parent
        self.row = row
        self.refresh_callback = refresh_callback
        self.shortids = []
        self._req_id = 0

        ttk.Label(self, text=f"Player: {row_name}", font=("", 10, "bold"), padding=(12, 12, 12, 0)).pack(anchor="w")

        img_kwargs = {}
        if p:
            img_kwargs["background"] = p["surface"]
        self.img_label = tk.Label(self, text="Loading archive index...", width=256, height=256, **img_kwargs)
        self.img_label.pack(padx=12, pady=8)

        nav = ttk.Frame(self)
        nav.pack(padx=12, pady=(0, 4))
        ttk.Button(nav, text="< Prev", command=self._on_prev).pack(side="left")
        self.shortid_var = tk.StringVar(value="")
        ent = ttk.Entry(nav, textvariable=self.shortid_var, width=6)
        ent.pack(side="left", padx=6)
        ent.bind("<Return>", lambda e: self._on_jump())
        ttk.Button(nav, text="Go", command=self._on_jump).pack(side="left")
        ttk.Button(nav, text="Random", command=self._on_random).pack(side="left", padx=(6, 0))
        ttk.Button(nav, text="Next >", command=self._on_next).pack(side="left", padx=(6, 0))

        self.lbl_status = ttk.Label(self, text="", wraplength=280, justify="left")
        self.lbl_status.pack(anchor="w", padx=12)

        btn_frm = ttk.Frame(self)
        btn_frm.pack(fill="x", padx=12, pady=12)
        apply_kwargs = {"style": "Accent.TButton"} if p else {}
        ttk.Button(btn_frm, text="Assign to Player", command=self._apply, **apply_kwargs).pack(side="right")
        ttk.Button(btn_frm, text="Cancel", command=self.destroy).pack(side="right", padx=(0, 8))

        self.cur_idx = 0
        threading.Thread(target=self._load_index, daemon=True).start()

    def _load_index(self):
        try:
            ast_path = self.parent.get_game_ast_path()
            if not ast_path:
                self.after(0, lambda: self.lbl_status.configure(text="Locate your game files first (see the Portrait panel)."))
                return
            cache_path = self.parent._portrait_archive_cache_path("player")
            if not os.path.isfile(cache_path):
                os.makedirs(PORTRAIT_CACHE_DIR, exist_ok=True)
                self.parent.model.run_bridge([
                    "portrait-extract-archive", "--ast", ast_path,
                    "--top-index", str(PORTRAIT_TOP_INDEX["player"]), "--out", cache_path,
                ])
            result = self.parent.model.run_bridge(["portrait-list", "--archive", cache_path])
            shortids = result.get("shortIds", [])
            current = safe_int(self.row.get(PLAYER_PORTRAIT_CODE, ""))
            start_idx = shortids.index(current) if current in shortids else 0
            self.after(0, lambda: self._on_index_loaded(shortids, start_idx))
        except Exception as e:
            self.after(0, lambda: self.lbl_status.configure(text=f"Couldn't load portrait archive: {e}"))

    def _on_index_loaded(self, shortids, start_idx):
        self.shortids = shortids
        self.cur_idx = start_idx
        self.lbl_status.configure(text=f"{len(shortids)} portraits available.")
        self._show_current()

    def _on_prev(self):
        if self.shortids:
            self.cur_idx = (self.cur_idx - 1) % len(self.shortids)
            self._show_current()

    def _on_next(self):
        if self.shortids:
            self.cur_idx = (self.cur_idx + 1) % len(self.shortids)
            self._show_current()

    def _on_random(self):
        if self.shortids:
            self.cur_idx = random.randrange(len(self.shortids))
            self._show_current()

    def _on_jump(self):
        if not self.shortids:
            return
        target = safe_int(self.shortid_var.get())
        if target is None or target not in self.shortids:
            messagebox.showwarning("Not found", f"'{self.shortid_var.get()}' isn't a valid portrait ID.")
            return
        self.cur_idx = self.shortids.index(target)
        self._show_current()

    def _show_current(self):
        if not self.shortids:
            return
        shortid = self.shortids[self.cur_idx]
        self.shortid_var.set(str(shortid))
        self._req_id += 1
        req_id = self._req_id
        self.img_label.configure(image="", text="Loading...")

        def worker():
            try:
                pil_image = self.parent._load_portrait_image("player", shortid)
                error = None
            except Exception as e:
                pil_image = None
                error = str(e)
            self.after(0, lambda: self._on_loaded(req_id, pil_image, error))

        threading.Thread(target=worker, daemon=True).start()

    def _on_loaded(self, req_id, pil_image, error):
        if req_id != self._req_id:
            return
        if error or pil_image is None:
            self.img_label.configure(image="", text="Error" if error else "No image")
            return
        photo = ImageTk.PhotoImage(pil_image)
        self._photo_ref = photo  # keep alive
        self.img_label.configure(image=photo, text="")

    def _apply(self):
        if not self.shortids:
            return
        shortid = self.shortids[self.cur_idx]
        self.row[PLAYER_PORTRAIT_CODE] = str(shortid)
        self.parent.mark_dirty()
        if self.refresh_callback:
            self.refresh_callback()
        messagebox.showinfo("Photo assigned", f"Portrait ID set to {shortid}.")
        self.destroy()


class PlayerTypeFitDialog(tk.Toplevel):
    """Rank a pool of players (a team, all teams, Free Agents, Draft Class, Game Changer Players) by how well their
    ratings suit one of the game's team position philosophies - the presets on the Team Philosophy screen - using
    the weights the game itself gives each rating (see load_philosophy_weights). Read-only. 'Team's pick' shows
    the preset each player's team has now (TPHS)."""

    POOL_OPTIONS = [
        ("this_team", "This Team"),
        ("all_teams", "All Teams"),
        ("free_agents", "Free Agents"),
        ("draft_class", "Draft Class"),
        ("game_changers", "Game Changer Players"),
    ]

    def __init__(self, parent, model):
        super().__init__(parent)
        p = getattr(parent, "_ui_palette", None)
        if p:
            self.configure(background=p["bg"])
        self.title("Player Type Fit")
        self.transient(parent)
        self.geometry("820x600")
        self.minsize(640, 420)
        self.resizable(True, True)

        self.parent = parent
        self.model = model

        if not PHILOSOPHY_WEIGHTS:
            ttk.Label(
                self, foreground="gray", wraplength=420, justify="left",
                text="The philosophy data isn't available. This feature needs it from your own game files "
                     "(qkl_boot.ast) - reopen Player Type Fit to locate it.",
            ).pack(anchor="w", padx=12, pady=12)
            ttk.Button(self, text="Close", command=self.destroy).pack(anchor="e", padx=12, pady=(0, 12))
            return

        self._groups = {label: (field, ppos) for label, field, ppos in PHILOSOPHY_GROUPS}
        self._preset_ids = {}

        top = ttk.Frame(self)
        top.pack(fill="x", padx=12, pady=(12, 4))
        ttk.Label(top, text="Position:").pack(side="left")
        self.group_var = tk.StringVar()
        cmb_group = ttk.Combobox(top, state="readonly", width=18, textvariable=self.group_var, values=[g[0] for g in PHILOSOPHY_GROUPS])
        cmb_group.pack(side="left", padx=(6, 14))
        cmb_group.bind("<<ComboboxSelected>>", lambda e: self._on_group())
        ttk.Label(top, text="Preset:").pack(side="left")
        self.preset_var = tk.StringVar()
        self.cmb_preset = ttk.Combobox(top, state="readonly", width=28, textvariable=self.preset_var)
        self.cmb_preset.pack(side="left", padx=(6, 14))
        self.cmb_preset.bind("<<ComboboxSelected>>", lambda e: self._refresh())
        ttk.Label(top, text="Pool:").pack(side="left")
        pool_labels = [label for _key, label in self.POOL_OPTIONS]
        self.pool_var = tk.StringVar(value=pool_labels[0])
        cmb_pool = ttk.Combobox(top, state="readonly", width=18, textvariable=self.pool_var, values=pool_labels)
        cmb_pool.pack(side="left", padx=(6, 0))
        cmb_pool.bind("<<ComboboxSelected>>", lambda e: self._refresh())

        opts = ttk.Frame(self)
        opts.pack(fill="x", padx=12, pady=(0, 2))
        self.other_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts, text="Include players of other positions (e.g. corners for a safety preset)",
                        variable=self.other_var, command=self._refresh).pack(side="left")

        self.lbl_key = ttk.Label(self, wraplength=780, justify="left")
        self.lbl_key.pack(anchor="w", padx=12, pady=(4, 2))
        ttk.Label(
            self, foreground="gray", wraplength=780, justify="left",
            text="Fit is the average of a player's ratings weighted the way the game weights them for this preset (the athletic "
                 "and skill weights from the game's files; height, weight and scouting factors are not included). It ranks who suits the "
                 "preset - it is not the game's overall, which may weigh things differently. Team's pick is the preset that player's team "
                 "has now. Nothing is changed.",
        ).pack(anchor="w", padx=12, pady=(0, 6))

        table_frm = ttk.Frame(self)
        table_frm.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        cols = ("name", "team", "pos", "ovr", "fit", "pick")
        headers = {"name": ("Player", 190), "team": ("Team", 140), "pos": ("Pos", 55), "ovr": ("OVR", 55), "fit": ("Fit", 60), "pick": ("Team's pick", 190)}
        self.tree = ttk.Treeview(table_frm, columns=cols, show="headings")
        for c in cols:
            text, width = headers[c]
            self.tree.heading(c, text=text, command=lambda c=c: self._sort_by(c))
            self.tree.column(c, width=width, anchor="w" if c in ("name", "team", "pick") else "center", stretch=(c in ("name", "team", "pick")))
        yscroll = ttk.Scrollbar(table_frm, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=yscroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")

        btn_frm = ttk.Frame(self)
        btn_frm.pack(fill="x", padx=12, pady=(0, 12))
        ttk.Button(btn_frm, text="Close", command=self.destroy).pack(side="right")

        self._sort_state = {}
        # start on the selected player's position, and on the preset his team has for it
        start_label, start_value = PHILOSOPHY_GROUPS[0][0], None
        idx = getattr(parent, "selected_player_index", None)
        if idx is not None and 0 <= idx < len(self.model.players):
            row = self.model.players[idx]
            ppos = (row.get(PLAYER_POS_CODE, "") or "").strip()
            for label, field, group_ppos in PHILOSOPHY_GROUPS:
                if ppos in group_ppos:
                    start_label = label
                    start_value = self._team_pick_value(self.model.player_team_id(row), field)
                    break
        self.group_var.set(start_label)
        self._on_group(select_value=start_value)

    # ---- presets
    def _on_group(self, select_value=None):
        field, _ppos = self._groups[self.group_var.get()]
        names = PHILOSOPHY_VALUES[field]
        self._preset_ids = {name: value for value, name in sorted(names.items())}
        self.cmb_preset.configure(values=list(self._preset_ids))
        chosen = next((n for n, v in self._preset_ids.items() if v == select_value), next(iter(self._preset_ids)))
        self.preset_var.set(chosen)
        self._refresh()

    def _team_pick_value(self, tid, field):
        if tid not in dict(SIGN_DEST_TEAMS):      # Free Agents / draft class / Game Changers have default rows but no team
            return None
        for r in self.model.tphs:
            if (r.get("TGID") or "").strip() == tid:
                return safe_int(r.get(field, ""))
        return None

    # ---- players
    def _pool_key(self):
        label = self.pool_var.get()
        for key, plabel in self.POOL_OPTIONS:
            if plabel == label:
                return key
        return "this_team"

    def _pool_rows(self):
        pool = self._pool_key()
        if pool == "this_team":
            tid = getattr(self.parent, "selected_team_id", None)
            tid = tid.get() if tid else ""
            if not tid:
                return []
            return [r for r in self.model.players if self.model.player_team_id(r) == tid]
        if pool == "free_agents":
            return [r for r in self.model.players if self.model.player_team_id(r) == "1009"]
        if pool == "draft_class":
            return [r for r in self.model.players if self.model.player_team_id(r) == "1015"]
        if pool == "game_changers":
            return [r for r in self.model.players if self.model.player_team_id(r) == "1013"]
        # all_teams: every real team, i.e. exclude the pool IDs above
        pool_ids = {"1009", "1013", "1015"}
        return [r for r in self.model.players if self.model.player_team_id(r) not in pool_ids and self.model.player_team_id(r)]

    def _refresh(self):
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        field, group_ppos = self._groups[self.group_var.get()]
        value = self._preset_ids.get(self.preset_var.get())
        weights = PHILOSOPHY_WEIGHTS.get(value)
        if weights is None:
            self.lbl_key.configure(text="No weights for this preset in the game data.")
            return
        self.lbl_key.configure(text="Key ratings for this preset: " + philosophy_key_ratings(weights))

        names = PHILOSOPHY_VALUES[field]
        everyone = self.other_var.get()
        count = 0
        for r in self._pool_rows():
            if not everyone and (r.get(PLAYER_POS_CODE, "") or "").strip() not in group_ppos:
                continue
            fit = compute_philosophy_fit(r, weights)
            if fit is None:
                continue
            team_id = self.model.player_team_id(r)
            pick_value = self._team_pick_value(team_id, field)
            self.tree.insert("", tk.END, iid=str(count), values=(
                self.model.player_name(r), TEAM_NAMES.get(team_id, team_id), self.model.player_pos(r),
                (r.get("POVR", "") or "").strip(), f"{fit:.1f}", names.get(pick_value, "")))
            count += 1

        self._sort_state = {}
        self._sort_by("fit", default_reverse=True)

    def _sort_by(self, col, default_reverse=None):
        reverse = self._sort_state.get(col, False) if default_reverse is None else default_reverse
        rows = [(self.tree.set(iid, col), iid) for iid in self.tree.get_children()]
        try:
            rows.sort(key=lambda r: float(r[0]), reverse=reverse)
        except ValueError:
            rows.sort(key=lambda r: r[0], reverse=reverse)
        for index, (_, iid) in enumerate(rows):
            self.tree.move(iid, "", index)
        self._sort_state[col] = not reverse


# -----------------------------
# Playbooks: a name-resolved view of the save's playbook tables.
#
# The save only stores IDs: PGPL (BOKL playbook, SETL set, PLYL play, PLTP
# type), PGFM (formations in a playbook), PGSL (which sets belong to which
# formation) and PGSS. The NAMES for stock content are not in the save at all -
# they're in the game's own qkl_boot.ast (tables PLAB / PBFM / SETL / PBPL),
# so they're extracted once into a local cache (see App._ensure_playbook_names)
# the same way the Player Type Fit archetypes are. Anything the user created
# in-game (custom plays/sets/playbooks) carries its own names in the save's
# own PBPL / SETL / PLAB tables, which take priority over the stock ones.
#
# Verified against a real save: every PGPL (set, play) pair, PGSS set and
# PGFM formation resolves except the user's custom content (named by the
# save's own tables) and 3 formation IDs; PGPL.PLTP always equals the name
# table's play-type code; BOKL equals PLAB.PBGI; TEAM.TOPB indexes the
# offensive playbook by PLAB.BORD for all 32 teams. TEAM.TDPB (defense) does
# NOT follow that scheme and its meaning is unknown, so defense usage is not
# shown.
#
# Which playbook a team uses is stored on EVERY coach of that team: COCH.CPID
# (offensive playbook) and COCH.CDID (defensive playbook), both a playbook's
# PLAB.BGID within its side (BOFF). Confirmed for all 32 teams (valid IDs
# everywhere; each team's coaches share the values, a few teams' coordinators
# differ from their head coach). The HC09 XML config labels TEAM.TOPB / TDPB
# "Offensive / Defense Playbook", but TDPB is really a small scheme-family
# value (all the 3-4 teams share 1, the Tampa-2 teams share 3), so team usage is
# read from the coordinators instead.
# -----------------------------
PLAYBOOK_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".hc09_gamedata_cache", "playbooks")
PLAYBOOK_NAME_FILES = ("plab.csv", "pbfm.csv", "setl.csv", "pbpl.csv")
PLAYBOOK_SAVE_TABLES = ["PGPL", "PGFM", "PGSS", "PGSL", "PBPL", "SETL", "PLAB"]
# The four tables that make up a playbook's contents, in CSV column order.
PLAYBOOK_TABLE_HEADERS = {
    "PGPL": ["BOKL", "SETL", "PLYL", "PLTP"],   # plays in a playbook
    "PGFM": ["BOKL", "PBFM", "SRFM"],           # formations in a playbook
    "PGSS": ["BOKL", "SETL"],                   # sets in a playbook
    "PGSL": ["BOKL", "SETL", "PBFM"],           # which formation each set sits under
}
PLAYBOOK_PLAY_CAP = 200   # in-game limit per playbook (200 offensive or 200 defensive), special teams not counted
PLAYBOOK_CREATED_FORMATIONS = {"8190", "8191"}   # the per-save "Created Plays" formations (offense / defense)
PLAYBOOK_SPECIAL_FORMATIONS = {"kickoff", "safety punt", "special teams", "kick return", "safety kick return", "special"}


def read_csv_dicts(path):
    """Plain CSV -> list of dicts (no model state touched, so it's safe on a worker thread)."""
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))
    except OSError:
        return []


def team_nickname(tid):
    name = TEAM_NAMES.get(tid, "")
    return name.split(" (")[0] if name else ""


class TeamPhilosophyDialog(tk.Toplevel):
    """Edit a team's philosophy (schemes, playbook control, position philosophies) by
    name, on a row of the TPHS table. Only fields the row has are shown (and a tab
    with none is left out); Apply writes just what changed."""

    def __init__(self, parent, rows_list, row_index, subject_label, refresh_callback, note=""):
        super().__init__(parent)
        p = getattr(parent, "_ui_palette", None)
        if p:
            self.configure(background=p["bg"])
        self.title("Team philosophy")
        self.minsize(520, 320)
        self.transient(parent)
        self.parent, self.rows_list, self.row_index, self.refresh_callback = parent, rows_list, row_index, refresh_callback
        self.row = rows_list[row_index]
        self.vars = {}      # field -> StringVar
        self.names = {}     # field -> {display text: stored value}

        # The button row is packed first so it can never be pushed off the bottom of a short screen;
        # each tab scrolls instead.
        btn = ttk.Frame(self)
        btn.pack(side="bottom", fill="x", padx=12, pady=(0, 12))
        ttk.Button(btn, text="Close", command=self.destroy).pack(side="right")
        ttk.Button(btn, text="Apply", style="Accent.TButton", command=self._apply).pack(side="right", padx=(0, 8))

        ttk.Label(self, text=subject_label, font=("", 10, "bold"), padding=(12, 12, 12, 0)).pack(anchor="w")
        ttk.Label(self, foreground="gray", wraplength=520, justify="left", padding=(12, 2, 12, 6),
                  text=note).pack(anchor="w")

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        self._nb, self._canvases, self._inners = nb, [], []
        for tab_name, sections in PHILOSOPHY_TABS:
            shown = [(section, [(c, l) for c, l in fields if c in self.row]) for section, fields in sections]
            shown = [(section, present) for section, present in shown if present]
            if not shown:
                continue
            frame = self._scroll_tab(nb, tab_name)
            for section, present in shown:
                box = ttk.LabelFrame(frame, text=section)
                box.pack(fill="x", padx=8, pady=(8, 0))
                for i, (code, label) in enumerate(present):
                    ttk.Label(box, text=label + ":", width=36, anchor="w").grid(row=i, column=0, sticky="w", padx=(8, 4), pady=3)
                    self._add_list_field(box, i, code)
        self.bind("<MouseWheel>", self._wheel)
        self.bind("<Escape>", lambda e: self.destroy())
        self._fit_to_screen(parent)
        self.grab_set()

    def _scroll_tab(self, nb, title):
        """Add a tab whose content scrolls; returns the frame to put the fields in."""
        outer = ttk.Frame(nb)
        nb.add(outer, text=title)
        pal = getattr(self.parent, "_ui_palette", None)
        canvas = tk.Canvas(outer, highlightthickness=0, borderwidth=0, **({"background": pal["bg"]} if pal else {}))
        sb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        inner = ttk.Frame(canvas)
        win = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e, c=canvas: c.configure(scrollregion=c.bbox("all")))
        canvas.bind("<Configure>", lambda e, c=canvas, w=win: c.itemconfigure(w, width=e.width))
        self._canvases.append(canvas)
        self._inners.append(inner)
        return inner

    def _wheel(self, event):
        """Mouse wheel scrolls the open tab - also over a drop-down or number box, so a scroll
        can't silently change a value."""
        try:
            canvas = self._canvases[self._nb.index("current")]
        except (tk.TclError, IndexError):
            return "break"
        if canvas.yview() != (0.0, 1.0):
            canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
        return "break"

    def _fit_to_screen(self, parent):
        """Open tall enough to show a whole tab if the screen allows, otherwise at most 80% of the
        screen height (the tabs scroll), beside the main window rather than off the edge."""
        if not self._canvases:
            return
        self.update_idletasks()
        canvas = self._canvases[0]
        need_h = self.winfo_reqheight() - canvas.winfo_reqheight() + max(i.winfo_reqheight() for i in self._inners) + 6
        need_w = max(600, max(i.winfo_reqwidth() for i in self._inners) + 90)
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = min(need_w, sw - 40), max(320, min(need_h, int(sh * 0.8)))
        x = max(0, min(parent.winfo_rootx() + 40, sw - w - 20))
        y = max(0, min(parent.winfo_rooty() + 20, sh - h - 80))
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _add_list_field(self, box, grid_row, code):
        values = dict(PHILOSOPHY_VALUES.get(code, {}))
        current = safe_int(self.row.get(code, ""))
        if current is not None and current not in values:
            values[current] = f"(value {current})"   # stored value the list doesn't name - keep it selectable
        names = {name: v for v, name in values.items()}
        self.names[code] = names
        var = tk.StringVar(value=values.get(current, ""))
        cb = ttk.Combobox(box, state="readonly", width=24, textvariable=var, values=list(names))
        cb.grid(row=grid_row, column=1, sticky="w", pady=3)
        cb.bind("<MouseWheel>", self._wheel)
        self.vars[code] = var

    def _apply(self):
        updates = {}
        for code, var in self.vars.items():
            new = self.names[code].get(var.get())
            if new is not None and str(new) != (self.row.get(code, "") or "").strip():
                updates[code] = str(new)
        self.row.update(updates)
        if updates:
            self.parent.mark_dirty()
            self.refresh_callback()
        self.destroy()


class PlaybookCopyDialog(tk.Toplevel):
    """Copy plays, whole sets or whole formations from another playbook into
    the target one. Shows exactly what would be added (and the 200-play limit)
    before anything is changed; on_apply(plan) performs the change."""

    AUTO = "Same formation name as the source (add it if missing)"
    OTHER = "Another playbook..."

    def __init__(self, app, data, target, on_apply, preselect=None, choices=()):
        """target: the BOKL plays are added INTO first. choices: [(label, BOKL)] shown
        in the 'Adding INTO' list (the chosen team's own playbooks), so the target can
        be switched without leaving the dialog."""
        super().__init__(app)
        p = getattr(app, "_ui_palette", None)
        if p:
            self.configure(background=p["bg"])
        self.app, self.data, self.target, self.on_apply = app, data, target, on_apply
        self._choices = list(choices)
        self._target_labels = {}
        self.title(f"Add plays INTO {data.book_label(target)}")
        self.transient(app)
        self.geometry("860x640")
        self.minsize(640, 460)
        self._plan = None
        self._sources = []
        self._into_ids = {}

        trow = ttk.Frame(self)
        trow.pack(fill="x", padx=10, pady=(10, 2))
        ttk.Label(trow, text="Adding INTO:", font=("TkDefaultFont", 10, "bold")).pack(side="left")
        self.target_var = tk.StringVar()
        self.cmb_target = ttk.Combobox(trow, state="readonly", width=58, textvariable=self.target_var)
        self.cmb_target.pack(side="left", padx=(8, 10))
        self.cmb_target.bind("<<ComboboxSelected>>", lambda e: self._on_target_choice())
        self.lbl_target = ttk.Label(trow, font=("TkDefaultFont", 10, "bold"))
        self.lbl_target.pack(side="left")
        self.lbl_shared = ttk.Label(self, foreground="#b9770e", wraplength=820, justify="left")
        self.lbl_shared.pack(anchor="w", padx=10, pady=(0, 2))
        ttk.Label(self, foreground="gray", wraplength=820, justify="left",
                  text="Plays are added INTO the playbook chosen in \"Adding INTO\" - it starts as your team's, and the list lets you "
                       "switch to your defense or any other playbook. That is the only playbook that changes. "
                       "Step 1: pick the playbook to copy FROM. Step 2: pick a play, a set or a whole formation from it. "
                       "Step 3: say where new sets go, check the summary, then add."
                  ).pack(anchor="w", padx=10, pady=(0, 6))

        body = ttk.PanedWindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=10, pady=4)

        left = ttk.Frame(body)
        ttk.Label(left, text="1. Copy FROM this playbook", font=("TkDefaultFont", 9, "bold")).pack(anchor="w", pady=(0, 3))
        top = ttk.Frame(left)
        top.pack(fill="x")
        ttk.Label(top, text="Filter:").pack(side="left")
        self.filter_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.filter_var).pack(side="left", fill="x", expand=True, padx=(6, 0))
        self.filter_var.trace_add("write", lambda *_: self._fill_sources())
        lf = ttk.Frame(left)
        lf.pack(fill="both", expand=True, pady=(4, 0))
        self.lst = tk.Listbox(lf, exportselection=False, width=30)
        lsb = ttk.Scrollbar(lf, orient="vertical", command=self.lst.yview)
        self.lst.configure(yscrollcommand=lsb.set)
        lsb.pack(side="right", fill="y")
        self.lst.pack(side="left", fill="both", expand=True)
        self.lst.bind("<<ListboxSelect>>", lambda e: self._on_source())
        body.add(left, weight=1)

        right = ttk.Frame(body)
        self.lbl_right = ttk.Label(right, text="2. Pick what to copy (choose a playbook first)", font=("TkDefaultFont", 9, "bold"))
        self.lbl_right.pack(anchor="w", pady=(0, 3))
        rf = ttk.Frame(right)
        rf.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(rf, show="tree", selectmode="browse")
        rsb = ttk.Scrollbar(rf, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=rsb.set)
        rsb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._on_pick())
        body.add(right, weight=2)

        opt = ttk.Frame(self)
        opt.pack(fill="x", padx=10, pady=(6, 0))
        self.lbl_step3 = ttk.Label(opt, font=("TkDefaultFont", 9, "bold"))
        self.lbl_step3.pack(side="left")
        self.into_var = tk.StringVar(value=self.AUTO)
        self.cmb_into = ttk.Combobox(opt, state="readonly", width=44, textvariable=self.into_var)
        self.cmb_into.pack(side="left", padx=(8, 0))
        self.cmb_into.bind("<<ComboboxSelected>>", lambda e: self._on_pick())
        self._fill_into()
        self.lbl_hint = ttk.Label(self, foreground="gray", wraplength=820, justify="left")
        self.lbl_hint.pack(anchor="w", padx=10, pady=(2, 0))

        self.lbl_summary = ttk.Label(self, wraplength=820, justify="left")
        self.lbl_summary.pack(fill="x", padx=10, pady=(8, 2))
        self.lbl_done = ttk.Label(self, wraplength=820, justify="left", foreground="#1e8449")
        self.lbl_done.pack(fill="x", padx=10, pady=(0, 4))
        btn = ttk.Frame(self)
        btn.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(btn, text="Close", command=self.destroy).pack(side="right")
        self.btn_add = ttk.Button(btn, command=self._add, state="disabled")
        self.btn_add.pack(side="right", padx=(0, 8))

        self._update_target_label()
        self._refresh_target_texts()
        self._refresh_target_combo()
        self._fill_sources(select=preselect[0] if preselect else None)
        if preselect:
            self._select_play(preselect[1], preselect[2])
        self.bind("<Escape>", lambda e: self.destroy())
        self.grab_set()

    def _update_target_label(self):
        d = self.data
        users = [f"offense: {', '.join(d.offense_used_by[self.target])}" for _ in [0] if d.offense_used_by.get(self.target)]
        users += [f"defense: {', '.join(d.defense_used_by[self.target])}" for _ in [0] if d.defense_used_by.get(self.target)]
        shared = len(d.offense_used_by.get(self.target, [])) + len(d.defense_used_by.get(self.target, []))
        names = d.book_names.get(self.target, [])
        extra = []
        if shared:
            extra.append(f"Used by {'; '.join(users)}. " + ("Changes apply to every team using it. " if shared > 1 else ""))
        if len(names) > 1:
            extra.append(f"This is one playbook shared under several names ({' / '.join(names)}), so the change shows under all of them.")
        self.lbl_target.configure(text=f"{d.counted_plays(self.target)} of {PLAYBOOK_PLAY_CAP} plays (special teams not counted)")
        if not d.side_of(self.target):
            extra.append("Can't tell whether this playbook is offense or defense, so copying into it is disabled.")
        if hasattr(self, "lbl_shared"):
            self.lbl_shared.configure(text=" ".join(extra))

    def _refresh_target_texts(self):
        """Everything that names the playbook being added INTO."""
        name = self.data.book_label(self.target)
        self.title(f"Add plays INTO {name}")
        self.lbl_step3.configure(text=f"3. If a copied set is new to {name}, put it under:")
        self.lbl_hint.configure(
            text=f"Sets {name} already has stay where they are (the copied plays just join them) - this choice only "
                 "applies to sets it doesn't have yet. Leave it on the first option to use the formation with the same name; "
                 "pick one of your own formations to put the new sets under that instead (e.g. a source's \"Shotgun\" sets under your \"Gun\").")
        self.btn_add.configure(text=f"Add to {name}")

    def _refresh_target_combo(self):
        """The 'Adding INTO' list: the team's playbooks, the current target if it came from
        'Another playbook...', then that option itself."""
        d = self.data
        self._target_labels = {}
        for label, bokl in self._choices:
            self._target_labels.setdefault(label, bokl)
        if self.target not in self._target_labels.values():
            side = d.side_of(self.target)
            self._target_labels[f"{d.book_label(self.target)}" + (f" ({side.lower()})" if side else "")] = self.target
        current = next(label for label, bokl in self._target_labels.items() if bokl == self.target)
        self.cmb_target.configure(values=list(self._target_labels) + [self.OTHER])
        self.target_var.set(current)

    def _on_target_choice(self):
        label = self.target_var.get()
        if label == self.OTHER:
            d = self.data
            rows = [(b, f"{name}  ({side.lower() if side else 'side unknown'})", b, "") for b, name, side, *_ in d.books()]
            dlg = PlaybookPickerDialog(self, "Add plays INTO which playbook?", rows, self.target)
            self.wait_window(dlg)
            self.grab_set()
            if dlg.result:
                self._set_target(dlg.result[2])
            else:
                self._refresh_target_combo()
            return
        bokl = self._target_labels.get(label)
        if bokl and bokl != self.target:
            self._set_target(bokl)

    def _set_target(self, bokl):
        """Switch the playbook being added INTO; the FROM list, the pick and the summary start over."""
        self.target = bokl
        self._plan = None
        self.lbl_done.configure(text="")
        self.into_var.set(self.AUTO)
        self._update_target_label()
        self._refresh_target_texts()
        self._fill_into()
        self._fill_sources()
        self._on_source()
        self._on_pick()     # nothing is picked any more: clears the summary and disables Add
        self._refresh_target_combo()

    def _fill_into(self):
        d = self.data
        self._into_ids = {self.AUTO: None}
        for f, sr in d.book_formations.get(self.target, []):
            if f in PLAYBOOK_CREATED_FORMATIONS:
                continue
            self._into_ids[d.formation_base(f, sr)] = f
        self.cmb_into.configure(values=list(self._into_ids))

    def _fill_sources(self, select=None):
        d = self.data
        q = " ".join(self.filter_var.get().lower().split())
        side = d.side_of(self.target)
        self.lst.delete(0, tk.END)
        self._sources = []
        for bokl, name, bside, _i, plays, _o, _d in d.books():
            if bokl == self.target or not side or bside != side or q not in name.lower():
                continue
            self._sources.append(bokl)
            self.lst.insert(tk.END, f"{name}  ({plays})")
        if select in self._sources:
            self.lst.selection_set(self._sources.index(select))
            self.lst.see(self._sources.index(select))
            self._on_source()

    def _source(self):
        sel = self.lst.curselection()
        return self._sources[sel[0]] if sel else None

    def _on_source(self):
        d, src = self.data, self._source()
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self.lbl_right.configure(text=f"2. Pick what to copy from {d.book_label(src)}" if src else "2. Pick what to copy (choose a playbook first)")
        if not src:
            return
        for f, sr in d.book_formations.get(src, []):
            if f in PLAYBOOK_CREATED_FORMATIONS:
                continue
            sets = d.formation_sets.get((src, f), [])
            fnode = self.tree.insert("", tk.END, iid=f"F|{f}", text=f"{d.formation_base(f, sr)}  ({len(sets)} sets)")
            for st in sets:
                plays = d.set_plays.get((src, st), [])
                snode = self.tree.insert(fnode, tk.END, iid=f"S|{f}|{st}", text=f"{d.set_label(st)}  ({len(plays)} plays)")
                for pl, _tp in plays:
                    self.tree.insert(snode, tk.END, iid=f"P|{f}|{st}|{pl}", text=d.play_label(st, pl))
        self._on_pick()

    def _select_play(self, setl, plyl):
        for iid in self._all_nodes():
            if iid.startswith("P|") and iid.split("|")[2:] == [setl, plyl]:
                parent = self.tree.parent(iid)
                self.tree.item(self.tree.parent(parent), open=True)
                self.tree.item(parent, open=True)
                self.tree.selection_set(iid)
                self.tree.see(iid)
                return

    def _all_nodes(self):
        out, stack = [], list(self.tree.get_children())
        while stack:
            n = stack.pop(0)
            out.append(n)
            stack = list(self.tree.get_children(n)) + stack
        return out

    def _on_pick(self):
        self._plan = None
        self.btn_add.configure(state="disabled")
        src, sel = self._source(), self.tree.selection()
        if not src or not sel:
            self.lbl_summary.configure(text="Select a play, a set or a formation to see what would be added.", foreground="gray")
            return
        parts = sel[0].split("|")
        into = self._into_ids.get(self.into_var.get())
        if parts[0] == "F":
            plan = self.data.plan_copy(src, self.target, "formation", parts[1], into)
        elif parts[0] == "S":
            plan = self.data.plan_copy(src, self.target, "set", parts[2], into)
        else:
            plan = self.data.plan_copy(src, self.target, "play", (parts[2], parts[3]), into)
        self._plan = plan
        if plan["error"]:
            self.lbl_summary.configure(text=plan["error"], foreground="#c0392b")
            return
        bits = [f"{plan['new_plays']} play(s)"]
        if plan["new_sets"]:
            bits.append(f"{plan['new_sets']} new set(s)")
        if plan["new_formations"]:
            bits.append("a new formation: " + ", ".join(plan["new_formations"]))
        text = (f"Will add {', '.join(bits)} FROM {self.data.book_label(src)} INTO {self.data.book_label(self.target)}, "
                f"taking it from {plan['counted_before']} to {plan['plays_after']} of {PLAYBOOK_PLAY_CAP} plays.")
        if plan["already"]:
            text += f" ({plan['already']} already there.)"
        if plan["notes"]:
            text += " " + " ".join(plan["notes"])
        self.lbl_summary.configure(text=text, foreground="")
        self.btn_add.configure(state="normal")

    def _add(self):
        if not self._plan or self._plan["error"]:
            return
        plan = self._plan
        try:
            n = self.on_apply(plan)
        except ValueError as e:
            messagebox.showerror("Add plays", str(e), parent=self)
            return
        self._update_target_label()
        self._fill_into()
        self._on_pick()
        self.lbl_done.configure(text=f"Added {n} row(s) FROM {self.data.book_label(plan['src'])} INTO {self.data.book_label(plan['tgt'])}. "
                                     "Use Save to File in the main window to keep them.")


class PlaybookPickerDialog(tk.Toplevel):
    """Pick one playbook by name from a filterable list. result = the chosen
    (BGID, name, BOKL, BORD) row, or None if cancelled."""

    def __init__(self, parent, title, rows, current_bgid=None):
        super().__init__(parent)
        p = getattr(parent, "_ui_palette", None)
        if p:
            self.configure(background=p["bg"])
        self.title(title)
        self.transient(parent)
        self.resizable(True, True)
        self.geometry("420x480")
        self.result = None
        self._rows = rows
        self._shown = []

        top = ttk.Frame(self)
        top.pack(fill="x", padx=10, pady=(10, 4))
        ttk.Label(top, text="Filter:").pack(side="left")
        self.var = tk.StringVar()
        ent = ttk.Entry(top, textvariable=self.var)
        ent.pack(side="left", fill="x", expand=True, padx=(6, 0))
        self.var.trace_add("write", lambda *_: self._fill())

        frm = ttk.Frame(self)
        frm.pack(fill="both", expand=True, padx=10, pady=4)
        self.lst = tk.Listbox(frm, exportselection=False)
        sb = ttk.Scrollbar(frm, orient="vertical", command=self.lst.yview)
        self.lst.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.lst.pack(side="left", fill="both", expand=True)
        self.lst.bind("<Double-1>", lambda e: self._ok())

        btn = ttk.Frame(self)
        btn.pack(fill="x", padx=10, pady=(4, 10))
        ttk.Button(btn, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(btn, text="Use this playbook", command=self._ok).pack(side="right", padx=(0, 8))
        self._current = current_bgid
        self._fill()
        ent.focus_set()
        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self.destroy())
        self.grab_set()

    def _fill(self):
        q = " ".join(self.var.get().lower().split())
        self.lst.delete(0, tk.END)
        self._shown = [r for r in self._rows if q in r[1].lower()]
        for bgid, name, _bokl, _bord in self._shown:
            self.lst.insert(tk.END, name + ("   (current)" if bgid == self._current else ""))
        for i, r in enumerate(self._shown):
            if r[0] == self._current:
                self.lst.selection_set(i)
                self.lst.see(i)
                break
        else:
            if self._shown:
                self.lst.selection_set(0)

    def _ok(self):
        sel = self.lst.curselection()
        if sel:
            self.result = self._shown[sel[0]]
            self.destroy()


# Playbooks 1-10 are the custom playbooks made in-game, and the custom plays and sets in them; their
# names live in the HC09 profile save (BLUS30128-PROFILE-*), not in the career. Read-only.
PLAYBOOK_PROFILE_TABLES = ("PLAB", "SETL", "PBPL", "PGPL")   # PGPL only to check the names belong to the career
PLAYBOOK_NAME_MATCH = 0.8   # a custom playbook is named only if this share of its profile plays is in the career's


def find_profile_saves(career_db_path):
    """Profile saves of the same game sitting next to a career save (savedata/<TITLE>-PROFILE-*/USR-DATA)."""
    folder = os.path.dirname(os.path.abspath(career_db_path))
    root = os.path.dirname(folder)
    title = os.path.basename(folder).split("-")[0]
    found = []
    try:
        for name in sorted(os.listdir(root)):
            path = os.path.join(root, name, os.path.basename(career_db_path))
            if name.startswith(title + "-PROFILE-") and os.path.isfile(path):
                found.append(path)
    except OSError:
        pass
    return found


class PlaybookData:
    def __init__(self, game, save, coaches, profile=None, control=None):
        """game / save: {table name in lowercase: [row dicts]} - stock names
        from the game files and the save's own tables. coaches: COCH rows.
        profile: the same shape (plab / setl / pbpl) from the player's profile save, which
        names the playbooks, sets and plays made in-game; only ids the game does not
        already name are taken from it. control: function (TGID, side "1"/"0") -> "hc" | "coord" | None,
        whose playbook the team uses on that side (the Playbook Control team philosophy)."""
        self.have_game_names = bool(game.get("plab"))
        g = lambda t: game.get(t, [])
        v = lambda t: save.get(t, [])
        prof = self._custom_names_only(game, profile or {})
        self.profile_bgids = {((r.get("BOFF") or "").strip(), (r.get("BGID") or "").strip()) for r in prof["plab"]}

        self.book_names = defaultdict(list)
        self.book_side = {}
        self.bgid_book = {}                         # (BOFF "1"/"0", BGID) -> BOKL; save rows win over stock
        self.bgid_info = {}                         # (BOFF, BGID) -> {"name", "bokl", "bord"}
        for r in g("plab") + prof["plab"] + v("plab"):
            bokl = (r.get("PBGI") or "").strip()
            name = (r.get("BNAM") or "").strip()
            side = (r.get("BOFF") or "").strip()
            bgid = (r.get("BGID") or "").strip()
            if bokl and bgid:
                self.bgid_book[(side, bgid)] = bokl
                self.bgid_info[(side, bgid)] = {"name": name or f"Playbook {bokl}", "bokl": bokl, "bord": (r.get("BORD") or "").strip()}
            if bokl and side in ("0", "1"):
                self.book_side[bokl] = "Offense" if side == "1" else "Defense"
            if bokl and name and name not in self.book_names[bokl]:
                self.book_names[bokl].append(name)

        self.formation_name = {(r.get("PBFM") or "").strip(): (r.get("name") or "").strip() for r in g("pbfm")}
        # What the game itself ships. Anything outside these is content the user
        # made in-game (Create-a-Play / Create-a-Playbook): the reporter found
        # copying that breaks flipping and puts punts in the Gun, so it is never copied.
        self.stock_sets = {(r.get("SETL") or "").strip() for r in g("setl")}
        self.stock_plays = {((r.get("SETL") or "").strip(), (r.get("PLYL") or "").strip()) for r in g("pbpl")}
        self.set_name = {}
        for r in g("setl") + prof["setl"] + v("setl"):
            self.set_name[(r.get("SETL") or "").strip()] = (r.get("name") or "").strip()
        self.play_info = {}
        for r in g("pbpl") + prof["pbpl"] + v("pbpl"):
            self.play_info[((r.get("SETL") or "").strip(), (r.get("PLYL") or "").strip())] = (
                (r.get("name") or "").strip(), (r.get("PLYT") or "").strip())

        # The four content tables are kept as editable row lists; everything
        # below is an index over them, rebuilt after each edit.
        self.tables = {name: list(v(name.lower())) for name in PLAYBOOK_TABLE_HEADERS}
        self.dirty_tables = set()
        self._index_structure()

        self.control = control
        self.set_usage(coaches)

    @staticmethod
    def _custom_names_only(game, profile):
        """The profile's rows for playbooks, sets and plays the game itself does not name."""
        key = lambda r, f: (r.get(f) or "").strip()
        stock_bokl = {key(r, "PBGI") for r in game.get("plab", [])}
        stock_bgid = {(key(r, "BOFF"), key(r, "BGID")) for r in game.get("plab", [])}
        stock_sets = {key(r, "SETL") for r in game.get("setl", [])}
        stock_plays = {(key(r, "SETL"), key(r, "PLYL")) for r in game.get("pbpl", [])}
        return {
            "plab": [r for r in profile.get("plab", []) if key(r, "PBGI") not in stock_bokl
                     and (key(r, "BOFF"), key(r, "BGID")) not in stock_bgid],
            "setl": [r for r in profile.get("setl", []) if key(r, "SETL") not in stock_sets],
            "pbpl": [r for r in profile.get("pbpl", []) if (key(r, "SETL"), key(r, "PLYL")) not in stock_plays],
        }

    def _index_structure(self):
        t = self.tables
        key = lambda r, f: (r.get(f) or "").strip()
        self.book_formations = defaultdict(list)   # BOKL -> [(PBFM, SRFM)]
        self.formation_srfm = {}                   # (BOKL, PBFM) -> SRFM
        for r in t["PGFM"]:
            b, f, sr = key(r, "BOKL"), key(r, "PBFM"), key(r, "SRFM")
            self.book_formations[b].append((f, sr))
            self.formation_srfm[(b, f)] = sr
        self.book_sets = defaultdict(set)          # BOKL -> {SETL}  (PGSS)
        for r in t["PGSS"]:
            self.book_sets[key(r, "BOKL")].add(key(r, "SETL"))
        self.formation_sets = defaultdict(list)    # (BOKL, PBFM) -> [SETL]
        self.set_formations = defaultdict(list)    # (BOKL, SETL) -> [PBFM]
        for r in t["PGSL"]:
            b, st, f = key(r, "BOKL"), key(r, "SETL"), key(r, "PBFM")
            self.formation_sets[(b, f)].append(st)
            self.set_formations[(b, st)].append(f)
        self.set_plays = defaultdict(list)         # (BOKL, SETL) -> [(PLYL, PLTP)]
        self.play_books = defaultdict(set)         # (SETL, PLYL) -> {BOKL}
        self.book_play_count = Counter()
        for r in t["PGPL"]:
            b, st, pl = key(r, "BOKL"), key(r, "SETL"), key(r, "PLYL")
            self.set_plays[(b, st)].append((pl, key(r, "PLTP")))
            self.play_books[(st, pl)].add(b)
            self.book_play_count[b] += 1
        self._infer_sides()

    def _infer_sides(self):
        """Playbooks that have no row in the game's playbook list (custom ones)
        have no recorded side. A stock set only ever appears on one side (checked:
        173 sets, none on both), so a book whose stock sets all agree is on that
        side. A book with no recognisable sets, or sets from both sides, stays unknown."""
        seen = defaultdict(set)
        for (b, st) in self.set_plays:
            if self.book_side.get(b):
                seen[st].add(self.book_side[b])
        set_side = {st: next(iter(v)) for st, v in seen.items() if len(v) == 1}
        self.inferred_side = {}
        books = {b for (b, _st) in self.set_plays} | set(self.book_formations)
        for b in books:
            if b in self.book_side:
                continue
            sides = {set_side[st] for (bb, st) in self.set_plays if bb == b and st in set_side}
            if len(sides) == 1:
                self.inferred_side[b] = next(iter(sides))

    def side_of(self, bokl):
        """"Offense", "Defense" or "" if it can't be told."""
        return self.book_side.get(bokl) or self.inferred_side.get(bokl) or ""

    # ---- editing: copy plays / sets / formations from one playbook into another
    def formation_base(self, pbfm, srfm=""):
        """A formation's plain name ("Gun"), ignoring the "(copy N)" marker."""
        return (self.formation_name.get(pbfm) or self.formation_name.get(srfm) or f"Formation {pbfm}").strip()

    def is_custom(self, setl, plyl=None, pbfm=None, srfm=""):
        """Made in-game rather than shipped by the game. Can only be judged when
        the game's own name tables are loaded."""
        if not self.have_game_names:
            return False
        if pbfm is not None and pbfm not in self.formation_name and srfm not in self.formation_name:
            return True
        if setl is not None and setl not in self.stock_sets:
            return True
        return plyl is not None and (setl, plyl) not in self.stock_plays

    def _is_special(self, bases):
        return bool(bases) and all(b.lower() in PLAYBOOK_SPECIAL_FORMATIONS for b in bases)

    def counted_plays(self, bokl):
        """Plays that count against the game's per-playbook cap (special teams don't)."""
        n = 0
        for (b, st), plays in self.set_plays.items():
            if b != bokl:
                continue
            bases = {self.formation_base(f, self.formation_srfm.get((bokl, f), ""))
                     for f in self.set_formations.get((bokl, st), []) if f not in PLAYBOOK_CREATED_FORMATIONS}
            if not self._is_special(bases):
                n += len(plays)
        return n

    def violations(self):
        """Breaks of the rules every stock playbook satisfies (verified on all 98
        books of a real save): a play's set must be in the playbook's set list and
        under a formation; every linked formation must exist in the playbook; every
        set has plays; every formation has sets; no duplicate rows."""
        out = set()
        for b in set(self.book_formations) | set(self.book_sets) | {k[0] for k in self.set_plays}:
            forms = {f for f, _ in self.book_formations.get(b, [])}
            sets = self.book_sets.get(b, set())
            played = {st for (bb, st) in self.set_plays if bb == b}
            linked = {st for (bb, st) in self.set_formations if bb == b}
            for st in played:
                if st not in sets: out.add(("play set not in set list", b, st))
                if st not in linked: out.add(("play set not under a formation", b, st))
            for st in sets:
                if st not in played: out.add(("set without plays", b, st))
                if st not in linked: out.add(("set not under a formation", b, st))
            for (bb, st), fs in self.set_formations.items():
                if bb != b: continue
                for f in fs:
                    if f not in forms: out.add(("formation link to a formation the playbook lacks", b, f))
                if len(fs) != len(set(fs)): out.add(("duplicate set link", b, st))
            for f in forms:
                if not self.formation_sets.get((b, f)): out.add(("formation without sets", b, f))
        for name, key in (("PGPL", ("BOKL", "SETL", "PLYL")), ("PGFM", ("BOKL", "PBFM")), ("PGSS", ("BOKL", "SETL")), ("PGSL", ("BOKL", "SETL", "PBFM"))):
            seen = Counter(tuple((r.get(k) or "").strip() for k in key) for r in self.tables[name])
            for k, c in seen.items():
                if c > 1: out.add((f"duplicate {name} row", *k))
        return out

    def plan_copy(self, src, tgt, kind, key, into_formation=None):
        """What copying from playbook src into tgt would add. kind: "play"
        (key = (SETL, PLYL)), "set" (key = SETL) or "formation" (key = the
        source's PBFM). Formation IDs are unique to each playbook, so a source
        formation is matched to the target's formation of the same NAME
        (X's 4-3 into your 4-3); only when the target has none is the source's
        formation added to it. A set the target already has is left where it is
        (the plays just join it); into_formation (a target PBFM) overrides the
        by-name matching for sets that are new to the target, e.g. to put a
        source's "Shotgun" sets under your "Gun". Nothing is written until
        apply_plan()."""
        plan = {"src": src, "tgt": tgt, "rows": {t: [] for t in PLAYBOOK_TABLE_HEADERS}, "new_plays": 0, "new_sets": 0,
                "new_formations": [], "already": 0, "notes": [], "error": None, "plays_after": None, "counted_before": 0}
        if not src or not tgt or src == tgt:
            plan["error"] = "Pick a different playbook to copy from."
            return plan
        if not self.have_game_names:
            plan["error"] = ("Editing playbooks needs the game's own name tables (to tell offense from defense and to recognise "
                             "custom plays). Open the Playbooks tab with qkl_boot.ast located and try again.")
            return plan
        ss, ts = self.side_of(src), self.side_of(tgt)
        for book, side in ((src, ss), (tgt, ts)):
            if not side:
                plan["error"] = (f"Can't tell whether {self.book_label(book)} is an offensive or a defensive playbook, so copying "
                                 "to or from it is blocked to avoid mixing the two.")
                return plan
        if ss != ts:
            word = {"Offense": "an offensive", "Defense": "a defensive"}
            plan["error"] = f"{self.book_label(src)} is {word[ss]} playbook and {self.book_label(tgt)} is {word[ts]} one."
            return plan

        planned_forms, planned_sets, planned_links, planned_plays = {}, set(), set(), set()
        new_counted = 0

        def target_formation(pbfm):
            if (tgt, pbfm) in self.formation_srfm or pbfm in planned_forms:
                return pbfm
            srfm = self.formation_srfm.get((src, pbfm), pbfm)
            base = self.formation_base(pbfm, srfm).lower()
            for pf, sf in list(self.book_formations.get(tgt, [])) + list(planned_forms.items()):
                if self.formation_base(pf, sf).lower() == base:
                    return pf
            planned_forms[pbfm] = srfm
            plan["rows"]["PGFM"].append({"BOKL": tgt, "PBFM": pbfm, "SRFM": srfm})
            plan["new_formations"].append(self.formation_base(pbfm, srfm))
            return pbfm

        def add_set(setl, plays, only_formation=None):
            nonlocal new_counted
            if self.is_custom(setl):
                plan["notes"].append(f'"{self.set_label(setl)}" is a custom set made in-game, so it was skipped - copying custom plays breaks flipping.')
                plan["skipped_custom"] = True
                return
            custom_plays = [pl for pl, _tp in plays if self.is_custom(setl, pl)]
            if custom_plays:
                plays = [(pl, tp) for pl, tp in plays if pl not in custom_plays]
                plan["notes"].append(f"{len(custom_plays)} custom play(s) in \"{self.set_label(setl)}\" were skipped.")
                plan["skipped_custom"] = True
            if not plays:
                return
            for f in self.set_formations.get((src, setl), []):
                if f not in PLAYBOOK_CREATED_FORMATIONS and self.is_custom(None, None, f, self.formation_srfm.get((src, f), "")) and into_formation is None and setl not in self.book_sets.get(tgt, set()):
                    plan["notes"].append(f'"{self.set_label(setl)}" sits under a custom formation in the source, so it was skipped.')
                    plan["skipped_custom"] = True
                    return
            set_is_new = setl not in self.book_sets.get(tgt, set())
            if not set_is_new:
                # The target already has this set: leave its formation links alone.
                mapped = [f for f in self.set_formations.get((tgt, setl), []) if f not in PLAYBOOK_CREATED_FORMATIONS]
            elif into_formation is not None:
                mapped = [into_formation]
            else:
                s_forms = [f for f in self.set_formations.get((src, setl), []) if f not in PLAYBOOK_CREATED_FORMATIONS]
                if only_formation is not None:
                    s_forms = [only_formation]
                if not s_forms:
                    plan["notes"].append(f'"{self.set_label(setl)}" is only under Created Plays in the source, so it was skipped.')
                    return
                mapped = []
                for f in s_forms:
                    tf = target_formation(f)
                    if tf not in mapped:
                        mapped.append(tf)
            if set_is_new and setl not in planned_sets:
                planned_sets.add(setl)
                plan["rows"]["PGSS"].append({"BOKL": tgt, "SETL": setl})
                plan["new_sets"] += 1
            for tf in mapped:
                if tf not in self.set_formations.get((tgt, setl), []) and (setl, tf) not in planned_links:
                    planned_links.add((setl, tf))
                    plan["rows"]["PGSL"].append({"BOKL": tgt, "SETL": setl, "PBFM": tf})
            have = {pl for pl, _ in self.set_plays.get((tgt, setl), [])}
            bases = {self.formation_base(f, planned_forms.get(f) or self.formation_srfm.get((tgt, f), "")) for f in mapped}
            for plyl, pltp in plays:
                if plyl in have or (setl, plyl) in planned_plays:
                    plan["already"] += 1
                    continue
                planned_plays.add((setl, plyl))
                plan["rows"]["PGPL"].append({"BOKL": tgt, "SETL": setl, "PLYL": plyl, "PLTP": pltp})
                plan["new_plays"] += 1
                if not self._is_special(bases):
                    new_counted += 1

        if kind == "play":
            setl, plyl = key
            plays = [(pl, tp) for pl, tp in self.set_plays.get((src, setl), []) if pl == plyl]
            if not plays:
                plan["error"] = "That play isn't in the source playbook."
                return plan
            add_set(setl, plays)
        elif kind == "set":
            add_set(key, list(self.set_plays.get((src, key), [])))
        elif kind == "formation":
            for st in self.formation_sets.get((src, key), []):
                add_set(st, list(self.set_plays.get((src, st), [])), only_formation=key)
        else:
            plan["error"] = f"Unknown kind {kind}"
            return plan

        plan["counted_before"] = self.counted_plays(tgt)
        plan["plays_after"] = plan["counted_before"] + new_counted
        if not any(plan["rows"].values()):
            if plan.get("skipped_custom"):
                plan["error"] = "Nothing to add: " + " ".join(plan["notes"])
            else:
                plan["error"] = "Nothing to add: everything selected is already in this playbook." if plan["already"] else "Nothing to add."
        elif plan["plays_after"] > PLAYBOOK_PLAY_CAP and new_counted:
            plan["error"] = (f"This would put {self.book_label(tgt)} at {plan['plays_after']} plays; the game allows "
                             f"{PLAYBOOK_PLAY_CAP} per playbook (special teams not counted).")
        return plan

    def apply_plan(self, plan):
        """Append a plan's rows. Refuses (and undoes it) if that would break any
        playbook rule that held before. Returns the number of rows added."""
        if plan.get("error"):
            raise ValueError(plan["error"])
        before_violations = self.violations()
        lengths = {t: len(r) for t, r in self.tables.items()}
        dirty_before = set(self.dirty_tables)
        for table, rows in plan["rows"].items():
            if rows:
                self.tables[table].extend(dict(r) for r in rows)
                self.dirty_tables.add(table)
        self._index_structure()
        new = self.violations() - before_violations
        if new:
            for table, n in lengths.items():
                del self.tables[table][n:]
            self.dirty_tables = dirty_before
            self._index_structure()
            raise ValueError("That change would break the playbook's structure and was not applied: " + "; ".join(f"{v[0]}" for v in sorted(new)[:3]))
        return sum(len(r) for r in plan["rows"].values())

    def in_use_who(self, tid, side):
        """Whose playbook a team uses on one side: "hc" if Playbook Control is the head coach, otherwise
        "coord" (also when the control is not known)."""
        return "hc" if self.control and self.control(tid, side) == "hc" else "coord"

    def set_usage(self, coaches, control=None):
        """Which real teams use each playbook: the head coach's (COPS 0) where the team's Playbook Control
        is the head coach, otherwise the coordinator's (OC = COPS 1 offense via CPID, DC = COPS 2 defense via
        CDID). A team has both, and only the one the control picks is played."""
        if control is not None:
            self.control = control
        real = dict(SIGN_DEST_TEAMS)
        self.offense_used_by = defaultdict(list)
        self.defense_used_by = defaultdict(list)
        for c in coaches:
            tid = (c.get("TGID") or "").strip()
            pos = (c.get("COPS") or "").strip()
            if tid not in real or pos not in ("0", "1", "2"):
                continue
            for side, field, coord_pos, bucket in (("1", "CPID", "1", self.offense_used_by), ("0", "CDID", "2", self.defense_used_by)):
                if pos != ("0" if self.in_use_who(tid, side) == "hc" else coord_pos):
                    continue
                book = self.bgid_book.get((side, (c.get(field) or "").strip()))
                if book and team_nickname(tid) not in bucket[book]:
                    bucket[book].append(team_nickname(tid))

    def side_books(self, side, include_custom=False):
        """Every selectable playbook for one side ("1" offense, "0" defense), as (BGID, name, BOKL, BORD):
        the game's in stock order. include_custom adds the player's custom playbooks (named from the
        profile, marked "(custom)") first - the game stores one on the head coach only."""
        rows = [(bgid, i["name"], i["bokl"], i["bord"]) for (sd, bgid), i in self.bgid_info.items()
                if sd == side and (sd, bgid) not in self.profile_bgids]
        rows.sort(key=lambda r: (int(r[3]) if r[3].isdigit() else 999, int(r[0]) if r[0].isdigit() else 0))
        if include_custom:
            custom = [(bgid, i["name"] + " (custom)", i["bokl"], i["bord"]) for (sd, bgid), i in self.bgid_info.items()
                      if sd == side and (sd, bgid) in self.profile_bgids]
            custom.sort(key=lambda r: int(r[0]) if r[0].isdigit() else 0)
            rows = custom + rows
        return rows

    def team_book(self, coaches, tid, side, who=None):
        """The BGID and name of the playbook a team holds on one side for who = "hc" (head coach) or "coord"
        (OC for offense, DC for defense); by default the one in use. (None, '') if the team has no such coach."""
        who = who or self.in_use_who(tid, side)
        pos = "0" if who == "hc" else ("1" if side == "1" else "2")
        field = "CPID" if side == "1" else "CDID"
        for c in coaches:
            if (c.get("TGID") or "").strip() == tid and (c.get("COPS") or "").strip() == pos:
                bgid = (c.get(field) or "").strip()
                info = self.bgid_info.get((side, bgid))
                return bgid, (info["name"] if info else f"Playbook #{bgid}")
        return None, ""

    def team_bokl(self, coaches, tid, side, who=None):
        """The BOKL (playbook table key) of the playbook a team holds on one side (default: the one in use), or None."""
        bgid, _name = self.team_book(coaches, tid, side, who)
        return self.bgid_book.get((side, bgid)) if bgid else None

    # ---- labels
    def book_label(self, bokl):
        names = self.book_names.get(bokl)
        return " / ".join(names) if names else f"Playbook {bokl}"

    def formation_label(self, pbfm, srfm=""):
        if pbfm in PLAYBOOK_CREATED_FORMATIONS and pbfm not in self.formation_name:
            return "Created Plays"      # where the game files plays made in Create-a-Play
        if pbfm in self.formation_name:
            return self.formation_name[pbfm]
        if srfm in self.formation_name:
            return f"{self.formation_name[srfm]} (copy {pbfm})"
        return f"Formation {pbfm}"

    def set_label(self, setl):
        return self.set_name.get(setl) or f"Set {setl}"

    def play_label(self, setl, plyl):
        return self.play_info.get((setl, plyl), ("", ""))[0] or f"Play {plyl}"

    # ---- tables for the UI
    def books(self):
        rows = []
        for bokl in sorted(set(self.book_play_count) | set(self.book_formations), key=lambda b: int(b) if b.isdigit() else 0):
            rows.append((bokl, self.book_label(bokl), self.side_of(bokl), bokl,
                         self.book_play_count.get(bokl, 0), ", ".join(self.offense_used_by.get(bokl, [])),
                         ", ".join(self.defense_used_by.get(bokl, []))))
        return rows

    def formations_for(self, bokl):
        return [(pbfm, self.formation_label(pbfm, srfm), pbfm, len(self.formation_sets.get((bokl, pbfm), [])))
                for pbfm, srfm in self.book_formations.get(bokl, [])]

    def plays_for(self, bokl, pbfm=None):
        if pbfm is None:
            sets = []
            for f, _srfm in self.book_formations.get(bokl, []):
                for st in self.formation_sets.get((bokl, f), []):
                    if st not in sets:
                        sets.append(st)
            for (b, st) in self.set_plays:
                if b == bokl and st not in sets:
                    sets.append(st)
        else:
            sets = self.formation_sets.get((bokl, pbfm), [])
        out = []
        for st in sets:
            for plyl, pltp in self.set_plays.get((bokl, st), []):
                out.append((f"{st}:{plyl}", self.play_label(st, plyl), self.set_label(st), pltp, st, plyl))
        return out

    def search(self, text):
        # The game's own names have stray double spaces ("Cover 2  QB Spy"), so
        # compare with whitespace collapsed on both sides.
        norm = lambda t: " ".join(t.lower().split())
        text = norm(text)
        if not text:
            return []
        keys = set(self.play_info) | set(self.play_books)
        hits = []
        for st, plyl in keys:
            name = self.play_label(st, plyl)
            if text in norm(name) or text in norm(self.set_label(st)):
                books = sorted(self.play_books.get((st, plyl), []), key=lambda b: int(b) if b.isdigit() else 0)
                pltp = self.play_info.get((st, plyl), ("", ""))[1]
                hits.append((f"{st}:{plyl}", name, self.set_label(st), pltp, st, plyl, len(books), books))
        hits.sort(key=lambda h: (h[1].lower(), h[2].lower()))
        return hits


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(BASE_TITLE)
        self.geometry("1320x820")
        self.minsize(1180, 700)

        self.ui_prefs = load_ui_prefs()
        self.dark_mode_var = tk.BooleanVar(value=(self.ui_prefs.get("mode") == "dark"))
        # Master switch: every feature added alongside the visual facelift
        # (Motivator boost, contract dialog, staff filters, per-save team
        # memory, background-thread load/save, etc.) works identically
        # either way - this only controls whether the custom colors/fonts/
        # dark-mode styling get applied, or the app just uses plain Tk/ttk
        # defaults. Takes effect on next launch (not live) since cleanly
        # undoing every style/option-database override without one would be
        # more fragile than just re-reading the preference at startup.
        self.facelift_var = tk.BooleanVar(value=self.ui_prefs.get("facelift_enabled", True))
        self._help_labels = []  # plain tk.Label help-text widgets, retheme target for Dark Mode toggle
        self._apply_theme(self.ui_prefs.get("mode", "light"))

        self.model = CSVModel()
        self.dirty = False  # True whenever there are unsaved edits
        self._tree_sort_state = {}  # id(tree) -> (column, reverse); survives table rebuilds

        self.selected_team_id = tk.StringVar(value="")
        self.selected_player_index = None
        self.selected_stat_key = None
        self._player_index_map = []

        # Portrait viewer state. self._portrait_photo_refs holds the current
        # ImageTk.PhotoImage per kind ("player"/"coach") - Tk drops the image
        # if nothing keeps a Python reference to it alive. The request id lets
        # a slow background lookup discard its result if the user has already
        # clicked a different player before it finishes.
        self._portrait_photo_refs = {}
        self._portrait_request_id = 0

        # Shared by the Trainer/Coach/GM tabs: those tables have 300+ league-
        # wide rows, which is what made those tabs slow to render/scroll -
        # defaulting to "my team only" cuts that by ~30x and is remembered.
        self.staff_filter_var = tk.StringVar(value=self.ui_prefs.get("staff_filter", "my_team"))
        self.staff_layout_var = tk.StringVar(value=self.ui_prefs.get("staff_layout", "vertical"))
        self._vviews = {}  # id(horizontal staff tree) -> its vertical view widgets

        self.motivator_state = load_motivator_state()
        # Boosts applied since the last successful Save. Kept separate from
        # motivator_state["boosts"] (which is only written to disk on Save)
        # so that Reload from File / loading a different save - which discard
        # unsaved edits - also discard the "already boosted" flag for boosts
        # that never actually made it into the save file.
        self.motivator_pending_boosts = {}

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self.on_close_request)

    # ---------- Unsaved-changes tracking ----------
    def mark_dirty(self):
        if not self.dirty:
            self.dirty = True
            self.title(BASE_TITLE + " *")

    def clear_dirty(self):
        if self.dirty:
            self.dirty = False
            self.title(BASE_TITLE)

    def on_close_request(self):
        if self.dirty:
            choice = messagebox.askyesnocancel(
                "Unsaved changes",
                "You have unsaved changes. Save before closing?"
            )
            if choice is None:  # Cancel
                return
            if choice:  # Yes
                try:
                    self.model.save_to_db()
                except Exception as e:
                    messagebox.showerror("Save Error", str(e))
                    return  # don't close if the save failed
        self.destroy()

    # ---------- Loading feedback ----------
    def set_busy(self, text):
        self.lbl_status.configure(text=text)
        self.config(cursor="watch")
        self.update_idletasks()

    def clear_busy(self):
        self.config(cursor="")

    def run_in_thread_with_busy(self, busy_text, work_fn, on_success, error_title="Error"):
        """Runs work_fn() (e.g. a slow bridge.js export/import) on a background
        thread so the window keeps painting/responding instead of Windows
        marking it "(Not Responding)" for the duration. work_fn must only
        touch self.model (plain data), never Tk widgets - those are only
        touched again in on_success, which runs back on the main thread."""
        self.set_busy(busy_text)
        result_box = {}

        def worker():
            try:
                result_box["value"] = work_fn()
            except Exception as e:
                result_box["error"] = e
            self.after(0, finish)

        def finish():
            self.clear_busy()
            if "error" in result_box:
                messagebox.showerror(error_title, str(result_box["error"]))
            else:
                on_success(result_box.get("value"))

        threading.Thread(target=worker, daemon=True).start()

    # ---------- Portrait viewer (Player Editor tab) ----------
    # Read-only for now - writing a replacement portrait back into the game's
    # AST archive is a separate, unsolved problem (repacking a nested BGFA
    # archive) and hasn't been attempted.
    def get_game_ast_path(self):
        path = self.ui_prefs.get("game_ast_path") or ""
        if path and os.path.isfile(path):
            return path
        for candidate in KNOWN_GAME_AST_CANDIDATES:
            if os.path.isfile(candidate):
                self.ui_prefs["game_ast_path"] = candidate
                save_ui_prefs(self.ui_prefs)
                return candidate
        return ""

    def on_locate_game_files(self):
        path = filedialog.askopenfilename(
            title="Locate qkl_fe2ig.ast (inside the game's PS3_GAME/USRDIR folder)",
            filetypes=[("AST archive", "qkl_fe2ig.ast"), ("All files", "*.*")],
        )
        if not path:
            return
        if self.ui_prefs.get("game_ast_path") != path:
            # A different install's archive may have different contents at
            # the same shortIds - drop any cached blob so it re-extracts.
            for kind in PORTRAIT_ARCHIVE_FILENAME:
                cache_path = self._portrait_archive_cache_path(kind)
                if os.path.isfile(cache_path):
                    try:
                        os.remove(cache_path)
                    except OSError:
                        pass
        self.ui_prefs["game_ast_path"] = path
        save_ui_prefs(self.ui_prefs)
        self._refresh_current_player_portrait()

    def _portrait_archive_cache_path(self, kind):
        return os.path.join(PORTRAIT_CACHE_DIR, PORTRAIT_ARCHIVE_FILENAME[kind])

    def _build_portrait_panel(self, parent, kind, extra_buttons=None):
        frm = ttk.LabelFrame(parent, text="Portrait")
        frm.pack(fill="x", pady=(0, 6))

        img_kwargs = {}
        if self._ui_palette:
            img_kwargs["background"] = self._ui_palette["surface"]
        # Native portrait size is 256x256 - shown full size (no thumbnail
        # downscale), so the placeholder box matches that.
        img_label = tk.Label(frm, text="No player selected", width=256, height=256, **img_kwargs)
        img_label.pack(side="left", padx=8, pady=8)

        status_col = ttk.Frame(frm)
        status_col.pack(side="left", fill="both", expand=True, padx=(0, 8), pady=8)
        status_label = ttk.Label(status_col, text="", wraplength=220, justify="left")
        status_label.pack(anchor="w")
        # Locate Game Files only needs a click if auto-detection (checked at
        # the top of get_game_ast_path) didn't find it - not shown otherwise.
        locate_btn = ttk.Button(status_col, text="Locate Game Files...", command=self.on_locate_game_files)
        locate_btn.pack(anchor="w", pady=(6, 0))

        if extra_buttons:
            btn_col = ttk.Frame(frm)
            btn_col.pack(side="left", fill="y", padx=(0, 8), pady=8)
            for text, command in extra_buttons:
                ttk.Button(btn_col, text=text, command=command).pack(anchor="w", pady=(0, 6))

        setattr(self, f"_portrait_img_label_{kind}", img_label)
        setattr(self, f"_portrait_status_label_{kind}", status_label)

    def _refresh_current_player_portrait(self):
        if getattr(self, "selected_player_index", None) is None:
            return
        row = self.model.players[self.selected_player_index]
        shortid = safe_int(row.get(PLAYER_PORTRAIT_CODE, ""))
        self._request_portrait_load("player", shortid)

    def _request_portrait_load(self, kind, shortid):
        img_label = getattr(self, f"_portrait_img_label_{kind}", None)
        status_label = getattr(self, f"_portrait_status_label_{kind}", None)
        if img_label is None:
            return

        self._portrait_request_id += 1
        req_id = self._portrait_request_id

        if not PIL_AVAILABLE:
            img_label.configure(image="", text="No image support")
            status_label.configure(text="Pillow (PIL) isn't installed - run: pip install Pillow")
            return

        if not self.get_game_ast_path():
            img_label.configure(image="", text="No photo")
            status_label.configure(text="Locate your game files to view in-game portraits.")
            return

        if shortid is None:
            img_label.configure(image="", text="No photo")
            status_label.configure(text="")
            return

        img_label.configure(image="", text="Loading...")
        status_label.configure(text="")

        def worker():
            try:
                pil_image = self._load_portrait_image(kind, shortid)
            except Exception as e:
                pil_image = None
                error = str(e)
            else:
                error = None
            self.after(0, lambda: self._on_portrait_loaded(kind, req_id, pil_image, error))

        threading.Thread(target=worker, daemon=True).start()

    def _load_portrait_image(self, kind, shortid):
        """Runs on a background thread. Ensures the (large, one-time) nested
        portrait archive is cached locally, looks up shortid within it via
        bridge.js, and returns a PIL Image - or None if not found."""
        cache_path = self._portrait_archive_cache_path(kind)
        if not os.path.isfile(cache_path):
            os.makedirs(PORTRAIT_CACHE_DIR, exist_ok=True)
            self.model.run_bridge([
                "portrait-extract-archive",
                "--ast", self.get_game_ast_path(),
                "--top-index", str(PORTRAIT_TOP_INDEX[kind]),
                "--out", cache_path,
            ])

        with tempfile.NamedTemporaryFile(suffix=".dds", delete=False) as tf:
            dds_path = tf.name
        try:
            result = self.model.run_bridge([
                "portrait-lookup", "--archive", cache_path,
                "--shortid", str(shortid), "--out", dds_path,
            ])
            if not result.get("found"):
                return None
            return Image.open(dds_path).convert("RGBA")
        finally:
            try:
                os.remove(dds_path)
            except OSError:
                pass

    def _on_portrait_loaded(self, kind, req_id, pil_image, error):
        if req_id != self._portrait_request_id:
            return  # a newer request has already superseded this one
        img_label = getattr(self, f"_portrait_img_label_{kind}", None)
        status_label = getattr(self, f"_portrait_status_label_{kind}", None)
        if img_label is None:
            return

        if error:
            img_label.configure(image="", text="Error")
            status_label.configure(text=f"Couldn't load portrait: {error}")
            return
        if pil_image is None:
            img_label.configure(image="", text="No photo\nfound")
            status_label.configure(text="No portrait entry matches this player's PSXP value in the archive.")
            return

        photo = ImageTk.PhotoImage(pil_image)  # shown full size (native 256x256)
        self._portrait_photo_refs[kind] = photo  # keep alive
        img_label.configure(image=photo, text="")
        status_label.configure(text="In-game portrait (read-only for now).")

    # ---------- Visual theme ----------
    def _apply_theme(self, mode=None):
        """Cosmetic-only pass: consistent colors/fonts/spacing across every
        tab, no behavior change. Safe to skip (falls back to Tk defaults) if
        anything here isn't supported on a given platform. Call again with a
        different mode ("light"/"dark") to live-switch - existing ttk widgets
        re-render automatically; raw tk widgets need _retheme_raw_widgets."""
        if mode is None:
            mode = getattr(self, "ui_mode", "light")
        self.ui_mode = mode

        if not self.ui_prefs.get("facelift_enabled", True):
            # Classic mode: leave Tk/ttk at their plain platform defaults.
            # self._ui_palette stays None - every dialog/widget that checks
            # it (contract editor, team picker, canvas theming, etc.) already
            # guards on that and just skips its custom colors when it's unset.
            self._ui_palette = None
            return

        p = UI_PALETTE_DARK if mode == "dark" else UI_PALETTE_LIGHT
        self._ui_palette = p

        try:
            self.configure(bg=p["bg"])

            import tkinter.font as tkfont
            for font_name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
                try:
                    tkfont.nametofont(font_name).configure(family=UI_FONT_FAMILY, size=9)
                except Exception:
                    pass

            # Plain tk widgets (Listbox/Text) aren't ttk-themeable, so set
            # their look via the option database instead. This only affects
            # widgets created AFTER this call - already-built ones need
            # _retheme_raw_widgets() to pick up a mode change live.
            self.option_add("*Listbox.background", p["surface"])
            self.option_add("*Listbox.foreground", p["text"])
            self.option_add("*Listbox.selectBackground", p["accent"])
            self.option_add("*Listbox.selectForeground", p["accent_text"])
            self.option_add("*Listbox.relief", "flat")
            self.option_add("*Listbox.borderWidth", 1)
            self.option_add("*Listbox.highlightThickness", 1)
            self.option_add("*Listbox.highlightBackground", p["border"])
            self.option_add("*Listbox.highlightColor", p["accent"])
            self.option_add("*Text.background", p["surface"])
            self.option_add("*Text.foreground", p["text"])
            self.option_add("*Text.relief", "flat")
            self.option_add("*Text.borderWidth", 1)
            self.option_add("*Text.highlightThickness", 1)
            self.option_add("*Text.highlightBackground", p["border"])
            self.option_add("*Label.background", p["bg"])
            self.option_add("*Label.foreground", p["text"])

            style = ttk.Style(self)
            try:
                style.theme_use("clam")
            except Exception:
                pass

            style.configure(".", background=p["bg"], foreground=p["text"], font=(UI_FONT_FAMILY, 9))
            style.configure("TFrame", background=p["bg"])
            style.configure("TLabel", background=p["bg"], foreground=p["text"])
            style.configure("TCheckbutton", background=p["bg"], foreground=p["text"])
            style.configure("TLabelframe", background=p["bg"], foreground=p["text"], bordercolor=p["border"])
            style.configure("TLabelframe.Label", background=p["bg"], foreground=p["text"], font=(UI_FONT_FAMILY, 9, "bold"))

            style.configure("TButton", padding=(10, 5), background=p["surface"], foreground=p["text"], bordercolor=p["border"])
            style.map(
                "TButton",
                background=[("active", p["header_bg"]), ("pressed", p["header_bg"]), ("disabled", p["bg"])],
                foreground=[("disabled", p["subtle"])],
            )
            # Reserved for the primary actions in the top toolbar (Load/Save).
            style.configure("Accent.TButton", padding=(12, 6), background=p["accent"], foreground=p["accent_text"],
                             bordercolor=p["accent"], font=(UI_FONT_FAMILY, 9, "bold"))
            style.map(
                "Accent.TButton",
                background=[("active", p["accent_hover"]), ("pressed", p["accent_hover"])],
                foreground=[("disabled", p["subtle"])],
            )

            style.configure("TEntry", fieldbackground=p["surface"], foreground=p["text"], bordercolor=p["border"], padding=4)
            style.configure("TCombobox", fieldbackground=p["surface"], foreground=p["text"], bordercolor=p["border"], padding=4)
            style.map("TCombobox", fieldbackground=[("readonly", p["surface"])])
            style.configure("TSpinbox", fieldbackground=p["surface"], foreground=p["text"], bordercolor=p["border"], padding=4)

            style.configure("TNotebook", background=p["bg"], bordercolor=p["border"], tabmargins=(6, 6, 6, 0))
            style.configure("TNotebook.Tab", padding=(16, 8), background=p["bg"], foreground=p["subtle"], font=(UI_FONT_FAMILY, 9, "bold"))
            style.map(
                "TNotebook.Tab",
                background=[("selected", p["surface"])],
                foreground=[("selected", p["accent"])],
            )

            style.configure("Treeview", background=p["surface"], fieldbackground=p["surface"], foreground=p["text"],
                             rowheight=24, bordercolor=p["border"], borderwidth=0)
            style.configure("Treeview.Heading", background=p["header_bg"], foreground=p["text"],
                             font=(UI_FONT_FAMILY, 9, "bold"), relief="flat")
            style.map(
                "Treeview",
                background=[("selected", p["accent"])],
                foreground=[("selected", p["accent_text"])],
            )

            style.configure("TSeparator", background=p["border"])
            style.configure("TPanedwindow", background=p["bg"])
            style.configure("Status.TLabel", background=p["bg"], foreground=p["subtle"])
            style.configure("TScrollbar", background=p["surface"], bordercolor=p["border"], arrowcolor=p["subtle"], troughcolor=p["bg"])
        except Exception:
            pass  # cosmetics only - never block the app over a styling error

    def _retheme_raw_widgets(self):
        """Live-updates plain tk (non-ttk) widgets that already existed before
        a Dark Mode toggle, since the Tk option database only affects widgets
        created after it's set."""
        p = self._ui_palette
        if p is None:
            return  # facelift disabled - nothing to retheme
        for name in ("lst_teams", "lst_players"):
            w = getattr(self, name, None)
            if w:
                w.configure(
                    background=p["surface"], foreground=p["text"],
                    selectbackground=p["accent"], selectforeground=p["accent_text"],
                    highlightbackground=p["border"], highlightcolor=p["accent"],
                )
        if getattr(self, "txt_desc", None):
            self.txt_desc.configure(background=p["surface"], foreground=p["text"], highlightbackground=p["border"])
        for lbl in getattr(self, "_help_labels", []):
            lbl.configure(background=p["bg"], foreground=p["subtle"])
        for canvas in getattr(self, "_themed_canvases", []):
            canvas.configure(background=p["bg"])

    def on_toggle_dark_mode(self):
        mode = "dark" if self.dark_mode_var.get() else "light"
        self._apply_theme(mode)
        self._retheme_raw_widgets()
        self.ui_prefs["mode"] = mode
        save_ui_prefs(self.ui_prefs)

    def on_toggle_facelift(self):
        """Master switch: every feature works the same regardless, this only
        controls whether the custom theme/colors/dark-mode get applied.
        Doesn't try to live-undo the current styling - restarting is simpler
        and more reliable than writing a matching 'un-theme' pass for every
        style/option-database override _apply_theme makes."""
        enabled = self.facelift_var.get()
        self.ui_prefs["facelift_enabled"] = enabled
        save_ui_prefs(self.ui_prefs)
        chk = getattr(self, "_options_dark_chk", None)
        if chk is not None and chk.winfo_exists():
            chk.state(["!disabled"] if enabled else ["disabled"])
        messagebox.showinfo(
            "Restart required",
            "This takes effect the next time you launch the app. Nothing else changes - "
            "every feature works the same either way, this only affects the look."
        )

    def _open_options_dialog(self):
        """Modern UI/Dark Mode live in a small dialog here rather than as two
        separate toolbar checkbuttons (that pair was what overflowed the
        toolbar at the app's default width) or a native tk.Menu (Windows
        renders tk.Menu via the OS menu system, which ignores Tk's color
        options, so it would never respect Dark Mode). A borderless auto-
        closing dropdown was tried first but never actually rendered on this
        machine despite Tk reporting it as created/viewable - likely a DPI-
        scaling coordinate mismatch between Tk and the physical screen. A
        plain Toplevel is the same proven-reliable pattern as every other
        dialog in this app."""
        if getattr(self, "_options_dlg", None) is not None and self._options_dlg.winfo_exists():
            self._options_dlg.lift()
            return

        dlg = tk.Toplevel(self)
        dlg.title("Options")
        dlg.resizable(False, False)
        dlg.transient(self)
        p = self._ui_palette
        if p:
            dlg.configure(background=p["bg"])

        inner = ttk.Frame(dlg)
        inner.pack(fill="both", expand=True, padx=16, pady=14)

        ttk.Checkbutton(
            inner, text="Modern UI", variable=self.facelift_var, command=self.on_toggle_facelift
        ).pack(anchor="w", pady=(0, 8))
        chk_dark = ttk.Checkbutton(
            inner, text="Dark Mode", variable=self.dark_mode_var, command=self.on_toggle_dark_mode
        )
        chk_dark.pack(anchor="w")
        if not self.facelift_var.get():
            chk_dark.state(["disabled"])
        self._options_dark_chk = chk_dark

        ttk.Button(inner, text="Close", command=dlg.destroy).pack(anchor="e", pady=(14, 0))
        self._options_dlg = dlg

        # Anchored near the Options button itself (top-right of the toolbar)
        # rather than left to Tk's default placement, which isn't consistent
        # enough to rely on for a small dialog like this.
        dlg.update_idletasks()
        x = self._options_btn.winfo_rootx() - dlg.winfo_reqwidth() + self._options_btn.winfo_width()
        y = self._options_btn.winfo_rooty() + self._options_btn.winfo_height() + 4
        dlg.geometry(f"+{x}+{y}")

    # ---------- UI layout ----------
    def _build_ui(self):
        top = ttk.Frame(self)
        top.pack(fill="x", padx=12, pady=10)

        ttk.Button(top, text="Load Save File", style="Accent.TButton", command=self.on_load).pack(side="left")
        ttk.Button(top, text="Save to File", style="Accent.TButton", command=self.on_save).pack(side="left", padx=(8, 0))
        ttk.Button(top, text="Reload from File", command=self.on_reload).pack(side="left", padx=(8, 0))

        ttk.Separator(top, orient="vertical").pack(side="left", fill="y", padx=12)

        ttk.Label(top, text="Recent:").pack(side="left")
        self.recent_files_var = tk.StringVar()
        self.cmb_recent = ttk.Combobox(top, width=26, state="readonly", textvariable=self.recent_files_var)
        self.cmb_recent.pack(side="left", padx=(4, 0))
        self.cmb_recent.bind("<<ComboboxSelected>>", self.on_load_recent)
        # ttk.Combobox can't show a per-row "x" inside its own dropdown - this
        # opens a small separate list that can, so entries can be individually
        # removed instead of only ever appending/aging out at RECENT_FILES_MAX.
        ttk.Button(top, text="Manage...", command=self.on_manage_recent_files).pack(side="left", padx=(4, 0))
        self._recent_display_to_path = {}
        self._refresh_recent_files_ui(load_recent_files())

        ttk.Separator(top, orient="vertical").pack(side="left", fill="y", padx=12)

        ttk.Button(top, text="Trade Players (Safe Swap)", command=self.on_open_swap_trade).pack(side="left")
        ttk.Button(top, text="Sign Free Agent...", command=self.on_open_sign_free_agent).pack(side="left", padx=(8, 0))
        ttk.Button(top, text="Player Type Fit...", command=self.on_open_player_type_fit).pack(side="left", padx=(8, 0))

        # Packed before the status label (both docking to the right) so it
        # always claims its space regardless of how long the status text
        # gets - previously a long "Loaded: ..." string could push this
        # entirely off the visible window. Modern UI/Dark Mode live under one
        # "Options" dropdown here rather than as two separate checkbuttons -
        # that pair was what overflowed the toolbar at the app's default
        # width. The dropdown is a small custom popup built from the same
        # ttk.Checkbutton widgets used everywhere else, NOT a native tk.Menu -
        # Windows renders tk.Menu via the OS menu system, which ignores Tk's
        # color options entirely, so a real dropdown menu here would always
        # look like a plain light Windows menu regardless of Dark Mode.
        self._options_btn = ttk.Button(top, text="Options...", command=self._open_options_dialog)
        self._options_btn.pack(side="right", padx=(8, 0))
        ttk.Separator(top, orient="vertical").pack(side="right", fill="y", padx=12)

        self.lbl_status = ttk.Label(top, text="Load play.csv to begin.", style="Status.TLabel", width=40, anchor="w")
        self.lbl_status.pack(side="left", fill="x", expand=True, padx=14)

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self.tab_players = ttk.Frame(self.notebook)
        self.tab_player_editor = ttk.Frame(self.notebook)
        self.tab_picks = ttk.Frame(self.notebook)

        self.notebook.add(self.tab_players, text="Players")
        self.notebook.add(self.tab_player_editor, text="Player Editor")
        self.notebook.add(self.tab_picks, text="Draft Picks")

        self._build_players_tab()
        self._build_player_editor_tab()
        self._build_picks_tab()
        # New staff tabs
        self._build_trainer_tab()
        self._build_coach_tab()
        self._build_gm_tab()
        self._build_playbooks_tab()

    def _build_players_tab(self):
        root = self.tab_players

        # Left: Teams. Bottom controls (team-wide buttons + cap panel) are
        # packed FIRST with side="bottom" so they always keep their reserved
        # space regardless of window height - otherwise a tall Teams listbox
        # can push them off-screen (same overflow bug fixed elsewhere, e.g.
        # the Draft Picks tab).
        left = ttk.Frame(root)
        left.pack(side="left", fill="y", padx=(0, 8), pady=6)

        bottom_left = ttk.Frame(left)
        bottom_left.pack(side="bottom", fill="x")
        ttk.Button(bottom_left, text="Set Team Bonus Min", command=self.on_set_team_bonus_min).pack(anchor="w", pady=(8, 0))
        ttk.Button(bottom_left, text="Max Team Staff", command=self.on_max_team_staff_skpt).pack(anchor="w", pady=(6, 0))
        ttk.Button(bottom_left, text="Apply Motivator Boost to Team...", command=self.on_open_team_motivator_dialog).pack(anchor="w", pady=(6, 0))
        self._build_cap_panel(bottom_left)

        ttk.Label(left, text="Teams").pack(anchor="w")
        self.lst_teams = tk.Listbox(left, height=28, exportselection=False)
        self.lst_teams.pack(fill="both", expand=True)
        self.lst_teams.bind("<<ListboxSelect>>", self.on_team_select)

        # Middle: Players
        mid = ttk.Frame(root)
        mid.pack(side="left", fill="both", expand=True, padx=(0, 8), pady=6)

        search_frm = ttk.Frame(mid)
        search_frm.pack(fill="x", pady=(0, 4))
        ttk.Label(search_frm, text="Find player (any team):").pack(side="left")
        self.player_search_var = tk.StringVar()
        self._player_search_after_id = None
        ent_player_search = ttk.Entry(search_frm, textvariable=self.player_search_var, width=18)
        ent_player_search.pack(side="left", padx=(4, 4))
        self.player_search_var.trace_add("write", self._on_player_search_changed)
        ttk.Button(search_frm, text="Clear", command=self.on_clear_player_search).pack(side="left", padx=(4, 0))

        sort_frm = ttk.Frame(mid)
        sort_frm.pack(fill="x", pady=(0, 4))
        ttk.Label(sort_frm, text="Sort team list by:").pack(side="left")
        saved_sort = self.ui_prefs.get("player_sort")
        self.player_sort_var = tk.StringVar(value=saved_sort if saved_sort in PLAYER_LIST_SORT_OPTIONS else PLAYER_LIST_SORT_OPTIONS[0])
        cmb_sort = ttk.Combobox(sort_frm, state="readonly", width=22, textvariable=self.player_sort_var, values=PLAYER_LIST_SORT_OPTIONS)
        cmb_sort.pack(side="left", padx=(4, 0))
        cmb_sort.bind("<<ComboboxSelected>>", self._on_player_sort_changed)

        self.lbl_players_header = ttk.Label(mid, text="Players on Team (play.csv)")
        self.lbl_players_header.pack(anchor="w")
        self.lst_players = tk.Listbox(mid, height=28, exportselection=False)
        self.lst_players.pack(fill="both", expand=True)
        self.lst_players.bind("<<ListboxSelect>>", self.on_player_select)

    def _build_cap_panel(self, parent):
        """Salary Cap (slri.csv) - lives on the Players tab alongside the
        other team-wide/mass-edit tools (team bonus min, staff max, team
        motivator boost) rather than its own thin notebook tab, since it's
        just one field + two buttons."""
        frm = ttk.LabelFrame(parent, text="Salary Cap (slri.csv)")
        frm.pack(anchor="w", fill="x", pady=(12, 0))

        row1 = ttk.Frame(frm)
        row1.pack(fill="x", padx=6, pady=(6, 4))
        self.ent_cap = ttk.Entry(row1, width=14)
        self.ent_cap.pack(side="left")
        ttk.Button(row1, text="Set to Max", command=self.set_cap_to_max).pack(side="left", padx=(6, 0))

        ttk.Button(
            frm, text="Apply (max 260,000,000 - higher freezes the game)",
            command=self.on_apply_cap,
        ).pack(anchor="w", padx=6, pady=(0, 4))

        self.lbl_cap_status = ttk.Label(frm, text="Load slri.csv to edit cap.", wraplength=200, justify="left")
        self.lbl_cap_status.pack(anchor="w", padx=6, pady=(0, 6))

    # ---------- Player Editor tab (individual-player editing) ----------
    def _build_player_editor_tab(self):
        root = self.tab_player_editor

        self.lbl_player_editor_header = ttk.Label(root, text="No player selected - pick one from the Players tab.", font=("", 10, "bold"))
        self.lbl_player_editor_header.pack(anchor="w", padx=10, pady=(10, 4))

        # This column can hold more content than fits vertically depending on
        # window size (e.g. the Contract Editor's 7-year grid), so it's
        # wrapped in a scrollable canvas rather than assuming everything
        # always fits - nothing gets silently clipped off below the window.
        right_outer = ttk.Frame(root)
        right_outer.pack(side="left", fill="both", expand=True, padx=10, pady=(0, 6))

        canvas_kwargs = dict(highlightthickness=0, bd=0)
        if self._ui_palette:
            canvas_kwargs["background"] = self._ui_palette["bg"]
        right_canvas = tk.Canvas(right_outer, **canvas_kwargs)
        self._themed_canvases = getattr(self, "_themed_canvases", [])
        self._themed_canvases.append(right_canvas)
        right_scroll = ttk.Scrollbar(right_outer, orient="vertical", command=right_canvas.yview)
        right_canvas.configure(yscrollcommand=right_scroll.set)
        right_canvas.pack(side="left", fill="both", expand=True)
        right_scroll.pack(side="right", fill="y")

        right = ttk.Frame(right_canvas)
        right_window_id = right_canvas.create_window((0, 0), window=right, anchor="nw")

        def _on_right_frame_configure(event=None):
            right_canvas.configure(scrollregion=right_canvas.bbox("all"))
        right.bind("<Configure>", _on_right_frame_configure)

        def _on_right_canvas_configure(event):
            right_canvas.itemconfigure(right_window_id, width=event.width)
        right_canvas.bind("<Configure>", _on_right_canvas_configure)

        def _on_right_mousewheel(event):
            right_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        right_canvas.bind("<MouseWheel>", _on_right_mousewheel)
        right.bind("<MouseWheel>", _on_right_mousewheel)

        # --- Portrait ---
        self._build_portrait_panel(right, kind="player", extra_buttons=[
            ("Assign Existing Photo...", self.on_open_assign_portrait_dialog),
            ("Edit Contract...", self.on_open_contract_editor),
            ("Personality...", self.on_open_player_personality_editor),
        ])

        # --- Name Editor ---
        namefrm = ttk.LabelFrame(right, text="Name Editor (PFNA / PLNA) (sanitized to avoid crashes)")
        namefrm.pack(fill="x", pady=(0, 6))

        ttk.Label(namefrm, text="First").grid(row=0, column=0, sticky="w")
        self.ent_first = ttk.Entry(namefrm, width=14)
        self.ent_first.grid(row=0, column=1, sticky="w", padx=6)

        ttk.Label(namefrm, text="Last").grid(row=0, column=2, sticky="w", padx=(10, 0))
        self.ent_last = ttk.Entry(namefrm, width=14)
        self.ent_last.grid(row=0, column=3, sticky="w", padx=6)

        ttk.Button(namefrm, text="Apply Name", command=self.on_apply_name).grid(row=0, column=4, sticky="w", padx=(8, 0))
        namefrm.grid_columnconfigure(4, weight=1)

        ttk.Button(right, text="Apply Motivator Boost...", command=self.on_open_motivator_dialog).pack(anchor="w", pady=(0, 6))

        ttk.Label(right, text="Stats (described only)").pack(anchor="w")

        cols = ("stat", "cur_col", "cur_val", "max_col", "max_val")
        self.tree_stats = ttk.Treeview(right, columns=cols, show="headings", height=11)
        for c, w in zip(cols, [260, 90, 80, 90, 80]):
            self.tree_stats.heading(c, text=c, command=lambda c=c: self._sort_tree(self.tree_stats, c))
            self.tree_stats.column(c, width=w, anchor="w", stretch=False)
        self.tree_stats.pack(fill="both", expand=True)
        self.tree_stats.bind("<<TreeviewSelect>>", self.on_stat_select)

        self.txt_desc = tk.Text(right, height=3, wrap="word")
        self.txt_desc.pack(fill="x", pady=(6, 6))
        self.txt_desc.configure(state="disabled")

        edit = ttk.Frame(right)
        edit.pack(fill="x")

        ttk.Label(edit, text="Cur").grid(row=0, column=0, sticky="w")
        self.ent_new_cur = ttk.Entry(edit, width=7)
        self.ent_new_cur.grid(row=0, column=1, sticky="w", padx=(4, 8))

        ttk.Label(edit, text="Max").grid(row=0, column=2, sticky="w")
        self.ent_new_max = ttk.Entry(edit, width=7)
        self.ent_new_max.grid(row=0, column=3, sticky="w", padx=(4, 8))

        ttk.Button(edit, text="Apply", command=self.on_apply_stat).grid(row=0, column=4, sticky="w")
        ttk.Button(edit, text="Apply Both", command=self.on_apply_both).grid(row=0, column=5, sticky="w", padx=(8, 0))

        info = ttk.Frame(right)
        info.pack(fill="x", pady=(6, 0))

        ttk.Label(info, text="Age").grid(row=0, column=0, sticky="w")
        self.ent_age = ttk.Entry(info, width=5)
        self.ent_age.grid(row=0, column=1, sticky="w", padx=(4, 12))
        ttk.Label(info, text="Years").grid(row=0, column=2, sticky="w")
        self.ent_years = ttk.Entry(info, width=5)
        self.ent_years.grid(row=0, column=3, sticky="w", padx=(4, 12))
        ttk.Button(info, text="Apply Age/Years", command=self.on_apply_age_years).grid(row=0, column=4, sticky="w")

        # Contract/Personality buttons live next to the portrait at the top
        # of this tab (see _build_portrait_panel's extra_buttons) rather than
        # here, to make use of the blank space beside the photo.

        # Raw column editor (ANY column)
        raw = ttk.LabelFrame(right, text="Raw Column Editor (any header)")
        raw.pack(fill="x", pady=(6, 0))

        ttk.Label(raw, text="Column").grid(row=0, column=0, sticky="w")
        self.cmb_raw_col = ttk.Combobox(raw, width=22, state="readonly")
        self.cmb_raw_col.grid(row=0, column=1, sticky="w", padx=6)

        ttk.Label(raw, text="Value").grid(row=0, column=2, sticky="w", padx=(10, 0))
        self.ent_raw_val = ttk.Entry(raw, width=26)
        self.ent_raw_val.grid(row=0, column=3, sticky="w", padx=6)

        ttk.Button(raw, text="Apply", command=self.on_apply_raw_column).grid(row=0, column=4, sticky="w", padx=8)

    # =========================================================================
    # DRAFT PICK REASSIGNMENT - RESTORED, "FRESH SAVE ONLY" THEORY DISPROVEN
    # =========================================================================
    # An "Assign to team" feature (writing DRAFT_PICK_ID directly, matching
    # the approach independently used and reported working by someone in the
    # NFL Head Coach modding Discord) was originally confirmed to CRASH THE
    # GAME ON DAY-ADVANCE on the primary test save (BLUS30128-CAREER-TEST) -
    # the same failure mode as the "Move Player -> Selected Team" investigation
    # earlier in this file. That same Discord thread had flagged this exact
    # risk up front: "It might f*ck up the game later since the trade details
    # are in the list I found earlier, but it should work on a new game."
    #
    # Ruled out two things that turned out NOT to be the cause: a separate
    # "trade details" table (searched, none found - DPTT/DRPP look like
    # draft-class scouting data, not a trade ledger; DPLP too sparse; TEAM.TRDE
    # is "Team Rating DEF", an unrelated red herring despite the name), and
    # DPOD staleness (writing DPOD to match the new team too made things
    # WORSE - the pick vanished from the destination team's board entirely -
    # and didn't stop the crash either, so DPOD is never written here).
    #
    # Also reproduced the crash via the REAL HC09Editor.exe's own binary
    # writer, not just this project's bridge - ruling out a bug specific to
    # this reimplementation.
    #
    # Initially looked like a "fresh vs. aged save" distinction (DRPK grows
    # from 448 records on a brand-new save to 672 once a season has passed -
    # one full 224-pick draft class per DPYO value): reassigning multiple
    # picks (both current AND next year, several rounds) worked cleanly on a
    # freshly-created save. BUT that theory was DISPROVEN by testing a THIRD,
    # separate save (BLUS30128-CAREER-DOLPHINS) that also has 672 DRPK
    # records (same "aged" bucket as the crashing TEST save) - the exact same
    # multi-pick reassignment worked fine there too, surviving day-advance.
    # So DRPK size/save age is NOT the deciding factor - two 672-record saves
    # gave opposite results.
    #
    # CURRENT WORKING THEORY (not confirmed): the crash is specific to
    # BLUS30128-CAREER-TEST itself, most likely from the sheer volume of
    # OTHER experimental edits made directly to that one save throughout this
    # project's development (dozens of rounds of Coach/GM/player/cap/roster
    # testing, including at least one other confirmed-crashy edit - the
    # "Move Player" TGID investigation - performed on the exact same save
    # file) rather than anything about draft picks specifically. Draft pick
    # reassignment itself is now confirmed working on TWO independent saves
    # (one fresh, one aged) and only ever failed on the one save that had
    # accumulated the most total editing history of any save in this project.
    # Still shows a confirmation dialog every time as a matter of caution,
    # since the real cause remains unconfirmed - just don't take the specific
    # "fresh save only" framing as accurate anymore.
    #
    # DURABILITY FOLLOW-UP: reassigned ~30 picks across many teams/rounds on
    # BLUS30128-CAREER-DOLPHINS, then played multiple additional games on a
    # continuation save (DOLPHINS2). Both current-year AND future-year
    # reassignments held up correctly over that span, matching what was
    # visible in-game. A narrower check of 3 specific future-year picks
    # briefly looked like it disproved future-year durability (they'd
    # reverted to their original owner) - but a broader check of ALL of
    # Dolphins' future-year picks showed the other ~17 reassigned ones were
    # still intact, so that was far more likely 3 picks getting legitimately
    # re-traded back by normal AI GM activity during simulated games (a real,
    # ongoing game mechanic) than anything reverting on its own. No real
    # "future picks don't stick" bug - retracted.
    #
    # PRACTICAL MITIGATION (unrelated to draft picks specifically - also
    # applies to RPCS3-level save hangs seen independent of any pick editing,
    # e.g. on QUICKSAVE which was never touched with pick reassignment):
    # whenever something has seemed off after heavy editing/testing on a
    # given save, starting a genuinely new save file and continuing from
    # there has resolved it every time it's been tried. Not a fix for a
    # specific known bug (no specific bug was ever isolated) - just the
    # practical workaround that's actually worked, echoed in the confirmation
    # dialog below.
    # =========================================================================
    def _build_picks_tab(self):
        root = self.tab_picks
        top = ttk.Frame(root)
        top.pack(fill="x", padx=10, pady=10)

        ttk.Label(top, text="Draft Picks (drpk.csv)").pack(side="left")
        ttk.Button(top, text="Refresh", command=self.refresh_picks).pack(side="left", padx=8)

        ttk.Label(top, text="Filter by team:").pack(side="left", padx=(16, 4))
        self.pick_filter_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.pick_filter_var, width=20).pack(side="left")
        self.pick_filter_var.trace_add("write", lambda *_a: self.refresh_picks())
        ttk.Button(top, text="Clear", command=lambda: self.pick_filter_var.set("")).pack(side="left", padx=(6, 0))

        help_text = (
            "Confirmed working reliably across multiple saves and games of play (both current AND future-year "
            "reassignments held up over time, alongside normal AI trade activity). Crashed once, on one heavily "
            "test-edited save, never reproduced since - if anything ever seems off, saving to a NEW file and "
            "continuing from there has resolved it every time it's come up. You'll get a confirmation prompt "
            "every time as a precaution. Click a pick to select it (ctrl/shift-"
            "click for multiple), pick a destination team below, then Assign. Per the Discord community: DPNM "
            "(raw pick number) is 0-indexed for the CURRENT year only (pick #1 overall = 0) - Round/Pick# below "
            "are already converted to the real, 1-indexed value you'd see in-game. For FUTURE years, DPNM isn't "
            "a pick number at all (the draft order isn't determined yet) - shown as \"Future\" rather than a "
            "fabricated round/pick. \"Year\" is a sequential 1/2... display of the save's real year-offset "
            "values, not a literal calendar year (that was tried and disproven). Only the current year and one "
            "year out are shown, matching what the in-game draft picks screen itself displays - DRPK can carry "
            "a further-out 3rd year that the game never shows, so this list skips it too."
        )
        help_frame = ttk.Frame(root)
        help_frame.pack(fill="x", padx=10)
        _lbl_help = tk.Label(help_frame, text=help_text, wraplength=1000, justify="left", fg="gray")
        _lbl_help.pack(fill="x", pady=(4, 6))
        self._help_labels.append(_lbl_help)

        # Bottom controls packed FIRST with side="bottom" so they always keep
        # their reserved space regardless of window size - previously the
        # tall picks table (height=20) could eat all the vertical space and
        # push the destination-team/Assign controls off-screen entirely.
        bottom = ttk.Frame(root)
        bottom.pack(side="bottom", fill="x", padx=10, pady=(0, 10))
        self.lbl_pick_selection = ttk.Label(bottom, text="No picks selected")
        self.lbl_pick_selection.pack(side="left")

        ttk.Label(bottom, text="Assign to:").pack(side="left", padx=(16, 4))
        # Draft picks can only be owned by real teams (confirmed: DPID values
        # in every save checked are always 1-32, never a pool ID) - same
        # 32-team list as Sign Free Agent's destination combo.
        self.pick_dest_combo = TeamAutocompleteCombo(bottom, SIGN_DEST_TEAMS, width=26).pack(side="left")

        ttk.Button(bottom, text="Assign", command=self.on_assign_picks).pack(side="left", padx=8)

        cols = ("team", "orig_team", "round", "pick_num", "year")
        headings = {
            "team": ("Team (current)", 220), "orig_team": ("Originally", 220),
            "round": ("Round", 70), "pick_num": ("Pick #", 70), "year": ("Year", 60),
        }
        self.tree_picks = ttk.Treeview(root, columns=cols, show="headings", height=12, selectmode="extended")
        for c in cols:
            text, width = headings[c]
            self.tree_picks.heading(c, text=text, command=lambda c=c: self._sort_tree(self.tree_picks, c))
            self.tree_picks.column(c, width=width, anchor="w", stretch=False)
        self.tree_picks.pack(fill="both", expand=True, padx=10, pady=(0, 6))
        self.tree_picks.bind("<<TreeviewSelect>>", lambda e: self._update_pick_selection_label())

    # ---------- Playbooks tab (read-only, names resolved) ----------
    def _build_playbooks_tab(self):
        root = ttk.Frame(self.notebook)
        self.tab_playbooks = root
        self.notebook.add(root, text="Playbooks")
        self._playbook_data = None
        self._playbook_stamp = None
        self._playbook_profile = ""     # the profile save the custom names came from, if one was found
        self._playbook_flagged = []     # custom playbooks whose name is marked * (the career's plays differ from the profile's)
        self._playbook_problems = []    # why a profile could not be read, if it could not
        self._profile_cache = {}        # profile path -> (mtime, names): not re-read while unchanged, and a fallback
        self._pb_team_manual = False   # True once the tab's Team box was changed by hand
        self.notebook.bind("<<NotebookTabChanged>>", self._on_notebook_tab_changed, add="+")

        top = ttk.Frame(root)
        top.pack(fill="x", padx=10, pady=(10, 4))
        ttk.Label(top, text="Playbooks").pack(side="left")
        ttk.Button(top, text="Load / Refresh", command=lambda: self.refresh_playbooks(force=True)).pack(side="left", padx=8)
        ttk.Button(top, text="Profile save...", command=self.on_pick_profile).pack(side="left")
        ttk.Button(top, text="Help", command=self._toggle_pb_help).pack(side="left", padx=(8, 0))
        self._pb_top_frame = top
        self.lbl_playbook_status = ttk.Label(top, text="Open this tab after loading a save.", foreground="gray")
        self.lbl_playbook_status.pack(side="left", padx=(8, 0))

        help_text = (
            "Browse playbooks with real play, set and formation names (read from your own game files, then cached). "
            "Find play shows a play's codes and every playbook that has it. Team playbooks changes a team's offense or "
            "defense by name. Add plays copies plays, sets or formations from another playbook into your team's "
            "(or any playbook you choose in the dialog; 200 per playbook, special teams don't count). Playbooks 1-10 "
            "and the plays in them that you made in the game are named from your profile save.\n\n"
            "A team holds a playbook for its head coach and one for each coordinator, and plays one of them: the one "
            "marked In use. Played by switches between them (this is the Playbook Control setting of Team Philosophy, "
            "so it is changed there too). Change... sets one of the game's playbooks on the head coach and both "
            "coordinators, so it is used either way. A custom playbook is set on the head coach only, as the game's own "
            "Playbook Select does, and Played by is switched to Head coach for you. Show: Offense / Defense picks which "
            "side's playbooks, find results and Add button you are working with. Then Save to File."
        )
        help_frame = ttk.Frame(root)         # shown by the Help button
        lbl = tk.Label(help_frame, text=help_text, wraplength=1000, justify="left", fg="gray")
        lbl.pack(fill="x", pady=(2, 6))
        self._help_labels.append(lbl)
        self._pb_help_frame = help_frame

        team = ttk.LabelFrame(root, text="Team playbooks")
        team.pack(fill="x", padx=10, pady=(0, 6))
        trow = ttk.Frame(team)
        trow.pack(fill="x", padx=6, pady=6)
        ttk.Label(trow, text="Team:").pack(side="left")
        self._pb_team_names = [(tid, team_nickname(tid)) for tid, _ in SIGN_DEST_TEAMS]
        self.pb_team_var = tk.StringVar()
        self.cmb_pb_team = ttk.Combobox(trow, state="readonly", width=16, textvariable=self.pb_team_var,
                                        values=[n for _t, n in self._pb_team_names])
        self.cmb_pb_team.pack(side="left", padx=(6, 14))
        self.cmb_pb_team.bind("<<ComboboxSelected>>", lambda e: self._on_pb_team_chosen())
        bold = ("TkDefaultFont", 9, "bold")
        self.pb_ctl_vars = {}
        for word, side, attr in (("Offense", "1", "off"), ("Defense", "0", "def")):
            row = ttk.Frame(team)
            row.pack(fill="x", padx=6, pady=(0, 4))
            ttk.Label(row, text=word, font=bold, width=8).pack(side="left")
            ttk.Label(row, text="In use:").pack(side="left")
            lbl = ttk.Label(row, text="-", font=bold, width=26)
            lbl.pack(side="left", padx=(4, 6))
            setattr(self, f"lbl_pb_{attr}", lbl)
            ttk.Button(row, text="Change...", command=lambda sd=side: self.on_change_team_playbook(sd)).pack(side="left", padx=(0, 12))
            ctlf = ttk.Frame(row)
            ctlf.pack(side="left")
            ttk.Label(ctlf, text="Played by:").pack(side="left")
            var = tk.StringVar(value="coord")
            self.pb_ctl_vars[side] = var
            coord_word = "Offensive coordinator" if side == "1" else "Defensive coordinator"
            rbs = []
            for text, value in (("Head coach", "hc"), (coord_word, "coord")):
                rb = ttk.Radiobutton(ctlf, text=text, variable=var, value=value, command=lambda sd=side: self._on_pb_control_toggle(sd))
                rb.pack(side="left", padx=(6, 0))
                rbs.append(rb)
            setattr(self, f"rb_pb_{attr}", rbs)
            ctl = ttk.Label(ctlf, text="", foreground="gray")
            ctl.pack(side="left", padx=(8, 0))
            setattr(self, f"lbl_pb_{attr}_ctl", ctl)
            det = ttk.Label(row, text="", foreground="gray")
            det.pack(side="left", padx=(12, 0))
            setattr(self, f"lbl_pb_{attr}_detail", det)

        search = ttk.Frame(root)
        search.pack(fill="x", padx=10, pady=(2, 4))
        self.pb_side_var = tk.StringVar(value="Offense")
        ttk.Label(search, text="Show:", font=bold).pack(side="left")
        for word in ("Offense", "Defense"):
            ttk.Radiobutton(search, text=word, variable=self.pb_side_var, value=word,
                            command=self._on_pb_side_changed).pack(side="left", padx=(8, 0))
        ttk.Separator(search, orient="vertical").pack(side="left", fill="y", padx=14)
        ttk.Label(search, text="Find play (name or set):").pack(side="left")
        self.playbook_search_var = tk.StringVar()
        ent = ttk.Entry(search, textvariable=self.playbook_search_var, width=26)
        ent.pack(side="left", padx=(6, 6))
        ent.bind("<Return>", lambda e: self.on_playbook_search())
        ttk.Button(search, text="Find", command=self.on_playbook_search).pack(side="left")
        ttk.Button(search, text="Clear", command=self.on_playbook_search_clear).pack(side="left", padx=(6, 0))
        self.btn_pb_add_found = ttk.Button(search, text="Add found play to a playbook...", command=self.on_playbook_add_found)
        self.btn_pb_add_found.pack(side="left", padx=(12, 0))
        self.lbl_playbook_hit = ttk.Label(search, text="", foreground="gray")
        self.lbl_playbook_hit.pack(side="left", padx=(12, 0))

        panes = ttk.PanedWindow(root, orient="horizontal")

        def make_tree(parent, cols, widths, height=6, weight=1):
            frm = ttk.Frame(parent)
            tree = ttk.Treeview(frm, columns=[c for c, _ in cols], show="headings", height=height, selectmode="browse")
            for (c, text), w in zip(cols, widths):
                tree.heading(c, text=text, command=lambda c=c, t=tree: self._sort_tree(t, c))
                tree.column(c, width=w, anchor="w", stretch=(c == cols[0][0]))
            sb = ttk.Scrollbar(frm, orient="vertical", command=tree.yview)
            tree.configure(yscrollcommand=sb.set)
            sb.pack(side="right", fill="y")
            tree.pack(side="left", fill="both", expand=True)
            parent.add(frm, weight=weight)
            return tree

        self.tree_pb_books = make_tree(panes, [("name", "Playbook"), ("side", "Side"), ("id", "ID"), ("plays", "Plays"), ("off", "Offense used by"), ("def", "Defense used by")],
                                       [200, 62, 44, 48, 120, 120], weight=3)
        self.tree_pb_forms = make_tree(panes, [("name", "Formation"), ("id", "ID"), ("sets", "Sets")], [160, 50, 44], weight=2)
        self.tree_pb_plays = make_tree(panes, [("play", "Play"), ("set", "Set"), ("type", "Type"), ("setl", "SETL"), ("plyl", "PLYL")],
                                       [190, 130, 46, 50, 50], weight=3)
        self._apply_pb_columns()
        self.tree_pb_books.bind("<<TreeviewSelect>>", lambda e: self._on_playbook_book_selected())
        self.tree_pb_forms.bind("<<TreeviewSelect>>", lambda e: self._on_playbook_form_selected())

        # The Add bar and Find results are packed to the bottom BEFORE the tables, so on a short
        # window it is the tables that shrink, never these.
        res = ttk.LabelFrame(root, text="Find results")          # packed (above the bottom edge) only when a search has results
        bar = ttk.Frame(root)
        bar.pack(side="bottom", fill="x", padx=10, pady=(0, 10))
        self._pb_res_frame, self._pb_bar_frame = res, bar
        self.btn_pb_add = ttk.Button(bar, text="Add plays...", command=lambda: self.on_playbook_add_plays(side=self.pb_side_var.get()))
        self.btn_pb_add.pack(side="left")
        self.lbl_pb_cap = ttk.Label(bar, text="", foreground="gray")
        self.lbl_pb_cap.pack(side="left", padx=(12, 0))
        panes.pack(fill="both", expand=True, padx=10, pady=(0, 4))
        ttk.Label(
            res, foreground="gray",
            text="Search for a play above to see its codes and which playbooks have it. "
                 "Click a row to list the playbooks that have it (this doesn't change which playbook is selected above).",
        ).pack(anchor="w", padx=6, pady=(4, 0))
        self.tree_pb_found = ttk.Treeview(
            res, columns=("play", "set", "type", "setl", "plyl", "n"), show="headings", height=4, selectmode="browse")
        for c, text, w in (("play", "Play", 220), ("set", "Set", 150), ("type", "Type", 50), ("setl", "SETL", 56), ("plyl", "PLYL", 56), ("n", "In playbooks", 90)):
            self.tree_pb_found.heading(c, text=text, command=lambda c=c: self._sort_tree(self.tree_pb_found, c))
            self.tree_pb_found.column(c, width=w, anchor="w", stretch=(c == "play"))
        self.tree_pb_found.pack(fill="x", padx=4, pady=4)
        self.tree_pb_found.bind("<<TreeviewSelect>>", lambda e: self._on_playbook_found_selected())
        self._playbook_hits = {}

    def _on_notebook_tab_changed(self, _event=None):
        try:
            current = self.notebook.nametowidget(self.notebook.select())
        except Exception:
            return
        if current is self.tab_playbooks:
            self._sync_pb_team()
            self.refresh_playbooks()

    def _playbook_stamp_now(self):
        path = self.model.db_path
        try:
            return (path, os.path.getmtime(path), self.model.load_serial) if path else None
        except OSError:
            return None

    def _playbook_names_cached(self):
        return all(os.path.isfile(os.path.join(PLAYBOOK_CACHE_DIR, f)) for f in PLAYBOOK_NAME_FILES)

    def refresh_playbooks(self, force=False):
        if not self.model.db_path or not self.model.players:
            self.lbl_playbook_status.configure(text="Load a save first.")
            return
        stamp = self._playbook_stamp_now()
        if not force and self._playbook_data is not None and stamp == self._playbook_stamp:
            return
        if force and self.model.pb_pending and not messagebox.askyesno(
                "Playbooks", "You have playbook changes that aren't saved yet. Reloading discards them. Reload anyway?"):
            return

        boot_ast = ""
        if not self._playbook_names_cached():
            # Asks for qkl_boot.ast on the main thread if it can't find it (same
            # prompt as Player Type Fit); cancelling just means IDs without names.
            boot_ast = self._find_boot_ast("Playbooks", "playbook, formation, set and play names")
        db_path, coaches = self.model.db_path, list(self.model.coaches)
        override = (self.ui_prefs.get("per_save", {}).get(self.get_current_save_key()) or {}).get("profile_path", "")

        def work():
            if boot_ast:
                self._extract_playbook_names(boot_ast)
            game = {os.path.splitext(f)[0]: read_csv_dicts(os.path.join(PLAYBOOK_CACHE_DIR, f)) for f in PLAYBOOK_NAME_FILES}
            tmp = tempfile.mkdtemp(prefix="hc09_playbooks_")
            try:
                self.model.run_bridge(["export", "--db", db_path, "--out", tmp, "--tables", ",".join(PLAYBOOK_SAVE_TABLES)])
                save = {t.lower(): read_csv_dicts(os.path.join(tmp, t.lower() + ".csv")) for t in PLAYBOOK_SAVE_TABLES}
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
            profile_path, profile, flagged, problems = self._choose_profile(db_path, game, save, override)
            return PlaybookData(game, save, coaches, profile, self._pb_control), stamp, profile_path, flagged, problems

        def done(result):
            (self._playbook_data, self._playbook_stamp, self._playbook_profile,
             self._playbook_flagged, self._playbook_problems) = result
            self.model.pb_pending = {}   # the reload replaced whatever was edited
            if boot_ast:
                self.ui_prefs["boot_ast_path"] = boot_ast
                save_ui_prefs(self.ui_prefs)
            self._fill_playbook_books()

        self.run_in_thread_with_busy("Loading playbooks...", work, done, error_title="Playbooks")

    def _read_profile_names(self, profile_path):
        """PLAB / SETL / PBPL rows (names of custom playbooks, sets and plays) from a profile save, plus its
        PGPL to verify them; None if the file has no such rows (so it is not a profile with custom content).
        Read-only, worker thread. A read that fails (say the emulator has the file open for a moment) is
        retried before the error is raised."""
        error = None
        for attempt in range(3):
            tmp = tempfile.mkdtemp(prefix="hc09_profile_")
            try:
                self.model.run_bridge(["export", "--db", profile_path, "--out", tmp, "--tables", ",".join(PLAYBOOK_PROFILE_TABLES)])
                paths = {t: os.path.join(tmp, t.lower() + ".csv") for t in PLAYBOOK_PROFILE_TABLES}
                if not any(os.path.isfile(p) for p in paths.values()):
                    return None
                names = {t.lower(): (read_csv_dicts(p) if os.path.isfile(p) else []) for t, p in paths.items()}
                return names if any(names[t] for t in ("plab", "setl", "pbpl")) else None
            except Exception as e:
                error = e
                time.sleep(0.4)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
        raise error

    def _choose_profile(self, db_path, game, save, override):
        """The profile save whose custom plays this career uses: the one picked by hand (remembered
        per save) if it reads and has custom content, otherwise the neighbouring profile whose custom plays
        match the career's playbook links best (the newest on a tie). A profile that cannot be read right
        now falls back to the last good read of it. Returns (path, names, flagged playbooks, problems) or
        ("", None, [], problems)."""
        key = lambda r, f: (r.get(f) or "").strip()
        stock = {(key(r, "SETL"), key(r, "PLYL")) for r in game.get("pbpl", [])}
        used = {(key(r, "SETL"), key(r, "PLYL")) for r in save.get("pgpl", [])} - stock
        problems = []

        def read(path):
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                mtime = None
            cached = self._profile_cache.get(path)
            if cached and cached[0] == mtime:
                return cached[1]
            try:
                names = self._read_profile_names(path)
            except Exception as e:
                problems.append(f"could not read {recent_file_display(path)}" + (" - using the last read of it" if cached else "") + f" ({str(e)[:70]})")
                return cached[1] if cached else None
            if names:
                self._profile_cache[path] = (mtime, names)
            return names

        if override and os.path.isfile(override):
            names = read(override)
            if names:
                return (override,) + self._verified_names(names, save) + (problems,)
        best_path, best_names, best_score = "", None, -1
        for path in find_profile_saves(db_path):
            names = read(path)
            if not names:
                continue
            score = len(used & {(key(r, "SETL"), key(r, "PLYL")) for r in names["pbpl"]})
            newer = best_path and os.path.getmtime(path) > os.path.getmtime(best_path)
            if score > best_score or (score == best_score and newer):
                best_path, best_names, best_score = path, names, score
        if best_names is None:
            return "", None, [], problems
        return (best_path,) + self._verified_names(best_names, save) + (problems,)

    @staticmethod
    def _verified_names(names, save):
        """Mark the profile's name with a * for any custom playbook whose plays in the profile are not (by
        PLAYBOOK_NAME_MATCH) the plays of the same-numbered playbook in the career - e.g. a career started
        before the playbook was edited in the game - so the name is shown, but never as if it were certain.
        Returns (names with the marks, [the marked playbooks' names])."""
        key = lambda r, f: (r.get(f) or "").strip()
        prof, car = defaultdict(set), defaultdict(set)
        for r in names.get("pgpl", []):
            prof[key(r, "BOKL")].add((key(r, "SETL"), key(r, "PLYL")))
        for r in save.get("pgpl", []):
            car[key(r, "BOKL")].add((key(r, "SETL"), key(r, "PLYL")))
        rows, flagged = [], []
        for r in names.get("plab", []):
            b = key(r, "PBGI")
            a, c = prof.get(b, set()), car.get(b, set())
            ok = (len(a & c) / len(a) >= PLAYBOOK_NAME_MATCH) if a else not c
            name = key(r, "BNAM") or f"Playbook {b}"
            if ok:
                rows.append(r)
            else:
                flagged.append(name)
                rows.append(dict(r, BNAM=name + " *"))
        return dict(names, plab=rows), flagged

    def on_pick_profile(self):
        """Point the Playbooks tab at a profile save by hand (remembered for this career)."""
        if not self.model.db_path:
            messagebox.showinfo("Playbooks", "Load a save first.")
            return
        path = filedialog.askopenfilename(
            title="Locate your profile save (USR-DATA inside the ...-PROFILE-... folder)",
            initialdir=os.path.dirname(os.path.dirname(self.model.db_path)))
        if not path:
            return

        def done(names):
            if names is None:
                messagebox.showinfo("Playbooks", "That file has no playbook names, so it isn't a profile save. Nothing was changed.")
                return
            self.ui_prefs.setdefault("per_save", {}).setdefault(self.get_current_save_key(), {})["profile_path"] = path
            save_ui_prefs(self.ui_prefs)
            self.refresh_playbooks(force=True)

        self.run_in_thread_with_busy("Reading profile...", lambda: self._read_profile_names(path), done, error_title="Playbooks")

    def _extract_playbook_names(self, boot_ast):
        """Pull the playbook / formation / set / play name tables out of the
        user's own qkl_boot.ast into a local cache (worker thread - bridge only).
        PLAB is asked for separately: it exists in two entries but only one has
        the PBGI playbook-ID column and actual rows."""
        out = PLAYBOOK_CACHE_DIR
        self.model.run_bridge(["shipped-table-export", "--ast", boot_ast, "--tables", "PLAB",
                               "--require-fields", "PBGI,BNAM", "--require-rows", "--out-dir", out])
        self.model.run_bridge(["shipped-table-export", "--ast", boot_ast, "--tables", "PBFM,SETL,PBPL",
                               "--out-dir", out])

    def _pb_selected_tid(self):
        name = self.pb_team_var.get()
        for tid, nick in self._pb_team_names:
            if nick == name:
                return tid
        return ""

    def _on_pb_team_chosen(self):
        self._pb_team_manual = True
        self._refresh_pb_team()

    def _sync_pb_team(self):
        """The tab's Team box follows the team chosen for this save (the one picked at load, or
        switched to in the team list) until it is changed by hand here."""
        names = [n for _t, n in self._pb_team_names]
        if not self._pb_team_manual:
            cur = team_nickname(self.selected_team_id.get().strip())
            if cur in names:
                self.pb_team_var.set(cur)
        if not self.pb_team_var.get():
            self.pb_team_var.set(names[0])
        self._refresh_pb_team()

    def _pb_control(self, tid, side):
        """Whose playbook a team plays on one side - "hc" (head coach) or "coord" (coordinator) - from the Team
        Philosophy's Playbook Control (OPPP offense, DPPP defense; 0 = Head Coach, 1 = Coordinator), or None."""
        field = "OPPP" if side == "1" else "DPPP"
        for r in self.model.tphs:
            if (r.get("TGID") or "").strip() == tid:
                return {"0": "hc", "1": "coord"}.get((r.get(field) or "").strip())
        return None

    def _set_pb_control(self, tid, side, value):
        """Set a team's Playbook Control ("0" head coach, "1" coordinator); False if the save has no row for it."""
        field = "OPPP" if side == "1" else "DPPP"
        for r in self.model.tphs:
            if (r.get("TGID") or "").strip() == tid and field in r:
                r[field] = value
                return True
        return False

    def _apply_pb_columns(self):
        """One side is shown at a time, so the Side column (the same on every row) and the other side's
        'used by' column are hidden; the values stay in the table."""
        used = "off" if self.pb_side_var.get() == "Offense" else "def"
        self.tree_pb_books.configure(displaycolumns=("name", "id", "plays", used))

    def _toggle_pb_help(self):
        frame = self._pb_help_frame
        if frame.winfo_ismapped():
            frame.pack_forget()
        else:
            frame.pack(fill="x", padx=10, after=self._pb_top_frame)

    def _show_find_results(self, show):
        """Find results take space only while a search has something to show."""
        res = self._pb_res_frame
        if show and not res.winfo_ismapped():
            res.pack(side="bottom", fill="x", padx=10, pady=(0, 10), before=self._pb_bar_frame)
        elif not show and res.winfo_ismapped():
            res.pack_forget()

    def _on_pb_side_changed(self):
        """Offense / Defense: show that side's playbooks and find results, start on the playbook the chosen team
        plays on that side, and point the Add buttons at it."""
        data = self._playbook_data
        if data is None:
            self._update_add_buttons()
            return
        tree = self.tree_pb_books
        tree.selection_set(())
        self._fill_playbook_books()
        if self.playbook_search_var.get().strip():
            self.on_playbook_search()
        tree.see(tree.selection()[0]) if tree.selection() else None
        self._update_add_buttons()

    def _on_pb_control_toggle(self, side):
        """The Played by switch: head coach or coordinator. Writes the team's Playbook Control (Team Philosophy)."""
        data, tid = self._playbook_data, self._pb_selected_tid()
        want = self.pb_ctl_vars[side].get()
        if data is None or not tid or not self._set_pb_control(tid, side, "0" if want == "hc" else "1"):
            self._refresh_pb_team()
            return
        self.mark_dirty()
        self._on_philosophy_changed()
        word = "offensive" if side == "1" else "defensive"
        who = "the head coach" if want == "hc" else "the coordinator"
        _b, name = data.team_book(self.model.coaches, tid, side)
        self.lbl_playbook_status.configure(
            text=f"{team_nickname(tid)} {word} playbook is now played by {who} ({name}) - Save to File to keep it.")

    def _on_philosophy_changed(self):
        """Playbook Control may have changed in Team Philosophy: which playbook a team plays follows it."""
        data = self._playbook_data
        if data is not None:
            data.set_usage(self.model.coaches, self._pb_control)
            self._fill_playbook_books()
            self._refresh_pb_team()

    def _update_add_buttons(self):
        """The Add buttons say which playbook they add to: the one the chosen team plays on the side picked
        with Offense / Defense (the head coach's or the coordinator's, whichever Played by says)."""
        data, tid = self._playbook_data, self._pb_selected_tid()
        side = self.pb_side_var.get()
        bokl = data.team_bokl(self.model.coaches, tid, "1" if side == "Offense" else "0") if data is not None and tid else None
        name = data.book_label(bokl) if bokl else None
        word = {"Offense": "offensive", "Defense": "defensive"}[side]
        self.btn_pb_add.configure(text=f"Add {word} plays to {name}..." if name else f"Add {word} plays...")
        self.btn_pb_add_found.configure(text=f"Add found play to {name}..." if name else "Add found play to a playbook...")

    def _refresh_pb_team(self):
        data = self._playbook_data
        tid = self._pb_selected_tid()
        self._update_add_buttons()
        for side, attr in (("1", "off"), ("0", "def")):
            getattr(self, f"lbl_pb_{attr}").configure(text="-")
            getattr(self, f"lbl_pb_{attr}_ctl").configure(text="")
            getattr(self, f"lbl_pb_{attr}_detail").configure(text="")
            self.pb_ctl_vars[side].set("coord")
            for rb in getattr(self, f"rb_pb_{attr}"):
                rb.configure(state="disabled")
        if data is None or not tid:
            return
        for side, attr, coord in (("1", "off", "Offensive coordinator"), ("0", "def", "Defensive coordinator")):
            who = data.in_use_who(tid, side)
            ctl = self._pb_control(tid, side)
            _b, in_use = data.team_book(self.model.coaches, tid, side)
            _b, hc = data.team_book(self.model.coaches, tid, side, "hc")
            _b, co = data.team_book(self.model.coaches, tid, side, "coord")
            getattr(self, f"lbl_pb_{attr}").configure(text=in_use or "-")
            self.pb_ctl_vars[side].set(ctl or "coord")
            getattr(self, f"lbl_pb_{attr}_ctl").configure(text="" if ctl else "(not in this save - coordinator assumed)")
            for rb in getattr(self, f"rb_pb_{attr}"):
                rb.configure(state="normal" if ctl else "disabled")
            mark = lambda w: "  [in use]" if who == w else ""
            getattr(self, f"lbl_pb_{attr}_detail").configure(
                text=f"Head coach: {hc or '-'}{mark('hc')}   |   {coord}: {co or '-'}{mark('coord')}")

    def on_change_team_playbook(self, side):
        data = self._playbook_data
        tid = self._pb_selected_tid()
        if data is None or not tid:
            messagebox.showinfo("Playbooks", "Load the playbook data and pick a team first.")
            return
        team_rows = [c for c in self.model.coaches if (c.get("TGID") or "").strip() == tid]
        hc_rows = [c for c in team_rows if (c.get("COPS") or "").strip() == "0"]
        field = "CPID" if side == "1" else "CDID"
        if not team_rows or any(field not in c for c in team_rows):
            messagebox.showwarning("Playbooks", f"This save has no {field} column on the coaches.")
            return
        current, _name = data.team_book(self.model.coaches, tid, side)
        label = "offensive" if side == "1" else "defensive"
        dlg = PlaybookPickerDialog(self, f"{team_nickname(tid)}: {label} playbook", data.side_books(side, include_custom=True), current)
        self.wait_window(dlg)
        if not dlg.result:
            return
        bgid, name, _bokl, bord = dlg.result
        if bgid == current:
            return
        if (side, bgid) in data.profile_bgids:
            # A custom playbook: the game stores it on the head coach's row only, and it is played only when the
            # head coach has Playbook Control.
            if not hc_rows:
                messagebox.showwarning("Playbooks", "This team has no head coach row to hold a custom playbook.")
                return
            switched = False
            if self._pb_control(tid, side) != "hc":
                if not self._set_pb_control(tid, side, "0"):
                    messagebox.showinfo("Playbooks", "This save has no team philosophy row for that team, so the playbook can't be switched to the head coach. Nothing was changed.")
                    return
                switched = True
            for c in hc_rows:
                c[field] = bgid
        else:
            for c in team_rows:
                c[field] = bgid
            if side == "1":
                for t in self.model.team:
                    # TEAM.TOPB follows the offensive book's PLAB.BORD (matches the coordinators for 28 of 32 teams)
                    if (t.get("TGID") or "").strip() == tid and "TOPB" in t and bord.isdigit():
                        t["TOPB"] = bord
        self.mark_dirty()
        data.set_usage(self.model.coaches, self._pb_control)
        self._fill_playbook_books()
        self._refresh_pb_team()
        extra = " (and Played by switched to Head coach)" if (side, bgid) in data.profile_bgids and switched else ""
        self.lbl_playbook_status.configure(text=f"{team_nickname(tid)} {label} playbook set to {name}{extra} - Save to File to keep it.")

    def _fill_playbook_books(self):
        data = self._playbook_data
        tree = self.tree_pb_books
        keep = tree.selection()
        for iid in tree.get_children():
            tree.delete(iid)
        shown_side = self.pb_side_var.get()
        self._apply_pb_columns()
        for bokl, name, side, ident, plays, off, dfn in data.books():
            if side in (shown_side, ""):    # a playbook whose side can't be told stays in both lists
                tree.insert("", tk.END, iid=bokl, values=(name, side, ident, plays, off, dfn))
        notes = [] if data.have_game_names else ["no game names - showing IDs only"]
        unnamed = sum(1 for row in data.books() if not data.book_names.get(row[0]))
        if self._playbook_profile:
            notes.append("custom names from " + recent_file_display(self._playbook_profile))
            if self._playbook_flagged:
                notes.append("* = this career's playbook has different plays than the profile's: " + ", ".join(self._playbook_flagged))
        elif unnamed:
            notes.append(f"{unnamed} playbooks have no name (custom ones are named in your profile save - use Profile save...)")
        notes.extend(self._playbook_problems)
        self.lbl_playbook_status.configure(
            text=f"{len(tree.get_children())} {shown_side.lower()} playbooks, {len(data.play_info)} named plays" + "".join(" - " + n for n in notes))
        self._finish_tree_refresh(tree, keep)
        if not tree.selection() and tree.get_children():
            tid = self._pb_selected_tid()
            in_use = data.team_bokl(self.model.coaches, tid, "1" if shown_side == "Offense" else "0") if tid else None
            tree.selection_set(in_use if in_use in tree.get_children() else tree.get_children()[0])
        elif not tree.get_children():
            self._on_playbook_book_selected()
        self._sync_pb_team()

    def _playbook_data_is_stale(self):
        """True (after starting a reload) if the save was loaded again since the
        tab read it - e.g. Reload from File, which doesn't change the file's
        timestamp - so edits are never built on discarded data."""
        if self._playbook_data is not None and self._playbook_stamp != self._playbook_stamp_now():
            self.refresh_playbooks()
            self.lbl_playbook_status.configure(text="The save was reloaded, so the playbook data was refreshed. Choose the playbook and try again.")
            return True
        return False

    def _playbook_target_choices(self, side="Offense"):
        """Where plays are added INTO. The first choice is the playbook of the team chosen on
        this tab (it starts as the team picked when the save was loaded) for the given side,
        followed by that team's other side and the playbook selected in the table.
        Returns ([(label, BOKL)], default BOKL or None)."""
        data = self._playbook_data
        tid = self._pb_selected_tid()
        nick = team_nickname(tid) if tid else ""
        choices = []
        for sd, word in (("1", "Offense"), ("0", "Defense")):
            bokl = data.team_bokl(self.model.coaches, tid, sd) if tid else None
            if bokl and bokl not in [b for _l, b in choices]:
                choices.append((f"{nick} {word.lower()} (in use): {data.book_label(bokl)}", bokl))
        sel = self.tree_pb_books.selection()
        if sel and sel[0] not in [b for _l, b in choices]:
            choices.append((f"Table selection: {data.book_label(sel[0])}", sel[0]))
        default = next((b for _l, b in choices if data.side_of(b) == side), choices[0][1] if choices else None)
        return choices, default

    def on_playbook_add_plays(self, preselect=None, side="Offense"):
        data = self._playbook_data
        if data is None:
            messagebox.showinfo("Playbooks", "Open the tab with a save loaded first.")
            return
        if self._playbook_data_is_stale():
            return
        choices, target = self._playbook_target_choices(side)
        if target is None:
            messagebox.showinfo("Playbooks", "Pick a team (or select a playbook in the table) to add plays to.")
            return
        PlaybookCopyDialog(self, data, target, self._apply_playbook_plan, preselect, choices)

    def on_playbook_add_found(self):
        data, found = self._playbook_data, self.tree_pb_found.selection()
        if data is None or not found:
            messagebox.showinfo("Playbooks", "Search for a play and select it in Find results first.")
            return
        setl, plyl = found[0].split(":")
        hits = self._playbook_hits.get(found[0], [])
        side = self.pb_side_var.get()
        _choices, target = self._playbook_target_choices(side)
        tside = data.side_of(target) if target else ""
        sources = [b for b in hits if b != target and tside and data.side_of(b) == tside]
        if not sources:
            messagebox.showinfo("Playbooks", "No other playbook of the same side contains that play, so there is nothing to copy it from.")
            return
        self.on_playbook_add_plays(preselect=(sources[0], setl, plyl), side=side)

    def _apply_playbook_plan(self, plan):
        """Apply a copy plan to the in-memory playbook tables (validated; raises
        ValueError if refused) and queue them for the next Save to File."""
        data = self._playbook_data
        if self._playbook_data_is_stale():
            raise ValueError("The save was reloaded since this dialog opened, so nothing was added. Close it and try again.")
        n = data.apply_plan(plan)
        self.model.pb_pending = {t: data.tables[t] for t in data.dirty_tables}
        self.mark_dirty()
        self._fill_playbook_books()
        self.lbl_playbook_status.configure(
            text=f"Added {n} row(s) from {data.book_label(plan['src'])} into {data.book_label(plan['tgt'])} - Save to File to keep them.")
        return n

    def _on_playbook_book_selected(self):
        sel = self.tree_pb_books.selection()
        if self._playbook_data is not None and sel:
            name = self._playbook_data.book_label(sel[0])
            self.lbl_pb_cap.configure(
                text=f"Viewing: {name}  -  {self._playbook_data.counted_plays(sel[0])} of {PLAYBOOK_PLAY_CAP} plays (special teams not counted)")
        else:
            self.lbl_pb_cap.configure(text="")
        tree = self.tree_pb_forms
        for iid in tree.get_children():
            tree.delete(iid)
        sel = self.tree_pb_books.selection()
        if not sel or self._playbook_data is None:
            self._fill_playbook_plays()
            return
        bokl = sel[0]
        tree.insert("", tk.END, iid="__all__", values=("(all formations)", "", ""))
        for iid, name, ident, n_sets in self._playbook_data.formations_for(bokl):
            tree.insert("", tk.END, iid=iid, values=(name, ident, n_sets))
        tree.selection_set("__all__")
        self._fill_playbook_plays()

    def _on_playbook_form_selected(self):
        self._fill_playbook_plays()

    def _fill_playbook_plays(self):
        tree = self.tree_pb_plays
        for iid in tree.get_children():
            tree.delete(iid)
        book = self.tree_pb_books.selection()
        if not book or self._playbook_data is None:
            return
        form = self.tree_pb_forms.selection()
        pbfm = None if (not form or form[0] == "__all__") else form[0]
        seen = set()
        for iid, play, setname, pltp, setl, plyl in self._playbook_data.plays_for(book[0], pbfm):
            if iid in seen:
                continue
            seen.add(iid)
            tree.insert("", tk.END, iid=iid, values=(play, setname, pltp, setl, plyl))
        self._finish_tree_refresh(tree)

    def on_playbook_search(self):
        if self._playbook_data is None:
            self.refresh_playbooks()
            if self._playbook_data is None:
                return
        hits = self._playbook_data.search(self.playbook_search_var.get())
        tree = self.tree_pb_found
        for iid in tree.get_children():
            tree.delete(iid)
        self._playbook_hits = {}
        side = self.pb_side_var.get()
        data = self._playbook_data
        mine = []
        for hit in hits:
            books = [b for b in hit[7] if data.side_of(b) in (side, "")]
            if books:                                   # keep only plays in a playbook of the chosen side
                mine.append(hit[:6] + (len(books), books))
        for iid, name, setname, pltp, setl, plyl, n, books in mine[:500]:
            self._playbook_hits[iid] = books
            tree.insert("", tk.END, iid=iid, values=(name, setname, pltp, setl, plyl, n))
        self._finish_tree_refresh(tree)
        shown = len(tree.get_children())
        self.lbl_playbook_hit.configure(
            text=f"{len(mine)} {side.lower()} match(es)" + (f", showing first {shown}" if len(mine) > shown else "")
            if self.playbook_search_var.get().strip() else "")
        self._show_find_results(bool(shown))
        self._update_add_buttons()

    def on_playbook_search_clear(self):
        self.playbook_search_var.set("")
        for iid in self.tree_pb_found.get_children():
            self.tree_pb_found.delete(iid)
        self._playbook_hits = {}
        self.lbl_playbook_hit.configure(text="")
        self._show_find_results(False)
        self._update_add_buttons()

    def _on_playbook_found_selected(self):
        self._update_add_buttons()
        sel = self.tree_pb_found.selection()
        if not sel or self._playbook_data is None:
            return
        books = self._playbook_hits.get(sel[0], [])
        names = [self._playbook_data.book_label(b) for b in books]
        shown = ", ".join(names[:6]) + (f" and {len(names) - 6} more" if len(names) > 6 else "")
        self.lbl_playbook_hit.configure(text=f"In: {shown}" if names else "In no playbook in this save")

    # ---------- Staff Tabs (Trainer / Coach / GM) ----------
    def _build_staff_team_filter(self, parent):
        """Shared 'My Team' / 'All Teams' toggle for the Trainer/Coach/GM
        tabs - these tables have 300+ league-wide rows, which is what made
        those tabs slow to render/scroll. One shared setting across all
        three, remembered across restarts."""
        frm = ttk.Frame(parent)
        frm.pack(side="left", padx=(16, 0))
        ttk.Label(frm, text="Show:").pack(side="left", padx=(0, 4))
        ttk.Radiobutton(
            frm, text="My Team", variable=self.staff_filter_var, value="my_team",
            command=self.on_staff_filter_changed,
        ).pack(side="left")
        ttk.Radiobutton(
            frm, text="All Teams", variable=self.staff_filter_var, value="all_teams",
            command=self.on_staff_filter_changed,
        ).pack(side="left", padx=(6, 0))
        # Layout gets its own row just under the toolbar: on the Coach tab the
        # toolbar is already full width, so anything added to it got cut off.
        lay = ttk.Frame(parent.master)
        lay.pack(fill="x", padx=10, after=parent)
        ttk.Label(lay, text="Layout:").pack(side="left", padx=(0, 4))
        ttk.Radiobutton(
            lay, text="Vertical", variable=self.staff_layout_var, value="vertical",
            command=self.on_staff_layout_changed,
        ).pack(side="left")
        ttk.Radiobutton(
            lay, text="Horizontal", variable=self.staff_layout_var, value="horizontal",
            command=self.on_staff_layout_changed,
        ).pack(side="left", padx=(6, 0))
        ttk.Label(lay, text="(vertical: click a name at the top to select it; double-click a section heading to collapse or expand it)", foreground="gray").pack(side="left", padx=(16, 0))

    def _build_trainer_tab(self):
        root = ttk.Frame(self.notebook)
        self.tab_trainer = root
        self.notebook.add(self.tab_trainer, text="Trainer")

        top = ttk.Frame(root)
        top.pack(fill="x", padx=10, pady=10)
        ttk.Label(top, text="Trainer (trvw.csv)").pack(side="left")
        ttk.Button(top, text="Refresh", command=self.refresh_trainer).pack(side="left", padx=8)
        ttk.Button(top, text="Max Selected Trainer's Stats", command=self.on_max_selected_trainer).pack(side="left", padx=(8, 0))
        self._build_staff_team_filter(top)

        help_text = (
            "Injury Eval (TSIE/TSIM): How accurately the trainer assesses recovery length for a player's injury.\n\n"
            "Rehab (TSRH/TSRM): How long it takes injured players to recover from all types of injuries.\n\n"
            "Fatigue Rec (TSFR/TSFM): How efficiently the trainer assists players in recovering fatigue.\n\n"
            "Each skill is a Cur/Max pair (double-click a cell to edit). In-game 'Level' shows once Cur == Max "
            "('Potential Reached'). Range is 1-5."
        )
        help_frame = ttk.Frame(root)
        help_frame.pack(fill="x", padx=10)
        _lbl_help = tk.Label(help_frame, text=help_text, wraplength=1000, justify="left", fg="gray")
        _lbl_help.pack(fill="x", pady=(6, 0))
        self._help_labels.append(_lbl_help)

        hframe = self._begin_staff_table_area(root)
        self.tree_trainer = ttk.Treeview(hframe, show="headings", height=10)
        self.tree_trainer.pack(fill="both", expand=True)
        xscroll_trainer = ttk.Scrollbar(hframe, orient="horizontal", command=self.tree_trainer.xview)
        xscroll_trainer.pack(fill="x", pady=(0, 6))
        self.tree_trainer.configure(xscrollcommand=xscroll_trainer.set)
        self._finish_staff_table_area(hframe, self.tree_trainer, "trainer")

        # Bottom editor for SKPT
        btm = ttk.Frame(root)
        btm.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Label(btm, text="Selected SKPT:").pack(side="left")
        self.ent_trainer_skpt = ttk.Entry(btm, width=12)
        self.ent_trainer_skpt.pack(side="left", padx=(6, 8))
        ttk.Button(btm, text="Set to Max", command=self.set_trainer_skpt_to_max).pack(side="left", padx=4)
        ttk.Button(btm, text="Apply SKPT", command=self._apply_trainer_skpt).pack(side="left")
        self.tree_trainer.bind("<<TreeviewSelect>>", lambda e: self._on_trainer_select(), add="+")
        self.tree_trainer.bind("<Double-1>", lambda e: self._on_tree_double_click(e, self.tree_trainer))

    def _build_coach_tab(self):
        root = ttk.Frame(self.notebook)
        self.tab_coach = root
        self.notebook.add(self.tab_coach, text="Coach")

        top = ttk.Frame(root)
        top.pack(fill="x", padx=10, pady=10)
        ttk.Label(top, text="Coach (coch.csv)").pack(side="left")
        ttk.Button(top, text="Refresh", command=self.refresh_coach).pack(side="left", padx=8)
        ttk.Button(top, text="Max Selected Coach's Stats", command=self.on_max_selected_coach).pack(side="left", padx=(8, 0))
        ttk.Button(top, text="Personality...", command=self.on_open_coach_personality_editor).pack(side="left", padx=(8, 0))
        ttk.Button(top, text="Team Philosophy...", command=self.on_open_team_philosophy).pack(side="left", padx=(8, 0))

        # Search controls for coach first/last name
        self.coach_search_var = tk.StringVar()
        ttk.Label(top, text="Search (First Last):").pack(side="left", padx=(12, 4))
        self.ent_coach_search = ttk.Entry(top, textvariable=self.coach_search_var, width=20)
        self.ent_coach_search.pack(side="left")
        ttk.Button(top, text="Find", command=lambda: self.refresh_coach()).pack(side="left", padx=(6, 4))
        ttk.Button(top, text="Clear", command=lambda: (self.coach_search_var.set(""), self.refresh_coach())).pack(side="left")
        self._build_staff_team_filter(top)

        # Help text reflects what's actually confirmed in-game (verified via direct testing).
        help_text = (
            "Play Call (SKPC/SKPX), Strategy (SKST/SKSM), Team Chemistry (SKCR/SKCM): current/max pairs, "
            "confirmed - the exact value you write is exactly what shows in-game. Range 1-5.\n\n"
            "Performance is NOT a single stored field - it's computed as MIN(SKPA, SKPF), confirmed across "
            "multiple in-game tests. Set both to 5 to max Performance; 'Max Selected Coach's Stats' does this "
            "automatically. Editing SKPA/SKPF alone won't show a predictable Performance number unless both are "
            "raised together.\n\n"
            "Physical/Intangible/Learning Development (right side, 10 position buckets each): confirmed via "
            "in-game testing. If current > max, the game clamps the displayed current value down to max."
        )
        # place the help below the top controls so it wraps across full width
        # place help in its own frame below the controls so it can span the full width
        help_frame = ttk.Frame(root)
        help_frame.pack(fill="x", padx=10)
        _lbl_help = tk.Label(help_frame, text=help_text, wraplength=1000, justify="left", fg="gray")
        _lbl_help.pack(fill="x", pady=(6, 0))
        self._help_labels.append(_lbl_help)

        hframe = self._begin_staff_table_area(root)
        self.tree_coach = ttk.Treeview(hframe, show="headings", height=10)
        self.tree_coach.pack(fill="both", expand=True)
        xscroll_coach = ttk.Scrollbar(hframe, orient="horizontal", command=self.tree_coach.xview)
        xscroll_coach.pack(fill="x", pady=(0, 6))
        self.tree_coach.configure(xscrollcommand=xscroll_coach.set)
        self._finish_staff_table_area(hframe, self.tree_coach, "coach")

        # Bottom editor for SKPT
        btm = ttk.Frame(root)
        btm.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Label(btm, text="Selected SKPT:").pack(side="left")
        self.ent_coach_skpt = ttk.Entry(btm, width=12)
        self.ent_coach_skpt.pack(side="left", padx=(6, 8))
        ttk.Button(btm, text="Set to Max", command=self.set_coach_skpt_to_max).pack(side="left", padx=4)
        ttk.Button(btm, text="Apply SKPT", command=self._apply_coach_skpt).pack(side="left")
        self.tree_coach.bind("<<TreeviewSelect>>", lambda e: self._on_coach_select(), add="+")
        self.tree_coach.bind("<Double-1>", lambda e: self._on_tree_double_click(e, self.tree_coach))

    def _build_gm_tab(self):
        root = ttk.Frame(self.notebook)
        self.tab_gm = root
        self.notebook.add(self.tab_gm, text="GM")

        top = ttk.Frame(root)
        top.pack(fill="x", padx=10, pady=10)
        ttk.Label(top, text="GM (gmvw.csv)").pack(side="left")
        ttk.Button(top, text="Refresh", command=self.refresh_gm).pack(side="left", padx=8)
        ttk.Button(top, text="Max Selected GM's Stats", command=self.on_max_selected_gm).pack(side="left", padx=(8, 0))
        self._build_staff_team_filter(top)

        help_text = (
            "Trade/Contract, Potential Eval (PE), and Rookie Scouting (RS) - each per position - are all "
            "editable below, double-click a cell, or use 'Max Selected GM's Stats' to max everything at once "
            "for the selected GM. Blank PE/RS cells mean this GM has no data yet. If current > max, the game "
            "clamps the displayed current value down to max."
        )
        help_frame = ttk.Frame(root)
        help_frame.pack(fill="x", padx=10)
        _lbl_help = tk.Label(help_frame, text=help_text, wraplength=1000, justify="left", fg="gray")
        _lbl_help.pack(fill="x", pady=(6, 0))
        self._help_labels.append(_lbl_help)

        hframe = self._begin_staff_table_area(root)
        self.tree_gm = ttk.Treeview(hframe, show="headings", height=10)
        self.tree_gm.pack(fill="both", expand=True)
        xscroll_gm = ttk.Scrollbar(hframe, orient="horizontal", command=self.tree_gm.xview)
        xscroll_gm.pack(fill="x", pady=(0, 6))
        self.tree_gm.configure(xscrollcommand=xscroll_gm.set)
        self._finish_staff_table_area(hframe, self.tree_gm, "gm")

        # Bottom editor for SKPT
        btm = ttk.Frame(root)
        btm.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Label(btm, text="Selected SKPT:").pack(side="left")
        self.ent_gm_skpt = ttk.Entry(btm, width=12)
        self.ent_gm_skpt.pack(side="left", padx=(6, 8))
        ttk.Button(btm, text="Set to Max", command=self.set_gm_skpt_to_max).pack(side="left", padx=4)
        ttk.Button(btm, text="Apply SKPT", command=self._apply_gm_skpt).pack(side="left")
        self.tree_gm.bind("<<TreeviewSelect>>", lambda e: self._on_gm_select(), add="+")
        self.tree_gm.bind("<Double-1>", lambda e: self._on_tree_double_click(e, self.tree_gm))

    # ---------- Load / Save ----------
    def _confirm_discard_if_dirty(self, action_desc):
        """If there are unsaved edits, confirm before an action that would discard
        them (loading a different file, reloading). Returns True to proceed."""
        if not self.dirty:
            return True
        return messagebox.askyesno(
            "Unsaved changes",
            f"You have unsaved changes that will be lost if you {action_desc}. Continue anyway?"
        )

    def _load_db_path(self, db_path, error_title="Load Error"):
        """Shared load logic used by Load Save File, Reload from File, and the
        recent-files list, so all three stay in sync. Runs the slow bridge.js
        export on a background thread so the window stays responsive instead
        of Windows marking it "(Not Responding)" during the load."""
        self.run_in_thread_with_busy(
            f"Loading {recent_file_display(db_path)}...",
            lambda: self.model.load_all_from_db(db_path),
            lambda _result: self._on_load_db_path_success(db_path),
            error_title=error_title,
        )

    def _on_load_db_path_success(self, db_path):
        # Any boosts applied since the last Save are being discarded along
        # with the rest of the in-memory edits - drop their "already
        # boosted" flags too so they don't get silently skipped later.
        self.motivator_pending_boosts = {}

        if not self.model.team_col:
            messagebox.showwarning(
                "Team Column Not Found",
                "Could not detect a team column in the player table (case-sensitive search: TID/TEAM/TMID/TGID)."
            )

        self.lbl_status.configure(
            text=f"Loaded: {recent_file_display(db_path)}  | TeamCol={self.model.team_col or 'N/A'}  | Players={len(self.model.players)}"
        )

        self.refresh_teams()
        self.refresh_picks()
        self.refresh_cap()
        self.refresh_trainer()
        self.refresh_coach()
        self.refresh_gm()
        self.refresh_raw_columns()
        self._select_default_team()

        self.clear_dirty()
        self._refresh_recent_files_ui(save_recent_file(db_path))

    def on_load(self):
        try:
            if not self._confirm_discard_if_dirty("load a different save"):
                return

            db_path = filedialog.askopenfilename(
                title="Select your career save file (USR-DATA)",
                filetypes=[("All files", "*.*")]
            )
            if not db_path:
                return

            self._load_db_path(db_path, error_title="Load Error")

        except Exception as e:
            self.clear_busy()
            messagebox.showerror("Load Error", str(e))

    def on_reload(self):
        try:
            if not self.model.db_path:
                messagebox.showinfo("Nothing loaded", "Load a save file first.")
                return
            if not self._confirm_discard_if_dirty("reload from disk"):
                return
            self._load_db_path(self.model.db_path, error_title="Reload Error")
        except Exception as e:
            self.clear_busy()
            messagebox.showerror("Reload Error", str(e))

    def on_load_recent(self, event=None):
        display = self.recent_files_var.get()
        path = self._recent_display_to_path.get(display)
        if not path:
            return
        if not os.path.isfile(path):
            messagebox.showerror("File not found", f"This save no longer exists:\n{path}")
            self._refresh_recent_files_ui(load_recent_files())
            return
        try:
            if not self._confirm_discard_if_dirty("load a different save"):
                return
            self._load_db_path(path, error_title="Load Error")
        except Exception as e:
            self.clear_busy()
            messagebox.showerror("Load Error", str(e))

    def _refresh_recent_files_ui(self, recents):
        self._recent_display_to_path = {recent_file_display(p): p for p in recents}
        values = list(self._recent_display_to_path.keys())
        self.cmb_recent["values"] = values
        if values:
            self.recent_files_var.set(values[0])

    def on_manage_recent_files(self):
        """Small standalone list (not the main Combobox - ttk.Combobox can't
        show a per-row button inside its own dropdown) where each recent file
        has its own X button to remove it individually."""
        dlg = tk.Toplevel(self)
        dlg.title("Manage Recent Files")
        dlg.geometry("420x260")
        dlg.minsize(360, 200)

        ttk.Label(dlg, text="Click X to remove an entry from the recent files list.").pack(
            anchor="w", padx=10, pady=(10, 6)
        )

        rows_frame = ttk.Frame(dlg)
        rows_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        def rebuild():
            for child in rows_frame.winfo_children():
                child.destroy()
            recents = load_recent_files()
            if not recents:
                ttk.Label(rows_frame, text="No recent files.", foreground="gray").pack(anchor="w", pady=6)
                return
            for path in recents:
                row = ttk.Frame(rows_frame)
                row.pack(fill="x", pady=2)
                ttk.Label(row, text=recent_file_display(path)).pack(side="left")
                ttk.Button(row, text="X", width=3, command=lambda p=path: remove_one(p)).pack(side="right")

        def remove_one(path):
            self._refresh_recent_files_ui(remove_recent_file(path))
            rebuild()

        rebuild()
        ttk.Button(dlg, text="Close", command=dlg.destroy).pack(pady=(0, 10))

    def on_save(self):
        if not self.model.players:
            messagebox.showinfo("Nothing to save", "Load a save file first.")
            return

        self.run_in_thread_with_busy(
            "Saving...",
            self.model.save_to_db,
            self._on_save_success,
            error_title="Save Error",
        )

    def _on_save_success(self, backup_path):
        self._commit_pending_motivator_boosts()
        self.clear_dirty()
        if self._playbook_data is not None:
            # Saving moved the file's timestamp, but what the Playbooks tab holds is exactly what was
            # just written - re-stamp it so the next Add plays isn't refused as "the save was reloaded".
            self._playbook_data.dirty_tables.clear()
            self._playbook_stamp = self._playbook_stamp_now()
        self.lbl_status.configure(
            text=f"Saved: {recent_file_display(self.model.db_path)}  | TeamCol={self.model.team_col or 'N/A'}  | Players={len(self.model.players)}"
        )

        messagebox.showinfo(
            "Saved",
            f"Changes written directly to:\n{self.model.db_path}\n\n"
            f"Backup of the previous version saved to:\n{backup_path}"
        )

    # ---------- Teams / Players ----------
    def refresh_teams(self):
        self.lst_teams.delete(0, tk.END)
        for tid, name in TEAM_NAMES.items():
            self.lst_teams.insert(tk.END, f"{tid}: {name}")

    def _select_default_team(self):
        """First time this save has ever been loaded (no remembered team),
        ask once which team to default to. Every load after that silently
        reselects the same team - switching teams any time from the list on
        the left is always available and updates the remembered choice."""
        remembered = self.ui_prefs.get("per_save", {}).get(self.get_current_save_key(), {}).get("last_team_id")
        if remembered:
            self._activate_team_by_id(remembered)
        else:
            self._prompt_first_team_choice()

    def _activate_team_by_id(self, tid):
        idx = None
        for i in range(self.lst_teams.size()):
            if self.lst_teams.get(i).startswith(str(tid) + ":"):
                idx = i
                break
        if idx is None:
            # Fall back to a real team, never Free Agents/Draft Class/Game
            # Changer Players - those aren't coachable and would make the
            # "My Team" filters on Trainer/Coach/GM come up empty.
            fallback_tid = SIGN_DEST_TEAMS[0][0]
            for i in range(self.lst_teams.size()):
                if self.lst_teams.get(i).startswith(fallback_tid + ":"):
                    idx = i
                    break
        if idx is None and self.lst_teams.size() > 0:
            idx = 0
        if idx is not None:
            self.lst_teams.selection_clear(0, tk.END)
            self.lst_teams.selection_set(idx)
            self.lst_teams.activate(idx)
            self.lst_teams.see(idx)
            self.on_team_select()

    def _prompt_first_team_choice(self):
        p = self._ui_palette
        dlg = tk.Toplevel(self, background=p["bg"] if p else None)
        dlg.title("Choose Your Team")
        dlg.transient(self)
        dlg.grab_set()
        dlg.geometry("420x620")
        dlg.minsize(380, 480)

        ttk.Label(
            dlg,
            text="Pick your team for this save.\nRemembered from now on - you can switch teams anytime from the list on the left.",
            justify="left", wraplength=380, padding=(12, 12, 12, 6),
        ).pack(anchor="w", fill="x")

        lb_kwargs = dict(exportselection=False)
        if p:
            lb_kwargs.update(
                font=(UI_FONT_FAMILY, 10),
                background=p["surface"], foreground=p["text"],
                selectbackground=p["accent"], selectforeground=p["accent_text"],
                highlightthickness=1, highlightbackground=p["border"], highlightcolor=p["accent"],
                relief="flat", borderwidth=1,
            )
        lb = tk.Listbox(dlg, **lb_kwargs)
        lb.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        # Only real coachable teams - not Free Agents/Draft Class/Game Changer
        # Players, which aren't a team you can actually coach.
        for tid, name in SIGN_DEST_TEAMS:
            lb.insert(tk.END, f"{tid}: {name}")

        def choose(event=None):
            sel = lb.curselection()
            if not sel:
                return
            txt = lb.get(sel[0])
            tid = txt.split(":", 1)[0].strip()
            dlg.destroy()
            self._activate_team_by_id(tid)

        lb.bind("<Double-1>", choose)

        btn_frm = ttk.Frame(dlg)
        btn_frm.pack(fill="x", padx=12, pady=(0, 12))
        ttk.Button(
            btn_frm, text="Skip",
            command=lambda: (dlg.destroy(), self._activate_team_by_id(SIGN_DEST_TEAMS[0][0])),
        ).pack(side="left")
        ttk.Button(btn_frm, text="Select", style="Accent.TButton", command=choose).pack(side="right")

    def on_team_select(self, event=None):
        sel = self.lst_teams.curselection()
        if not sel:
            return
        txt = self.lst_teams.get(sel[0])
        tid = txt.split(":", 1)[0].strip()
        self.selected_team_id.set(tid)
        self._pb_team_manual = False   # the Playbooks tab follows the newest team choice
        self.refresh_players_for_team()

        per_save = self.ui_prefs.setdefault("per_save", {})
        per_save.setdefault(self.get_current_save_key(), {})["last_team_id"] = tid
        save_ui_prefs(self.ui_prefs)

        if self.staff_filter_var.get() == "my_team":
            self.refresh_trainer()
            self.refresh_coach()
            self.refresh_gm()

    def on_staff_filter_changed(self):
        self.ui_prefs["staff_filter"] = self.staff_filter_var.get()
        save_ui_prefs(self.ui_prefs)
        self.refresh_trainer()
        self.refresh_coach()
        self.refresh_gm()

    def on_set_team_bonus_min(self):
        if not self.model.players:
            messagebox.showinfo("Load first", "Load play.csv first.")
            return

        tid = self.selected_team_id.get().strip()
        if not tid:
            messagebox.showinfo("No team", "Select a team first.")
            return

        team_name = TEAM_NAMES.get(tid, tid)
        ok = messagebox.askyesno(
            "Confirm team bonus reset",
            f"Add each year's bonus into that year's salary, then set every bonus to 0, "
            f"for every player on {team_name}?\n\n"
            "Each year's cap hit stays the same. Bonus is really guaranteed money - "
            "it's what causes a cap penalty when a player is cut or traded - so this "
            "removes that penalty without changing what the player costs per year."
        )
        if not ok:
            return

        headers = set(self.model.player_headers or [])
        team_col = self.model.team_col
        if not team_col:
            messagebox.showwarning("No team column", "Team column not detected in play.csv.")
            return

        updated_players = 0
        overflow_players = 0
        for row in self.model.players:
            if (row.get(team_col, "") or "").strip() != tid:
                continue
            changed, overflowed = fold_bonuses_into_salary(row, headers)
            if changed:
                updated_players += 1
            if overflowed:
                overflow_players += 1

        if updated_players:
            self.mark_dirty()
        self.refresh_players_for_team()
        msg = (
            f"Folded bonuses into salary for {updated_players} player(s) on {team_name}. "
            "Per-year cap hits are unchanged."
        )
        if overflow_players:
            msg += (
                f"\n\n{overflow_players} player(s) had a year whose salary + bonus is more than the "
                "salary field can hold - their salary was filled to its maximum and the "
                "remainder was left as bonus for that year."
            )
        messagebox.showinfo("Team bonus updated", msg)

    def on_max_team_staff_skpt(self):
        """Max SKPT and every confirmed skill (Trainer/Coach/GM) for every staff
        member on the selected team - the team-wide version of the per-row
        'Max Selected X's Stats' buttons on each staff tab."""
        tid = self.selected_team_id.get().strip()
        if not tid:
            messagebox.showinfo("No team", "Select a team first.")
            return

        team_name = TEAM_NAMES.get(tid, tid)
        ok = messagebox.askyesno(
            "Confirm team staff max",
            f"Max SKPT and all confirmed skills for every trainer, coach, and GM on {team_name}?"
        )
        if not ok:
            return

        def apply_staff_max(rows, headers, field_names):
            headers = set(headers or [])
            if "TGID" not in headers or "SKPT" not in headers:
                return 0
            count = 0
            for row in rows:
                if (row.get("TGID", "") or "").strip() != tid:
                    continue
                row["SKPT"] = str(STAFF_SKPT_MAX_VALUE)
                for f in field_names:
                    if f in headers:
                        _, hi = STAFF_NUMERIC_FIELDS.get(f, (0, 0))
                        row[f] = str(hi)
                count += 1
            return count

        trainer_count = apply_staff_max(self.model.trainers, self.model.trainer_headers, TRAINER_MAXABLE_SKILL_FIELDS)
        coach_count = apply_staff_max(self.model.coaches, self.model.coach_headers, COACH_MAXABLE_SKILL_FIELDS)
        gm_count = apply_staff_max(self.model.gms, self.model.gm_headers, GM_MAXABLE_SKILL_FIELDS)

        # GM Potential Evaluation + Rookie Scouting live in a separate table (GMSK)
        # keyed by row index, so they need their own pass rather than a simple
        # field-name loop like the other staff types above.
        for idx, row in enumerate(self.model.gms):
            if (row.get("TGID", "") or "").strip() == tid:
                self._max_out_gm_potential_eval(idx)

        # Same story for Coach Development, which lives in CSKL.
        for idx, row in enumerate(self.model.coaches):
            if (row.get("TGID", "") or "").strip() == tid:
                self._max_out_coach_development(idx)

        self.refresh_trainer()
        self.refresh_coach()
        self.refresh_gm()

        messagebox.showinfo(
            "Team staff updated",
            f"{team_name}\n\n"
            f"Trainers maxed (SKPT + skills): {trainer_count}\n"
            f"Coaches maxed (SKPT + skills): {coach_count}\n"
            f"GMs maxed (SKPT + skills): {gm_count}"
        )

    def _on_player_search_changed(self, *_args):
        """Live search: debounced so a full redraw doesn't happen on every
        single keystroke while typing fast."""
        if self._player_search_after_id is not None:
            self.after_cancel(self._player_search_after_id)
        self._player_search_after_id = self.after(150, self._run_player_search)

    def _run_player_search(self):
        self._player_search_after_id = None
        query = (self.player_search_var.get() or "").strip().lower()

        if not query:
            self.lbl_players_header.configure(text="Players on Team (play.csv)")
            self.refresh_players_for_team()
            return

        if not self.model.players:
            return

        parts = query.split()

        def match(r):
            fn = (r.get(PLAYER_FIRST_NAME_CODE, "") or "").lower()
            ln = (r.get(PLAYER_LAST_NAME_CODE, "") or "").lower()
            if len(parts) == 2:
                return parts[0] in fn and parts[1] in ln
            return query in fn or query in ln

        matches = [(i, r) for i, r in enumerate(self.model.players) if match(r)]
        matches = sorted(matches, key=lambda item: (
            (item[1].get(self.model.team_col, "") or "") if self.model.team_col else "",
            item[1].get(PLAYER_FIRST_NAME_CODE, "").strip(),
            item[1].get(PLAYER_LAST_NAME_CODE, "").strip()
        ))

        self.lst_players.delete(0, tk.END)
        self.selected_player_index = None
        self.clear_stats_view()
        self._player_index_map = [i for i, _ in matches]

        for i, r in matches:
            pos = self.model.player_pos(r)
            name = self.model.player_name(r)
            tid = self.model.player_team_id(r)
            team_name = TEAM_NAMES.get(tid, tid) if tid else "?"
            self.lst_players.insert(tk.END, f"{pos}  {name}   [{team_name}]")

        self.lbl_players_header.configure(text=f"Search Results ({len(matches)})")

        if self.lst_players.size() > 0:
            self.lst_players.selection_set(0)
            self.lst_players.activate(0)
            self.on_player_select()

    def on_clear_player_search(self):
        if self._player_search_after_id is not None:
            self.after_cancel(self._player_search_after_id)
            self._player_search_after_id = None
        self.player_search_var.set("")  # triggers _on_player_search_changed -> reverts to team view
        self.refresh_players_for_team()

    def _on_player_sort_changed(self, _event=None):
        self.ui_prefs["player_sort"] = self.player_sort_var.get()
        save_ui_prefs(self.ui_prefs)
        # Only the team view is sortable this way; search results keep their own order.
        if not (self.player_search_var.get() or "").strip():
            self.refresh_players_for_team()

    def _player_list_sort_key(self, item):
        """item = (model_idx, row). Every option falls back to the same
        position/name order, so ties stay predictable."""
        r = item[1]
        pos = POSITION_ORDER.get((r.get(PLAYER_POS_CODE, "") or "").strip(), 999)
        first = r.get(PLAYER_FIRST_NAME_CODE, "").strip()
        last = r.get(PLAYER_LAST_NAME_CODE, "").strip()
        mode = self.player_sort_var.get()
        if mode == "Name":
            return (last.lower(), first.lower(), pos)
        if mode == "OVR (high first)":
            return (-(safe_int(r.get("POVR", "")) or 0), pos, first, last)
        if mode == "Age (oldest first)":
            return (-(safe_int(r.get(AGE_COL, "")) or 0), pos, first, last)
        if mode == "Salary (highest first)":
            cap = (safe_int(r.get("PSA0", "")) or 0) + (safe_int(r.get("PSB0", "")) or 0)
            return (-cap, pos, first, last)
        return (pos, first, last)

    def refresh_players_for_team(self, preselect_model_idx=None):
        """preselect_model_idx: keep this player (by index into
        self.model.players, not listbox position) selected across the
        rebuild instead of always jumping back to the first row - matters
        for anything that edits the currently-selected player and then
        refreshes (e.g. the contract dialog), since otherwise the visible
        selection silently jumps to a different player and the edit looks
        like it didn't take effect."""
        if preselect_model_idx is None:
            preselect_model_idx = self.selected_player_index

        self.lbl_players_header.configure(text="Players on Team (play.csv)")
        self.lst_players.delete(0, tk.END)
        self.selected_player_index = None
        self.clear_stats_view()

        tid = self.selected_team_id.get()
        if not tid or not self.model.players:
            return

        if self.model.team_col:
            filtered = [(i, r) for i, r in enumerate(self.model.players)
                        if (r.get(self.model.team_col, "") or "").strip() == tid]
        else:
            filtered = list(enumerate(self.model.players))

        # Default: position (custom order), then first name, then last name;
        # the "Sort team list by" dropdown picks another order.
        filtered = sorted(filtered, key=self._player_list_sort_key)

        self._player_index_map = [i for i, _ in filtered]

        for i, r in filtered:
            pos = self.model.player_pos(r)
            name = self.model.player_name(r)
            age = (r.get(AGE_COL, "") or "").strip()
            ovr = (r.get("POVR", "") or "").strip()

            # Always read PSA0/PSB0 (Year 0) here - that's exactly what the
            # first row of the Edit Contract dialog writes, so an edit there
            # always shows up. (An earlier version tried to compute the
            # player's true "current" contract year from PCON-PCYL for
            # players signed mid-contract, but that meant editing Year 0 in
            # the dialog silently didn't move this number for anyone not
            # freshly signed - not obvious/predictable enough to be worth it.)
            years_left = safe_int(r.get("PCYL", ""))
            cap_summary = ""
            if years_left is not None and years_left > 0:
                cap_units = (safe_int(r.get("PSA0", "")) or 0) + (safe_int(r.get("PSB0", "")) or 0)
                cap_summary = f"{years_left}y {format_cap_dollars(cap_units)}/yr"

            self.lst_players.insert(
                tk.END,
                f"{pos}  {name}   OVR:{ovr or '-'}  Age:{age or '-'}  {cap_summary}".rstrip()
            )

        if self.lst_players.size() > 0:
            lb_idx = 0
            if preselect_model_idx is not None and preselect_model_idx in self._player_index_map:
                lb_idx = self._player_index_map.index(preselect_model_idx)
            self.lst_players.selection_set(lb_idx)
            self.lst_players.activate(lb_idx)
            self.lst_players.see(lb_idx)
            self.on_player_select()

    def on_player_select(self, event=None):
        sel = self.lst_players.curselection()
        if not sel:
            return
        lb_idx = sel[0]
        real_idx = self._player_index_map[lb_idx]
        self.selected_player_index = real_idx
        self.refresh_stats_for_player()

        r = self.model.players[real_idx]

        # Prefill Age/Years
        self.ent_age.delete(0, tk.END)
        self.ent_age.insert(0, (r.get(AGE_COL, "") or "").strip())
        self.ent_years.delete(0, tk.END)
        self.ent_years.insert(0, (r.get(YEARS_COL, "") or "").strip())

        # Prefill Name Editor
        self.ent_first.delete(0, tk.END)
        self.ent_first.insert(0, (r.get(PLAYER_FIRST_NAME_CODE, "") or "").strip())
        self.ent_last.delete(0, tk.END)
        self.ent_last.insert(0, (r.get(PLAYER_LAST_NAME_CODE, "") or "").strip())

        # Prefill raw column value
        self.on_raw_column_changed()

        self.lbl_player_editor_header.configure(text=f"Editing: {self.model.player_name(r)}")
        self._refresh_current_player_portrait()
        # Only auto-switch tabs for a real user click on the list (event is
        # set by the <<ListboxSelect>> binding) - not for the programmatic
        # preselection that happens on save load / team switch / list refresh.
        if event is not None:
            self.notebook.select(self.tab_player_editor)

    # ---------- Name Editor ----------
    def on_apply_name(self):
        if self.selected_player_index is None:
            messagebox.showinfo("No player", "Select a player first.")
            return

        r = self.model.players[self.selected_player_index]
        headers_set = set(self.model.player_headers)

        fn_raw = self.ent_first.get()
        ln_raw = self.ent_last.get()

        fn = sanitize_name(fn_raw, max_len=15)
        ln = sanitize_name(ln_raw, max_len=15)

        if fn != fn_raw.strip() or ln != ln_raw.strip():
            messagebox.showinfo(
                "Name sanitized",
                "Your name was sanitized to reduce HC09 crash risk.\n\n"
                f"First: '{fn_raw.strip()}' -> '{fn}'\n"
                f"Last:  '{ln_raw.strip()}' -> '{ln}'"
            )

        if PLAYER_FIRST_NAME_CODE in headers_set:
            r[PLAYER_FIRST_NAME_CODE] = fn
        else:
            messagebox.showwarning("Missing column", f"{PLAYER_FIRST_NAME_CODE} not found in play.csv headers.")

        if PLAYER_LAST_NAME_CODE in headers_set:
            r[PLAYER_LAST_NAME_CODE] = ln
        else:
            messagebox.showwarning("Missing column", f"{PLAYER_LAST_NAME_CODE} not found in play.csv headers.")

        self.refresh_players_for_team()

    # ---------- Stats ----------
    def clear_stats_view(self):
        for iid in self.tree_stats.get_children():
            self.tree_stats.delete(iid)
        self.selected_stat_key = None
        self._set_desc("")
        self.ent_new_cur.delete(0, tk.END)
        self.ent_new_max.delete(0, tk.END)

    def refresh_stats_for_player(self):
        self.clear_stats_view()
        if self.selected_player_index is None:
            return
        r = self.model.players[self.selected_player_index]
        headers_set = set(self.model.player_headers)

        for base_key in STAT_META.keys():
            cur_col = base_key if base_key in headers_set else None
            max_col = self.model.max_map.get(base_key)
            if not cur_col and not max_col:
                continue

            nice, _ = STAT_META.get(base_key, (base_key, ""))
            cur_val = (r.get(cur_col, "") if cur_col else "")
            max_val = (r.get(max_col, "") if max_col else "")

            self.tree_stats.insert(
                "",
                tk.END,
                iid=base_key,
                values=(nice, cur_col or "N/A", cur_val or "-", max_col or "N/A", max_val or "-")
            )
        self._finish_tree_refresh(self.tree_stats)

    def on_stat_select(self, event=None):
        sel = self.tree_stats.selection()
        if not sel:
            return
        base_key = sel[0]
        self.selected_stat_key = base_key

        nice, desc = STAT_META.get(base_key, (base_key, ""))
        self._set_desc(f"{nice} ({base_key})\n\n{desc}")

        r = self.model.players[self.selected_player_index]
        headers_set = set(self.model.player_headers)

        cur_col = base_key if base_key in headers_set else None
        max_col = self.model.max_map.get(base_key)

        self.ent_new_cur.delete(0, tk.END)
        self.ent_new_max.delete(0, tk.END)
        if cur_col:
            self.ent_new_cur.insert(0, (r.get(cur_col, "") or "").strip())
        if max_col:
            self.ent_new_max.insert(0, (r.get(max_col, "") or "").strip())

    def _set_desc(self, text):
        self.txt_desc.configure(state="normal")
        self.txt_desc.delete("1.0", tk.END)
        self.txt_desc.insert("1.0", text)
        self.txt_desc.configure(state="disabled")

    def _enforce_current_le_max(self, row, cur_col, max_col):
        if not cur_col or not max_col:
            return
        c = safe_int(row.get(cur_col, ""))
        m = safe_int(row.get(max_col, ""))
        if c is None or m is None:
            return
        if c > m:
            row[cur_col] = str(m)

    def on_apply_stat(self):
        if self.selected_player_index is None or not self.selected_stat_key:
            return
        base_key = self.selected_stat_key
        r = self.model.players[self.selected_player_index]
        headers_set = set(self.model.player_headers)

        cur_col = base_key if base_key in headers_set else None
        max_col = self.model.max_map.get(base_key)

        new_cur = self.ent_new_cur.get().strip()
        new_max = self.ent_new_max.get().strip()

        try:
            if new_cur != "" and cur_col:
                r[cur_col] = str(clamp_stat(int(new_cur)))
            if new_max != "" and max_col:
                r[max_col] = str(clamp_stat(int(new_max)))

            self._enforce_current_le_max(r, cur_col, max_col)
            self.refresh_stats_for_player()
            self.tree_stats.selection_set(base_key)
            self.tree_stats.see(base_key)
        except Exception as e:
            messagebox.showerror("Apply Error", str(e))

    def on_apply_both(self):
        if self.selected_player_index is None or not self.selected_stat_key:
            return
        base_key = self.selected_stat_key
        r = self.model.players[self.selected_player_index]
        headers_set = set(self.model.player_headers)

        cur_col = base_key if base_key in headers_set else None
        max_col = self.model.max_map.get(base_key)

        new_cur = self.ent_new_cur.get().strip()
        new_max = self.ent_new_max.get().strip()

        try:
            if new_max != "" and max_col:
                r[max_col] = str(clamp_stat(int(new_max)))
            if new_cur != "" and cur_col:
                r[cur_col] = str(clamp_stat(int(new_cur)))

            self._enforce_current_le_max(r, cur_col, max_col)
            self.refresh_stats_for_player()
            self.tree_stats.selection_set(base_key)
            self.tree_stats.see(base_key)
        except Exception as e:
            messagebox.showerror("Apply Error", str(e))

    # ---------- Motivator Boost ----------
    def _commit_pending_motivator_boosts(self):
        """Called after a successful Save: fold this session's pending boosts
        into the persisted history so they now count as 'already boosted'."""
        if not self.motivator_pending_boosts:
            return
        boosts = self.motivator_state.setdefault("boosts", {})
        for save_key, per_player in self.motivator_pending_boosts.items():
            save_boosts = boosts.setdefault(save_key, {})
            for pgid, entries in per_player.items():
                save_boosts.setdefault(pgid, []).extend(entries)
        self.motivator_pending_boosts = {}
        save_motivator_state(self.motivator_state)

    def get_current_save_key(self):
        """Key used to namespace boost history per save (folder name, since
        every save file is literally named USR-DATA)."""
        return recent_file_display(self.model.db_path) if self.model.db_path else "unknown"

    def get_player_boost_history(self, pgid):
        save_key = self.get_current_save_key()
        saved = self.motivator_state.get("boosts", {}).get(save_key, {}).get(str(pgid), [])
        pending = self.motivator_pending_boosts.get(save_key, {}).get(str(pgid), [])
        return saved + pending

    def on_open_motivator_dialog(self):
        if self.selected_player_index is None:
            messagebox.showinfo("No player", "Select a player first.")
            return

        r = self.model.players[self.selected_player_index]
        pgid = (r.get("PGID", "") or "").strip()
        player_label = self.model.player_name(r) if hasattr(self.model, "player_name") else pgid
        history = self.get_player_boost_history(pgid)

        dlg = tk.Toplevel(self)
        dlg.title("Apply Motivator Boost")
        dlg.transient(self)
        dlg.grab_set()

        frm = ttk.Frame(dlg, padding=12)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text=f"Player: {player_label}", font=("", 10, "bold")).pack(anchor="w")

        if history:
            total = sum(h.get("amount", 0) for h in history)
            last = history[-1]
            hist_text = (
                f"Already boosted {len(history)} time(s) on this save "
                f"(total +{total}, last +{last.get('amount')})."
            )
        else:
            hist_text = "Not boosted yet on this save."
        ttk.Label(frm, text=hist_text, foreground="#8a5a00", wraplength=340, justify="left").pack(anchor="w", pady=(4, 10))

        ttk.Label(frm, text="Mode:").pack(anchor="w")
        mode_var = tk.StringVar(value=self.motivator_state.get("last_mode", MOTIVATOR_MODE_RANDOM))
        cmb_mode = ttk.Combobox(
            frm, state="readonly", width=22, textvariable=mode_var,
            values=[MOTIVATOR_MODE_RANDOM, MOTIVATOR_MODE_CUSTOM]
        )
        cmb_mode.pack(anchor="w", pady=(2, 8))

        custom_frm = ttk.Frame(frm)
        custom_frm.pack(anchor="w", fill="x")
        ttk.Label(custom_frm, text="Custom amount (added to every potential stat):").pack(side="left")
        ent_custom = ttk.Entry(custom_frm, width=6)
        ent_custom.insert(0, str(self.motivator_state.get("last_custom_value", "10")))
        ent_custom.pack(side="left", padx=(6, 0))

        def _sync_custom_state(*_):
            ent_custom.configure(state="normal" if mode_var.get() == MOTIVATOR_MODE_CUSTOM else "disabled")
        mode_var.trace_add("write", _sync_custom_state)
        _sync_custom_state()

        include_var = tk.BooleanVar(value=bool(self.motivator_state.get("include_excluded_stats", False)))
        ttk.Checkbutton(
            frm, variable=include_var,
            text="Also include Acceleration & Stamina caps (real perk never boosts these)"
        ).pack(anchor="w", pady=(0, 8))

        ttk.Label(
            frm,
            text="By default applies to every potential/max stat except Acceleration\n"
                 "and Stamina caps (confirmed never boosted by the real perk).\n"
                 "Current stats are left untouched, same as the real perk.",
            justify="left", foreground="#555"
        ).pack(anchor="w", pady=(0, 10))

        btn_frm = ttk.Frame(frm)
        btn_frm.pack(anchor="e", fill="x")

        def do_apply():
            mode = mode_var.get()
            if mode == MOTIVATOR_MODE_CUSTOM:
                try:
                    amount = int(ent_custom.get().strip())
                except Exception:
                    messagebox.showerror("Invalid amount", "Custom amount must be a whole number.")
                    return
            else:
                amount = random.randint(MOTIVATOR_RANDOM_MIN, MOTIVATOR_RANDOM_MAX)

            include_excluded = include_var.get()
            self._apply_motivator_boost(pgid, amount, include_excluded)

            self.motivator_state["last_mode"] = mode
            if mode == MOTIVATOR_MODE_CUSTOM:
                self.motivator_state["last_custom_value"] = str(amount)
            self.motivator_state["include_excluded_stats"] = include_excluded
            save_motivator_state(self.motivator_state)

            dlg.destroy()
            note = "" if include_excluded else " (except accel/stamina caps)"
            messagebox.showinfo("Motivator Boost applied", f"{player_label}: +{amount} to all potential stats{note}.")

        ttk.Button(btn_frm, text="Cancel", command=dlg.destroy).pack(side="right")
        ttk.Button(btn_frm, text="Apply", command=do_apply).pack(side="right", padx=(0, 8))

    def _apply_motivator_boost(self, pgid, amount, include_excluded=False):
        self._apply_motivator_boost_to_row(self.model.players[self.selected_player_index], amount, include_excluded)
        self.mark_dirty()
        self.refresh_stats_for_player()

    def _apply_motivator_boost_to_row(self, r, amount, include_excluded=False):
        """Mutates one player row + records boost history. No UI refresh here
        so this can be called in a loop for team-wide application."""
        for base_key, max_col in self.model.max_map.items():
            if base_key in MOTIVATOR_EXCLUDED_BASE_KEYS and not include_excluded:
                continue
            cur_val = safe_int(r.get(max_col, "")) or 0
            r[max_col] = str(clamp_stat(cur_val + amount))

        pgid = (r.get("PGID", "") or "").strip()
        save_key = self.get_current_save_key()
        save_pending = self.motivator_pending_boosts.setdefault(save_key, {})
        history = save_pending.setdefault(str(pgid), [])
        history.append({"amount": amount, "included_accel_stamina": include_excluded})

    def on_open_team_motivator_dialog(self):
        if not self.model.players:
            messagebox.showinfo("Load first", "Load play.csv first.")
            return
        tid = self.selected_team_id.get().strip()
        if not tid:
            messagebox.showinfo("No team", "Select a team first.")
            return
        team_col = self.model.team_col
        if not team_col:
            messagebox.showwarning("No team column", "Team column not detected in play.csv.")
            return

        team_name = TEAM_NAMES.get(tid, tid)
        team_rows = [r for r in self.model.players if (r.get(team_col, "") or "").strip() == tid]
        if not team_rows:
            messagebox.showinfo("No players", f"No players found on {team_name}.")
            return

        already_boosted = sum(1 for r in team_rows if self.get_player_boost_history((r.get("PGID", "") or "").strip()))

        dlg = tk.Toplevel(self)
        dlg.title("Apply Motivator Boost to Team")
        dlg.transient(self)
        dlg.grab_set()

        frm = ttk.Frame(dlg, padding=12)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text=f"Team: {team_name} ({len(team_rows)} players)", font=("", 10, "bold")).pack(anchor="w")
        if already_boosted:
            ttk.Label(
                frm, foreground="#8a5a00", wraplength=360, justify="left",
                text=f"{already_boosted} of {len(team_rows)} player(s) on this team already have a boost recorded on this save."
            ).pack(anchor="w", pady=(4, 10))

        ttk.Label(frm, text="Mode:").pack(anchor="w")
        mode_var = tk.StringVar(value=self.motivator_state.get("last_mode", MOTIVATOR_MODE_RANDOM))
        cmb_mode = ttk.Combobox(
            frm, state="readonly", width=22, textvariable=mode_var,
            values=[MOTIVATOR_MODE_RANDOM, MOTIVATOR_MODE_CUSTOM]
        )
        cmb_mode.pack(anchor="w", pady=(2, 8))

        custom_frm = ttk.Frame(frm)
        custom_frm.pack(anchor="w", fill="x")
        ttk.Label(custom_frm, text="Custom amount (same for every player):").pack(side="left")
        ent_custom = ttk.Entry(custom_frm, width=6)
        ent_custom.insert(0, str(self.motivator_state.get("last_custom_value", "10")))
        ent_custom.pack(side="left", padx=(6, 0))

        def _sync_custom_state(*_):
            ent_custom.configure(state="normal" if mode_var.get() == MOTIVATOR_MODE_CUSTOM else "disabled")
        mode_var.trace_add("write", _sync_custom_state)
        _sync_custom_state()

        note_text = "Random mode rolls a fresh 5-9 independently for each player (matches the real perk - it's not the same amount for everyone)."
        ttk.Label(frm, text=note_text, wraplength=360, justify="left", foreground="#555").pack(anchor="w", pady=(0, 8))

        include_var = tk.BooleanVar(value=bool(self.motivator_state.get("include_excluded_stats", False)))
        ttk.Checkbutton(
            frm, variable=include_var,
            text="Also include Acceleration & Stamina caps (real perk never boosts these)"
        ).pack(anchor="w", pady=(0, 4))

        skip_var = tk.BooleanVar(value=bool(self.motivator_state.get("team_skip_already_boosted", True)))
        ttk.Checkbutton(
            frm, variable=skip_var,
            text="Skip players who already have a boost recorded on this save"
        ).pack(anchor="w", pady=(0, 10))

        btn_frm = ttk.Frame(frm)
        btn_frm.pack(anchor="e", fill="x")

        def do_apply():
            mode = mode_var.get()
            fixed_amount = None
            if mode == MOTIVATOR_MODE_CUSTOM:
                try:
                    fixed_amount = int(ent_custom.get().strip())
                except Exception:
                    messagebox.showerror("Invalid amount", "Custom amount must be a whole number.")
                    return

            include_excluded = include_var.get()
            skip_already = skip_var.get()

            boosted = 0
            skipped = 0
            for r in team_rows:
                pgid = (r.get("PGID", "") or "").strip()
                if skip_already and self.get_player_boost_history(pgid):
                    skipped += 1
                    continue
                amount = fixed_amount if fixed_amount is not None else random.randint(MOTIVATOR_RANDOM_MIN, MOTIVATOR_RANDOM_MAX)
                self._apply_motivator_boost_to_row(r, amount, include_excluded)
                boosted += 1

            self.motivator_state["last_mode"] = mode
            if fixed_amount is not None:
                self.motivator_state["last_custom_value"] = str(fixed_amount)
            self.motivator_state["include_excluded_stats"] = include_excluded
            self.motivator_state["team_skip_already_boosted"] = skip_already
            save_motivator_state(self.motivator_state)

            self.mark_dirty()
            self.refresh_players_for_team()
            self.refresh_stats_for_player()

            dlg.destroy()
            messagebox.showinfo(
                "Team Motivator Boost applied",
                f"{team_name}: boosted {boosted} player(s), skipped {skipped} already-boosted."
            )

        ttk.Button(btn_frm, text="Cancel", command=dlg.destroy).pack(side="right")
        ttk.Button(btn_frm, text="Apply to Team", command=do_apply).pack(side="right", padx=(0, 8))

    def on_apply_age_years(self):
        if self.selected_player_index is None:
            return
        r = self.model.players[self.selected_player_index]
        a = self.ent_age.get().strip()
        y = self.ent_years.get().strip()
        try:
            if AGE_COL in set(self.model.player_headers) and a != "":
                r[AGE_COL] = str(max(0, min(99, int(a))))
            if YEARS_COL in set(self.model.player_headers) and y != "":
                r[YEARS_COL] = str(max(0, min(30, int(y))))
            self.refresh_players_for_team()
        except Exception as e:
            messagebox.showerror("Apply Error", str(e))

    # ---------- Contract Editor ----------
    def _parse_contract_number(self, raw):
        try:
            return int(raw)
        except ValueError:
            return int(float(raw))

    def on_open_contract_editor(self):
        if self.selected_player_index is None:
            messagebox.showinfo("No player", "Select a player first.")
            return
        PlayerContractDialog(self, self.model, self.selected_player_index)

    def on_open_player_personality_editor(self):
        if self.selected_player_index is None:
            messagebox.showinfo("No player", "Select a player first.")
            return
        row = self.model.players[self.selected_player_index]
        name = self.model.player_name(row) if hasattr(self.model, "player_name") else ""
        PersonalityDialog(
            self, self.model.players, self.selected_player_index,
            f"Player: {name}", refresh_callback=self.refresh_stats_for_player,
            subject_kind="player",
        )

    def on_open_player_type_fit(self):
        if not self.model.players:
            messagebox.showinfo("No data", "Load a save first.")
            return
        if not PHILOSOPHY_WEIGHTS and not self._extract_philosophy_weights_from_game():
            return
        PlayerTypeFitDialog(self, self.model)

    def _find_boot_ast(self, feature="Player Type Fit", what="team philosophies and their weights"):
        saved = self.ui_prefs.get("boot_ast_path") or ""
        if saved and os.path.isfile(saved):
            return saved
        fe2ig = self.get_game_ast_path()
        if fe2ig:
            sibling = os.path.join(os.path.dirname(fe2ig), BOOT_AST_FILENAME)
            if os.path.isfile(sibling):
                return sibling
        messagebox.showinfo(
            f"{feature} needs game data",
            f"This feature reads the game's {what} straight from your own game files.\n\n"
            f"Next, locate {BOOT_AST_FILENAME} (inside the game's PS3_GAME/USRDIR folder). "
            "This is only needed once.",
        )
        path = filedialog.askopenfilename(
            title=f"Locate {BOOT_AST_FILENAME} (inside the game's PS3_GAME/USRDIR folder)",
            filetypes=[("AST archive", BOOT_AST_FILENAME), ("All files", "*.*")],
        )
        return path or ""

    def _extract_philosophy_weights_from_game(self):
        """Pull the PEAW / PEIW tables out of the user's own qkl_boot.ast into a local cache and load them.
        Returns True if the philosophy weights are now available."""
        global PHILOSOPHY_WEIGHTS
        boot_ast = self._find_boot_ast()
        if not boot_ast:
            return False
        self.config(cursor="watch")
        self.update_idletasks()
        try:
            self.model.run_bridge(["shipped-table-export", "--ast", boot_ast, "--tables", ",".join(PHILOSOPHY_WEIGHT_TABLES),
                                   "--out-dir", PHILOSOPHY_CACHE_DIR])
        except Exception as e:
            messagebox.showerror("Couldn't read game data", str(e))
            return False
        finally:
            self.config(cursor="")
        PHILOSOPHY_WEIGHTS = load_philosophy_weights()
        if not PHILOSOPHY_WEIGHTS:
            messagebox.showerror(
                "Couldn't read game data",
                f"Extracted the tables from {os.path.basename(boot_ast)} but they held no usable philosophy weights. "
                "Make sure this is the NFL Head Coach 09 qkl_boot.ast.",
            )
            return False
        self.ui_prefs["boot_ast_path"] = boot_ast
        save_ui_prefs(self.ui_prefs)
        return True

    def on_open_assign_portrait_dialog(self):
        if self.selected_player_index is None:
            messagebox.showinfo("No player", "Select a player first.")
            return
        row = self.model.players[self.selected_player_index]
        name = self.model.player_name(row) if hasattr(self.model, "player_name") else ""
        AssignPortraitDialog(
            self, row, name, refresh_callback=self._refresh_current_player_portrait,
        )

    # ---------- Trades ----------
    def on_open_swap_trade(self):
        if not self.model.players:
            messagebox.showinfo("Load first", "Load play.csv first.")
            return
        SwapTradeDialog(self, self.model)

    def on_open_sign_free_agent(self):
        if not self.model.players:
            messagebox.showinfo("Load first", "Load play.csv first.")
            return
        SignFreeAgentDialog(self, self.model)

    # ---------- Picks ----------
    def refresh_picks(self):
        for iid in self.tree_picks.get_children():
            self.tree_picks.delete(iid)
        if not self.model.picks:
            self._update_pick_selection_label()
            return

        query = (self.pick_filter_var.get() or "").strip().lower() if hasattr(self, "pick_filter_var") else ""

        # Sort by team, then by year offset (0, 1, 3...), then by round/pick
        sorted_picks = sorted(
            enumerate(self.model.picks),
            key=lambda item: (
                int((item[1].get(DRAFT_PICK_ID, "") or "").strip() or "99999"),
                y if (y := safe_int(item[1].get(DRAFT_PICK_YEAR, ""))) is not None else 999,
                safe_int(item[1].get(DRAFT_PICK_NUM, "")) or 0,
            )
        )

        # Sequential display mapping for year offsets: 0->1, 1->2, 3->3, etc.
        # NOT real calendar years - cINF.SEYR was tried for that (see
        # CSVModel.get_current_season_year / CINF_SEASON_YEAR_OFFSET) and
        # briefly shipped, but DISPROVEN: two different saves independently
        # confirmed as showing 2008 and 2009 in-game both have SEYR=255. It
        # isn't dynamically tracking the season the way it appeared to on the
        # first save - that match was a coincidence, not a real relationship.
        # get_current_season_year()/CINF_SEASON_YEAR_OFFSET are left in place
        # (documented as unreliable) in case cINF's real meaning gets solved
        # later, but nothing here uses them anymore.
        unique_years = sorted(set(
            safe_int(p.get(DRAFT_PICK_YEAR, ""))
            for _, p in sorted_picks
            if safe_int(p.get(DRAFT_PICK_YEAR, "")) is not None
        ))
        year_map = {y: i + 1 for i, y in enumerate(unique_years)}
        current_year_off = unique_years[0] if unique_years else None

        # In-game, the draft picks screen only ever shows the current year
        # plus one year out (2 years total) - confirmed by the user. DRPK can
        # carry a 3rd, further-out year (e.g. DPYO 0, 1, 3 - a gap at 2) that
        # the game itself never displays, so this list is limited to the same
        # 2 years the game actually shows, to match and avoid clutter.
        visible_years = set(unique_years[:2])

        for orig_idx, p in sorted_picks:
            tid = (p.get(DRAFT_PICK_ID, "") or "").strip()
            team_name = TEAM_NAMES.get(tid, tid or "Unknown")
            if query and query not in team_name.lower() and query not in tid.lower():
                continue

            pick_num = safe_int(p.get(DRAFT_PICK_NUM, ""))
            year_off = safe_int(p.get(DRAFT_PICK_YEAR, ""))
            if year_off not in visible_years:
                continue
            year_display = year_map.get(year_off, "-") if year_off is not None else "-"

            # DPNM's meaning is confirmed to change by year (per the Discord
            # community): for the CURRENT year (the lowest DPYO value), it's
            # 0-indexed pick number - 1st overall = 0, 45th overall = 44 - so
            # +1 gives the real in-game pick number, and round = DPNM // 32 + 1.
            # For FUTURE years, DPNM is NOT a pick number at all (the actual
            # draft order isn't determined yet) - at least for 1st-rounders,
            # it's confirmed to instead be (original owning team's TGID - 1).
            # Showing a computed round/pick for those would be confidently
            # wrong, not just imprecise, so future-year picks show "Future"
            # instead of a fabricated round/pick number.
            if year_off is not None and year_off == current_year_off:
                pick_disp = "-" if pick_num is None else str(pick_num + 1)
                round_num = (pick_num // 32) + 1 if pick_num is not None else "-"
                round_disp = f"R{round_num}"
            else:
                pick_disp = "-"
                round_disp = "Future"

            orig_tid = (p.get(DRAFT_PICK_ORIGINAL_TEAM, "") or "").strip()
            orig_name = TEAM_NAMES.get(orig_tid, orig_tid or "-")
            orig_disp = "(own pick)" if orig_tid == tid else f"{orig_tid}: {orig_name}"

            self.tree_picks.insert(
                "", tk.END, iid=str(orig_idx),
                values=(f"{tid}: {team_name}", orig_disp, round_disp, pick_disp, str(year_display)),
            )

        self._finish_tree_refresh(self.tree_picks)
        self._update_pick_selection_label()

    def _update_pick_selection_label(self):
        if not hasattr(self, "lbl_pick_selection"):
            return
        n = len(self.tree_picks.selection())
        self.lbl_pick_selection.configure(text="No picks selected" if n == 0 else f"{n} pick(s) selected")

    def on_assign_picks(self):
        if not self.model.picks:
            messagebox.showinfo("No picks", "Load drpk.csv to edit picks.")
            return

        sel = self.tree_picks.selection()
        if not sel:
            messagebox.showwarning("No picks selected", "Select one or more picks in the list first.")
            return

        dest_tid = self.pick_dest_combo.get_tid()
        if not dest_tid:
            messagebox.showerror("Unknown team", f"'{self.pick_dest_combo.combo.get()}' doesn't match any team.")
            return

        # See the investigation log above _build_picks_tab - confirmed working
        # durably across 2 independent saves (fresh, aged, and re-verified
        # across multiple additional games of play alongside normal AI trade
        # activity). Crashed once, on ONE specific heavily test-edited save -
        # never reproduced anywhere else despite much heavier later testing.
        # Also confirmed practically (RPCS3-level save hangs unrelated to
        # picks specifically, on this same save): starting a genuinely new
        # save file resolved the hang every time it was tried. So the
        # practical mitigation, if anything ever seems off after using this,
        # is the same either way - save to a new file and continue from
        # there, same as you would for any other odd save-state issue.
        dest_name = TEAM_NAMES.get(dest_tid, dest_tid)
        ok = messagebox.askyesno(
            "Confirm pick reassignment",
            f"Reassign {len(sel)} pick(s) to {dest_tid}: {dest_name}?\n\n"
            "Confirmed working reliably across multiple saves and games of play. If anything ever "
            "seems off afterward (crash, hang, etc.), the fix that's worked every time so far is to "
            "save to a NEW file and continue from there, rather than reusing a heavily-edited save."
        )
        if not ok:
            return

        count = 0
        for iid in sel:
            try:
                model_idx = int(iid)
            except ValueError:
                continue
            self.model.picks[model_idx][DRAFT_PICK_ID] = dest_tid
            count += 1

        messagebox.showinfo("Picks assigned", f"Assigned {count} pick(s) to {dest_tid}: {dest_name}")
        self.refresh_picks()

    # ---------- Salary Cap ----------
    def refresh_cap(self):
        if not self.model.salaries:
            self.lbl_cap_status.configure(text="Load slri.csv to edit cap.")
            self.ent_cap.delete(0, tk.END)
            return

        cap_row = self.model.salaries[0]
        cap_val = cap_row.get(SALARY_CAP_KEY, cap_row.get("SCAD", "0"))
        self.ent_cap.delete(0, tk.END)
        self.ent_cap.insert(0, str(cap_val))
        self.lbl_cap_status.configure(text=f"Loaded slri.csv rows: {len(self.model.salaries)}")

    def _populate_tree_with_rows(self, tree: ttk.Treeview, headers: list, rows: list):
        # Clear existing
        for iid in tree.get_children():
            tree.delete(iid)

        if not headers:
            tree["columns"] = ()
            return

        tree["columns"] = headers
        for h in headers:
            tree.heading(h, text=h)
            tree.column(h, width=140, anchor="w", stretch=False)

        for i, r in enumerate(rows):
            vals = [ (r.get(h, "") or "") for h in headers ]
            tree.insert("", tk.END, iid=str(i), values=vals)

    def _filter_rows_by_staff_team(self, rows):
        """rows is a list of (model_idx, row) tuples. Applies the shared
        My Team / All Teams toggle from _build_staff_team_filter."""
        if self.staff_filter_var.get() != "my_team":
            return rows
        tid = self.selected_team_id.get().strip()
        if not tid:
            return rows
        return [(i, r) for i, r in rows if (r.get("TGID", "") or "").strip() == tid]

    def refresh_trainer(self):
        # Show TGID, SKPT, and confirmed skill fields (Injury Eval/Rehab/Fatigue Recovery) if present
        desired = ["TGID", "SKPT", "TSIE", "TSIM", "TSRH", "TSRM", "TSFR", "TSFM"]
        headers = [h for h in desired if h in (self.model.trainer_headers or [])]
        if not headers:
            self._populate_tree_with_rows(self.tree_trainer, self.model.trainer_headers, self.model.trainers)
            return

        # Prepare rows as (model_idx, row) for sorting
        rows = list(enumerate(self.model.trainers))
        rows = self._filter_rows_by_staff_team(rows)

        # Sort by TGID if present, numeric when possible
        if "TGID" in (self.model.trainer_headers or []):
            def tg_key(ir):
                _, r = ir
                tid = (r.get("TGID", "") or "").strip()
                tnum = safe_int(tid)
                return (0, tnum) if tnum is not None else (1, tid)
            rows = sorted(rows, key=tg_key)

        # Clear and set columns
        prev_sel = self.tree_trainer.selection()
        for iid in self.tree_trainer.get_children():
            self.tree_trainer.delete(iid)

        self.tree_trainer["columns"] = headers
        for h in headers:
            self.tree_trainer.heading(h, text=STAFF_FIELD_LABELS.get(h, h), command=lambda h=h: self._sort_tree(self.tree_trainer, h))
            self.tree_trainer.column(h, width=110 if h in STAFF_FIELD_LABELS else 160, anchor="w", stretch=False)

        for idx, r in rows:
            vals = []
            for h in headers:
                if h == "TGID":
                    tid = (r.get("TGID", "") or "").strip()
                    vals.append(f"{tid}: {TEAM_NAMES.get(tid, tid)}" if tid else "")
                else:
                    vals.append((r.get(h, "") or ""))
            self.tree_trainer.insert("", tk.END, iid=str(idx), values=vals)
        self._finish_tree_refresh(self.tree_trainer, prev_sel)

    def _on_trainer_select(self):
        sel = self.tree_trainer.selection()
        if not sel:
            return
        iid = sel[0]
        try:
            idx = int(iid)
        except Exception:
            return
        # find SKPT value from model if present
        try:
            row = self.model.trainers[idx]
        except IndexError:
            return  # stale selection from before a reload shrank the list
        sk = row.get("SKPT") if row is not None else None
        self.ent_trainer_skpt.delete(0, tk.END)
        if sk is not None:
            self.ent_trainer_skpt.insert(0, str(sk))

    def _max_out_staff_skills(self, tree, staff_list, field_names):
        """Set the selected row's skill fields (e.g. Trade/Contract, Injury/Rehab/Fatigue) to their max.
        Returns the selected row's iid (str) so the caller can restore the selection after a refresh."""
        sel = tree.selection()
        if not sel:
            return None
        iid = sel[0]
        try:
            idx = int(iid)
        except Exception:
            return None
        if idx < 0 or idx >= len(staff_list):
            return None
        row = staff_list[idx]
        headers = set(row.keys())
        for field in field_names:
            if field in headers:
                _, hi = STAFF_NUMERIC_FIELDS.get(field, (0, 0))
                row[field] = str(hi)
        return iid

    def _reselect(self, tree, iid):
        if iid and tree.exists(iid):
            tree.selection_set(iid)
            tree.see(iid)

    def set_trainer_skpt_to_max(self):
        """Auto-fill trainer SKPT entry field with maximum value (131071) and max out this trainer's skills."""
        self.ent_trainer_skpt.delete(0, tk.END)
        self.ent_trainer_skpt.insert(0, "131071")
        iid = self._max_out_staff_skills(self.tree_trainer, self.model.trainers, TRAINER_MAXABLE_SKILL_FIELDS)
        self.refresh_trainer()
        self._reselect(self.tree_trainer, iid)

    def set_coach_skpt_to_max(self):
        """Auto-fill coach SKPT entry field with maximum value (131071) and max out this
        coach's skills (including Development, for whichever position buckets are populated)."""
        self.ent_coach_skpt.delete(0, tk.END)
        self.ent_coach_skpt.insert(0, "131071")
        iid = self._max_out_staff_skills(self.tree_coach, self.model.coaches, COACH_MAXABLE_SKILL_FIELDS)

        sel = self.tree_coach.selection()
        if sel:
            try:
                self._max_out_coach_development(int(sel[0]))
            except Exception:
                pass

        self.refresh_coach()
        self._reselect(self.tree_coach, iid)

    def _max_out_gm_potential_eval(self, gm_idx):
        """Max out the selected GM's Potential Evaluation AND Rookie Scouting for
        all 10 position buckets, if populated (confirmed via in-game testing,
        including the correct SKSC/SKSX pairing - see GM_ROOKIE_SCOUTING_CUR_FIELD)."""
        try:
            gm_row = self.model.gms[gm_idx]
        except (IndexError, TypeError):
            return
        pe_rows = self.model.get_gm_potential_eval_rows(gm_row.get("PNid"))
        for pe_row in pe_rows.values():
            pe_row[GM_POTENTIAL_EVAL_CUR_FIELD] = str(GM_POTENTIAL_EVAL_MAX_VALUE)
            pe_row[GM_POTENTIAL_EVAL_MAX_FIELD] = str(GM_POTENTIAL_EVAL_MAX_VALUE)
            pe_row[GM_ROOKIE_SCOUTING_CUR_FIELD] = str(GM_ROOKIE_SCOUTING_MAX_VALUE)
            pe_row[GM_ROOKIE_SCOUTING_MAX_FIELD] = str(GM_ROOKIE_SCOUTING_MAX_VALUE)

    def _max_out_coach_development(self, coach_idx):
        """Max out the selected coach's Physical/Intangible/Learning Development
        for all 10 position buckets, if populated (confirmed via in-game testing -
        see COACH_DEV_CATEGORIES)."""
        try:
            coach_row = self.model.coaches[coach_idx]
        except (IndexError, TypeError):
            return
        dev_rows = self.model.get_coach_development_rows(coach_row.get("PNid"))
        for dev_row in dev_rows.values():
            for cur_field, max_field, _name in COACH_DEV_CATEGORIES.values():
                dev_row[cur_field] = str(COACH_DEV_MAX_VALUE)
                dev_row[max_field] = str(COACH_DEV_MAX_VALUE)

    def set_gm_skpt_to_max(self):
        """Auto-fill GM SKPT entry field with maximum value (131071) and max out this GM's skills
        (Trade/Contract Negotiation, plus Potential Evaluation and Rookie Scouting for all 10
        position buckets if populated)."""
        self.ent_gm_skpt.delete(0, tk.END)
        self.ent_gm_skpt.insert(0, "131071")
        iid = self._max_out_staff_skills(self.tree_gm, self.model.gms, GM_MAXABLE_SKILL_FIELDS)

        sel = self.tree_gm.selection()
        if sel:
            try:
                self._max_out_gm_potential_eval(int(sel[0]))
            except Exception:
                pass

        self.refresh_gm()
        self._reselect(self.tree_gm, iid)

    def _ensure_tree_selection(self, tree):
        """If nothing is selected, auto-select the first visible row instead
        of requiring an extra click - most useful when filtered to "My Team"
        where there's often just one (or few) row(s) shown anyway. Returns
        the resulting selection tuple (possibly still empty if the tree has
        no rows at all)."""
        sel = tree.selection()
        if sel:
            return sel
        children = tree.get_children()
        if children:
            tree.selection_set(children[0])
            tree.focus(children[0])
            return tree.selection()
        return sel

    def on_max_selected_gm(self):
        """Max out ALL of the selected GM's stats in one click: Trade, Contract, and
        Potential Evaluation + Rookie Scouting (for whichever position buckets this GM has data for)."""
        sel = self._ensure_tree_selection(self.tree_gm)
        if not sel:
            messagebox.showinfo("No GMs shown", "No GM rows to select - check the My Team/All Teams filter.")
            return
        iid = self._max_out_staff_skills(self.tree_gm, self.model.gms, GM_MAXABLE_SKILL_FIELDS)
        self._max_out_gm_potential_eval(int(sel[0]))
        self.refresh_gm()
        self._reselect(self.tree_gm, iid)

    def on_max_selected_trainer(self):
        """Max out ALL of the selected trainer's stats: Injury Eval, Rehab, Fatigue Rec."""
        sel = self._ensure_tree_selection(self.tree_trainer)
        if not sel:
            messagebox.showinfo("No trainers shown", "No trainer rows to select - check the My Team/All Teams filter.")
            return
        iid = self._max_out_staff_skills(self.tree_trainer, self.model.trainers, TRAINER_MAXABLE_SKILL_FIELDS)
        self.refresh_trainer()
        self._reselect(self.tree_trainer, iid)

    def on_max_selected_coach(self):
        """Max out ALL of this coach's confirmed stats: Play Call (SKPC/SKPX), Strategy
        (SKST/SKSM), Team Chemistry (SKCR/SKCM), Performance (MIN(SKPA, SKPF), so setting
        both to 5 maxes it), and Physical/Intangible/Learning Development for all 10
        position buckets. See the investigation log above COACH_MAXABLE_SKILL_FIELDS."""
        sel = self._ensure_tree_selection(self.tree_coach)
        if not sel:
            messagebox.showinfo("No coaches shown", "No coach rows to select - check the My Team/All Teams filter.")
            return
        iid = self._max_out_staff_skills(self.tree_coach, self.model.coaches, COACH_MAXABLE_SKILL_FIELDS)
        self._max_out_coach_development(int(sel[0]))
        self.refresh_coach()
        self._reselect(self.tree_coach, iid)

    def _apply_trainer_skpt(self):
        sel = self.tree_trainer.selection()
        if not sel:
            messagebox.showwarning("No selection", "Select a trainer row first.")
            return
        iid = sel[0]
        try:
            idx = int(iid)
        except Exception:
            return
        val = self.ent_trainer_skpt.get().strip()
        try:
            v = safe_int(val)
            if v is None:
                raise ValueError("Invalid integer")
            orig = v
            # Clamp to allowed range
            v = max(0, min(131071, v))
            self.model.trainers[idx]["SKPT"] = str(v)
            self.refresh_trainer()
            if orig != v:
                # show only the clamped numeric value (no decimal)
                messagebox.showinfo("SKPT", str(v))
        except Exception as e:
            messagebox.showerror("Invalid SKPT", str(e))

    def refresh_coach(self):
        # Shown columns: TGID/name/SKPT plus all 5 confirmed skill fields
        # (SKPC=Play Call, SKST=Strategy, SKCR=Team Chemistry all directly
        # editable; SKPA+SKPF feed Performance=MIN(SKPA,SKPF), not independently
        # meaningful). See the investigation log above COACH_MAXABLE_SKILL_FIELDS.
        desired = ["TGID", "CFNM", "CLNM", "COPS", "SKPT", "SKPC", "SKPX", "SKST", "SKSM", "SKCR", "SKCM", "SKPA", "SKPF", "POVS"]
        headers = [h for h in desired if h in (self.model.coach_headers or [])]
        if not headers:
            headers = self.model.coach_headers

        # Confirmed Development columns, joined from CSKL via PNid
        has_pnid = "PNid" in (self.model.coach_headers or [])
        show_dev = has_pnid and bool(self.model.cskl)
        if show_dev:
            headers = headers + COACH_DEV_COLUMNS

        # Build filtering predicate from search box (supports "first last" or just first or last)
        q = (self.coach_search_var.get() or "").strip().lower() if hasattr(self, 'coach_search_var') else ""

        # Prepare rows as (model_idx, row) and apply filter
        rows = list(enumerate(self.model.coaches))
        rows = self._filter_rows_by_staff_team(rows)
        if q:
            def match(r):
                fn = (r.get("CFNM", "") or "").lower()
                ln = (r.get("CLNM", "") or "").lower()
                parts = q.split()
                if len(parts) == 2:
                    # Search for first name + last name (e.g., "John Smith")
                    return parts[0] in fn and parts[1] in ln
                else:
                    # Search in either first or last name
                    return q in fn or q in ln
            rows = [(i, r) for i, r in rows if match(r)]

        # Sort by TGID if present, numeric when possible
        if "TGID" in (self.model.coach_headers or []):
            def tg_key(ir):
                _, r = ir
                tid = (r.get("TGID", "") or "").strip()
                tnum = safe_int(tid)
                return (0, tnum) if tnum is not None else (1, tid)
            rows = sorted(rows, key=lambda ir: (tg_key(ir), (ir[1].get("CLNM", "") or ""), (ir[1].get("CFNM", "") or "")))
        else:
            rows = sorted(rows, key=lambda ir: ((ir[1].get("CLNM", "") or ""), (ir[1].get("CFNM", "") or "")))

        # clear and set columns
        prev_sel = self.tree_coach.selection()
        for iid in self.tree_coach.get_children():
            self.tree_coach.delete(iid)

        self.tree_coach["columns"] = headers or []
        for h in headers or []:
            self.tree_coach.heading(h, text=STAFF_FIELD_LABELS.get(h, h), command=lambda h=h: self._sort_tree(self.tree_coach, h))
            self.tree_coach.column(h, width=90 if h in COACH_DEV_COLUMNS else 140, anchor="w", stretch=False)

        # Insert rows using original model indices as iids
        for idx, r in rows:
            vals = []
            dev_rows = self.model.get_coach_development_rows(r.get("PNid")) if show_dev else {}
            for h in headers or []:
                if h == "TGID":
                    tid = (r.get("TGID", "") or "").strip()
                    vals.append(f"{tid}: {TEAM_NAMES.get(tid, tid)}" if tid else "")
                elif h == "COPS":
                    cops = (r.get("COPS", "") or "").strip()
                    vals.append(COACH_POSITION_LABELS.get(cops, cops))
                elif h in COACH_DEV_COLUMNS:
                    cat, bucket, is_max = parse_dev_column(h)
                    cur_field, max_field, _name = COACH_DEV_CATEGORIES[cat]
                    row = dev_rows.get(bucket)
                    vals.append(row.get(max_field if is_max else cur_field, "") if row else "")
                else:
                    vals.append((r.get(h, "") or ""))
            self.tree_coach.insert("", tk.END, iid=str(idx), values=vals)
        self._finish_tree_refresh(self.tree_coach, prev_sel)

    def _on_coach_select(self):
        sel = self.tree_coach.selection()
        if not sel:
            return
        iid = sel[0]
        try:
            idx = int(iid)
        except Exception:
            return
        try:
            row = self.model.coaches[idx]
        except IndexError:
            return  # stale selection from before a reload shrank the list
        sk = row.get("SKPT") if row is not None else None
        self.ent_coach_skpt.delete(0, tk.END)
        if sk is not None:
            self.ent_coach_skpt.insert(0, str(sk))

    def on_open_coach_personality_editor(self):
        sel = self.tree_coach.selection()
        if not sel:
            messagebox.showinfo("No coach", "Select a coach first.")
            return
        try:
            idx = int(sel[0])
        except Exception:
            return
        row = self.model.coaches[idx]
        name = f"{(row.get('CFNM','') or '').strip()} {(row.get('CLNM','') or '').strip()}".strip()
        PersonalityDialog(
            self, self.model.coaches, idx,
            f"Coach: {name}", refresh_callback=self.refresh_coach,
            subject_kind="coach",
        )

    def on_open_team_philosophy(self):
        """The team philosophy the game's Team Philosophy screen shows (TPHS table), for the
        selected coach's team, or the team selected on the Players tab if no coach is."""
        tid = ""
        sel = self.tree_coach.selection()
        if sel:
            try:
                tid = (self.model.coaches[int(sel[0])].get("TGID") or "").strip()
            except (ValueError, IndexError):
                tid = ""
        tid = tid or self.selected_team_id.get().strip()
        idx = next((i for i, r in enumerate(self.model.tphs) if (r.get("TGID") or "").strip() == tid), None)
        if idx is None:
            messagebox.showinfo("Team philosophy", "This save has no team philosophy data for that team. Select a team's coach first.")
            return
        nick = team_nickname(tid) or f"Team {tid}"
        TeamPhilosophyDialog(
            self, self.model.tphs, idx, f"{nick} team philosophy", self._on_philosophy_changed,
            note="This is the data behind the game's Team Philosophy screen. Checked against the game: the playcall "
                 "settings and the QB, CB, FS, SS, kicker and punter philosophies (at least one value each). The other "
                 "names come from a community list - try changes on a copy of your save.")

    def _apply_coach_skpt(self):
        sel = self.tree_coach.selection()
        if not sel:
            messagebox.showwarning("No selection", "Select a coach row first.")
            return
        iid = sel[0]
        try:
            idx = int(iid)
        except Exception:
            return
        val = self.ent_coach_skpt.get().strip()
        try:
            v = safe_int(val)
            if v is None:
                raise ValueError("Invalid integer")
            orig = v
            # Clamp to allowed range
            v = max(0, min(131071, v))
            self.model.coaches[idx]["SKPT"] = str(v)
            self.refresh_coach()
            if orig != v:
                messagebox.showinfo("SKPT", str(v))
        except Exception as e:
            messagebox.showerror("Invalid SKPT", str(e))

    def refresh_gm(self):
        # Show TGID, SKPT, and confirmed skill fields (Trade/Contract Negotiation).
        # GM_SCOUTING_FIELDS (CBMP/FBMP/etc.) deliberately NOT shown by default -
        # confirmed to have no effect on anything, just clutters the view.
        desired = ["TGID", "SKPT", "SKTD", "SKTM", "SKNG", "SKNM"]
        headers = [h for h in desired if h in (self.model.gm_headers or [])]
        if not headers:
            self._populate_tree_with_rows(self.tree_gm, self.model.gm_headers, self.model.gms)
            return

        # Confirmed Potential Evaluation + Rookie Scouting columns, joined from GMSK via PNid
        has_pnid = "PNid" in (self.model.gm_headers or [])
        show_pe = has_pnid and bool(self.model.gmsk)
        if show_pe:
            headers = headers + GM_POTENTIAL_EVAL_COLUMNS + GM_ROOKIE_SCOUTING_COLUMNS

        # Prepare rows as (model_idx, row) for sorting
        rows = list(enumerate(self.model.gms))
        rows = self._filter_rows_by_staff_team(rows)

        # Sort by TGID if present, numeric when possible
        if "TGID" in (self.model.gm_headers or []):
            def tg_key(ir):
                _, r = ir
                tid = (r.get("TGID", "") or "").strip()
                tnum = safe_int(tid)
                return (0, tnum) if tnum is not None else (1, tid)
            rows = sorted(rows, key=tg_key)

        # Clear and set columns
        prev_sel = self.tree_gm.selection()
        for iid in self.tree_gm.get_children():
            self.tree_gm.delete(iid)

        self.tree_gm["columns"] = headers
        for h in headers:
            self.tree_gm.heading(h, text=STAFF_FIELD_LABELS.get(h, h), command=lambda h=h: self._sort_tree(self.tree_gm, h))
            is_bucket_col = h in GM_POTENTIAL_EVAL_COLUMNS or h in GM_ROOKIE_SCOUTING_COLUMNS
            self.tree_gm.column(h, width=90 if is_bucket_col else (110 if h in STAFF_FIELD_LABELS else 160), anchor="w", stretch=False)

        for idx, r in rows:
            vals = []
            pe_rows = self.model.get_gm_potential_eval_rows(r.get("PNid")) if show_pe else {}
            for h in headers:
                if h == "TGID":
                    tid = (r.get("TGID", "") or "").strip()
                    vals.append(f"{tid}: {TEAM_NAMES.get(tid, tid)}" if tid else "")
                elif h in GM_POTENTIAL_EVAL_COLUMNS:
                    bucket, is_max = parse_pe_column(h)
                    row = pe_rows.get(bucket)
                    field = GM_POTENTIAL_EVAL_MAX_FIELD if is_max else GM_POTENTIAL_EVAL_CUR_FIELD
                    vals.append(row.get(field, "") if row else "")
                elif h in GM_ROOKIE_SCOUTING_COLUMNS:
                    bucket, is_max = parse_rs_column(h)
                    row = pe_rows.get(bucket)
                    field = GM_ROOKIE_SCOUTING_MAX_FIELD if is_max else GM_ROOKIE_SCOUTING_CUR_FIELD
                    vals.append(row.get(field, "") if row else "")
                else:
                    vals.append((r.get(h, "") or ""))
            self.tree_gm.insert("", tk.END, iid=str(idx), values=vals)
        self._finish_tree_refresh(self.tree_gm, prev_sel)

    def _on_gm_select(self):
        sel = self.tree_gm.selection()
        if not sel:
            return
        iid = sel[0]
        try:
            idx = int(iid)
        except Exception:
            return
        row = self.model.gms[idx]
        sk = row.get("SKPT") if row is not None else None
        self.ent_gm_skpt.delete(0, tk.END)
        if sk is not None:
            self.ent_gm_skpt.insert(0, str(sk))

    def _apply_gm_skpt(self):
        sel = self.tree_gm.selection()
        if not sel:
            messagebox.showwarning("No selection", "Select a GM row first.")
            return
        iid = sel[0]
        try:
            idx = int(iid)
        except Exception:
            return
        val = self.ent_gm_skpt.get().strip()
        try:
            v = safe_int(val)
            if v is None:
                raise ValueError("Invalid integer")
            orig = v
            # Clamp to allowed range
            v = max(0, min(131071, v))
            self.model.gms[idx]["SKPT"] = str(v)
            self.refresh_gm()
            if orig != v:
                messagebox.showinfo("SKPT", str(v))
        except Exception as e:
            messagebox.showerror("Invalid SKPT", str(e))

    def _sort_tree(self, tree, col):
        """Click-to-sort for a table's column heading: first click sorts
        ascending, clicking the same column again flips to descending. The
        choice is remembered per table (see _finish_tree_refresh) so it
        survives the table being rebuilt after an edit instead of snapping
        back to the default order."""
        cur = self._tree_sort_state.get(id(tree))
        reverse = bool(cur and cur[0] == col and not cur[1])
        self._tree_sort_state[id(tree)] = (col, reverse)
        self._apply_tree_sort(tree)
        self._sync_vertical(tree)

    def _apply_tree_sort(self, tree):
        state = self._tree_sort_state.get(id(tree))
        if not state:
            return
        col, reverse = state
        if col not in tree["columns"]:
            del self._tree_sort_state[id(tree)]
            return
        rows = [(tree.set(iid, col), iid) for iid in tree.get_children("")]
        for index, iid in enumerate(sort_table_cells(rows, reverse)):
            tree.move(iid, "", index)
        for c in tree["columns"]:
            text = re.sub(r" [▲▼]$", "", str(tree.heading(c, "text")))
            if c == col:
                text += " ▼" if reverse else " ▲"
            tree.heading(c, text=text)

    def _finish_tree_refresh(self, tree, prev_selection=()):
        """Call at the end of anything that rebuilds a table: puts the rows
        back in the user's chosen sort order and restores the selection that
        the rebuild wiped out."""
        self._apply_tree_sort(tree)
        keep = [iid for iid in prev_selection if tree.exists(iid)]
        if keep:
            tree.selection_set(keep)
        self._sync_vertical(tree)

    def _on_tree_double_click(self, event, tree: ttk.Treeview):
        # Identify clicked row/column
        region = tree.identify_region(event.x, event.y)
        if region != "cell":
            return
        rowid = tree.identify_row(event.y)
        col = tree.identify_column(event.x)  # returns like '#1'
        if not rowid or not col:
            return
        try:
            col_idx = int(col.replace('#', '')) - 1
        except Exception:
            return
        cols = list(tree["columns"]) if tree["columns"] else []
        if col_idx < 0 or col_idx >= len(cols):
            return
        colname = cols[col_idx]
        bbox = tree.bbox(rowid, column=col)
        if not bbox:
            return
        self._edit_staff_cell(tree, rowid, colname, tree, bbox)

    # ---------- Vertical layout for the Trainer / Coach / GM tabs ----------
    # The horizontal Treeview stays the single source of truth (selection, sort,
    # the SKPT box, "Max Selected ...", Personality... all keep working off it);
    # when the layout is Vertical it is simply not shown, and a second Treeview
    # draws the same data turned on its side - one column per coach/GM/trainer,
    # one row per stat - so reaching e.g. a coach's WR development means
    # scrolling down a list, like the in-game staff screen, instead of across
    # 80 columns.
    STAFF_IDENTITY_COLS = ("TGID", "CFNM", "CLNM")

    def _begin_staff_table_area(self, root):
        area = ttk.Frame(root)
        area.pack(fill="both", expand=True, padx=10)
        hframe = ttk.Frame(area)
        hframe.pack(fill="both", expand=True)
        return hframe

    def _finish_staff_table_area(self, hframe, tree, kind):
        area = hframe.master
        vframe = ttk.Frame(area)
        vtree = ttk.Treeview(vframe, show="headings", selectmode="none", height=10)
        yscroll = ttk.Scrollbar(vframe, orient="vertical", command=vtree.yview)
        xscroll = ttk.Scrollbar(vframe, orient="horizontal", command=vtree.xview)
        vtree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        xscroll.pack(side="bottom", fill="x", pady=(0, 6))
        yscroll.pack(side="right", fill="y")
        vtree.pack(side="left", fill="both", expand=True)
        view = {"kind": kind, "tree": tree, "hframe": hframe, "vframe": vframe, "vtree": vtree,
                "collapsed": set(), "sections": {}}
        self._vviews[id(tree)] = view
        vtree.bind("<Button-1>", lambda e, v=view: self._vertical_click(v, e))
        vtree.bind("<Double-1>", lambda e, v=view: self._vertical_double_click(v, e))
        tree.bind("<<TreeviewSelect>>", lambda e, t=tree: self._refresh_vertical_headings(t), add="+")
        self._show_staff_layout(view)

    def _show_staff_layout(self, view):
        if self.staff_layout_var.get() == "vertical":
            view["hframe"].pack_forget()
            view["vframe"].pack(fill="both", expand=True)
            self._sync_vertical(view["tree"])
        else:
            view["vframe"].pack_forget()
            view["hframe"].pack(fill="both", expand=True)

    def on_staff_layout_changed(self):
        self.ui_prefs["staff_layout"] = self.staff_layout_var.get()
        save_ui_prefs(self.ui_prefs)
        for view in self._vviews.values():
            self._show_staff_layout(view)

    def _staff_field_section(self, kind, field):
        """Section title a field is listed under in the vertical layout (None =
        no section headings for this table)."""
        if kind == "coach":
            parsed = parse_dev_column(field)
            return f"{COACH_DEV_CATEGORIES[parsed[0]][2]} Development" if parsed else "Skills"
        if kind == "gm":
            if parse_pe_column(field) is not None:
                return "Potential Evaluation"
            if parse_rs_column(field) is not None:
                return "Rookie Scouting"
            return "Skills"
        return None

    def _vertical_heading(self, view, iid, selected):
        tree, kind = view["tree"], view["kind"]
        cols = tree["columns"]
        tid = tree.set(iid, "TGID") if "TGID" in cols else ""
        nick = tid.split(": ", 1)[-1].split(" (")[0] if tid else "?"
        if kind == "coach":
            pos = tree.set(iid, "COPS") if "COPS" in cols else ""
            last = tree.set(iid, "CLNM") if "CLNM" in cols else ""
            who = f"{pos} {last}".strip()
            text = who if self.staff_filter_var.get() == "my_team" else f"{nick}: {who}"
        else:
            text = nick
        return ("\u25b6 " if selected else "") + text

    def _refresh_vertical_headings(self, tree):
        view = self._vviews.get(id(tree))
        if not view or self.staff_layout_var.get() != "vertical":
            return
        sel = set(tree.selection())
        vtree = view["vtree"]
        for col in vtree["columns"][1:]:
            iid = col[1:]
            if tree.exists(iid):
                vtree.heading(col, text=self._vertical_heading(view, iid, iid in sel))

    def _sync_vertical(self, tree):
        """Redraw the vertical view from the horizontal table's current rows
        (and current order, so sorting by a stat reorders the columns)."""
        view = self._vviews.get(id(tree))
        if not view or self.staff_layout_var.get() != "vertical":
            return
        vtree, kind = view["vtree"], view["kind"]
        xpos, ypos = vtree.xview()[0], vtree.yview()[0]
        for iid in vtree.get_children():
            vtree.delete(iid)

        iids = list(tree.get_children(""))
        rec_cols = [f"r{iid}" for iid in iids]
        vtree["columns"] = ["field"] + rec_cols
        vtree.heading("field", text="Stat  (click one to sort)", anchor="w")
        vtree.column("field", width=230, anchor="w", stretch=False)
        rec_width = 110 if (kind == "coach" and self.staff_filter_var.get() == "my_team") else 150
        for col in rec_cols:
            vtree.column(col, width=rec_width, anchor="center", stretch=False)
        self._refresh_vertical_headings(tree)

        pal = getattr(self, "_ui_palette", None)
        vtree.tag_configure(
            "section",
            background=pal["header_bg"] if pal else "#d9d9d9",
            foreground=pal["text"] if pal else "black",
        )

        sort = self._tree_sort_state.get(id(tree))
        collapsed = view["collapsed"]
        view["sections"] = {}
        last_section = object()
        n_sections = 0
        for field in (c for c in tree["columns"] if c not in self.STAFF_IDENTITY_COLS):
            section = self._staff_field_section(kind, field)
            if section != last_section:
                last_section = section
                if section is not None:
                    n_sections += 1
                    sec_iid = f"__sec_{n_sections}"
                    view["sections"][sec_iid] = section
                    arrow = "\u25b8" if section in collapsed else "\u25be"
                    vtree.insert("", tk.END, iid=sec_iid, tags=("section",),
                                 values=[f"{arrow} {section}"] + [""] * len(rec_cols))
            if section is not None and section in collapsed:
                continue
            label = STAFF_FIELD_LABELS.get(field, field)
            if sort and sort[0] == field:
                label += " \u25bc" if sort[1] else " \u25b2"
            vtree.insert("", tk.END, iid=field, values=[label] + [tree.set(iid, field) for iid in iids])

        vtree.xview_moveto(xpos)
        vtree.yview_moveto(ypos)

    def _vertical_cell_at(self, view, event):
        vtree = view["vtree"]
        if vtree.identify_region(event.x, event.y) != "cell":
            return None
        row = vtree.identify_row(event.y)
        try:
            k = int(vtree.identify_column(event.x).replace("#", "")) - 1
        except ValueError:
            return None
        cols = list(vtree["columns"])
        if not row or row.startswith("__sec_") or k < 0 or k >= len(cols):
            return None
        return row, k, cols

    def _vertical_heading_record(self, view, event):
        """The record (iid in the real staff table) whose name heading was clicked, or None."""
        vtree = view["vtree"]
        if vtree.identify_region(event.x, event.y) != "heading":
            return None
        try:
            k = int(vtree.identify_column(event.x).replace("#", "")) - 1
        except ValueError:
            return None
        cols = list(vtree["columns"])
        return cols[k][1:] if 1 <= k < len(cols) else None

    def _vertical_click(self, view, event):
        rec = self._vertical_heading_record(view, event)
        if rec is not None:
            view["tree"].selection_set(rec)   # the name at the top selects that coach, like a cell under it
            return
        hit = self._vertical_cell_at(view, event)
        if not hit:
            return
        row, k, cols = hit
        if k == 0:
            self._sort_tree(view["tree"], row)  # clicking a stat's name orders the columns by it
        else:
            view["tree"].selection_set(cols[k][1:])

    def _vertical_double_click(self, view, event):
        if self._vertical_heading_record(view, event) is not None:
            self._vertical_click(view, event)   # a quick second click on a name still selects
            return
        row = view["vtree"].identify_row(event.y)
        if row in view["sections"]:
            title = view["sections"][row]
            if title in view["collapsed"]:
                view["collapsed"].discard(title)
            else:
                view["collapsed"].add(title)
            self._sync_vertical(view["tree"])
            return
        hit = self._vertical_cell_at(view, event)
        if not hit:
            return
        row, k, cols = hit
        if k == 0:
            # Tk reports a quick second click on a stat name as a double-click
            # instead of a click, so it has to sort here too or flipping the
            # direction by clicking twice would silently do nothing.
            self._vertical_click(view, event)
            return
        bbox = view["vtree"].bbox(row, column=cols[k])
        if bbox:
            self._edit_staff_cell(view["tree"], cols[k][1:], row, view["vtree"], bbox)

    def _edit_staff_cell(self, tree, rowid, colname, host, bbox):
        """Edit one staff stat. tree is always the real (horizontal) staff table,
        rowid is the record's iid in it (= index into the model list) and colname
        the field; host/bbox say where on screen to put the editor, so the same
        code serves both the horizontal table and the vertical layout."""
        is_pe_column = tree is self.tree_gm and parse_pe_column(colname) is not None
        is_rs_column = tree is self.tree_gm and parse_rs_column(colname) is not None
        is_dev_column = tree is self.tree_coach and parse_dev_column(colname) is not None
        is_cops_column = tree is self.tree_coach and colname == "COPS"
        # Allow editing any known staff numeric column (SKPT, coach 1-7 fields, GM/trainer skill pairs)
        # or a GM Potential Evaluation/Rookie Scouting or Coach Development column (each lives in a
        # different table, handled specially below), or the Coach Position column (also special-cased:
        # it's a small fixed set of codes, edited via dropdown rather than a free-integer box).
        if not is_pe_column and not is_rs_column and not is_dev_column and not is_cops_column and colname not in STAFF_NUMERIC_FIELDS:
            return

        x, y, w, h = bbox

        if is_cops_column:
            # Pop-up menu of position labels rather than a raw 0-10 number field -
            # the table shows the mapped label (e.g. "DC"), so editing works in
            # those same terms. (A Combobox was tried first, but it loses focus
            # the moment its list opens, which cancelled the edit.)
            try:
                idx = int(rowid)
            except Exception:
                return
            cur_code = (self.model.coaches[idx].get("COPS", "") or "").strip()
            chosen = tk.StringVar(value=cur_code)

            def pick(code):
                if code == cur_code:
                    return
                self.model.coaches[idx]["COPS"] = code
                self.mark_dirty()
                self.refresh_coach()

            menu = tk.Menu(host, tearoff=0)
            for code, label in COACH_POSITION_LABELS.items():
                menu.add_radiobutton(label=label, variable=chosen, value=code, command=lambda c=code: pick(c))
            try:
                menu.tk_popup(host.winfo_rootx() + x, host.winfo_rooty() + y + h)
            finally:
                menu.grab_release()
            return

        # Create entry overlay
        entry = ttk.Entry(host)
        entry.place(x=x, y=y, width=w, height=h)
        # prefill with current value
        cur = tree.set(rowid, colname)
        entry.insert(0, cur)
        entry.focus_set()

        def finish(save: bool):
            val = entry.get().strip()
            entry.destroy()
            if not save:
                return
            try:
                # Accept integer or integer-like float (e.g. "131071.0")
                v = None
                try:
                    v = int(val)
                except Exception:
                    try:
                        f = float(val)
                        v = int(f)
                    except Exception:
                        v = None


                if v is None:
                    raise ValueError("Invalid integer")

                orig_v = v

                try:
                    idx = int(rowid)
                except Exception:
                    return

                if is_pe_column or is_rs_column:
                    # Potential Evaluation / Rookie Scouting live in a different table
                    # (GMSK), joined to this GM row via PNid - not a same-row field.
                    # Looked up by each row's own PPGR field, not by list position
                    # (see get_gm_potential_eval_rows / PPGR_TO_POSITION).
                    gm_row = self.model.gms[idx]
                    pe_rows = self.model.get_gm_potential_eval_rows(gm_row.get("PNid"))
                    if not pe_rows:
                        messagebox.showinfo(
                            "No data",
                            "This GM has no Potential Evaluation / Rookie Scouting data populated yet (fresh/never-invested GMs have no GMSK rows)."
                        )
                        return
                    if is_pe_column:
                        bucket, is_max = parse_pe_column(colname)
                        lo, hi = GM_POTENTIAL_EVAL_MIN_VALUE, GM_POTENTIAL_EVAL_MAX_VALUE
                        field = GM_POTENTIAL_EVAL_MAX_FIELD if is_max else GM_POTENTIAL_EVAL_CUR_FIELD
                    else:
                        bucket, is_max = parse_rs_column(colname)
                        lo, hi = GM_ROOKIE_SCOUTING_MIN_VALUE, GM_ROOKIE_SCOUTING_MAX_VALUE
                        field = GM_ROOKIE_SCOUTING_MAX_FIELD if is_max else GM_ROOKIE_SCOUTING_CUR_FIELD
                    v = max(lo, min(hi, v))
                    row = pe_rows.get(bucket)
                    if row is None:
                        return
                    row[field] = str(v)
                    self.mark_dirty()
                    self.refresh_gm()
                    return

                if is_dev_column:
                    # Development lives in a different table (CSKL), joined to this
                    # coach row via PNid, looked up by each row's own PPGR field
                    # (see get_coach_development_rows / PPGR_TO_POSITION).
                    v = max(COACH_DEV_MIN_VALUE, min(COACH_DEV_MAX_VALUE, v))
                    coach_row = self.model.coaches[idx]
                    dev_rows = self.model.get_coach_development_rows(coach_row.get("PNid"))
                    if not dev_rows:
                        messagebox.showinfo(
                            "No data",
                            "This coach has no Development data populated yet (fresh/never-invested coaches have no CSKL rows)."
                        )
                        return
                    cat, bucket, is_max = parse_dev_column(colname)
                    cur_field, max_field, _name = COACH_DEV_CATEGORIES[cat]
                    row = dev_rows.get(bucket)
                    if row is None:
                        return
                    row[max_field if is_max else cur_field] = str(v)
                    self.mark_dirty()
                    self.refresh_coach()
                    return

                # Determine clamp range
                lo, hi = STAFF_NUMERIC_FIELDS.get(colname, (0, 131071))
                v = max(lo, min(hi, v))

                target = None
                if tree is self.tree_trainer:
                    target = self.model.trainers
                elif tree is self.tree_coach:
                    target = self.model.coaches
                elif tree is self.tree_gm:
                    target = self.model.gms
                if target is None:
                    return
                # write back
                try:
                    target[idx][colname] = str(v)
                except Exception:
                    return
                self.mark_dirty()
                # refresh appropriate view
                if tree is self.tree_trainer:
                    self.refresh_trainer()
                elif tree is self.tree_coach:
                    self.refresh_coach()
                elif tree is self.tree_gm:
                    self.refresh_gm()
            except Exception as e:
                messagebox.showerror("Invalid SKPT", str(e))

        entry.bind("<Return>", lambda e: finish(True))
        entry.bind("<FocusOut>", lambda e: finish(True))
        entry.bind("<Escape>", lambda e: finish(False))

    def set_cap_to_max(self):
        """Auto-fill the salary cap entry field with the real in-game max. NOT the
        signed 32-bit ceiling (2,147,483,647) - confirmed via the NFL Head Coach
        Discord server that going above 260,000,000 FREEZES THE GAME (worse than
        the earlier-fixed negative-wrap issue). 260,000,000 is also what at least
        one other community tool independently caps its salary cap editor at."""
        self.ent_cap.delete(0, tk.END)
        self.ent_cap.insert(0, "260000000")

    def on_apply_cap(self):
        if not self.model.salaries:
            messagebox.showinfo("No salary data", "Load slri.csv first.")
            return
        
        raw = self.ent_cap.get().strip()
        if not raw:
            messagebox.showwarning("Empty field", "Enter a salary cap value.")
            return
        
        try:
            # Parse as integer, with float fallback
            v = None
            try:
                v = int(raw)
            except ValueError:
                try:
                    v = int(float(raw))
                except ValueError:
                    raise ValueError("Invalid number format")
            
            # Remember original for comparison
            orig_v = v
            
            # Clamp to 0-260,000,000 - confirmed via the community Discord that going
            # above 260 million FREEZES THE GAME (not just a display/wrap issue like
            # the raw signed-int ceiling of 2,147,483,647 would allow past this point).
            v = max(0, min(260_000_000, v))
            
            # Update model
            cap_row = self.model.salaries[0]
            cap_row[SALARY_CAP_KEY] = str(v)
            
            # Update display
            self.ent_cap.delete(0, tk.END)
            self.ent_cap.insert(0, str(v))
            if orig_v != v:
                self.lbl_cap_status.configure(text=f"Value {orig_v} was clamped to {v}.")
            else:
                self.lbl_cap_status.configure(text=f"Updated to {v}")

        except Exception as e:
            messagebox.showerror("Cap Error", str(e))

    # ---------- Raw Column Editor ----------
    def refresh_raw_columns(self):
        if not self.model.player_headers:
            self.cmb_raw_col["values"] = []
            return
        self.cmb_raw_col["values"] = self.model.player_headers
        self.cmb_raw_col.current(0)
        self.cmb_raw_col.bind("<<ComboboxSelected>>", lambda e: self.on_raw_column_changed())

    def on_raw_column_changed(self):
        if self.selected_player_index is None:
            return
        col = self.cmb_raw_col.get().strip()
        if not col:
            return
        r = self.model.players[self.selected_player_index]
        self.ent_raw_val.delete(0, tk.END)
        self.ent_raw_val.insert(0, (r.get(col, "") or "").strip())

    def on_apply_raw_column(self):
        if self.selected_player_index is None:
            messagebox.showinfo("No player", "Select a player first.")
            return
        col = self.cmb_raw_col.get().strip()
        if not col:
            return
        val = self.ent_raw_val.get()
        self.model.players[self.selected_player_index][col] = val
        self.refresh_stats_for_player()
        self.refresh_players_for_team()

# -----------------------------
# Unsaved-changes tracking: auto-wrap every editing entry point so App.dirty
# gets set without having to hand-edit each method body. May mark dirty on a
# no-op edge case (e.g. a validation error before any real change) - that's
# an acceptable false positive, since under-marking (silently losing edits)
# would be the far worse failure mode. _do_swap (SwapTradeDialog) and the
# finish() closure inside _on_tree_double_click aren't App methods, so they
# call self.mark_dirty()/self.parent.mark_dirty() directly instead - see above.
# -----------------------------
_MUTATING_APP_METHODS = [
    "on_apply_name", "on_apply_stat", "on_apply_both", "on_apply_age_years",
    "on_assign_picks", "on_set_team_bonus_min",
    "on_max_team_staff_skpt", "on_apply_cap", "on_apply_raw_column",
    "_apply_trainer_skpt", "_apply_coach_skpt", "_apply_gm_skpt",
    "set_trainer_skpt_to_max", "set_coach_skpt_to_max", "set_gm_skpt_to_max",
    "on_max_selected_gm", "on_max_selected_trainer", "on_max_selected_coach",
]

def _wrap_mutating(method):
    def wrapped(self, *args, **kwargs):
        result = method(self, *args, **kwargs)
        self.mark_dirty()
        return result
    wrapped.__name__ = method.__name__
    return wrapped

for _name in _MUTATING_APP_METHODS:
    setattr(App, _name, _wrap_mutating(getattr(App, _name)))
del _name


if __name__ == "__main__":
    app = App()
    app.mainloop()
