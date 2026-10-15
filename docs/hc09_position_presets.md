# Position presets (team position philosophies) and their weights

What the game's "player type" presets really are, what the game's files say about them, and what is still unknown. Checked on one real career and the game's `qkl_boot.ast`.

## What the presets are

The presets on the game's Team Philosophy screen (five each for CB, FS and SS, three for K and P, and so on) are the **team position philosophies**: the `xxPP` values 0 to 80 of the `TPHS` table (see `docs/hc09_field_reference.md`):

| Position | Values | Presets |
|---|---|---|
| QB | 0 to 4 | Mobile/Speed, Strong Arm/Tools, Pure Passer, Field General, Balanced |
| HB | 5 to 10 | Speed, Moves, Power, Receiving, Workhorse, Balanced |
| FB | 11 to 14 | Ball Carrier, Blocking, Receiving, Balanced |
| WR | 15 to 19 | Strong/Blocking, Tall/Redzone Threat, Speed, Quick/Route Runner, Balanced |
| TE | 20 to 24 | Soft Hands/Routes, Blocking, Playmaker, H-back, Balanced |
| OT / OG / C | 25 to 29 / 30 to 34 / 35 to 39 | Size/Strength/Engulfer (Mauler for OG and C), Run Block Specialist, Pass Block Specialist, Zone Blocking, Balanced |
| DE | 40 to 44 | Balanced, Prototype, Undersized Speed Rusher, Run Stopper, Versatile/3-4 |
| DT | 45 to 49 | Balanced, Prototype, One Gap Penetrator, Run Stopper, Versatile/3-4 |
| OLB / MLB | 50 to 54 / 55 to 59 | OLB: Balanced, Coverage/Cover 2, Run Stopper, PassRusher/3-4 Blitzer, Prototype; MLB: Balanced, Coverage/Speed, Power/Blitzer, 3-4/Tackler, Prototype |
| CB | 60 to 64 | Balanced, Man Coverage/Ballhawk, Strong/Press/Run Support, Prototype, Cover 2 |
| FS | 65 to 69 | Balanced, Man Coverage, Centerfielder, Prototype, Run Support/Blitzer |
| SS | 70 to 74 | Balanced, Coverage, Prototype, Run Support/Big Hitter, Smart/Productive |
| K / P | 75 to 77 / 78 to 80 | Big Foot/Distance, Pinpoint Accuracy, Balanced / Big Foot/Distance, Pinpoint Accuracy, Balanced |

All the names are the game's own: table `EGPP` in `qkl_boot.ast` names every preset (value 0 to 80), and the CB, FS, SS, DT, K, P and QB names also match what users saw on the Team Philosophy screen. The game writes them with the position ("Prototype CB"); the editor leaves the position off. The community config's tight end list was in a different order from the game's (the weight tables agree with the game), which an earlier version of this editor repeated.

## What is *not* a preset

The `PLYT` table (37 rows, `PTId`, four archetypes per position group with a description such as "A Pocket QB is deadly accurate...") is what the game uses to **generate players**. It has no five-per-safety lists and nothing like "Freak Kicker" exists in game as a preset. An earlier version of Player Type Fit used `PLYT`, which is why its list did not match the game's.

## Where the game keeps what each preset values

The game's own files (`qkl_boot.ast`, the same database `PLYT` and `PORC` come from) hold one row per preset, keyed by `GMPP` = the preset's value (0 to 80, some tables also 81):

- **`PEAW`** (athletic): `ACCW SPDW AGLW FIMW SPMW THPW JMPW STRW RBSW ELUW JMVW HPWW KPWW PBSw`
- **`PEIW`** (skills, 34 columns): `THAW STAW IMBW RNBW KACW TACW SPCW PBFW RBFW PRGW TGHW INJW PBKW TRKW RELW STMW PWMW LRNW IMPW MORW RORW PURW AWRW BKSW RNSW CATW CITW KRTW BCVW MCVW ZCVW CARw PRSw`
- **`PEOW`** (seven factor weights `OPDW OINW OLNW ODRW OATW OPTW OSZW`) and **`PESW`** (`HTSW WTSW`, how much height and weight count inside the size factor): these are the factors of the Evaluate Roster screen ("Each player is graded on several key factors. Those factors make up their overall."). The names read as production, individual skills, learning, durability, athleticism, potential and size. Used by the estimate below.
- `PEDW` (`CUHW CHLW CFTW`) is the same for every preset (5, 10, 1). Not used.
- `PORC` (21 rows, one per position, weights stored as IEEE floats with a `PRDH` / `PRDL` range) is the per-position side, presumably how the standard overall is built. Not used by the editor.

Each weight column names a player rating (`ACCW` acceleration, `MCVW` man coverage, `HPWW` hit power, ...); the editor's pairing is by name, and each was checked against which position groups use it (hit power is heavy for MLB, SS and OLB; route running for WR and TE; power move for DT and DE). `RNSW` is zero for every preset.

The weights read like the in-game names. For the five CB presets: Man Coverage/Ballhawk weighs man coverage 31 and zone coverage 0; Cover 2 the reverse; Strong/Press/Run Support weighs tackling, pursuit and press; Prototype has the most ratings at the maximum weight.

## What the editor does with it

**Player Type Fit** lists a position's presets (with the team's current preset beside each player, from `TPHS`) and shows an **Est. OVR** for each player: an estimate of the overall the game's Evaluate Roster screen shows under that preset. The tab says so, with the margin: against the 55 readings below the estimate is within 2 points for most and within 3 for nearly all (worst reading 5 off, and an unusual build may be further out), for cornerbacks, safeties and defensive tackles only; other positions use the same method unchecked. (*Saved OVR* is the overall stored in the save, which can be stale or from another preset.)

The estimate is `Sum(factor weight * factor score) / Sum(factor weight)` over the `PEOW` factors. The game names the grade categories (table `EGRD`: Overall, Potential, Athletic, Intangibles, Production, Size, Learning, Durability), so the seven `PEOW` weights are OAT Athletic, OIN Intangibles, OPD Production, OPT Potential, OSZ Size, OLN Learning and ODR Durability; "Intangibles" is the one built from the skill ratings:

| Factor | Weight | Score used | Known or stand-in |
|---|---|---|---|
| OIN Intangibles | `OINW` | the player's skill ratings weighted by `PEIW` | from the files |
| OAT Athletic | `OATW` | the athletic ratings weighted by `PEAW` | from the files |
| OLN Learning | `OLNW` | the Learning rating | stand-in |
| ODR Durability | `ODRW` | the Injury rating | stand-in |
| OPT Potential + OPD Production | `OPTW + OPDW` | the skills averaged with the `PEIW` weights of the position's Balanced preset | stand-in |
| OSZ Size | `OSZW` | `51.1 + (0.271 * HTSW * h + 1.350 * WTSW * w) / (HTSW + WTSW)`, h and w = the player's height and weight percentile (0 to 99) among that position's players in the save | stand-in, three numbers fitted |

A plain weighted average of the `PEAW` and `PEIW` ratings was tried first (what an earlier version of this tab showed). It matched the game under Balanced (within 2) but was up to 19 points off under other presets (Graham under Cover 2: 74 against the game's 55), because it ignored the factor weights: Man Coverage/Ballhawk gives athleticism 15 of 71 where Balanced gives 31 of 102, and Prototype gives size 15 of 73.

## In-game readings

Taken from the Evaluate Roster screen of a test career (Bears), one preset at a time, each shown as *game / the editor's estimate* (rounded). The bodies (`PHGT` inches, `PWGT` pounds minus 160): Tillman 73 / 36, R. Manning 68 / 25, Vasher 70 / 17, Graham 72 / 35, McBride 69 / 25, Archuleta 72 / 55, Harris 75 / 132, Dvoracek 75 / 145, Adams 72 / 139, Garay 76 / 150, M. Brown 70 / 47, D. Manning 71 / 42.

| Preset | Tillman | R. Manning | Vasher | Graham | McBride | Archuleta |
|---|---|---|---|---|---|---|
| CB Balanced (60) |  | 82 / 83 | 89 / 91 | 69 / 68 | 76 / 76 |  |
| CB Man Coverage/Ballhawk (61) |  | 78 / 80 | 88 / 90 | 64 / 65 | 72 / 73 |  |
| CB Strong/Press/Run Support (62) |  | 79 / 81 | 85 / 88 | 70 / 72 | 73 / 75 |  |
| CB Prototype (63) | 87 / 92 | 78 / 78 | 85 / 84 | 74 / 72 |  |  |
| CB Cover 2 (64) | 84 / 89 | 77 / 80 | 88 / 91 | 55 / 58 |  |  |
| SS Balanced (70) |  |  |  |  |  | 67 / 66 |
| SS Coverage (71) |  |  |  |  |  | 62 / 62 |
| SS Prototype (72) |  |  |  |  |  | 78 / 78 |
| SS Run Support/Big Hitter (73) |  |  |  |  |  | 73 / 74 |
| SS Smart/Productive (74) |  |  |  |  |  | 62 / 62 |

| Preset | Harris | Dvoracek | Adams | Garay |
|---|---|---|---|---|
| DT Balanced (45) | 89 / 89 | 69 / 67 | 66 / 69 | 66 / 64 |
| DT Prototype (46) | 84 / 84 | 73 / 71 | 72 / 71 | 76 / 73 |
| DT One Gap Penetrator (47) | 90 / 91 | 68 / 67 | 65 / 67 | 54 / 55 |
| DT Run Stopper (48) | 86 / 86 | 70 / 70 | 71 / 71 | 71 / 72 |
| DT Versatile/3-4 (49) | 87 / 87 | 69 / 68 | 70 / 69 | 70 / 68 |

| Preset | M. Brown | D. Manning |
|---|---|---|
| FS Balanced (65) | 82 / 83 | 77 / 76 |
| FS Man Coverage (66) | 82 / 82 | 75 / 75 |
| FS Centerfielder (67) | 82 / 83 | 75 / 74 |
| FS Prototype (68) | 82 / 84 | 82 / 78 |
| FS Run Support/Blitzer (69) | 80 / 82 | 74 / 74 |

Over these 55 readings the estimate is within 1 for 26, within 2 for 40, within 3 for 50; the worst is 4.7 (Tillman under Cover 2) and the root-mean-square error is 1.8 (CB 2.3, DT 1.5, FS 1.7, SS 0.4). Cover 2 corners are all over-estimated by about 3, and Danieal Manning's FS Prototype reading (82) is 4 above the estimate. The stand-ins were fitted to these same readings, so the figures are in-sample. Leaving one player out at a time, the root-mean-square error was 2.1 and the worst 7.6 (Tillman under Prototype, a body the rest of the fit hadn't seen), then 4.7 (Tillman under Cover 2) and 4.6 (D. Manning under FS Prototype).

The readings came in batches, and each new batch was scored with the model as it stood before refitting. The first model (25 CB and SS readings, size as one percentile) was within 2.9 on the Balanced DT and FS readings, but 5 to 7 low for the big defensive tackles under Prototype, which led to the current size score (weight counts about five times as much as height) and to the Balanced-weights potential stand-in. Scored on the DT Run Stopper and FS Prototype readings before they were used, the refit was within 4.3 (RMS 2.2); on DT Versatile/3-4 and FS Run Support/Blitzer, within 2.1 (RMS 1.2).

## Not known

- **The game's exact overall formula.** The structure above fits, but only the `OIN` and `OAT` scores are known from the files. How learning, durability, potential, production and size are scored is guessed from the readings. In particular the height part of the size score is poorly pinned down (one weight-heavy fit explains the data almost as well), which may matter for positions where height is weighted heavily, such as WR Tall (`HTSW` 15).
- Every position other than CB, FS, SS and DT has no readings, so the estimate there is unchecked. Readings for MLB, WR and HB would be the next most useful.
- Whether potential and production (`OPTW`, `OPDW`) use the same ratings as skills; the displayed potential (POT) also changes with the preset, so it is computed the same way from projected ratings.
