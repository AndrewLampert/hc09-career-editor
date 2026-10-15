# What the game's own data holds

Notes from reading the shipped database in `qkl_boot.ast` (the game's data, not a save) and comparing it with real saves. Everything here is read from files; where something was checked on the game's screen it says so. Companion documents: `hc09_field_reference.md` (the community field list and what the editor found to be wrong in it), `hc09_position_presets.md` (the Player Type Fit formulas and readings).

## How to read it

- The shipped database is **entry 46 of `qkl_boot.ast`**: a TDB database with 716 tables (`docs/gamedata/shipped_db_716_tables.txt` lists them with row counts and fields). Export one or several tables with the bridge:
  `node hc09-bridge/bridge.js shipped-table-export --ast <qkl_boot.ast> --tables A,B,C --out-dir <dir>` (or `--table A --out file.csv`). Add `--top-index 46` to skip the scan.
- **String quirk:** text fields in the shipped tables come back as a window into a shared string pool, so one field can hold several names run together with control characters (length prefixes such as `\x0b`) between them. The real text of a record is everything before the first character below `0x20`; where that is cut short (a few last records), the short-name column (`ENSN`) or the neighbouring field often holds the rest.
- **Case matters in table names** (`PEDW` and `PEdW` are different tables) but Windows file names do not: export such tables one at a time to different file names.
- Saves are read with the same bridge (`export`, `inspect`); a save has about 208 tables, most of them empty.

## Naming conventions (tentative, from reading the tables)

Tables named `E***` with columns `AGDE ENDN ENSN ENUV` (or `BNMN ENUV BNMX` for numeric ranges) are **enumerations**: `ENUV` is the stored value, `ENDN` the display name, `ENSN` a short name. There are 136 of them and they name almost every setting value in the game, so they are the first place to look when a value's meaning is in doubt. `L***` tables are mostly lookup / decision tables for the simulation (contracts, trades, injuries, scouting), `P***` tables are player-related, `C***` coach-related. Trailing-`P` four-letter tables (`CPCP`, `DSPP`, `TAGP`, ...) are the value lists for the Team Philosophy fields.

## The names and value lists the editor now uses

| Table | What it names |
|---|---|
| `EGPP` (82) | every position preset, value 0 to 80 (and 81 "Balanced R"); the game writes them with the position ("Prototype CB") |
| `PCAT` (110) | every Team Philosophy category in the game's order, with its default; all 110 `TPHS` fields are matched in `hc09_field_reference.md` |
| `CHCP`, `TAGP`, `BOSP`, `ETFP`, `TFDP`, `TDPP`, `EIWP`, `RSSP`, `ENTP`, `CINP`, `ESCP`, `GMSP`, `RFAP`, `GMRP`, `ECPS`, `BTTP`, `PREP`, ... | the value lists of those categories |
| `EGRD` (8) | the grade names: Overall, Potential, Athletic, Intangibles, Production, Size, Learning, Durability |
| `LGRD` (13) | letter grades with their score ranges: A+ 95-100, A 90-94, A- 87-89, ... F |
| `EPNT` (17), `EPRT` (54) | the personality types and traits (the editor's list matches the game's for the 17 types; the game has two traits, Indecisive and Thrifty, that the editor's reference lacks) |

A mistake this found: the community config's **tight end** preset list is in a different order from the game's, which the editor repeated (the game: 20 Soft Hands/Routes, 21 Blocking, 22 Playmaker, 23 H-back, 24 Balanced).

## Player grades (the Evaluate Roster / Roster Breakdown screens)

A save stores the game's own grades for the draft class in table **`RPGR`** (11,550 rows: 350 prospects for each of 33 "teams"). The pseudo-team 1015 has every grade revealed (`PATG` athletic, `PInG` intangibles, `PLNG` learning, `PDRG` durability, `PPTG` potential, `PSZG` size, `PPDG` production, `POVG` overall); the 32 real teams have only what they scouted (flags `AFLG DFLG IFLG LFLG PFLG SFLG pFLG`). Comparing it with the player rows gave the grade formulas (all in `hc09_position_presets.md`, checked on 350 players across 21 positions): athletic, intangibles, learning and potential are exact; durability is the body parts weighted by table `LPHC` (310 of 350 exact); size is a stepped lookup that is not in any data table; production is unknown. Draft prospects' overall uses the position-group weights of `PEdW` (position to group via `PLPS`), a team's Evaluate Roster overall uses `PEOW` for its preset.

Other tables in this area: `PLRM` (save, 1,589 rows: per-player roadmap evaluation `OAGE PBKE OVRE UPSE CNTE MOVE ROlE`, matching the Player Roadmap Evaluation philosophy), `POSC` (per-position-group ranges, probably the production scale), `PORC` (21 rows, one per position: weights over the ratings with a `PRDH` / `PRDL` range; presumably how the stored overall `POVR` is built, not decoded).

## Staff

- **Special skills** (`ESPS`, 62 names: Accommodation, Off Season Rehab, First Round Intuition, Draft Intuition, Charisma, ..., Superb Strategist, Potential Intuition) are stored in the save's table **`PSSK`** as one 64-bit mask per person (`SPSB`, hex text, one bit per skill, bit *n* = `ESPS` value *n*; `PNid` is the person). Decoded for the test career, the Bears head coach (Lovie Smith) has Coverage Analysis and the GM has Small School Insider. The editor does not show or edit them yet. Matched from data, not checked on the game's screen.
- `OWNR` holds the owner's control levels (`GmCP OCCP DCCP PCCP TRCP`), `GMVW` the GM's philosophy fields, `TRVW` the trainer's; `TPHS` looks like the per-team result of these and the head coach's settings.
- Shipped pools: `GMPL` (51 GM profiles, with the same philosophy fields), `COPL` (289 coaches, 179 fields); `CCOD` (28 rows, 68 fields) and the small tables `COPW` / `COCW` / `AcoW` were not examined.

## Draft, trades, contracts, injuries

- `DRCL` (7,710 rows, 59 fields) and `DCDC` (704 rows: a letter grade and a blurb such as "Decent CBs" per draft class `DFCL`) look like a library of about 22 pre-built draft classes; the first class of a career is the 350 players on the draft-class pseudo-team in the save. `DPL1` to `DPL4` (5,600 rows each, 217 fields) are bigger lookups, not examined.
- Trading: `LTPC` (a value by `TDFP` and the stage of the season: 25 / 35 / 30 for Heavy / Light / Neutral late in the season), `DTDC` (a chance by `TDFP` and board order), `LTRV` / `LTOV` (values by `TMSP`). What the values are in game terms was not worked out.
- Contracts, cuts and owner logic: `LKPR`, `LRES`, `LCUT`, `LRDA`, `LUOE` are decision tables keyed by position group, role and grade tiers; not decoded.
- Injuries: `EINJ` names 116 injuries (Broken Jaw ... Torn ACL, MCL and PCL ... Stinger); injury simulation tables are `LINC` (10,206 rows), `LHPA` / `LHPD` / `LHPI`, `LISF` / `LISP`, `LETV` (not decoded); `LPHC` weights the body parts.
- Development: `LPCL` (21,250 rows with age, position and ranges) may be the progression curves; not decoded. `PEPW` (1,073 rows keyed by preset) and `LPRR` (5,304 rows) were not explained.
- News and events: `FRNE` names 248 event types (staff suggestions, defining moments, milestones, awards).

## Other tables in a save that the editor never touches

Season stat history (`PSOF` 2,791 rows, `PSDE`, `PSNG`, `PSKP`, `PSKI`, `PCDE`, `PCOF`, ...: one row per player and season), `DCHT` (depth chart, 1,683 rows), `DSCT`, `TRNK`, `TUNI` (uniforms), `STAD` (stadiums, 85 fields), `CITY`, `SCHD`-related tables, the injury table `INJY`, draft-order tables (`DRPP`, `DPLP`).

## Ideas, roughly by value

1. **Staff special skills**: show and edit them with the game's names (the 64-bit mask in `PSSK`). Needs a row appended for staff who have none.
2. **Recompute the stored overall** (`POVR`) after rating edits, if the game does not: needs the `PORC` formula decoded (a regression against saves where the stored overall is current would settle it).
3. **Exact Size grade**: the stepped height / weight lookup (probably in the executable); more stored grades would let a per-position table be fitted (per-position fits reached an error of about 4.7 against 6.5 for one global fit).
4. **Production grade**: what it is for veterans (counted as 0 and that fits) and where the prospects' values come from.
5. **Team Philosophy**: check the GM, staff, roster-minimum, health and fatigue settings against the game's screen (one change per tab), and find out whether the game recomputes `TPHS` from the staff.
6. **Draft class preview or swap** using `DRCL` / `DCDC`.
7. **Injury names** wherever the editor shows an injury (`EINJ`).
