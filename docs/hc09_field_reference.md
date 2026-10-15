# HC09 database field reference (from the community config)

Generated from the **HC09 Detailed Config.xml** (made by JHamilton9 in 2020 for the EA Generic DB Editor; shared in the Operation Sports "Head Coach 09 XML config file" thread). It names 383 of the 679 fields it defines, groups them by the screen they appear on, and gives value lists for 48 drop-down fields. The labels are community-written, **not developer-confirmed, and some are wrong** (see TDPB below), so treat a label as a lead to test in-game, not as proof. The raw value lists are in [`hc09_value_lists.json`](hc09_value_lists.json).

## What it independently confirms in this editor

- **Coach position codes (`COPS`)**: the config's list is `0 HC, 1 OC, 2 DC, 3 STC, 4 QBC, 5 RBC, 6 WRC, 7 OLC, 8 LBC, 9 DLC, 10 DBC` - identical to the mapping the editor uses.
- **Coach playbooks (`CPID` / `CDID`)**: the lists have 46 offensive and 43 defensive playbooks, indexed exactly like the playbook list in the game files (a playbook's `BGID` within its side). Confirms where the Playbooks tab reads and writes a team's playbooks.
- **Personality (`PTId`)**: the 17 names and their order match the editor's mapping (the config spells it "Superstar").
- **Names of fields flagged earlier**: `PHGT` Height, `PWGT` Weight, `PCOL` College (with a 297-entry list), `HDAp` Overall Approval, `PLAC/PRAC/PHDC/PLLC/PTRC` body-part health, `PFPB` Pro Bowl, `PJEN` Jersey Number, `PSTY` Throwing Style. `HDAp` is on the **coach table** (and club officials and players' contract view), not on a team table.
- `TMSA` is labelled "Team Salaries".

## Where the config and the editor disagree

| Field | Editor says | Config says | Notes |
|---|---|---|---|
| `PPBS` | Pass Block Power | Pass Block Strength | same meaning, different word (the attribute is `PassBlockPowerRating` in the other lookup sheet) |
| `PPBF` | Pass Block Finesse | Pass Block Footwork | same meaning (`PassBlockFinesseRating`) |
| `PRBF` | Run Block Finesse | Run Block Footwork | same meaning (`RunBlockFinesseRating`) |
| `SKPX` | Play Call Max | Play Call Potential | "potential" = the max of the pair; consistent |
| `SKSM` | Strategy Max | Strategy Potential | consistent |
| `SKCM` | Chemistry Max | Chemistry Potential | consistent |
| `SKPA` | Perf. Input A | Performance Potential | **conflict worth testing**: the editor found Performance = MIN(SKPA, SKPF) in-game; the config calls SKPA "Performance Potential" and SKPF "Performance Current" |
| `SKPF` | Perf. Input B | Performance Current | see SKPA; the editor's in-game tests take priority |
| `TDPB` | not used | "Defense Playbook" | **Label is wrong.** Values are only {0,1,3,4,5,6} and teams with the same scheme share one (the 3-4 teams share 1, the Tampa-2 teams share 3), so it is a scheme family, not a playbook index. A team's real defensive playbook is `COCH.CDID`. |
| `OSPP` | 3 = Spread, 4 = Power Running (checked in game) | 3 = "Speed", 4 = "Power Run" | **Label is wrong** for value 3; see "Checked in the game: Team Philosophy" below |
| `TOPB` | offense, by `PLAB.BORD` | "Offensive Playbook" | Matches the coordinators for 28 of 32 teams; the coaches' `CPID` is the real assignment. |

### Checked in the game: Team Philosophy

Changing the three playcall settings on the game's Team Philosophy screen and saving moved exactly three fields, in the **`TPHS`** table (34 rows, keyed by `TGID`). That table, not the coach rows, is what the screen reads: the same field codes also sit on each coach's `COCH` row, but editing those did not change the screen. (The config files the philosophy fields under a table it calls `TPHL` and names `TPHS` "Team Health"; in a real save the philosophy columns are in `TPHS`. `TPHL` has the same 111-column layout with lower-case names and was not examined.)

It was then checked the other way: values written with the editor and read off the screen after loading the career. Every value below showed the expected name.

| Field | In-game name | Values checked | Notes |
|---|---|---|---|
| `NHPP` | No Huddle Philosophy | 0 Heavily, 1 Balanced, 2 Rarely | same as the config |
| `OPPP` | Offensive Playbook Control | 0 Head Coach, 1 Offensive Coordinator | config: "Off Call Preference", 0 HC, 1 OC |
| `OSPP` | Offensive Scheme | 0 West Coast Normal, 2 Vertical Passing, **3 Spread**, **4 Power Running** | config says 3 is "Speed" (**wrong**) and 4 "Power Run"; 1 (West Coast Heavy Pass) unchecked |
| `DSPP` | Defensive Scheme | 0 3-4 | 1 (4-3) and 2 (4-6) unchecked |
| `DPPP` | Defensive Playbook Control | 1 Defensive Coordinator | 0 should be Head Coach, not seen |
| `BZPP` | Blitz Philosophy | 0 Heavy ("Blitz Heavy") | 1 Normal, 2 Light unchecked |
| `CVPP` | Pass Coverage Philosophy | 2 Zone ("Zone Coverage") | 0 Man, 1 Cover 2 unchecked |
| `DMPP` | Defining Moment Philosophy | 0 Aggressive | 1 Conservative, 2 Balanced unchecked |
| `QBPP` | QB Philosophy | 0 "Mobile/Speed QB" | other QB values unchecked |
| `CBPP` | Cornerback Philosophy | 61 "Man Coverage/Ballhawk CB" | config: "Man" |
| `KKPP` | Kicker Philosophy | 75 "Big Foot/Distance K" | config: "Power" |
| `FSPP`, `SsPP`, `KPPP` | FS / SS / Punter Philosophy | 67 "Centerfielder FS", 74 "Smart/Productive SS", 79 "Pinpoint Accuracy P" | seen as the saved values; config: Centerfielder, Smart, Accuracy |

The game words the position philosophies in full ("... QB", "... CB", "... K"); the config's short names are the same options for most, but not all (the tight end list is in a different order). The editor now uses the game's own names (see "Team Philosophy: all 110 fields" below); the lists in "Value lists" are the config's.

The editor's **Team Philosophy...** button (Coach tab) edits `TPHS`: every one of its 110 fields, in five tabs.

### Team Philosophy: all 110 fields (decoded from the game's data)

The game's own data names every field and value. Table `PCAT` in `qkl_boot.ast` lists the 110 Team Philosophy categories in the game's order (id, name, default); `EGPP` names the 81 position presets (values 0 to 80); and a small table per category names its values (for example `CHCP` for the hire-control levels, `TAGP` for the franchise tag, `BOSP` for benching decisions). Field codes were matched to categories from the group they belong to (the position philosophies, the roster minimums, practice and game health and fatigue, and the playcall settings already checked in game), from the number of values each category has against the values in real saves (every value stored in every team of every test save is one of the named values), from the short names `PCAT` gives, and from the other game tables that use the same codes (for instance the GM profile table `GMPL`, the coach pool `COPL` and the trade tables `LTPC` / `DTDC`). Which of three trade columns (`TDFP`, `GFTP`, `GTDP`) is which rests on the names and on `LTPC`, where `TDFP` values 0 / 1 / 2 map to 25 / 35 / 30, heavy lowest and light highest, as a frequency would: **matched from data, not yet checked in the game** (only the rows marked checked were).

The hire-control fields (`GmCP`, `OCCP`, `DCCP`, `PCCP`, `TRCP`) are also on the owner rows (`OWNR`) and the GM profile fields on the GM rows (`GMVW`): `TPHS` looks like the per-team result of the owner, GM, head coach and trainer settings, which fits "some are locked based on control given up during staff hiring" and why editing the coach rows alone never changed the screen. Whether the game recomputes `TPHS` from the staff (for example when staff change) is not known.

Notes from the data: the tight end list in the community config is in a different order from the game's (the game: 20 Soft Hands/Routes, 21 Blocking, 22 Playmaker, 23 H-back, 24 Balanced; the weight tables agree: 21 weighs impact and run blocking, 20 route running and catching). The earlier idea that `xxPH` means "Physical Development" is wrong: `xxPH` is practice health, `xxHS` game health, `xxFP` practice fatigue and `xxFS` game fatigue, one per position group. `GSMP` is the GM spending philosophy, not a roster minimum. The 11th `xxFP` column, `TDFP`, is trading frequency. Roster minimum values are an index: the number shown is the minimum number of players kept at the position. `TPHL` (31 in every column of every team) is not explained by this.

| # | Field | The game's name | Game default | Values (value name) |
|---|---|---|---|---|
| 0 | `GmCP` | GM Hire Control | 1 | 0 Give up a lot of control; 1 Give up some control; 2 Give up a little control; 3 Give up no control |
| 1 | `OCCP` | OC Hire Control | 1 | 0 Give up a lot of control; 1 Give up some control; 2 Give up a little control; 3 Give up no control |
| 2 | `DCCP` | DC Hire Control | 1 | 0 Give up a lot of control; 1 Give up some control; 2 Give up a little control; 3 Give up no control |
| 3 | `PCCP` | Position Coach Hire Control | 1 | 0 Give up a lot of control; 1 Give up some control; 2 Give up a little control; 3 Give up no control |
| 4 | `TRCP` | Trainer Hire Control | 1 | 0 Give up a lot of control; 1 Give up some control; 2 Give up a little control; 3 Give up no control |
| 5 | `TDFP` | Trading Frequency | 2 | 0 Heavy Trader; 1 Light Trader; 2 Neutral |
| 6 | `TMSP` | Trading Philosophy | 1 | 0 Passive; 1 Normal; 2 Aggressive |
| 7 | `GFTP` | GM Future Draft Picks | 2 | 0 Overvalue future draft picks; 1 Undervalue future draft picks; 2 Neutral |
| 8 | `GTDP` | GM Draft Trade Philosophy | 2 | 0 Trade up; 1 Trade down; 2 Neutral |
| 9 | `DFTP` | Draft Philosophy | 0 | 0 Draft best available players; 1 Draft biggest team needs |
| 10 | `IWKP` | Workouts Scouting Philosophy | 0 | 0 Scout best available players; 1 Scout biggest team needs |
| 11 | `RSSP` | Reg. Season Scouting Philosophy | 3 | 0 Big school focus; 1 Medium school focus; 2 Small school focus; 3 Balanced focus; 4 Team needs focus |
| 12 | `FTGP` | Franchise Tag Philosophy | 1 | 0 Heavily use; 1 Sometimes use; 2 Rarely use |
| 13 | `NGTP` | General Negotiation Philosophy | 2 | 0 Low ball; 1 Give in to demands; 2 Haggle; 3 Overpay |
| 14 | `CINP` | Counter Offer Philosophy | 1 | 0 Cheap; 1 Normal; 2 Generous |
| 15 | `ESCP` | GM Salary Cap Philosophy | 1 | 0 Prefers 5M in cap room; 1 Prefers 3M in cap room; 2 Prefers 1M in cap room |
| 16 | `GSMP` | GM Spending Philosophy | 0 | 0 Distribute money evenly; 1 Spend on the biggest need; 2 Spend on the 2 biggest needs; 3 Spend on the 3 biggest needs |
| 17 | `RFAP` | GM RFA Philosophy | 0 | 0 Normal; 1 Tender with higher compensation; 2 Tender with lower compensation |
| 18 | `RSPP` | GM Re-sign Philosophy | 2 | 0 Re-sign based on high approval; 1 Re-sign all players; 2 Based on quality |
| 19 | `CDVP` | Career Development | 0 | 0 Physical development; 1 Intangibles development; 2 Learning development |
| 20 | `BTTP` | Team Building Philosophy | 0 | 0 Build through the NFL draft; 1 Build through free agency |
| 21 | `PRDP` | Player Roadmap Evaluation | 0 | 0 Favors overall grade; 1 Favors role; 2 Favors upside; 3 Favors contract; 4 Favors play knowledge |
| 22 | `QBPP` | QB Philosophy (checked in game) | 4 | 0 Mobile/Speed; 1 Strong Arm/Tools; 2 Pure Passer; 3 Field General; 4 Balanced |
| 23 | `HBPP` | HB Philosophy | 10 | 5 Speed; 6 Moves; 7 Power; 8 Receiving; 9 Workhorse; 10 Balanced |
| 24 | `FBPP` | FB Philosophy | 14 | 11 Ball Carrier; 12 Blocking; 13 Receiving; 14 Balanced |
| 25 | `WRPP` | WR Philosophy | 19 | 15 Strong/Blocking; 16 Tall/Redzone Threat; 17 Speed; 18 Quick/Route Runner; 19 Balanced |
| 26 | `TEPP` | TE Philosophy | 24 | 20 Soft Hands/Routes; 21 Blocking; 22 Playmaker; 23 H-back; 24 Balanced |
| 27 | `TKPP` | Tackle Philosophy | 29 | 25 Size/Strength/Engulfer; 26 Run Block Specialist; 27 Pass Block Specialist; 28 Zone Blocking; 29 Balanced |
| 28 | `GDPP` | Guard Philosophy | 34 | 30 Size/Strength/Mauler; 31 Run Block Specialist; 32 Pass Block Specialist; 33 Zone Blocking; 34 Balanced |
| 29 | `CRPP` | Center Philosophy | 39 | 35 Size/Strength/Mauler; 36 Run Block Specialist; 37 Pass Block Specialist; 38 Zone Blocking; 39 Balanced |
| 30 | `DEPP` | DE Philosophy | 40 | 40 Balanced; 41 Prototype; 42 Undersized Speed Rusher; 43 Run Stopper; 44 Versatile/3-4 |
| 31 | `DTPP` | DT Philosophy (checked in game) | 45 | 45 Balanced; 46 Prototype; 47 One Gap Penetrator; 48 Run Stopper; 49 Versatile/3-4 |
| 32 | `OLPP` | OLB Philosophy | 50 | 50 Balanced; 51 Coverage/Cover 2; 52 Run Stopper; 53 PassRusher/3-4 Blitzer; 54 Prototype |
| 33 | `MLPP` | MLB Philosophy | 55 | 55 Balanced; 56 Coverage/Speed; 57 Power/Blitzer; 58 3-4/Tackler; 59 Prototype |
| 34 | `CBPP` | Cornerback Philosophy (checked in game) | 60 | 60 Balanced; 61 Man Coverage/Ballhawk; 62 Strong/Press/Run Support; 63 Prototype; 64 Cover 2 |
| 35 | `FSPP` | FS Philosophy (checked in game) | 65 | 65 Balanced; 66 Man Coverage; 67 Centerfielder; 68 Prototype; 69 Run Support/Blitzer |
| 36 | `SsPP` | SS Philosophy (checked in game) | 70 | 70 Balanced; 71 Coverage; 72 Prototype; 73 Run Support/Big Hitter; 74 Smart/Productive |
| 37 | `KKPP` | Kicker Philosophy (checked in game) | 77 | 75 Big Foot/Distance; 76 Pinpoint Accuracy; 77 Balanced |
| 38 | `KPPP` | Punter Philosophy (checked in game) | 80 | 78 Big Foot/Distance; 79 Pinpoint Accuracy; 80 Balanced |
| 39 | `QBMP` | QB Roster Minimum | 1 | 0 2; 1 3; 2 4 |
| 40 | `HBMP` | HB Roster Minimum | 1 | 0 2; 1 3; 2 4 |
| 41 | `FBMP` | FB Roster Minimum | 1 | 0 0; 1 1; 2 2 |
| 42 | `WRMP` | WR Roster Minimum | 0 | 0 4; 1 5; 2 6 |
| 43 | `TEMP` | TE Roster Minimum | 1 | 0 2; 1 3; 2 4 |
| 44 | `TKMP` | Tackle Roster Minimum | 0 | 0 3; 1 4; 2 5 |
| 45 | `GDMP` | Guard Roster Minimum | 0 | 0 3; 1 4; 2 5 |
| 46 | `CRMP` | Center Roster Minimum | 1 | 0 1; 1 2; 2 3 |
| 47 | `DEMP` | DE Roster Minimum | 1 | 0 3; 1 4; 2 5 |
| 48 | `DTMP` | DT Roster Minimum | 1 | 0 2; 1 3; 2 4 |
| 49 | `OLMP` | OLB Roster Minimum | 1 | 0 3; 1 4; 2 5 |
| 50 | `MLMP` | MLB Roster Minimum | 1 | 0 2; 1 3; 2 4 |
| 51 | `CBMP` | Cornerback Roster Minimum | 1 | 0 4; 1 5; 2 6 |
| 52 | `FSMP` | FS Roster Minimum | 1 | 0 1; 1 2; 2 3 |
| 53 | `SSMP` | SS Roster Minimum | 1 | 0 1; 1 2; 2 3 |
| 54 | `KKMP` | Kicker Roster Minimum | 0 | 0 1; 1 2 |
| 55 | `KPMP` | Punter Roster Minimum | 1 | 0 0; 1 1; 2 2 |
| 56 | `QBPH` | QB Practice Health Status | 0 | 0 Practice at moderate health; 1 Practice at low health |
| 57 | `HBPH` | HB Practice Health Status | 0 | 0 Practice at moderate health; 1 Practice at low health |
| 58 | `FBPH` | FB Practice Health Status | 0 | 0 Practice at moderate health; 1 Practice at low health |
| 59 | `WRPH` | WR Practice Health Status | 0 | 0 Practice at moderate health; 1 Practice at low health |
| 60 | `TEPH` | TE Practice Health Status | 0 | 0 Practice at moderate health; 1 Practice at low health |
| 61 | `OLPH` | OL Practice Health Status | 0 | 0 Practice at moderate health; 1 Practice at low health |
| 62 | `DLPH` | DL Practice Health Status | 0 | 0 Practice at moderate health; 1 Practice at low health |
| 63 | `LBPH` | LB Practice Health Status | 0 | 0 Practice at moderate health; 1 Practice at low health |
| 64 | `DBPH` | DB Practice Health Status | 0 | 0 Practice at moderate health; 1 Practice at low health |
| 65 | `KPPH` | K/P Practice Health Status | 0 | 0 Practice at moderate health; 1 Practice at low health |
| 66 | `QBHS` | QB Game Health Status | 0 | 0 Sub player at moderate health; 1 Sub player at low health |
| 67 | `HBHS` | HB Game Health Status | 0 | 0 Sub player at moderate health; 1 Sub player at low health |
| 68 | `FBHS` | FB Game Health Status | 0 | 0 Sub player at moderate health; 1 Sub player at low health |
| 69 | `WRHS` | WR Game Health Status | 0 | 0 Sub player at moderate health; 1 Sub player at low health |
| 70 | `TEHS` | TE Game Health Status | 0 | 0 Sub player at moderate health; 1 Sub player at low health |
| 71 | `OLHS` | OL Game Health Status | 0 | 0 Sub player at moderate health; 1 Sub player at low health |
| 72 | `DLHS` | DL Game Health Status | 0 | 0 Sub player at moderate health; 1 Sub player at low health |
| 73 | `LBHS` | LB Game Health Status | 0 | 0 Sub player at moderate health; 1 Sub player at low health |
| 74 | `DBHS` | DB Game Health Status | 0 | 0 Sub player at moderate health; 1 Sub player at low health |
| 75 | `KPHS` | K/P Game Health Status | 0 | 0 Sub player at moderate health; 1 Sub player at low health |
| 76 | `QBFP` | QB Practice Fatigue Status | 0 | 0 Practice at moderate fatigue; 1 Practice at heavy fatigue |
| 77 | `HBFP` | HB Practice Fatigue Status | 0 | 0 Practice at moderate fatigue; 1 Practice at heavy fatigue |
| 78 | `FBFP` | FB Practice Fatigue Status | 0 | 0 Practice at moderate fatigue; 1 Practice at heavy fatigue |
| 79 | `WRFP` | WR Practice Fatigue Status | 0 | 0 Practice at moderate fatigue; 1 Practice at heavy fatigue |
| 80 | `TEFP` | TE Practice Fatigue Status | 0 | 0 Practice at moderate fatigue; 1 Practice at heavy fatigue |
| 81 | `OLFP` | OL Practice Fatigue Status | 0 | 0 Practice at moderate fatigue; 1 Practice at heavy fatigue |
| 82 | `DLFP` | DL Practice Fatigue Status | 0 | 0 Practice at moderate fatigue; 1 Practice at heavy fatigue |
| 83 | `LBFP` | LB Practice Fatigue Status | 0 | 0 Practice at moderate fatigue; 1 Practice at heavy fatigue |
| 84 | `DBFP` | DB Practice Fatigue Status | 0 | 0 Practice at moderate fatigue; 1 Practice at heavy fatigue |
| 85 | `KPFP` | K/P Practice Fatigue Status | 0 | 0 Practice at moderate fatigue; 1 Practice at heavy fatigue |
| 86 | `QBFS` | QB Game Fatigue Status | 0 | 0 Sub player at moderate fatigue; 1 Sub player at heavy fatigue |
| 87 | `HBFS` | HB Game Fatigue Status | 0 | 0 Sub player at moderate fatigue; 1 Sub player at heavy fatigue |
| 88 | `FBFS` | FB Game Fatigue Status | 0 | 0 Sub player at moderate fatigue; 1 Sub player at heavy fatigue |
| 89 | `WRFS` | WR Game Fatigue Status | 0 | 0 Sub player at moderate fatigue; 1 Sub player at heavy fatigue |
| 90 | `TEFS` | TE Game Fatigue Status | 0 | 0 Sub player at moderate fatigue; 1 Sub player at heavy fatigue |
| 91 | `OLFS` | OL Game Fatigue Status | 0 | 0 Sub player at moderate fatigue; 1 Sub player at heavy fatigue |
| 92 | `DLFS` | DL Game Fatigue Status | 0 | 0 Sub player at moderate fatigue; 1 Sub player at heavy fatigue |
| 93 | `LBFS` | LB Game Fatigue Status | 0 | 0 Sub player at moderate fatigue; 1 Sub player at heavy fatigue |
| 94 | `DBFS` | DB Game Fatigue Status | 0 | 0 Sub player at moderate fatigue; 1 Sub player at heavy fatigue |
| 95 | `KPFS` | K/P Game Fatigue Status | 0 | 0 Sub player at moderate fatigue; 1 Sub player at heavy fatigue |
| 96 | `OPPP` | Offensive Playbook Control (checked in game) | 1 | 0 Head Coach; 1 Offensive Coordinator |
| 97 | `DPPP` | Defensive Playbook Control (checked in game) | 1 | 0 Head Coach; 1 Defensive Coordinator |
| 98 | `DMPP` | Defining Moment Philosophy (checked in game) | 2 | 0 Aggressive; 1 Conservative; 2 Balanced |
| 99 | `DSPP` | Defensive Scheme (checked in game) | 0 | 0 3-4; 1 4-3; 2 46/Multiple Front |
| 100 | `BZPP` | Blitz Philosophy (checked in game) | 0 | 0 Heavy; 1 Normal; 2 Light |
| 101 | `CVPP` | Pass Coverage Philosophy (checked in game) | 0 | 0 Man; 1 Cover 2; 2 Zone |
| 102 | `OSPP` | Offensive Scheme (checked in game) | 0 | 0 West Coast Normal; 1 West Coast Heavy Pass; 2 Vertical Passing; 3 Spread; 4 Power Running |
| 103 | `NHPP` | No Huddle Philosophy (checked in game) | 1 | 0 Heavily; 1 Balanced; 2 Rarely |
| 104 | `BPSP` | Bench Player | 2 | 0 Prefers to bench; 1 Prefers to start; 2 Balanced |
| 105 | `SRQP` | Start Rookie QB | 2 | 0 Prefers to start; 1 Doesn't prefer to start; 2 Balanced |
| 106 | `SRHP` | Start Rookie HB | 2 | 0 Prefers to start; 1 Doesn't prefer to start; 2 Balanced |
| 107 | `BMCP` | Bench Media Complainer | 2 | 0 Prefers to bench; 1 Prefers to start; 2 Balanced |
| 108 | `BNPP` | Bench Skip Practice | 2 | 0 Prefers to bench; 1 Prefers to start; 2 Balanced |
| 109 | `IPSP` | Injury Playing Status | 1 | 0 Aggressive; 1 Moderate; 2 Conservative |

The config has no name for 11 fields the editor already edits (`PLJM`, `SKTD`, `SKTM`, `SKNG`, `SKNM`, `TSIE`, `TSIM`, `TSRH`, `TSRM`, `TSFR`, `TSFM`); those come from the editor's own in-game testing.

## Value lists

These are the community config's lists. For the Team Philosophy fields the editor uses the game's own names instead (section "Team Philosophy: all 110 fields"), which differ in wording for most position presets and in order for tight ends.

The number in front of each label is the value stored in the save. Checked against a real save: every stored value in 14 coach fields (`CRPP CBPP DEPP QBPP OSPP DSPP CDTY OPPP DPPP NHPP COPS PTId CFDA CFFA`) falls inside its list, with none outside. Small lists are shown in full; `PNid` (3,585 names), `PCOL` (297 colleges) and the team lists are in the JSON file.

- `CDTY` **Def Philosophy**: 5 3-4; 95 4-3
- `CFDA` **Draft Player**: 0 User; 1 CPU
- `CFDP` **Sign Draft Picks**: 0 User; 1 CPU
- `CFFA` **Sign FAs**: 0 User; 1 CPU
- `CFFR` **Fill Rosters**: 0 User; 1 CPU
- `CFRP` **Re-sign Players**: 0 User; 1 CPU
- `CFRR` **Depth Chart**: 0 User; 1 CPU
- `CFUC` **User Control**: 0 False; 1 True
- `DPPP` **Def Call Preference**: 0 HC; 1 DC
- `OPPP` **Off Call Preference**: 0 HC; 1 OC
- `BZPP` **Blitz Phil**: 0 Heavy; 1 Normal; 2 Light
- `CVPP` **Coverage Phil**: 0 Man; 1 Cover 2; 2 Zone
- `DMPP` **Defining Moment Phil**: 0 Aggressive; 1 Conservative; 2 Balanced
- `DSPP` **Def Scheme**: 0 3-4; 1 4-3; 2 4-6
- `KKPP` **K Phil**: 75 Power; 76 Accuracy; 77 Balanced
- `KPPP` **P Phil**: 78 Power; 79 Accuracy; 80 Balanced
- `NHPP` **No Huddle Phil**: 0 Heavily; 1 Balanced; 2 Rarely
- `FBPP` **FB Phil**: 11 Ball Carrier; 12 Blocking; 13 Receiving; 14 Balanced
- `CBPP` **CB Phil**: 60 Balanced; 61 Man; 62 Strong; 63 Prototype; 64 Cover 2
- `CRPP` **C Phil**: 35 Size; 36 Run Block; 37 Pass Block; 38 Zone Block; 39 Balanced
- `DEPP` **DE Phil**: 40 Balanced; 41 Prototype; 42 Speed; 43 Run Stopper; 44 3-4
- `DTPP` **DT Phil**: 45 Balanced; 46 Prototype; 47 One-Gap; 48 Run Stopper; 49 3-4
- `FSPP` **FS Phil**: 65 Balanced; 66 Man Coverage; 67 Centerfielder; 68 Prototype; 69 Run Support
- `GDPP` **G Phil**: 30 Size; 31 Run Block; 32 Pass Block; 33 Zone Block; 34 Balanced
- `MLPP` **MLB Phil**: 55 Balanced; 56 Coverage; 57 Power; 58 Tackler; 59 Prototype
- `OLPP` **OLB Phil**: 50 Balanced; 51 Cover 2; 52 Run Stopper; 53 3-4 Pass Rush; 54 Prototype
- `OSPP` **Off Scheme**: 0 West Coast Normal; 1 West Coast Heavy Pass; 2 Vertical Passing; 3 Speed (the game shows 3 as Spread); 4 Power Run (the game shows 4 as Power Running; 2 Vertical Passing checked)
- `PNPs` **Club Title**: 11 GM; 12 Owner; 13 Trainer; 14 ; 15 
- `QBPP` **QB Phil**: 0 Mobile/Speed; 1 Strong Arm/Tools; 2 Pure Passer; 3 Field General; 4 Balanced
- `SsPP` **SS Phil**: 70 Balanced; 71 Coverage; 72 Prototype; 73 Run Support; 74 Smart
- `TEPP` **TE Phil**: 20 Playmaker; 21 H-Back; 22 Balanced; 23 Soft Hands; 24 Blocking
- `TKPP` **OT Phil**: 25 Size; 26 Run Block; 27 Pass Block; 28 Zone Block; 29 Balanced
- `WRPP` **WR Phil**: 15 Strong; 16 Tall; 17 Speed; 18 Route-Runner; 19 Balanced
- `HBPP` **HB Phil**: 5 Speed; 6 Moves; 7 Power; 8 Receiving; 9 Workhorse; 10 Balanced
- `GDow` **Day of Week**: 0 Thursday; 1 Friday; 2 Saturday; 3 Sunday; 4 Monday; 5 Tuesday; 6 Wednesday
- `PPGR` **Position Group**: 0 QB; 1 RB; 2 WR; 3 TE; 4 OL; 5 DL; 6 LB; 7 DB; 8 K; 9 P
- `COPS` **Position**: 0 HC; 1 OC; 2 DC; 3 STC; 4 QBC; 5 RBC; 6 WRC; 7 OLC; 8 LBC; 9 DLC; 10 DBC
- `PTId` **Personality**: 0 Commander; 1 Superstar; 2 Traditionalist; 3 Loyalist; 4 Guru; 5 Lone Wolf; 6 Ambassador; 7 Promoter; 8 Headliner; 9 Captain; 10 Analyst; 11 Optimist; 12 Stoic; 13 Virtuoso; 14 Anchor; 15 Titan; 16 Ally
- `PPOS` **Position**: 0 QB; 1 HB; 2 FB; 3 WR; 4 TE; 5 LT; 6 LG; 7 C; 8 RG; 9 RT; 10 LE; 11 RE; 12 DT; 13 LOLB; 14 MLB; 15 ROLB; 16 CB; 17 FS; 18 SS; 19 K; 20 P; 21 KR; 22 PR; 23 KOS; 24 LS; 25 3DB
- `GATG` **Away Team** - 40 entries (see JSON)
- `GHTG` **Home Team** - 40 entries (see JSON)
- `TRV1` **Rival 1** - 40 entries (see JSON)
- `TRV2` **Rival 2** - 40 entries (see JSON)
- `TRV3` **Rival 3** - 40 entries (see JSON)
- `CDID` **Defensive Playbook** - 43 entries (see JSON)
- `CPID` **Offensive Playbook** - 46 entries (see JSON)
- `PCOL` **College** - 297 entries (see JSON)
- `PNid` **Non-Player ID** - 3585 entries (see JSON)

## Fields by table and screen

Only fields the config names are listed; `?` marks fields it defines but leaves unnamed.

### COCH - Coach Basics
`CFNM` First Name, `CLNM` Last Name, `CSXP` Portrait ID, `TGID` Team ID, `TOID` Team Official ID, `COPS` Position [11], `CSPC` Coach Specialty, `CFUC` User Control [2], `HDAp` Overall Approval, `CCYT` Yrs w/ this Team, `CSAL` Salary, `CCLN` Contract Length, `CLTF` Last Team, `CAGE` Age, `CETH` Ethics, `CSKI` Skin Color, `CHGT` Height, `PTId` Personality [17], `PNid` Non-Player ID [3585].

### COCH - Gameday Skills
`CFNM` First Name, `CLNM` Last Name, `SKPT` Skill Points, `SKST` Strategy Current, `SKSM` Strategy Potential, `SKPC` Play Call Current, `SKPX` Play Call Potential, `SKPF` Performance Current, `SKPA` Performance Potential, `SKCR` Chemistry Current, `SKCM` Chemistry Potential, `CDVP` Career Current.

### COCH - Planning
`CFNM` First Name, `CLNM` Last Name, `CPID` Offensive Playbook [46], `OSPP` Off Scheme [5], `COTA` CPU Off Playcall Aggress, `CRBT` RB Strat, `OPPP` Off Call Preference [2], `SRHP` Start Young HB, `SRQP` Start Rookie QB, `COTR` Sim Off RunPass Ratio, `CDID` Defensive Playbook [43], `DSPP` Def Scheme [3], `CDTY` Def Philosophy [2], `CDTA` Def Playcall Aggress, `DPPP` Def Call Preference [2], `CDTR` Sim Def RunPass Ratio.

### COCH - Coach Ratings
`CFNM` First Name, `CLNM` Last Name, `CCHM` Chemistry, `CKNW` Knowledge, `CMOT` Motivation, `POVS` Overall Score, `COFF` Coach Offense, `CDEF` Coach Defense, `CRQB` QB Rating, `CRRB` RB Rating, `CRWR` WR Rating, `CROL` OL Rating, `CRDL` DL Rating, `CRLB` LB Rating, `CRDB` DB Rating, `CRKS` K Rating, `CRPS` P Rating.

### COCH - Coach Philosophies
`CFNM` First Name, `CLNM` Last Name, `NHPP` No Huddle Phil [3], `QBPP` QB Phil [5], `HBPP` HB Phil [6], `FBPP` FB Phil [4], `WRPP` WR Phil [5], `TEPP` TE Phil [5], `TKPP` OT Phil [5], `GDPP` G Phil [5], `CRPP` C Phil [5], `BZPP` Blitz Phil [3], `CVPP` Coverage Phil [3], `DEPP` DE Phil [5], `DTPP` DT Phil [5], `OLPP` OLB Phil [5], `MLPP` MLB Phil [5], `CBPP` CB Phil [5], `FSPP` FS Phil [5], `SsPP` SS Phil [5], `KKPP` K Phil [3], `KPPP` P Phil [3], `DMPP` Defining Moment Phil [3].

### COCH - Responsibilities
`CFNM` First Name, `CLNM` Last Name, `CFDA` Draft Player [2], `CFDP` Sign Draft Picks [2], `CFFA` Sign FAs [2], `CFFR` Fill Rosters [2], `CFRP` Re-sign Players [2], `CFRR` Depth Chart [2].

### COCH - Record
`CFNM` First Name, `CLNM` Last Name, `CCWI` Career Wins, `CCLO` Career Losses, `CCTI` Career Ties, `CCWS` Winning Seasons, `CCPM` HC Playoff Appearances, `CCPW` Playoff Wins, `CCPL` Playoff Losses, `CSBW` SB Wins, `CSBL` SB Losses.

### COCH - Coach Unknowns
`CFNM` First Name, `CLNM` Last Name.

Unnamed: `CAAB`, `CCTC`, `CHSD`, `CFRE`, `CAPH`, `DBPH`, `FBPH`, `HBPH`, `LBPH`, `QBPH`, `TEPH`, `DLPH`, `OLPH`, `KPPH`, `WRPH`, `CFSH`, `CFHL`, `CWPL`, `BMCP`, `CRCP`, `DBFP`, `FBFP`, `HBFP`, `LBFP`, `QBFP`, `TEFP`, `DLFP`, `OLFP`, `KPFP`, `WRFP`, `CBMP`, `FBMP`, `HBMP`, `QBMP`, `GDMP`, `DEMP`, `TEMP`, `KKMP`, `TKMP`, `MLMP`, `OLMP`, `KPMP`, `CRMP`, `WRMP`, `FSMP`, `SSMP`, `DTMP`, `BNPP`, `CRRP`, `BPSP`, `IPSP`, `CLTR`, `JOBS`, `DBFS`, `FBFS`, `HBFS`, `LBFS`, `QBFS`, `TEFS`, `DLFS`, `OLFS`, `KPFS`, `WRFS`, `DBHS`, `FBHS`, `HBHS`, `LBHS`, `QBHS`, `TEHS`, `DLHS`, `OLHS`, `KPHS`, `WRHS`, `CTJS`, `CFEX`, `CHTY`, `COTY`, `CBSZ`, `PHRd`, `CThg`, `PNPt`, `PNCw`, `CTgw`

### TEAM - Team Basic Info
`TLNA` Team Location Name, `TDNA` Team Name, `TSNA` Team Short Name, `TMNC` Medium Nickname, `TMSA` Team Salaries, `TGID` Team ID, `TOID` Team Official ID, `FRID` Franchise ID, `TORD` Team Roster Order, `CYID` City ID, `TTYP` Team Type, `LGID` League ID, `CGID` Conference ID, `DGID` Division ID, `TRV1` Rival 1 [40], `TRV2` Rival 2 [40], `TRV3` Rival 3 [40], `TLGL` Team Logo, `TLGS` Secondary Logo, `TBCR` Primary Red, `TBCB` Primary Blue, `TBCG` Primary Green, `TB2R` Secondary Red, `TB2B` Secondary Blue, `TB2G` Secondary Green, `TDAN` Announcer Database.

### TEAM - Team Stadium
`TLNA` Team Location Name, `TDNA` Team Name, `SGID` Stadium ID, `SID1` Stadium Open Roof ID, `TEZ1` End Zone 1, `TEZ2` End Zone 2, `TMFL` Mid-Field Logo, `TAth` Thanksgiving Host, `TAss` Shares Stadium.

### TEAM - Team Off / Def
`TLNA` Team Location Name, `TDNA` Team Name, `TOPB` Offensive Playbook, `TDPB` Defense Playbook, `TROV` Rating Overall, `TROF` Offense Rating, `TRDE` Defense Rating, `TRST` ST Rating, `TRQB` QB Rating, `TRRB` RB Rating, `TWRR` WR Rating, `TROL` OL Rating, `TRDL` DL Rating, `TRLB` LB Rating, `TRDB` DB Rating.

### TEAM - Team Win Record
`TLNA` Team Location Name, `TDNA` Team Name, `DISN` Division Standing, `TPSW` Prior Season Wins, `TPSL` Prior Season Losses, `TPST` Prior Season Ties, `TREP` Team Reputation.

### TEAM - Team Unknowns
`TLNA` Team Location Name, `TDNA` Team Name.

Unnamed: `TLSA`, `TLPB`, `TLSB`, `TLTB`, `TSID`, `TCHE`, `TTSE`, `TLPG`, `TLSG`, `TLTG`, `TFTL`, `TCDO`, `TSHO`, `TUHO`, `TFLO`, `TAUO`, `TCRP`, `TGRP`, `TLPR`, `TLSR`, `TLTR`, `TVIS`, `TVQS`, `TGPT`, `TUAW`, `TSOW`, `TCTX`

### PLAY - Player Info
`TGID` Team ID, `PFNA` Player First Name, `PLNA` Player Last Name, `PGID` Player ID, `POID` Player Original ID, `PSXP` Portrait ID, `PPOS` Position [26], `PBMO` Birth Month, `PBDA` Birth Day, `PAGE` Player Age, `PCOL` College [297], `PHTN` Hometown, `PHSN` Home State, `PPTI` Acquired From, `PDRO` Draft Round, `PDPI` Round Pick, `PFPB` Pro Bowl.

### PLAY - Player Appearance
`PFNA` Player First Name, `PLNA` Player Last Name, `BSAA` Arm Definition, `BSBA` Butt Definition, `BSCA` Calf Definition, `BSFA` Foot Definition, `BSGA` Gut Definition, `BSPA` Pad Definition, `BSSA` Shoulder Definition, `BSTA` Thigh Definition, `BSWA` Waist Definition, `PGID` Player ID, `TGID` Team ID, `POID` Player Original ID, `PGHE` Face, `PUHE` Cyberface, `PCPH` Skin Color, `PSKI` Skin Color ID, `PTAL` Tattoo Left, `PHCL` Hair Color, `PHAN` Preferred Hand, `PTAR` Tattoo Right, `BSAT` Arm Size, `BSBT` Butt Size, `BSCT` Calf Size, `BSFT` Foot Size, `PHGT` Height, `BSGT` Gut Size, `PWGT` Weight, `BSST` Shoulder Size, `BSTT` Thigh Size, `BSWT` Waist Size, `PTId` Personality [17].

### PLAY - Equipment
`PFNA` Player First Name, `PLNA` Player Last Name, `PMPC` Mouthpiece, `PGID` Player ID, `TGID` Team ID, `POID` Player Original ID, `PLHA` Left Hand, `TLHA` Left Hand 2, `PRHA` Right Hand, `TRHA` Right Hand 2, `PBRE` Nasal Strip, `PEYE` Eye Paint, `PLSH` Left Shoe, `PRSH` Right Shoe, `PLTH` Left Knee, `PRTH` Right Knee, `PNEK` Neck Pad, `PFMK` Facemask, `PLEL` Left Elbow 1, `TLEL` Left Elbow 2, `PREL` Right Elbow 1, `TREL` Right Elbow 2, `PSPL` Left Ankle, `PGSL` Arm Sleeves, `PTSL` Arm Sleeves 2, `PHLM` Helmet, `PJEN` Jersey Number, `PLKN` Left Knee, `PRKN` Right Knee, `PJER` Sleeves 3, `PSPR` Right Ankle, `PLWR` Left Wrist, `TLWR` Left Wrist 2, `PRWR` Right Wrist, `TRWR` Right Wrist 2, `PVIS` Visor, `BSPT` Shoulder Pad Size, `PJTY` 1st Initial Jersey.

### PLAY - Player Style
`PFNA` Player First Name, `PLNA` Player Last Name, `PGID` Player ID, `TGID` Team ID, `PCEL` Celebration Chance, `PEPS` Celebration, `PSTY` Throwing Style.

### PLAY - Player Ratings
`PFNA` Player First Name, `PLNA` Player Last Name, `PGID` Player ID, `TGID` Team ID, `PPOS` Position [26], `POPS` Original Position ID, `PTEN` Tendency, `POVR` Overall, `PSPD` Speed, `PSDX` Speed Max, `PAGI` Agility, `PAGX` Agility Max, `PACC` Acceleration, `PACX` Acceleration Max, `PSTR` Strength, `PSTX` Strength Max, `PAWR` Awareness, `PAWX` Awareness Max, `PSTA` Stamina, `PINJ` Injury, `PINX` Injury Max, `PLTR` Trucking, `PLTX` Trucking Max, `PELU` Elusiveness, `PELX` Elusiveness Max, `PBCV` Ball Carrier Vision, `PBCX` Ball Carrier Vision Max, `PLSA` Stiff Arm, `PLSX` Stiff Arm Max, `PLSM` Spin Move, `PLJX` Juke Move Max, `PCAR` Carrying, `PCAX` Carry Max, `PTHP` Throw Power, `PTPX` Throw Power Max, `PTHA` Throw Accuracy, `PTAX` Throw Accuracy Max, `PCTH` Catching, `PCTX` Catch Max, `PLSC` Spectacular Catch, `PSCX` Spectacular Catch Max, `PLCI` Catch in Traffic, `PLCX` Catch in Traffic Max, `PLRR` Route Running, `PRRX` Route Running Max, `PLRL` Release, `PRLX` Release Max, `PJMP` Jumping, `PJMX` Jump Max, `PPBK` Pass Block, `PPBX` Pass Block Max, `PRBK` Run Block, `PRBX` Run Block Max, `PLIB` Impact Block, `PIBX` Impact Block Max, `PRBS` Run Block Strength, `PRSX` Run Block Strength Max, `PRBF` Run Block Footwork, `PRFX` Run Block Footwork Max, `PPBS` Pass Block Strength, `PPSX` Pass Block Strength Max, `PPBF` Pass Block Footwork, `PPFX` Pass Block Footwork Max, `PTAK` Tackling, `PTKX` Tackle Max, `PLHT` Hit Power, `PLHX` Hit Power Max, `PLPm` Power Moves, `PPMX` Power Moves Max, `PFMS` Finesse Moves, `PFMX` Finesse Moves Max, `PBSG` Block Shedding, `PBSX` Block Shedding Max, `PLPU` Pursuit, `PPUX` Pursuit Max, `PLPR` Play Recognition, `PPRX` Play Recognition Max, `PLMC` Man Coverage, `PLMX` Man Coverage Max, `PLZC` Zone Coverage, `PLZX` Zone Coverage Max, `PLPE` Press Coverage, `PKPR` Kick Power, `PKPX` Kick Power Max, `PKAC` Kick Accuracy, `PKAX` Kick Accuracy Max, `PKRT` Kick Return, `PKRX` Kick Return Max, `PLRN` Learning, `PLRX` Learning Max, `PTGH` Toughness, `PTGX` Toughness Max, `PCAF` Fatigue 1, `PSEF` Fatigue 2, `PCUF` Fatigue 3.

Unnamed: `PSAX`, `PSMx`, `PLJM`, `PPEX`, `PRSx`

### PLAY - Contract Info
`PFNA` Player First Name, `PLNA` Player Last Name, `TGID` Team ID, `PCON` Contract Years, `PCYL` Contract Yrs Left, `PTSA` Total Salary, `PSBO` Signing Bonus, `PCSA` Current Salary Total, `PSA0` Salary Year 1, `PSB0` Sign Bonus Year 1, `PSA1` Salary Year 2, `PSB1` Sign Bonus Year 2, `PSA2` Salary Year 3, `PSB2` Sign Bonus Year 3, `PSA3` Salary Year 4, `PSB3` Sign Bonus Year 4, `PSA4` Salary Year 5, `PSB4` Sign Bonus Year 5, `PSA5` Salary Year 6, `PSB5` Sign Bonus Year 6, `PSA6` Salary Year 7, `PSB6` Sign Bonus Year 7, `PVCO` V Contract Years, `PVTS` V Total Salary, `PVSB` V Signing Bonus, `PGID` Player ID, `PROL` Player Role ID, `PIMP` Importance, `PIMX` Importance Max, `PFHO` Holdout, `PMOR` Morale, `PMOX` Morale Max, `PCMT` Comment, `PYWT` Years with Team, `HDAp` Overall Approval.

### PLAY - Player Health
`PFNA` Player First Name, `PLNA` Player Last Name, `PGID` Player ID, `TGID` Team ID, `PHDC` Head Health, `PHDX` Head Health Max, `PLAC` Left Arm Health, `PLAX` Left Arm Health Max, `PRAC` Right Arm Health, `PRAX` Right Arm Health Max, `PTRC` Torso Health, `PTRX` Torso Health Max, `PLLC` Left Leg Health, `PRLc` Right Leg Health, `PRLx` Right Leg Health Max.

Unnamed: `PLLX`

### PLAY - Player Unknowns
`PFNA` Player First Name, `PLNA` Player Last Name.

Unnamed: `PUND`, `PRSE`, `PUCL`, `PSTM`, `PLES`

### GMVW - GMVW
`TGID` Team ID, `CBPP` CB Phil [5], `FBPP` FB Phil [4], `HBPP` HB Phil [6], `QBPP` QB Phil [5], `GDPP` G Phil [5], `DEPP` DE Phil [5], `TEPP` TE Phil [5], `KKPP` K Phil [3], `TKPP` OT Phil [5], `MLPP` MLB Phil [5], `OLPP` OLB Phil [5], `KPPP` P Phil [3], `CRPP` C Phil [5], `WRPP` WR Phil [5], `FSPP` FS Phil [5], `DTPP` DT Phil [5], `SsPP` SS Phil [5], `CDVP` Career Current, `POVS` Overall Score, `SKPT` Skill Points, `PTId` Personality [17], `PNid` Non-Player ID [3585].

Unnamed: `GMAB`, `SKTD`, `SKNG`, `GMPH`, `SKNM`, `SKTM`, `RFAP`, `CRCP`, `ESCP`, `PRDP`, `GTDP`, `TDFP`, `FTGP`, `IWKP`, `CBMP`, `FBMP`, `HBMP`, `QBMP`, `GDMP`, `DEMP`, `TEMP`, `KKMP`, `TKMP`, `MLMP`, `OLMP`, `KPMP`, `CRMP`, `WRMP`, `FSMP`, `GSMP`, `SSMP`, `DTMP`, `CINP`, `GCPP`, `GSPP`, `RSPP`, `TMSP`, `RSSP`, `DFTP`, `GFTP`, `NGTP`, `BTTP`

### TRVW - Trainers
`TGID` Team ID, `CDVP` Career Current, `POVS` Overall Score, `SKPT` Skill Points, `PTId` Personality [17], `PNid` Non-Player ID [3585].

Unnamed: `TRAB`, `TSIE`, `DBPH`, `FBPH`, `HBPH`, `LBPH`, `QBPH`, `TEPH`, `DLPH`, `OLPH`, `KPPH`, `TRPH`, `WRPH`, `TSRH`, `TRCI`, `TRSI`, `TSFM`, `TRGM`, `TSIM`, `TSRM`, `TRSM`, `CRCP`, `DBFP`, `FBFP`, `HBFP`, `LBFP`, `QBFP`, `TEFP`, `DLFP`, `OLFP`, `KPFP`, `WRFP`, `IPSP`, `TSFR`, `DBFS`, `FBFS`, `HBFS`, `LBFS`, `QBFS`, `TEFS`, `DLFS`, `OLFS`, `KPFS`, `WRFS`, `DBHS`, `FBHS`, `HBHS`, `LBHS`, `QBHS`, `TEHS`, `DLHS`, `OLHS`, `KPHS`, `WRHS`

### OWNR - Owners
`PTId` Personality [17], `PNid` Non-Player ID [3585].

Unnamed: `ONAB`, `ONPH`, `DCCP`, `OCCP`, `PCCP`, `TRCP`, `GmCP`

### Club Officials - Club Officials
`TGID` Team ID, `TOID` Team Official ID, `POVS` Overall Score, `HDAp` Overall Approval, `PTId` Personality [17], `PNid` Non-Player ID [3585], `PNFs` First Name, `PNMl` Mid Name, `PNLn` Last Name, `PNPs` Club Title [5], `SKPT` Skill Points.

Unnamed: `PEBS`, `PTJS`, `PSHC`, `PSHT`, `PCYT`, `PHRd`, `PNFe`, `PNAg`, `PNSi`, `PNCt`, `PNHt`, `PNPt`, `PNWt`

### GMSK - GMSK
`PPGR` Position Group [10], `PNid` Non-Player ID [3585].

Unnamed: `SKSC`, `SKRE`, `SKRM`, `SKSX`

### TPHL - Team Philosophies
111 fields (1 named); mostly per-position preference and health tables, see the config.

### TPHS - Team Philosophy (the config calls it "Team Health")
111 fields (29 named in the config); all 110 philosophy fields are decoded above, in "Team Philosophy: all 110 fields".

### DCHT - Depth Chart
`TGID` Team ID, `PPOS` Position [26], `ddep` Depth, `PGID` Player ID.

Unnamed: `DCLK`

### INJY - Injuries
`PGID` Player ID, `TGID` Team ID, `INJL` Injury Length, `INIR` Injured Reserve, `INJT` Injury Type.

Unnamed: `IJSK`, `INJR`, `INTT`, `RHBU`, `ITUt`

### DRPP - Draft
`PGID` Player ID, `TGID` Team ID, `PDRO` Draft Round, `PDPI` Round Pick, `DPNM` Overall Pick.

### SCHD - Schedule
`SEYR` Season Year, `SESI` Seasons IN, `SEWN` Week Num, `SGNM` Game Num, `GATG` Away Team [40], `GHTG` Home Team [40], `GDow` Day of Week [7], `GTOD` Time of Day, `SEST` Preseason, `GFTG` Thanksgiving, `GSTA` Playoffs, `SGID` Stadium ID, `SEWT` Weight.

## What could be built next (ranked)

1. **Coach game plan - built**, as the **Team Philosophy...** button, on the team's `TPHS` row (the table the game's screen reads; see "Checked in the game" above): all 110 fields, from the offensive and defensive scheme, no-huddle, playbook control, blitzing, coverage, defining moments and the position philosophies, to the GM and staff settings, roster minimums and health and fatigue substitution. **Not built, and not looked at in the game:** the coach-row (`COCH`) versions of these fields, `CDTY` defensive philosophy, CPU play-call aggression (`COTA`, `CDTA`), simulated run/pass ratios (`COTR`, `CDTR`), RB strategy `CRBT`, and start young HB / rookie QB (`SRHP`, `SRQP`). An earlier version of the editor wrote some of these on the coach rows; it was removed because the Team Philosophy screen did not read them, which says nothing about whether the game uses them elsewhere.
2. **Coach philosophies** on the coach rows (23 fields, the same lists as the team's): the team versions are built (item 1); whether the coach-row copies matter is untested.
3. **Who handles what** (`COCH` Responsibilities): User / CPU for drafting, signing draft picks and free agents, filling rosters, re-signing, depth chart (`CFDA`, `CFDP`, `CFFA`, `CFFR`, `CFRP`, `CFRR`), plus `CFUC` User Control.
4. **Player info with names**: College (297-name list), position names, height, weight, home state/town, jersey number, Pro Bowl flag, throwing style, body-part health (all named above).
5. **Names for the cosmetic editor**: the Player Appearance (33 fields), Equipment (38) and Player Style views name the appearance and gear fields the earlier cosmetic-editor idea needs.
6. **Team info**: primary/secondary team colors as RGB (`TBCR/TBCG/TBCB`, `TB2R/TB2G/TB2B`), three rivals (`TRV1-3`, team list), stadium and end-zone/mid-field logos, Thanksgiving host, shared stadium, team reputation `TREP`, prior-season record, team-position ratings `TROV/TROF/TRDE/...` (probably calculated).
7. Club officials, owners and trainers: names and personality, mostly already reachable.

Nothing here has been tested in-game; each item above should be checked on a copy of a save before it is trusted.
