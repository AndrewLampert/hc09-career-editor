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
import json
import random
import shutil
import tempfile
import threading
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
}

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
        self.team_path = os.path.join(tmp_dir, DB_TABLE_FILES["TEAM"])
        self.cinf_path = os.path.join(tmp_dir, DB_TABLE_FILES["cINF"])

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
        if self.team:
            self._write_csv(os.path.join(tmp_dir, DB_TABLE_FILES["TEAM"]), self.team, self.team_headers)
        if self.cinf:
            self._write_csv(os.path.join(tmp_dir, DB_TABLE_FILES["cINF"]), self.cinf, self.cinf_headers)

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
        self.team, self.team_headers = self.load_csv(self.team_path) if self.team_path else ([], [])
        self.cinf, self.cinf_headers = self.load_csv(self.cinf_path) if self.cinf_path else ([], [])

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
        row[TEAM_SALARY_CAP_FIELD] = str(max(0, cur + delta_units))
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
        self.parent = parent
        self.model = model

        self.team1 = tk.StringVar(value="1009")
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
        self.geometry("640x640")
        self.minsize(600, 560)
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
        top.pack(fill="x", padx=10, pady=10)
        ttk.Label(
            top,
            text="Reverses an in-game 'cut' - confirmed field-for-field via a live before/after test.",
            wraplength=600, justify="left",
        ).pack(anchor="w")

        src_frame = ttk.LabelFrame(self, text="Source pool")
        src_frame.pack(fill="both", expand=True, padx=10, pady=(0, 8))

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
        contract.pack(fill="x", padx=10, pady=(0, 8))

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
        bottom.pack(fill="x", padx=10, pady=(0, 10))
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

            self.model.set_player_team_id(row, dest_tid)
            row["PCON"] = str(years)
            row["PCYL"] = str(years)
            row["PCSA"] = str(year1_cap_hit)
            row["PTSA"] = str(total_salary + total_bonus)
            row["PVSB"] = str(total_bonus)
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
        if enabled:
            self.chk_dark_mode.state(["!disabled"])
        else:
            self.chk_dark_mode.state(["disabled"])
        messagebox.showinfo(
            "Restart required",
            "This takes effect the next time you launch the app. Nothing else changes - "
            "every feature works the same either way, this only affects the look."
        )

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

        # Packed before the status label (both docking to the right) so they
        # always claim their space regardless of how long the status text
        # gets - previously a long "Loaded: ..." string could push these
        # entirely off the visible window.
        self.chk_dark_mode = ttk.Checkbutton(
            top, text="Dark Mode", variable=self.dark_mode_var, command=self.on_toggle_dark_mode
        )
        self.chk_dark_mode.pack(side="right", padx=(8, 0))
        if not self.facelift_var.get():
            self.chk_dark_mode.state(["disabled"])

        ttk.Checkbutton(
            top, text="Modern UI", variable=self.facelift_var, command=self.on_toggle_facelift
        ).pack(side="right", padx=(8, 0))

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
            self.tree_stats.heading(c, text=c)
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
            self.tree_picks.heading(c, text=text)
            self.tree_picks.column(c, width=width, anchor="w", stretch=False)
        self.tree_picks.pack(fill="both", expand=True, padx=10, pady=(0, 6))
        self.tree_picks.bind("<<TreeviewSelect>>", lambda e: self._update_pick_selection_label())

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

        self.tree_trainer = ttk.Treeview(root, show="headings", height=10)
        self.tree_trainer.pack(fill="both", expand=True, padx=10, pady=(0, 0))
        xscroll_trainer = ttk.Scrollbar(root, orient="horizontal", command=self.tree_trainer.xview)
        xscroll_trainer.pack(fill="x", padx=10, pady=(0, 6))
        self.tree_trainer.configure(xscrollcommand=xscroll_trainer.set)

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
        ttk.Button(top, text="Personality...", command=self.on_open_coach_personality_editor).pack(side="left", padx=(8, 0))

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

        self.tree_coach = ttk.Treeview(root, show="headings", height=10)
        self.tree_coach.pack(fill="both", expand=True, padx=10, pady=(0, 0))
        xscroll_coach = ttk.Scrollbar(root, orient="horizontal", command=self.tree_coach.xview)
        xscroll_coach.pack(fill="x", padx=10, pady=(0, 6))
        self.tree_coach.configure(xscrollcommand=xscroll_coach.set)

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

        self.tree_gm = ttk.Treeview(root, show="headings", height=10)
        self.tree_gm.pack(fill="both", expand=True, padx=10, pady=(0, 0))
        xscroll_gm = ttk.Scrollbar(root, orient="horizontal", command=self.tree_gm.xview)
        xscroll_gm.pack(fill="x", padx=10, pady=(0, 6))
        self.tree_gm.configure(xscrollcommand=xscroll_gm.set)

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
        for iid in self.tree_trainer.get_children():
            self.tree_trainer.delete(iid)

        self.tree_trainer["columns"] = headers
        for h in headers:
            self.tree_trainer.heading(h, text=STAFF_FIELD_LABELS.get(h, h))
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
        desired = ["TGID", "CFNM", "CLNM", "SKPT", "SKPC", "SKPX", "SKST", "SKSM", "SKCR", "SKCM", "SKPA", "SKPF", "POVS"]
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
        for iid in self.tree_coach.get_children():
            self.tree_coach.delete(iid)

        self.tree_coach["columns"] = headers or []
        for h in headers or []:
            self.tree_coach.heading(h, text=STAFF_FIELD_LABELS.get(h, h))
            self.tree_coach.column(h, width=90 if h in COACH_DEV_COLUMNS else 140, anchor="w", stretch=False)

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
        for iid in self.tree_gm.get_children():
            self.tree_gm.delete(iid)

        self.tree_gm["columns"] = headers
        for h in headers:
            self.tree_gm.heading(h, text=STAFF_FIELD_LABELS.get(h, h))
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
