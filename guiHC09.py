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
    * If team column is NOT TGID -> you can "Move player to selected team"
    * ALWAYS available: "HC09-SAFE SWAP TRADE" (swap player data across teams WITHOUT changing TGID)

Run:
  python guiHC09.py
"""

import csv
import os
import re
import json
import shutil
import tempfile
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

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

def recent_file_display(path):
    """Show the save folder name (e.g. BLUS30128-CAREER-TEST) since every
    save file is literally named USR-DATA and wouldn't be distinguishable."""
    folder = os.path.basename(os.path.dirname(path))
    return folder or path
DB_TABLE_FILES = {
    "PLAY": "play.csv",
    "DRPK": "drpk.csv",
    "SLRI": "slri.csv",
    "TRVW": "trvw.csv",
    "COCH": "coch.csv",
    "GMVW": "gmvw.csv",
    "GMSK": "gmsk.csv",
    "CSKL": "cskl.csv",
}

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
    "33": "Free Agents", "1015": "Draft Class"
}

PLAYER_FIRST_NAME_CODE = "PFNA"
PLAYER_LAST_NAME_CODE = "PLNA"
PLAYER_POS_CODE = "PPOS"
PREFERRED_TEAM_COLS = ["TID", "TEAM", "TMID", "TGID"]  # TGID last as fallback

DRAFT_PICK_ID = "DPID"
DRAFT_PICK_NUM = "DPNM"
DRAFT_PICK_YEAR = "DPYO"

SALARY_CAP_KEY = "SCAD"
PLAYER_CONTRACT_COLS = [f"PSA{i}" for i in range(7)]
PLAYER_BONUS_COLS = [f"PSB{i}" for i in range(7)]
PLAYER_SALARY_MAX_VALUE = 16383
PLAYER_BONUS_MAX_VALUE = 8191
STAFF_SKPT_MAX_VALUE = 131071
AGE_COL = "PAGE"
YEARS_COL = "PYRP"

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
    "SKTD": (STAFF_SKILL_MIN_VALUE, STAFF_SKILL_MAX_VALUE), "SKTM": (STAFF_SKILL_MIN_VALUE, STAFF_SKILL_MAX_VALUE),
    "SKNG": (STAFF_SKILL_MIN_VALUE, STAFF_SKILL_MAX_VALUE), "SKNM": (STAFF_SKILL_MIN_VALUE, STAFF_SKILL_MAX_VALUE),
    "TSIE": (STAFF_SKILL_MIN_VALUE, STAFF_SKILL_MAX_VALUE), "TSIM": (STAFF_SKILL_MIN_VALUE, STAFF_SKILL_MAX_VALUE),
    "TSRH": (STAFF_SKILL_MIN_VALUE, STAFF_SKILL_MAX_VALUE), "TSRM": (STAFF_SKILL_MIN_VALUE, STAFF_SKILL_MAX_VALUE),
    "TSFR": (STAFF_SKILL_MIN_VALUE, STAFF_SKILL_MAX_VALUE), "TSFM": (STAFF_SKILL_MIN_VALUE, STAFF_SKILL_MAX_VALUE),
    **{f: (GM_SCOUTING_MIN_VALUE, GM_SCOUTING_MAX_VALUE) for f in GM_SCOUTING_FIELDS},
}

# Skill fields maxed out per staff type when "Set to Max" is clicked (besides SKPT).
# GM_SCOUTING_FIELDS deliberately excluded - their in-game effect is unknown (see note above).
GM_MAXABLE_SKILL_FIELDS = ["SKTD", "SKTM", "SKNG", "SKNM"]
TRAINER_MAXABLE_SKILL_FIELDS = ["TSIE", "TSIM", "TSRH", "TSRM", "TSFR", "TSFM"]
# Maxing SKPA and SKPF to 5 also maxes Performance (MIN(SKPA,SKPF) = 5).
# SKPX/SKSM/SKCM included alongside their current-value partners so maxing a
# coach also raises the cap on Play Call/Strategy/Chemistry, not just the
# current value (see STAFF_NUMERIC_FIELDS note above on their unverified status).
COACH_MAXABLE_SKILL_FIELDS = ["SKPC", "SKPX", "SKPA", "SKPF", "SKST", "SKSM", "SKCR", "SKCM"]

# =============================================================================
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
    "SKPA": "Perf. Input A", "SKPF": "Perf. Input B",
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

        self.team_col = None
        self.max_map = {}
        self.csv_formats = {}

        self.db_path = ""       # path to the .db / USR-DATA save file
        self._load_tmp_dir = "" # temp dir holding the CSVs exported from db_path

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

        tmp_dir = tempfile.mkdtemp(prefix="hc09_bridge_load_")
        self.run_bridge(["export", "--db", db_path, "--out", tmp_dir])

        self.db_path = db_path
        self._load_tmp_dir = tmp_dir

        self.play_path = os.path.join(tmp_dir, DB_TABLE_FILES["PLAY"])
        self.drpk_path = os.path.join(tmp_dir, DB_TABLE_FILES["DRPK"])
        self.slri_path = os.path.join(tmp_dir, DB_TABLE_FILES["SLRI"])
        self.trainer_path = os.path.join(tmp_dir, DB_TABLE_FILES["TRVW"])
        self.coach_path = os.path.join(tmp_dir, DB_TABLE_FILES["COCH"])
        self.gm_path = os.path.join(tmp_dir, DB_TABLE_FILES["GMVW"])
        self.gmsk_path = os.path.join(tmp_dir, DB_TABLE_FILES["GMSK"])
        self.cskl_path = os.path.join(tmp_dir, DB_TABLE_FILES["CSKL"])

        self._finish_load()

    def save_to_db(self):
        """Write current in-memory tables straight back into the .db save file."""
        if not self.db_path:
            raise ValueError("No save file loaded.")

        tmp_dir = tempfile.mkdtemp(prefix="hc09_bridge_save_")

        self._write_csv(os.path.join(tmp_dir, DB_TABLE_FILES["PLAY"]), self.players, self.player_headers)
        if self.picks:
            self._write_csv(os.path.join(tmp_dir, DB_TABLE_FILES["DRPK"]), self.picks, self.pick_headers)
        if self.salaries:
            self._write_csv(os.path.join(tmp_dir, DB_TABLE_FILES["SLRI"]), self.salaries, self.salary_headers)
        if self.trainers:
            self._write_csv(os.path.join(tmp_dir, DB_TABLE_FILES["TRVW"]), self.trainers, self.trainer_headers)
        if self.coaches:
            self._write_csv(os.path.join(tmp_dir, DB_TABLE_FILES["COCH"]), self.coaches, self.coach_headers)
        if self.gms:
            self._write_csv(os.path.join(tmp_dir, DB_TABLE_FILES["GMVW"]), self.gms, self.gm_headers)
        if self.gmsk:
            self._write_csv(os.path.join(tmp_dir, DB_TABLE_FILES["GMSK"]), self.gmsk, self.gmsk_headers)
        if self.cskl:
            self._write_csv(os.path.join(tmp_dir, DB_TABLE_FILES["CSKL"]), self.cskl, self.cskl_headers)

        backup_path = self.db_path + ".bak"
        shutil.copy2(self.db_path, backup_path)

        # No --out: save in place. (Passing --out equal to --db would hit a
        # clone-to-self race in HC09Helper.save() and corrupt the file.)
        self.run_bridge(["import", "--db", self.db_path, "--in", tmp_dir])

        shutil.rmtree(tmp_dir, ignore_errors=True)
        return backup_path

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
        self.players, self.player_headers = self.load_csv(self.play_path)
        self.picks, self.pick_headers = self.load_csv(self.drpk_path) if self.drpk_path else ([], [])
        self.salaries, self.salary_headers = self.load_csv(self.slri_path) if self.slri_path else ([], [])
        self.trainers, self.trainer_headers = self.load_csv(self.trainer_path) if self.trainer_path else ([], [])
        self.coaches, self.coach_headers = self.load_csv(self.coach_path) if self.coach_path else ([], [])
        self.gms, self.gm_headers = self.load_csv(self.gm_path) if self.gm_path else ([], [])
        self.gmsk, self.gmsk_headers = self.load_csv(self.gmsk_path) if self.gmsk_path else ([], [])
        self.cskl, self.cskl_headers = self.load_csv(self.cskl_path) if self.cskl_path else ([], [])

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
        if not self.team_col:
            return
        row[self.team_col] = str(tid)

    def _rows_by_position(self, table_rows, pnid):
        """Return {position_bucket: row} for a PPGR-linked table (GMSK or CSKL),
        keyed by each row's own PPGR field (see PPGR_TO_POSITION) - NOT by
        file/insertion order, which is confirmed inconsistent between records
        (e.g. Jauron's CSKL rows and Andrews' GMSK rows were stored in
        different physical orders despite using the same PPGR scheme)."""
        if not pnid:
            return {}
        result = {}
        for r in table_rows:
            if (r.get("PNid", "") or "").strip() != str(pnid):
                continue
            bucket = PPGR_TO_POSITION.get((r.get("PPGR", "") or "").strip())
            if bucket:
                result[bucket] = r
        return result

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
        self.title("HC09-SAFE SWAP TRADE (does not change TGID)")
        self.geometry("980x520")
        self.minsize(900, 480)
        self.parent = parent
        self.model = model

        self.team1 = tk.StringVar(value="33")
        self.team2 = tk.StringVar(value="1")

        self.idx1 = None  # real index into model.players
        self.idx2 = None

        self._build()

    def _build(self):
        top = ttk.Frame(self)
        top.pack(fill="x", padx=10, pady=10)

        warn = (
            "This trade swaps player DATA between two roster rows, but keeps TGID/IDs unchanged.\n"
            "That is the safest method when TGID is the only team column."
        )
        ttk.Label(top, text=warn).pack(anchor="w")

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, padx=10, pady=(0, 10))

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
        self._set_combo_to_tid(self.cmb_t1, "33")
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
        bottom.pack(fill="x", padx=10, pady=(0, 10))

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

        messagebox.showinfo("Trade complete", f"✅ HC09-SAFE SWAP TRADE COMPLETED\n\n{n1}  ⇄  {n2}")

        # Refresh the parent's views
        self.parent.refresh_players_for_team()
        self.parent.refresh_stats_for_player()
        self.parent.refresh_picks()


BASE_TITLE = "HC09 CSV Editor (GUI) - Safe Trades"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(BASE_TITLE)
        self.geometry("1320x820")
        self.minsize(1180, 700)

        self.model = CSVModel()
        self.dirty = False  # True whenever there are unsaved edits

        self.selected_team_id = tk.StringVar(value="")
        self.selected_player_index = None
        self.selected_stat_key = None
        self._player_index_map = []
        self._pick_index_map = []  # For acquire picks dropdown mapping
        self.contract_year_var = tk.StringVar(value="0")

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

    # ---------- UI layout ----------
    def _build_ui(self):
        top = ttk.Frame(self)
        top.pack(fill="x", padx=10, pady=8)

        ttk.Button(top, text="Load Save File", command=self.on_load).pack(side="left")
        ttk.Button(top, text="Save to File", command=self.on_save).pack(side="left", padx=(8, 0))
        ttk.Button(top, text="Reload from File", command=self.on_reload).pack(side="left", padx=(8, 0))

        ttk.Separator(top, orient="vertical").pack(side="left", fill="y", padx=10)

        ttk.Label(top, text="Recent:").pack(side="left")
        self.recent_files_var = tk.StringVar()
        self.cmb_recent = ttk.Combobox(top, width=26, state="readonly", textvariable=self.recent_files_var)
        self.cmb_recent.pack(side="left", padx=(4, 0))
        self.cmb_recent.bind("<<ComboboxSelected>>", self.on_load_recent)
        self._recent_display_to_path = {}
        self._refresh_recent_files_ui(load_recent_files())

        ttk.Separator(top, orient="vertical").pack(side="left", fill="y", padx=10)

        ttk.Button(top, text="HC09-SAFE SWAP TRADE", command=self.on_open_swap_trade).pack(side="left")
        self.btn_move_trade = ttk.Button(top, text="Move Player → Selected Team", command=self.on_move_trade_to_selected_team)
        self.btn_move_trade.pack(side="left", padx=(8, 0))

        self.lbl_status = ttk.Label(top, text="Load play.csv to begin.")
        self.lbl_status.pack(side="left", padx=12)

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)

        self.tab_players = ttk.Frame(self.notebook)
        self.tab_picks = ttk.Frame(self.notebook)
        self.tab_cap = ttk.Frame(self.notebook)

        self.notebook.add(self.tab_players, text="Players + Stats")
        self.notebook.add(self.tab_picks, text="Draft Picks")
        self.notebook.add(self.tab_cap, text="Salary Cap")

        self._build_players_tab()
        self._build_picks_tab()
        self._build_cap_tab()
        # New staff tabs
        self._build_trainer_tab()
        self._build_coach_tab()
        self._build_gm_tab()

    def _build_players_tab(self):
        root = self.tab_players

        # Left: Teams
        left = ttk.Frame(root)
        left.pack(side="left", fill="y", padx=(0, 8), pady=6)

        ttk.Label(left, text="Teams").pack(anchor="w")
        self.lst_teams = tk.Listbox(left, height=28, exportselection=False)
        self.lst_teams.pack(fill="y")
        self.lst_teams.bind("<<ListboxSelect>>", self.on_team_select)
        ttk.Button(left, text="Set Team Bonus Min", command=self.on_set_team_bonus_min).pack(anchor="w", pady=(8, 0))
        ttk.Button(left, text="Max Team Staff", command=self.on_max_team_staff_skpt).pack(anchor="w", pady=(6, 0))

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

        self.lbl_players_header = ttk.Label(mid, text="Players on Team (play.csv)")
        self.lbl_players_header.pack(anchor="w")
        self.lst_players = tk.Listbox(mid, height=28, exportselection=False)
        self.lst_players.pack(fill="both", expand=True)
        self.lst_players.bind("<<ListboxSelect>>", self.on_player_select)

        # Right: Name editor + Stats editor + Raw editor
        right = ttk.Frame(root)
        right.pack(side="left", fill="both", expand=True, pady=6)

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

        ttk.Label(right, text="Stats (described only)").pack(anchor="w")

        cols = ("stat", "cur_col", "cur_val", "max_col", "max_val")
        self.tree_stats = ttk.Treeview(right, columns=cols, show="headings", height=11)
        for c, w in zip(cols, [260, 90, 80, 90, 80]):
            self.tree_stats.heading(c, text=c)
            self.tree_stats.column(c, width=w, anchor="w")
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

        contract = ttk.LabelFrame(right, text="Contract Editor (PSA#/PSB# from play.csv)")
        contract.pack(fill="x", pady=(6, 0))

        ttk.Label(contract, text="Year").grid(row=0, column=0, sticky="w")
        self.cmb_contract_year = ttk.Combobox(
            contract,
            width=4,
            state="readonly",
            textvariable=self.contract_year_var,
            values=[str(i) for i in range(7)]
        )
        self.cmb_contract_year.grid(row=0, column=1, sticky="w", padx=6)
        self.cmb_contract_year.bind("<<ComboboxSelected>>", lambda e: self.refresh_contract_editor())
        self.cmb_contract_year.current(0)

        ttk.Label(contract, text="Salary").grid(row=0, column=2, sticky="w", padx=(10, 0))
        self.ent_contract_salary = ttk.Entry(contract, width=9)
        self.ent_contract_salary.grid(row=0, column=3, sticky="w", padx=4)

        ttk.Label(contract, text="Bonus").grid(row=0, column=4, sticky="w", padx=(10, 0))
        self.ent_contract_bonus = ttk.Entry(contract, width=9)
        self.ent_contract_bonus.grid(row=0, column=5, sticky="w", padx=4)

        ttk.Button(contract, text="Apply Salary/Bonus", command=self.on_apply_contract).grid(
            row=0, column=6, sticky="w", padx=(8, 0)
        )

        ttk.Button(contract, text="Set All Salary Min", command=self.set_contract_salary_to_min).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(4, 0)
        )
        ttk.Button(contract, text="Set All Bonus Min", command=self.set_contract_bonus_to_min).grid(
            row=1, column=2, columnspan=2, sticky="w", pady=(4, 0)
        )

        self.lbl_contract_cols = ttk.Label(contract, text="Year 0 uses PSA0 / PSB0")
        self.lbl_contract_cols.grid(row=2, column=0, columnspan=7, sticky="w", pady=(4, 0))

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

    def _build_picks_tab(self):
        root = self.tab_picks
        top = ttk.Frame(root)
        top.pack(fill="x", padx=10, pady=10)

        ttk.Label(top, text="Draft Picks (drpk.csv)").pack(side="left")
        ttk.Button(top, text="Refresh", command=self.refresh_picks).pack(side="left", padx=8)

        cols = ("team", "pick", "year_offset")
        self.tree_picks = ttk.Treeview(root, columns=cols, show="headings", height=22)
        for c, w in zip(cols, [320, 120, 120]):
            self.tree_picks.heading(c, text=c)
            self.tree_picks.column(c, width=w, anchor="w")
        self.tree_picks.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        bottom = ttk.Frame(root)
        bottom.pack(fill="x", padx=10, pady=(0, 10))

        ttk.Label(bottom, text="Acquire picks: From Team").pack(side="left")
        self.cmb_pick_from = ttk.Combobox(bottom, width=24, state="readonly")
        team_vals = [f"{tid}: {name}" for tid, name in TEAM_NAMES.items()]
        self.cmb_pick_from["values"] = team_vals
        self.cmb_pick_from.pack(side="left", padx=6)
        self.cmb_pick_from.bind("<<ComboboxSelected>>", self._on_from_team_changed)

        ttk.Label(bottom, text="→ To Team").pack(side="left", padx=(10, 0))
        self.cmb_pick_to = ttk.Combobox(bottom, width=24, state="readonly")
        self.cmb_pick_to["values"] = team_vals
        self.cmb_pick_to.pack(side="left", padx=6)

        ttk.Label(bottom, text="Pick(s)").pack(side="left", padx=(10, 0))
        self.cmb_pick_idxs = ttk.Combobox(bottom, width=30, state="readonly")
        self.cmb_pick_idxs.pack(side="left", padx=6)

        ttk.Button(bottom, text="Acquire", command=self.on_acquire_picks).pack(side="left", padx=8)

    def _build_cap_tab(self):
        root = self.tab_cap
        frm = ttk.Frame(root)
        frm.pack(fill="x", padx=10, pady=14)

        ttk.Label(frm, text="Salary Cap (slri.csv)").grid(row=0, column=0, sticky="w")
        self.ent_cap = ttk.Entry(frm, width=18)
        self.ent_cap.grid(row=0, column=1, sticky="w", padx=8)
        ttk.Button(frm, text="Set to Max", command=self.set_cap_to_max).grid(row=0, column=2, sticky="w", padx=4)
        ttk.Button(frm, text="Click to apply changes (max 260,000,000 - higher freezes the game)", command=self.on_apply_cap).grid(row=0, column=3, sticky="w", padx=4)

        self.lbl_cap_status = ttk.Label(root, text="Load slri.csv to edit cap.")
        self.lbl_cap_status.pack(anchor="w", padx=10, pady=(8, 0))

    # ---------- Staff Tabs (Trainer / Coach / GM) ----------
    def _build_trainer_tab(self):
        root = ttk.Frame(self.notebook)
        self.tab_trainer = root
        self.notebook.add(self.tab_trainer, text="Trainer")

        top = ttk.Frame(root)
        top.pack(fill="x", padx=10, pady=10)
        ttk.Label(top, text="Trainer (trvw.csv)").pack(side="left")
        ttk.Button(top, text="Refresh", command=self.refresh_trainer).pack(side="left", padx=8)
        ttk.Button(top, text="Max Selected Trainer's Stats", command=self.on_max_selected_trainer).pack(side="left", padx=(8, 0))

        help_text = (
            "Injury Eval (TSIE/TSIM): How accurately the trainer assesses recovery length for a player's injury.\n\n"
            "Rehab (TSRH/TSRM): How long it takes injured players to recover from all types of injuries.\n\n"
            "Fatigue Rec (TSFR/TSFM): How efficiently the trainer assists players in recovering fatigue.\n\n"
            "Each skill is a Cur/Max pair (double-click a cell to edit). In-game 'Level' shows once Cur == Max "
            "('Potential Reached'). Range is 1-5."
        )
        help_frame = ttk.Frame(root)
        help_frame.pack(fill="x", padx=10)
        tk.Label(help_frame, text=help_text, wraplength=1000, justify="left", fg="gray").pack(fill="x", pady=(6, 0))

        self.tree_trainer = ttk.Treeview(root, show="headings", height=20)
        self.tree_trainer.pack(fill="both", expand=True, padx=10, pady=(0, 6))

        # Bottom editor for SKPT
        btm = ttk.Frame(root)
        btm.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Label(btm, text="Selected SKPT:").pack(side="left")
        self.ent_trainer_skpt = ttk.Entry(btm, width=12)
        self.ent_trainer_skpt.pack(side="left", padx=(6, 8))
        ttk.Button(btm, text="Set to Max", command=self.set_trainer_skpt_to_max).pack(side="left", padx=4)
        ttk.Button(btm, text="Apply SKPT", command=self._apply_trainer_skpt).pack(side="left")
        self.tree_trainer.bind("<<TreeviewSelect>>", lambda e: self._on_trainer_select())
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

        # Search controls for coach first/last name
        self.coach_search_var = tk.StringVar()
        ttk.Label(top, text="Search (First Last):").pack(side="left", padx=(12, 4))
        self.ent_coach_search = ttk.Entry(top, textvariable=self.coach_search_var, width=20)
        self.ent_coach_search.pack(side="left")
        ttk.Button(top, text="Find", command=lambda: self.refresh_coach()).pack(side="left", padx=(6, 4))
        ttk.Button(top, text="Clear", command=lambda: (self.coach_search_var.set(""), self.refresh_coach())).pack(side="left")

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
        tk.Label(help_frame, text=help_text, wraplength=1000, justify="left", fg="gray").pack(fill="x", pady=(6,0))

        self.tree_coach = ttk.Treeview(root, show="headings", height=20)
        self.tree_coach.pack(fill="both", expand=True, padx=10, pady=(0, 6))

        # Bottom editor for SKPT
        btm = ttk.Frame(root)
        btm.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Label(btm, text="Selected SKPT:").pack(side="left")
        self.ent_coach_skpt = ttk.Entry(btm, width=12)
        self.ent_coach_skpt.pack(side="left", padx=(6, 8))
        ttk.Button(btm, text="Set to Max", command=self.set_coach_skpt_to_max).pack(side="left", padx=4)
        ttk.Button(btm, text="Apply SKPT", command=self._apply_coach_skpt).pack(side="left")
        self.tree_coach.bind("<<TreeviewSelect>>", lambda e: self._on_coach_select())
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

        help_text = (
            "Trade/Contract, Potential Eval (PE), and Rookie Scouting (RS) - each per position - are all "
            "editable below, double-click a cell, or use 'Max Selected GM's Stats' to max everything at once "
            "for the selected GM. Blank PE/RS cells mean this GM has no data yet. If current > max, the game "
            "clamps the displayed current value down to max."
        )
        help_frame = ttk.Frame(root)
        help_frame.pack(fill="x", padx=10)
        tk.Label(help_frame, text=help_text, wraplength=1000, justify="left", fg="gray").pack(fill="x", pady=(6, 0))

        self.tree_gm = ttk.Treeview(root, show="headings", height=20)
        self.tree_gm.pack(fill="both", expand=True, padx=10, pady=(0, 6))

        # Bottom editor for SKPT
        btm = ttk.Frame(root)
        btm.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Label(btm, text="Selected SKPT:").pack(side="left")
        self.ent_gm_skpt = ttk.Entry(btm, width=12)
        self.ent_gm_skpt.pack(side="left", padx=(6, 8))
        ttk.Button(btm, text="Set to Max", command=self.set_gm_skpt_to_max).pack(side="left", padx=4)
        ttk.Button(btm, text="Apply SKPT", command=self._apply_gm_skpt).pack(side="left")
        self.tree_gm.bind("<<TreeviewSelect>>", lambda e: self._on_gm_select())
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

    def _load_db_path(self, db_path):
        """Shared load logic used by Load Save File, Reload from File, and the
        recent-files list, so all three stay in sync."""
        self.set_busy(f"Loading {recent_file_display(db_path)}...")
        try:
            self.model.load_all_from_db(db_path)
        finally:
            self.clear_busy()

        if not self.model.team_col:
            messagebox.showwarning(
                "Team Column Not Found",
                "Could not detect a team column in the player table (case-sensitive search: TID/TEAM/TMID/TGID)."
            )

        self.lbl_status.configure(
            text=f"Loaded: {recent_file_display(db_path)}  | TeamCol={self.model.team_col or 'N/A'}  | Players={len(self.model.players)}"
        )

        # enable/disable move-trade button
        # If team col is TGID, we do NOT want to change it (your requirement).
        if (self.model.team_col or "") == "TGID":
            self.btn_move_trade.state(["disabled"])
        else:
            self.btn_move_trade.state(["!disabled"])

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

            self._load_db_path(db_path)

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
            self._load_db_path(self.model.db_path)
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
            self._load_db_path(path)
        except Exception as e:
            self.clear_busy()
            messagebox.showerror("Load Error", str(e))

    def _refresh_recent_files_ui(self, recents):
        self._recent_display_to_path = {recent_file_display(p): p for p in recents}
        values = list(self._recent_display_to_path.keys())
        self.cmb_recent["values"] = values
        if values:
            self.recent_files_var.set(values[0])

    def on_save(self):
        try:
            if not self.model.players:
                messagebox.showinfo("Nothing to save", "Load a save file first.")
                return

            self.set_busy("Saving...")
            try:
                backup_path = self.model.save_to_db()
            finally:
                self.clear_busy()

            self.clear_dirty()
            self.lbl_status.configure(
                text=f"Saved: {recent_file_display(self.model.db_path)}  | TeamCol={self.model.team_col or 'N/A'}  | Players={len(self.model.players)}"
            )

            messagebox.showinfo(
                "Saved",
                f"Changes written directly to:\n{self.model.db_path}\n\n"
                f"Backup of the previous version saved to:\n{backup_path}"
            )
        except Exception as e:
            self.clear_busy()
            messagebox.showerror("Save Error", str(e))

    # ---------- Teams / Players ----------
    def refresh_teams(self):
        self.lst_teams.delete(0, tk.END)
        for tid, name in TEAM_NAMES.items():
            self.lst_teams.insert(tk.END, f"{tid}: {name}")

    def _select_default_team(self):
        target = "33"  # Free Agents
        idx = None
        for i in range(self.lst_teams.size()):
            if self.lst_teams.get(i).startswith(target + ":"):
                idx = i
                break
        if idx is None and self.lst_teams.size() > 0:
            idx = 0
        if idx is not None:
            self.lst_teams.selection_clear(0, tk.END)
            self.lst_teams.selection_set(idx)
            self.lst_teams.activate(idx)
            self.on_team_select()

    def on_team_select(self, event=None):
        sel = self.lst_teams.curselection()
        if not sel:
            return
        txt = self.lst_teams.get(sel[0])
        tid = txt.split(":", 1)[0].strip()
        self.selected_team_id.set(tid)
        self.refresh_players_for_team()

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
            f"Set PSB0 through PSB6 to 0 for every player on {team_name}?"
        )
        if not ok:
            return

        headers = set(self.model.player_headers or [])
        team_col = self.model.team_col
        if not team_col:
            messagebox.showwarning("No team column", "Team column not detected in play.csv.")
            return

        updated_players = 0
        for row in self.model.players:
            if (row.get(team_col, "") or "").strip() != tid:
                continue
            for col in PLAYER_BONUS_COLS:
                if col in headers:
                    row[col] = "0"
            updated_players += 1

        self.refresh_players_for_team()
        self.refresh_contract_editor()
        messagebox.showinfo(
            "Team bonus updated",
            f"Set PSB0 through PSB6 to 0 for {updated_players} player(s) on {team_name}."
        )

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

    def refresh_players_for_team(self):
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

        # Sort by position (custom order), then first name, then last name
        filtered = sorted(filtered, key=lambda item: (
            POSITION_ORDER.get((item[1].get(PLAYER_POS_CODE, "") or "").strip(), 999),
            item[1].get(PLAYER_FIRST_NAME_CODE, "").strip(),
            item[1].get(PLAYER_LAST_NAME_CODE, "").strip()
        ))

        self._player_index_map = [i for i, _ in filtered]

        for i, r in filtered:
            pos = self.model.player_pos(r)
            name = self.model.player_name(r)
            age = (r.get(AGE_COL, "") or "").strip()
            yrs = (r.get(YEARS_COL, "") or "").strip()
            self.lst_players.insert(tk.END, f"{pos}  {name}   (Age:{age or '-'} Yrs:{yrs or '-'})")

        if self.lst_players.size() > 0:
            self.lst_players.selection_set(0)
            self.lst_players.activate(0)
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

        # Prefill contract editor
        self.refresh_contract_editor()

        # Prefill raw column value
        self.on_raw_column_changed()

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
    def _current_contract_columns(self):
        year_idx = self.cmb_contract_year.get().strip() if hasattr(self, "cmb_contract_year") else "0"
        if year_idx not in [str(i) for i in range(7)]:
            year_idx = "0"
        return f"PSA{year_idx}", f"PSB{year_idx}"

    def refresh_contract_editor(self):
        salary_col, bonus_col = self._current_contract_columns()
        self.lbl_contract_cols.configure(text=f"Year {self.cmb_contract_year.get() or '0'} uses {salary_col} / {bonus_col}")

        self.ent_contract_salary.delete(0, tk.END)
        self.ent_contract_bonus.delete(0, tk.END)

        if self.selected_player_index is None:
            return

        row = self.model.players[self.selected_player_index]
        self.ent_contract_salary.insert(0, (row.get(salary_col, "") or "").strip())
        self.ent_contract_bonus.insert(0, (row.get(bonus_col, "") or "").strip())

    def _parse_contract_number(self, raw):
        try:
            return int(raw)
        except ValueError:
            return int(float(raw))

    def set_contract_salary_to_min(self):
        if self.selected_player_index is None:
            messagebox.showinfo("No player", "Select a player first.")
            return
        row = self.model.players[self.selected_player_index]
        headers = set(self.model.player_headers or [])
        updated = False
        for col in PLAYER_CONTRACT_COLS:
            if col in headers:
                row[col] = "0"
                updated = True
        self.refresh_contract_editor()
        if updated:
            messagebox.showinfo("Salary updated", "Set PSA0 through PSA6 to 0 for the selected player.")

    def set_contract_bonus_to_min(self):
        if self.selected_player_index is None:
            messagebox.showinfo("No player", "Select a player first.")
            return
        row = self.model.players[self.selected_player_index]
        headers = set(self.model.player_headers or [])
        updated = False
        for col in PLAYER_BONUS_COLS:
            if col in headers:
                row[col] = "0"
                updated = True
        self.refresh_contract_editor()
        if updated:
            messagebox.showinfo("Bonus updated", "Set PSB0 through PSB6 to 0 for the selected player.")

    def on_apply_contract(self):
        if self.selected_player_index is None:
            messagebox.showinfo("No player", "Select a player first.")
            return

        salary_col, bonus_col = self._current_contract_columns()
        headers = set(self.model.player_headers or [])
        if salary_col not in headers or bonus_col not in headers:
            messagebox.showwarning(
                "Missing columns",
                f"Could not find {salary_col} and/or {bonus_col} in play.csv."
            )
            return

        salary_raw = self.ent_contract_salary.get().strip()
        bonus_raw = self.ent_contract_bonus.get().strip()
        if salary_raw == "" and bonus_raw == "":
            messagebox.showwarning("Nothing to apply", "Enter a salary and/or bonus value.")
            return

        row = self.model.players[self.selected_player_index]

        try:
            updates = []
            if salary_raw != "":
                salary_val = self._parse_contract_number(salary_raw)
                salary_val = max(0, min(PLAYER_SALARY_MAX_VALUE, salary_val))
                row[salary_col] = str(salary_val)
                updates.append(f"{salary_col}={salary_val}")

            if bonus_raw != "":
                bonus_val = self._parse_contract_number(bonus_raw)
                bonus_val = max(0, min(PLAYER_BONUS_MAX_VALUE, bonus_val))
                row[bonus_col] = str(bonus_val)
                updates.append(f"{bonus_col}={bonus_val}")

            self.refresh_contract_editor()
            self.refresh_players_for_team()
            self.refresh_stats_for_player()
            messagebox.showinfo("Contract updated", "Updated " + ", ".join(updates))
        except Exception as e:
            messagebox.showerror("Contract Error", str(e))

    # ---------- Trades ----------
    def on_open_swap_trade(self):
        if not self.model.players:
            messagebox.showinfo("Load first", "Load play.csv first.")
            return
        SwapTradeDialog(self, self.model)

    def on_move_trade_to_selected_team(self):
        """
        Only works if we have a non-TGID team column.
        Your export: TGID only -> button disabled.
        """
        if not self.model.players or self.selected_player_index is None:
            return
        if not self.model.team_col:
            messagebox.showwarning("No team column", "Team column not detected.")
            return
        if self.model.team_col == "TGID":
            messagebox.showwarning(
                "TGID-only file",
                "Your play.csv only has TGID as the team column.\n\n"
                "Use 'HC09-SAFE SWAP TRADE' instead (it does NOT change TGID)."
            )
            return

        dest_tid = self.selected_team_id.get()
        if not dest_tid:
            return

        r = self.model.players[self.selected_player_index]
        src_tid = self.model.player_team_id(r)

        if src_tid == dest_tid:
            messagebox.showinfo("No change", "Player already on that team.")
            return

        self.model.set_player_team_id(r, dest_tid)
        self.refresh_players_for_team()

    # ---------- Picks ----------
    def refresh_picks(self):
        for iid in self.tree_picks.get_children():
            self.tree_picks.delete(iid)
        if not self.model.picks:
            self.cmb_pick_from.set("")
            self.cmb_pick_to.set("")
            self.cmb_pick_idxs.set("")
            self.cmb_pick_idxs["values"] = []
            return

        # Sort picks by team, then by year offset (0, 1, 3...), then by round
        sorted_picks = sorted(
            enumerate(self.model.picks),
            key=lambda item: (
                int((item[1].get(DRAFT_PICK_ID, "") or "").strip() or "99999"),  # Team ID first
                y if (y := safe_int(item[1].get(DRAFT_PICK_YEAR, ""))) is not None else 999,  # Year offset (0, 1, 3...)
                (safe_int(item[1].get(DRAFT_PICK_NUM, "")) or 0) // 32  # Round number
            )
        )

        # Create a mapping of year offsets to sequential display numbers (1, 2, 3...)
        unique_years = sorted(set(
            safe_int(p.get(DRAFT_PICK_YEAR, "")) 
            for _, p in sorted_picks 
            if safe_int(p.get(DRAFT_PICK_YEAR, "")) is not None
        ))
        year_map = {y: i + 1 for i, y in enumerate(unique_years)}

        for i, (orig_idx, p) in enumerate(sorted_picks):
            tid = (p.get(DRAFT_PICK_ID, "") or "").strip()
            pick_num = safe_int(p.get(DRAFT_PICK_NUM, ""))
            year_off = safe_int(p.get(DRAFT_PICK_YEAR, ""))

            pick_disp = "-" if pick_num is None else str(pick_num + 1)
            team_name = TEAM_NAMES.get(tid, tid or "Unknown")
            round_num = (pick_num + 1 - 1) // 32 + 1 if pick_num is not None else "-"
            
            # Display year using sequential mapping: 0→1, 1→2, 3→3, etc.
            year_display = year_map.get(year_off, "-") if year_off is not None else "-"

            self.tree_picks.insert("", tk.END, iid=str(orig_idx),
                                  values=(f"{tid}: {team_name}", f"R{round_num}:{pick_disp}", str(year_display)))
        
        # Reset dropdowns
        if self.cmb_pick_from["values"]:
            self.cmb_pick_from.current(0)
            self._on_from_team_changed()

    def _on_from_team_changed(self, event=None):
        """Populate picks dropdown when 'from team' is selected."""
        from_combo_val = self.cmb_pick_from.get()
        if not from_combo_val or ":" not in from_combo_val:
            self.cmb_pick_idxs["values"] = []
            return

        from_tid = from_combo_val.split(":", 1)[0].strip()
        
        # Get all picks for this team
        team_picks_raw = []
        for model_idx, p in enumerate(self.model.picks):
            if (p.get(DRAFT_PICK_ID, "") or "").strip() == from_tid:
                pick_num = safe_int(p.get(DRAFT_PICK_NUM, ""))
                year_off = safe_int(p.get(DRAFT_PICK_YEAR, ""))
                round_num = (pick_num + 1 - 1) // 32 + 1 if pick_num is not None else 999
                team_picks_raw.append((model_idx, pick_num, year_off, round_num))
        
        # Sort by year offset (ascending = most recent first), then round, then pick number
        # This ensures consistent ordering: all Yr:0 first, then Yr:1, etc.
        team_picks_raw.sort(key=lambda x: (
            y if (y := x[2]) is not None else 999,  # year_off
            x[3],  # round_num
            p if (p := x[1]) is not None else 999  # pick_num
        ))
        
        # Create a mapping of year offsets to sequential display numbers (1, 2, 3...)
        unique_years = sorted(set(y for _, _, y, _ in team_picks_raw if y is not None))
        year_map = {y: i + 1 for i, y in enumerate(unique_years)}
        
        # Create display list with indexes and store model indices
        pick_displays = []
        self._pick_index_map = []  # Store model indices for later reference
        for local_idx, (model_idx, pick_num, year_off, round_num) in enumerate(team_picks_raw):
            # Display year using sequential mapping: 0→1, 1→2, 3→3, etc.
            year_display = year_map.get(year_off, "?") if year_off is not None else "?"
            pick_display = f"R{round_num}:{pick_num + 1 if pick_num is not None else '-'} (Yr:{year_display})  [Idx:{local_idx}]"
            pick_displays.append(pick_display)
            self._pick_index_map.append(model_idx)  # Store the actual model index
        
        self.cmb_pick_idxs["values"] = pick_displays
        if pick_displays:
            self.cmb_pick_idxs.current(0)

    def on_acquire_picks(self):
        if not self.model.picks:
            messagebox.showinfo("No picks", "Load drpk.csv to edit picks.")
            return

        from_combo_val = self.cmb_pick_from.get()
        to_combo_val = self.cmb_pick_to.get()
        pick_display = self.cmb_pick_idxs.get()

        if not from_combo_val or not to_combo_val or not pick_display:
            messagebox.showwarning("Missing selection", "Select from team, to team, and pick(s).")
            return

        from_tid = from_combo_val.split(":", 1)[0].strip() if ":" in from_combo_val else from_combo_val
        to_tid = to_combo_val.split(":", 1)[0].strip() if ":" in to_combo_val else to_combo_val

        # Get the current index from the dropdown
        current_display_idx = self.cmb_pick_idxs.current()
        if current_display_idx < 0 or current_display_idx >= len(self._pick_index_map):
            messagebox.showwarning("Invalid selection", "Please select a valid pick.")
            return

        # Get the actual model index from the mapping
        model_idx = self._pick_index_map[current_display_idx]

        # Modify the pick directly in model.picks
        self.model.picks[model_idx][DRAFT_PICK_ID] = to_tid

        messagebox.showinfo("Acquired", f"Moved pick from {from_tid} → {to_tid}")
        self.refresh_picks()
        self._on_from_team_changed()  # Refresh picks dropdown

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
            tree.column(h, width=140, anchor="w")

        for i, r in enumerate(rows):
            vals = [ (r.get(h, "") or "") for h in headers ]
            tree.insert("", tk.END, iid=str(i), values=vals)

    def refresh_trainer(self):
        # Show TGID, SKPT, and confirmed skill fields (Injury Eval/Rehab/Fatigue Recovery) if present
        desired = ["TGID", "SKPT", "TSIE", "TSIM", "TSRH", "TSRM", "TSFR", "TSFM"]
        headers = [h for h in desired if h in (self.model.trainer_headers or [])]
        if not headers:
            self._populate_tree_with_rows(self.tree_trainer, self.model.trainer_headers, self.model.trainers)
            return

        # Prepare rows as (model_idx, row) for sorting
        rows = list(enumerate(self.model.trainers))

        # Sort by TGID if present, numeric when possible
        if "TGID" in (self.model.trainer_headers or []):
            def tg_key(ir):
                _, r = ir
                tid = (r.get("TGID", "") or "").strip()
                tnum = safe_int(tid)
                return (0, tnum) if tnum is not None else (1, tid)
            rows = sorted(rows, key=tg_key)

        # Clear and set columns
        for iid in self.tree_trainer.get_children():
            self.tree_trainer.delete(iid)

        self.tree_trainer["columns"] = headers
        for h in headers:
            self.tree_trainer.heading(h, text=STAFF_FIELD_LABELS.get(h, h))
            self.tree_trainer.column(h, width=110 if h in STAFF_FIELD_LABELS else 160, anchor="w")

        for idx, r in rows:
            vals = []
            for h in headers:
                if h == "TGID":
                    tid = (r.get("TGID", "") or "").strip()
                    vals.append(f"{tid}: {TEAM_NAMES.get(tid, tid)}" if tid else "")
                else:
                    vals.append((r.get(h, "") or ""))
            self.tree_trainer.insert("", tk.END, iid=str(idx), values=vals)

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
        row = self.model.trainers[idx]
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

    def on_max_selected_gm(self):
        """Max out ALL of the selected GM's stats in one click: Trade, Contract, and
        Potential Evaluation + Rookie Scouting (for whichever position buckets this GM has data for)."""
        sel = self.tree_gm.selection()
        if not sel:
            messagebox.showinfo("No selection", "Select a GM row first.")
            return
        iid = self._max_out_staff_skills(self.tree_gm, self.model.gms, GM_MAXABLE_SKILL_FIELDS)
        self._max_out_gm_potential_eval(int(sel[0]))
        self.refresh_gm()
        self._reselect(self.tree_gm, iid)

    def on_max_selected_trainer(self):
        """Max out ALL of the selected trainer's stats: Injury Eval, Rehab, Fatigue Rec."""
        sel = self.tree_trainer.selection()
        if not sel:
            messagebox.showinfo("No selection", "Select a trainer row first.")
            return
        iid = self._max_out_staff_skills(self.tree_trainer, self.model.trainers, TRAINER_MAXABLE_SKILL_FIELDS)
        self.refresh_trainer()
        self._reselect(self.tree_trainer, iid)

    def on_max_selected_coach(self):
        """Max out ALL of this coach's confirmed stats: Play Call (SKPC/SKPX), Strategy
        (SKST/SKSM), Team Chemistry (SKCR/SKCM), Performance (MIN(SKPA, SKPF), so setting
        both to 5 maxes it), and Physical/Intangible/Learning Development for all 10
        position buckets. See the investigation log above COACH_MAXABLE_SKILL_FIELDS."""
        sel = self.tree_coach.selection()
        if not sel:
            messagebox.showinfo("No selection", "Select a coach row first.")
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
        desired = ["TGID", "CFNM", "CLNM", "SKPT", "SKPC", "SKPX", "SKST", "SKSM", "SKCR", "SKCM", "SKPA", "SKPF"]
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
        for iid in self.tree_coach.get_children():
            self.tree_coach.delete(iid)

        self.tree_coach["columns"] = headers or []
        for h in headers or []:
            self.tree_coach.heading(h, text=STAFF_FIELD_LABELS.get(h, h))
            self.tree_coach.column(h, width=70 if h in COACH_DEV_COLUMNS else 140, anchor="w")

        # Insert rows using original model indices as iids
        for idx, r in rows:
            vals = []
            dev_rows = self.model.get_coach_development_rows(r.get("PNid")) if show_dev else {}
            for h in headers or []:
                if h == "TGID":
                    tid = (r.get("TGID", "") or "").strip()
                    vals.append(f"{tid}: {TEAM_NAMES.get(tid, tid)}" if tid else "")
                elif h in COACH_DEV_COLUMNS:
                    cat, bucket, is_max = parse_dev_column(h)
                    cur_field, max_field, _name = COACH_DEV_CATEGORIES[cat]
                    row = dev_rows.get(bucket)
                    vals.append(row.get(max_field if is_max else cur_field, "") if row else "")
                else:
                    vals.append((r.get(h, "") or ""))
            self.tree_coach.insert("", tk.END, iid=str(idx), values=vals)

    def _on_coach_select(self):
        sel = self.tree_coach.selection()
        if not sel:
            return
        iid = sel[0]
        try:
            idx = int(iid)
        except Exception:
            return
        row = self.model.coaches[idx]
        sk = row.get("SKPT") if row is not None else None
        self.ent_coach_skpt.delete(0, tk.END)
        if sk is not None:
            self.ent_coach_skpt.insert(0, str(sk))

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

        # Sort by TGID if present, numeric when possible
        if "TGID" in (self.model.gm_headers or []):
            def tg_key(ir):
                _, r = ir
                tid = (r.get("TGID", "") or "").strip()
                tnum = safe_int(tid)
                return (0, tnum) if tnum is not None else (1, tid)
            rows = sorted(rows, key=tg_key)

        # Clear and set columns
        for iid in self.tree_gm.get_children():
            self.tree_gm.delete(iid)

        self.tree_gm["columns"] = headers
        for h in headers:
            self.tree_gm.heading(h, text=STAFF_FIELD_LABELS.get(h, h))
            is_bucket_col = h in GM_POTENTIAL_EVAL_COLUMNS or h in GM_ROOKIE_SCOUTING_COLUMNS
            self.tree_gm.column(h, width=70 if is_bucket_col else (110 if h in STAFF_FIELD_LABELS else 160), anchor="w")

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
        is_pe_column = tree is self.tree_gm and parse_pe_column(colname) is not None
        is_rs_column = tree is self.tree_gm and parse_rs_column(colname) is not None
        is_dev_column = tree is self.tree_coach and parse_dev_column(colname) is not None
        # Allow editing any known staff numeric column (SKPT, coach 1-7 fields, GM/trainer skill pairs)
        # or a GM Potential Evaluation/Rookie Scouting or Coach Development column (each lives in a
        # different table, handled specially below).
        if not is_pe_column and not is_rs_column and not is_dev_column and colname not in STAFF_NUMERIC_FIELDS:
            return

        bbox = tree.bbox(rowid, column=col)
        if not bbox:
            return
        x, y, w, h = bbox

        # Create entry overlay
        entry = ttk.Entry(tree)
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
            self.lbl_cap_status.configure(text=f"Updated to {v}")
            
            # Show result message
            if orig_v != v:
                messagebox.showinfo("Clamped", f"Value {orig_v} was clamped to {v}. Click 'Save' to write to file.")
            else:
                messagebox.showinfo("Updated", f"Salary cap set to {v}. Click 'Save' to write to file.")
            
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
    "set_contract_salary_to_min", "set_contract_bonus_to_min", "on_apply_contract",
    "on_move_trade_to_selected_team", "on_acquire_picks", "on_set_team_bonus_min",
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
