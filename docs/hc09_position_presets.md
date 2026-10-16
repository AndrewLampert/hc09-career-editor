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

**Player Type Fit** lists a position's presets (with the team's current preset beside each player, from `TPHS`) and shows an **Est. OVR** for each player: the overall the game's Evaluate Roster screen shows under that preset, rebuilt with the game's own formulas. Selecting a player shows his seven grades, as the game's Roster Breakdown does. The tab says what is exact and what is approximate, with the margin: against the 55 readings below the estimate is within 1 point for 51 and never more than 3 off, for cornerbacks, safeties and defensive tackles; other positions use the same formulas, which were checked against the game's stored grades for all 21 positions but not against the Evaluate Roster screen. (*Saved OVR* is the overall stored in the save, which can be stale or from another preset.)

The overall is `floor(Sum(PEOW weight * grade) / Sum(PEOW weight))` over the game's seven grades (table `EGRD`), each a 0 to 99 score. The grade formulas were settled from table **`RPGR`** in a save, which holds the game's own grades for the draft class: every grade revealed for all 350 prospects (the pseudo-team 1015), plus what each team has scouted. Against those stored grades:

| Grade | Formula | Against the game |
|---|---|---|
| Athletic | `floor(PEAW-weighted average of the athletic ratings)` | exact, 350 of 350 |
| Intangibles | `floor(PEIW-weighted average of all the skill ratings, Learning included)` | exact, 350 of 350 |
| Learning | the Learning rating | exact, 350 of 350 |
| Durability | `floor(body-part healths weighted by LPHC for the position and the player's hand / 10)`; the six parts are head, torso, both arms, both legs (maximum health, 0 to 1000); `LPHC` weights add to 100, a quarterback's throwing arm counts 25 and the other 5 | 310 of 350 exact, 347 within 2 |
| Potential | `floor(Sum(PEOW * grade) / Sum(PEOW))` over Intangibles, Learning, Athletic, Durability and Size, with Intangibles, Learning and Athletic computed from the **maximum** ratings (the `...X` columns) | exact, 350 of 350, given the stored Size |
| Size | a stepped lookup of height and weight, weighted by `PESW` (`HTSW`, `WTSW`); it is not in the game's data tables. Approximated as `71.8 + 0.316 * h * HTSW share + 0.39 * w * WTSW share`, h and w the player's height and weight percentile (0 to 99) among that position's players, at most 99 | approximate, RMS 6.5 |
| Production | counted as 0 (its `OPDW` weight stays in the divisor); the draft class's stored Production grades run 1 to 99 (median 20) and come from something that is not in the player rows | fits the readings best |

The stored overall of a draft prospect uses a different set of weights, table `PEdW` (17 rows, one per position group, mapped from the position by table `PLPS`), not the preset's `PEOW`: `floor(Sum(PEdW * grade) / Sum(PEdW))` matches the stored overall for all 350 prospects. The `PEIW` weight columns for stiff arm and stamina are `STAW` (stiff arm, `PLSA`) and `STMW` (stamina, `PSTA`): an earlier version of this editor had them the other way round.

How it got here: a plain weighted average of the `PEAW` and `PEIW` ratings was tried first (what the first version of this tab showed). It matched the game under Balanced (within 2) but was up to 19 points off under other presets (Graham under Cover 2: 74 against the game's 55). A second version used the factor weights with stand-ins for the unknown grades (learning rating, injury rating for durability, skills under the Balanced preset for potential, size from percentiles), fitted to the readings: within 3 for 50 of 55, worst 4.7. The stored draft-class grades then showed what the grades really are (durability is the body parts, not the injury rating; potential is the same overall computed from the maximum ratings; intangibles includes learning).

## The weighting breakdown ("?") and the weak DT / DE types

The **?** button next to the preset list opens a breakdown of the preset selected now, beside the position's Balanced preset: the seven grades and their `PEOW` weights, then every rating as its share of the whole overall. A rating counts directly (through the Athletic or Intangibles grade) and again through Potential, which is the same weighted average over the maximum ratings, so the second table adds both up: `grade share = (w + OPTW * w / (OINW + OLNW + OATW + ODRW + OSZW)) / Sum(all seven)`, split among the ratings by their `PEAW` / `PEIW` weights. The Learning rating also counts as its own grade (`OLNW`). Production's weight stays in the divisor and counts as 0.

**One Gap Penetrator (DT, 47) and Undersized Speed Rusher (DE, 42)** (the community calls them the Aaron Donald / John Randle and Dwight Freeney / Elvis Dumervil types) are weak in the game's own data, compared with the position's Balanced preset (45 and 40):

| | PEIW Play Rec `PRGW` | PEIW Awareness `AWRW` | PEIW Learning `LRNW` | PEOW Intangibles `OINW` | PEOW Learning `OLNW` |
|---|---|---|---|---|---|
| DT Balanced (45) / One Gap (47) | 10 / 5 | 31 / 10 | 18 / 5 | 15 / 3 | 10 / 3 |
| DE Balanced (40) / Speed Rusher (42) | 15 / 5 | 31 / 5 | 18 / 5 | 25 / 3 | 15 / 1 |

So a smart pass rusher rates low under those types. **Fix weak DT / DE types...** (bottom of Player Type Fit) copies the chosen weights from Balanced into the game's database, which exists as entry 46 of `qkl_boot.ast` and as a byte-identical copy in entry 1816 of `qkl_fe2ig.ast` (both are patched). The options: the three `PEIW` rating weights, the Learning grade's weight `OLNW` (both ticked by default), and the Intangibles grade's weight `OINW` (off by default). Measured on the league's players in a save, the three rating weights alone move an overall by about 0.2 points on average (at most 1), so the Learning grade's weight is what makes the difference: with it, overalls move by 2.3 (DT) and 3.6 (DE) on average, up to -13 / +8, and the correlation of the type with the average of Play Rec, Awareness and Learning goes from 0.54 to 0.75 (DT) and 0.65 to 0.85 (DE); adding `OINW` brings it to 0.88 and 0.92.

How the patch is made (bridge commands `shipped-table-patch` and `shipped-table-restore`): the entries are stored as plain bytes at a fixed offset, and opening one with the DB library and saving it unchanged gives back the same bytes, so only the changed bytes are written over the same range and the archive's table of contents is untouched (8 edited values change about 30 bytes). Before writing, the patch is read back and the number of changed bytes is checked against the number of edits. The original entry is kept (with a checksum) in `.hc09_gamedata_cache/patch_backups` the first time, never overwritten, and **Restore original weights** writes it back; on a copy of both archives a restore gave a byte-identical file. The change applies to every save and every team that uses those types. Grades the game has already stored in a save (the draft class's `RPGR`) may not change until the game works them out again. Whether the game shows the new weights was not yet checked in the game when this was written.

## In-game readings

Taken from the Evaluate Roster screen of a test career (Bears), one preset at a time, each shown as *game / the editor's estimate*. The bodies (`PHGT` inches, `PWGT` pounds minus 160): Tillman 73 / 36, R. Manning 68 / 25, Vasher 70 / 17, Graham 72 / 35, McBride 69 / 25, Archuleta 72 / 55, Harris 75 / 132, Dvoracek 75 / 145, Adams 72 / 139, Garay 76 / 150, M. Brown 70 / 47, D. Manning 71 / 42.

| Preset | Tillman | R. Manning | Vasher | Graham | McBride | Archuleta |
|---|---|---|---|---|---|---|
| CB Balanced (60) |  | 82 / 82 | 89 / 89 | 69 / 69 | 76 / 76 |  |
| CB Man Coverage/Ballhawk (61) |  | 78 / 78 | 88 / 87 | 64 / 65 | 72 / 72 |  |
| CB Strong/Press/Run Support (62) |  | 79 / 79 | 85 / 84 | 70 / 71 | 73 / 74 |  |
| CB Prototype (63) | 87 / 87 | 78 / 78 | 85 / 84 | 74 / 74 |  |  |
| CB Cover 2 (64) | 84 / 82 | 77 / 77 | 88 / 87 | 55 / 56 |  |  |
| SS Balanced (70) |  |  |  |  |  | 67 / 66 |
| SS Coverage (71) |  |  |  |  |  | 62 / 62 |
| SS Prototype (72) |  |  |  |  |  | 78 / 77 |
| SS Run Support/Big Hitter (73) |  |  |  |  |  | 73 / 72 |
| SS Smart/Productive (74) |  |  |  |  |  | 62 / 62 |

| Preset | Harris | Dvoracek | Adams | Garay |
|---|---|---|---|---|
| DT Balanced (45) | 89 / 89 | 69 / 69 | 66 / 69 | 66 / 67 |
| DT Prototype (46) | 84 / 85 | 73 / 74 | 72 / 72 | 76 / 77 |
| DT One Gap Penetrator (47) | 90 / 89 | 68 / 68 | 65 / 65 | 54 / 54 |
| DT Run Stopper (48) | 86 / 85 | 70 / 70 | 71 / 71 | 71 / 72 |
| DT Versatile/3-4 (49) | 87 / 87 | 69 / 70 | 70 / 69 | 70 / 70 |

| Preset | M. Brown | D. Manning |
|---|---|---|
| FS Balanced (65) | 82 / 81 | 77 / 76 |
| FS Man Coverage (66) | 82 / 81 | 75 / 75 |
| FS Centerfielder (67) | 82 / 81 | 75 / 74 |
| FS Prototype (68) | 82 / 80 | 82 / 80 |
| FS Run Support/Blitzer (69) | 80 / 79 | 74 / 73 |

Over these 55 readings the estimate is exact for 24, within 1 for 51, within 2 for 54; the worst is 3, and the root-mean-square error is 0.9 (CB 0.8, DT 0.9, FS 1.2, SS 0.8). The only fitted part is the Size approximation, which was fitted to the draft class's stored Size grades, not to these readings, so the figures are close to out-of-sample. The remaining error is mostly Size (the real one is stepped) and the few durability grades that are off by 1 or 2.

## Not known

- **The exact Size grade.** It is a stepped lookup of height and weight, with a plateau every two inches of height for cornerbacks and a weight below which the score doesn't fall, and it can fall again above an ideal body. The tables are not in the game's data files (no shipped table has height or weight tiers), so they are probably in the executable. Fitting a table per position needs more stored grades than the 350 prospects give (per-position fits reached an out-of-sample error of about 4.7 against 6.5 for the global one). The game's stored Size grade of any prospect is in `RPGR` (`PSZG`).
- **What Production is** for veterans (counted as 0 here, which fits) and for prospects (their stored grades run 1 to 99 with a median of 20 and correlate with Learning and Awareness; a table `POSC` with a range per position group may be its scale).
- **The last bit of Durability**: about one prospect in nine differs from the body-part average by 1 or 2.
- Positions other than CB, FS, SS and DT have not been compared with the Evaluate Roster screen. Readings for MLB, WR and HB would be the next most useful.
