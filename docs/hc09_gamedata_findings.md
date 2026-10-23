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

Other tables in this area: `PLRM` (save, 1,589 rows: per-player roadmap evaluation `OAGE PBKE OVRE UPSE CNTE MOVE ROlE`, matching the Player Roadmap Evaluation philosophy), `POSC` (per-position-group ranges, probably the production scale), `PORC` (21 rows, one per position: weights over the ratings with a `PRDH` / `PRDL` range; presumably how the stored overall `POVR` is built). Tried and not reproduced: mapping its columns to ratings by name, the weighted rating relates to the stored `POVR` of the test save's veterans with an RMS of about 5 and a slope near 1 (a `PRDH`-to-`PRDL` range scale would give about 1.8), so either some column pairings are off or the stored overalls are stale in that save; the overall the Evaluate Roster screen shows does not use `PORC` (see the grade formulas).

## Staff

- **Special skills** (`ESPS`, 62 names: Accommodation, Off Season Rehab, First Round Intuition, Draft Intuition, Charisma, ..., Superb Strategist, Potential Intuition) are stored in the save's table **`PSSK`** as one 64-bit mask per person (`SPSB`, hex text, one bit per skill, bit *n* = `ESPS` value *n*; `PNid` is the person). The bit order was checked statistically: across the 185 people with skills each skill is held only by the staff it belongs to (Accommodation and the School Insider skills only by GMs; Off Season Rehab and Cardio Training only by trainers; the blocking skills by offensive line coaches; the kick skills by special teams coaches). In the test career the Bears head coach (Lovie Smith) has Coverage Analysis and the GM has Small School Insider. The editor's **Special skills...** button (Coach, Trainer and GM tabs) reads and writes the mask. Matched from data, not checked on the game's screen.
- `OWNR` holds the owner's control levels (`GmCP OCCP DCCP PCCP TRCP`), `GMVW` the GM's philosophy fields, `TRVW` the trainer's; `TPHS` looks like the per-team result of these and the head coach's settings.
- Shipped pools: `GMPL` (51 GM profiles, with the same philosophy fields), `COPL` (289 coaches, 179 fields); `CCOD` (28 rows, 68 fields) and the small tables `COPW` / `COCW` / `AcoW` were not examined.

## Draft, trades, contracts, injuries

- `DRCL` (7,710 rows, 59 fields) and `DCDC` (704 rows: a letter grade and a blurb such as "Decent CBs" per draft class `DFCL`) look like a library of about 22 pre-built draft classes; the first class of a career is the 350 players on the draft-class pseudo-team in the save. `DPL1` to `DPL4` (5,600 rows each, 217 fields) are bigger lookups, not examined.
- Trading: `LTPC` (a value by `TDFP` and the stage of the season: 25 / 35 / 30 for Heavy / Light / Neutral late in the season), `DTDC` (a chance by `TDFP` and board order), `LTRV` / `LTOV` (values by `TMSP`). What the values are in game terms was not worked out.
- Contracts, cuts and owner logic: `LKPR`, `LRES`, `LCUT`, `LRDA`, `LUOE` are decision tables keyed by position group, role and grade tiers; not decoded.
- Injuries: `EINJ` names 116 injuries (Broken Jaw ... Torn ACL, MCL and PCL ... Stinger); injury simulation tables are `LINC` (10,206 rows), `LHPA` / `LHPD` / `LHPI`, `LISF` / `LISP`, `LETV` (not decoded); `LPHC` weights the body parts.
- Development: `LPCL` (21,250 rows with age, position and ranges) may be the progression curves; not decoded. `PEPW` (1,073 rows keyed by preset) and `LPRR` (5,304 rows) were not explained.
- News and events: `FRNE` names 248 event types (staff suggestions, defining moments, milestones, awards).

## The Game reference window

The toolbar's **Game reference...** shows four tables of the shipped database as read-only panels (code: `hc09_reference.py`). The tables are read out of `qkl_boot.ast` once into the editor's cache folder (`reference` next to the other cached game data) and never written back. All four are the game's data: whether and how the game uses a table in a match is not confirmed.

- **Injuries (`LINC`, 10,206 rows).** A chance LEVEL from 0 to 4, not a percentage (the table does not say what chance a level is). Keys: position (21), body part (6: ids 0 and 1 are the legs, 2 and 3 the arms, 4 the head, 5 the torso; which leg or arm is the left one is not known), Injury rating (bins `Eirt`: 90-100, 76-89, 0-75), body-part health (`Ebph`: 925-1000, 825-924, 0-824) and impact severity (`Eisv`: 7000-10000, 2000-6999, 0-1999). Fatigue (`EFAT`: 92-100, 75-91, 0-74) is also a key but changes the level in 1 of 3,402 cases. Mean level by Injury rating: 0.00 (90+), 0.81 (76-89), 1.81 (75 or less). Injury rating 90+ is level 0 in all but 12 of 3,402 cases (all receivers: a hit of severity 7000+ on body part 0 or 1 whose health is below 925); an earlier note that it was level 0 "in every case" was wrong by those 12. Mean level by severity: 1.28 (7000+), 0.90, 0.44; by body-part health: 0.68 (healthy), 0.81 (825-924), 1.14 (below 825). Quarterbacks (1.16) and receivers (1.02) have higher means than the other positions (0.85). The bins are looked up by range: the rows are stored out of order and the bin number of the middle health band (2) is higher than that of the hurt band (1).
- **Draft pick values (`DVCD`, `DVCP`, `DVFD`, `DVFP`).** `DVCD`: the value of each of the 224 picks (pick 1 = 30,000, 2 = 26,000, 3 = 22,000, 32 = 5,900, 33 = 5,800, 64 = 2,700, 224 = 20; pick number 0 in the table is pick 1). `DVFD`: next year's picks by round (10,000, 4,200, 1,900, 700, 340, 210, 80) for a team that builds through the draft; teams that build through free agency get 90% of that (9,000, 3,780, ...). `DVCP` and `DVFP` are the "player value" counterparts on a smaller scale (pick 1 = 300 and 270). The panel's calculator adds up the chart's values for the picks typed in; how the CPU weighs a trade is not decoded, so the sum is not a prediction.
- **Contract talks (`LPCN`, 2,025 rows).** Accept (`ACCP`), walk away (`LVPT`) and ultimatum (`ULTP`) chances in percent. Keys: head coach approval (`EHCB`: 0-40, 41-70, 71-99), player overall (`POGB`: 0-69, 70-79, 80-89, 90-94, 95-99), counter offers so far (`NCOB`: 0-2, 3-5, 6+) and the gap between the offer and the package he wants (`PCPG`, in package steps: 0-6, 7-18, 19-36), plus a negotiation type (`NGTY`, 3 values) and a player trait (`CSLT`, 5 values) that are not named in the game's data, so the panel averages over them and shows the lowest and highest. `LVRP`, `ACCR`, `ULTR` and `CNTR` are ids of response texts, not chances.
- **Injured body parts (`PHAE`, 102 rows; `PLPS`).** Per position group (17: QB, HB, FB, WR, TE, OT, OG, C, DE, DT, OLB, MLB, CB, FS, SS, K, P) and body part, up to 11 rating ids that an injury to that body part lowers (47 marks an unused slot). `PLPS` maps a position to its group (LT and RT are the OT group, and so on). The table says which ratings, not by how much: `HATE` (1,836 rows) is the likely home of the amounts but only holds a 0 or 1 per health threshold, so the size of a drop is not decoded. A leg injury lowers Acceleration, Agility and Speed for every group; a head injury Awareness for every group.

## Plays

The shipped boot tables name playbooks, sets, formations and plays (`PLAB`, `SETL`, `PBFM`, `PBPL`, used by the Playbooks tab) and hold per-team play usage (`PKxx`, one table per team, about 5,000 rows each of `PGID PLYL PKNO`), but **no play definitions** (routes, assignments): a custom play's definition is in the profile save and the stock ones are in another archive. Making plays outside the game needs those, so it is not possible from `qkl_boot.ast` alone.

## Other tables in a save that the editor never touches

Season stat history (`PSOF` 2,791 rows, `PSDE`, `PSNG`, `PSKP`, `PSKI`, `PCDE`, `PCOF`, ...: one row per player and season), `DCHT` (depth chart, 1,683 rows), `DSCT`, `TRNK`, `TUNI` (uniforms), `STAD` (stadiums, 85 fields), `CITY`, `SCHD`-related tables, the injury table `INJY`, draft-order tables (`DRPP`, `DPLP`).

## Ideas, roughly by value

1. **Staff special skills**: done in the editor (the 64-bit mask in `PSSK`, with a row appended for staff who had none). To check in the game: give a coach one skill and look at his card.
2. **Recompute the stored overall** (`POVR`) after rating edits, if the game does not: needs the `PORC` formula decoded (a regression against saves where the stored overall is current would settle it).
3. **Exact Size grade**: the stepped height / weight lookup (probably in the executable); more stored grades would let a per-position table be fitted (per-position fits reached an error of about 4.7 against 6.5 for one global fit).
4. **Production grade**: what it is for veterans (counted as 0 and that fits) and where the prospects' values come from.
5. **Team Philosophy**: check the GM, staff, roster-minimum, health and fatigue settings against the game's screen (one change per tab), and find out whether the game recomputes `TPHS` from the staff.
6. **Draft class preview or swap** using `DRCL` / `DCDC`.
7. **Injury names** wherever the editor shows an injury (`EINJ`).
