# Position presets (team position philosophies) and their weights

What the game's "player type" presets really are, what the game's files say about them, and what is still unknown. Checked on one real career and the game's `qkl_boot.ast`.

## What the presets are

The presets on the game's Team Philosophy screen (five each for CB, FS and SS, three for K and P, and so on) are the **team position philosophies**: the `xxPP` values 0 to 80 of the `TPHS` table (see `docs/hc09_field_reference.md`):

| Position | Values | Presets |
|---|---|---|
| QB | 0 to 4 | Mobile/Speed, Strong Arm/Tools, Pure Passer, Field General, Balanced |
| HB | 5 to 10 | Speed, Moves, Power, Receiving, Workhorse, Balanced |
| FB | 11 to 14 | Ball Carrier, Blocking, Receiving, Balanced |
| WR | 15 to 19 | Strong, Tall, Speed, Route-Runner, Balanced |
| TE | 20 to 24 | Playmaker, H-Back, Balanced, Soft Hands, Blocking |
| OT / OG / C | 25 to 29 / 30 to 34 / 35 to 39 | Size, Run Block, Pass Block, Zone Block, Balanced |
| DE / DT | 40 to 44 / 45 to 49 | Balanced, Prototype, Speed or One-Gap, Run Stopper, 3-4 |
| OLB / MLB | 50 to 54 / 55 to 59 | OLB: Balanced, Cover 2, Run Stopper, 3-4 Pass Rush, Prototype; MLB: Balanced, Coverage, Power, Tackler, Prototype |
| CB | 60 to 64 | Balanced, Man Coverage/Ballhawk, Strong/Press/Run Support, Prototype, Cover 2 |
| FS | 65 to 69 | Balanced, Man Coverage, Centerfielder, Prototype, Run Support/Blitzer |
| SS | 70 to 74 | Balanced, Coverage, Prototype, Run Support/Big Hitter, Smart/Productive |
| K / P | 75 to 77 / 78 to 80 | Big Foot/Distance, Accuracy, Balanced / Power, Pinpoint Accuracy, Balanced |

Names for CB, FS and SS come from the game (a user's list and screenshots); the K, P and QB names were seen on the game's screens; the rest are the community config's and unchecked.

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

**Player Type Fit** lists a position's presets (with the team's current preset beside each player, from `TPHS`) and shows an **Est. OVR** for each player: an estimate of the overall the game's Evaluate Roster screen shows under that preset. The tab says so, with the margin: against the readings below it is typically within 2 to 3 points (worst reading 5 off, and an unusual build may be further out), for cornerbacks and a strong safety only; other positions use the same method unchecked. (*Saved OVR* is the overall stored in the save, which can be stale or from another preset.)

The estimate is `Sum(factor weight * factor score) / Sum(factor weight)` over the `PEOW` factors:

| Factor | Weight | Score used | Known or stand-in |
|---|---|---|---|
| OIN | `OINW` | the player's skill ratings weighted by `PEIW` | from the files |
| OAT | `OATW` | the athletic ratings weighted by `PEAW` | from the files |
| OLN | `OLNW` | the Learning rating | stand-in |
| ODR | `ODRW` | the Injury rating | stand-in |
| OPT + OPD | `OPTW + OPDW` | the `PEIW`-weighted skills without Learning | stand-in |
| OSZ | `OSZW` | `55.1 + 0.592 * p`, p = the `HTSW` / `WTSW` weighted height and weight percentile (0 to 99) among that position's players in the save | stand-in, two numbers fitted |

A plain weighted average of the `PEAW` and `PEIW` ratings was tried first (what an earlier version of this tab showed). It matched the game under Balanced (within 2) but was up to 19 points off under other presets (Graham under Cover 2: 74 against the game's 55), because it ignored the factor weights: Man Coverage/Ballhawk gives athleticism 15 of 71 where Balanced gives 31 of 102, and Prototype gives size 15 of 73.

## In-game readings

Taken from the Evaluate Roster screen of a test career (Bears), one preset at a time, with the estimate the editor gives for the same player. The players: Tillman 6'1" 196 lb (`PHGT` 73, `PWGT` 36), R. Manning 5'8" (68, 25), Vasher 5'10" (70, 17), Graham 6'0" (72, 35), McBride 5'9" (69, 25), Archuleta 6'0" 215 lb (72, 55). The weight is stored as pounds minus 160.

| Preset | Tillman | Manning | Vasher | Graham | McBride | Archuleta |
|---|---|---|---|---|---|---|
| CB Balanced (60) | | 82 / 82 | 89 / 91 | 69 / 69 | 76 / 76 | |
| CB Man Coverage/Ballhawk (61) | | 78 / 79 | 88 / 90 | 64 / 65 | 72 / 73 | |
| CB Strong/Press/Run Support (62) | | 79 / 80 | 85 / 88 | 70 / 71 | 73 / 75 | |
| CB Prototype (63) | 87 / 92 | 78 / 77 | 85 / 86 | 74 / 72 | | |
| CB Cover 2 (64) | 84 / 88 | 77 / 80 | 88 / 91 | 55 / 59 | | |
| SS Balanced (70) | | | | | | 67 / 66 |
| SS Coverage (71) | | | | | | 62 / 62 |
| SS Prototype (72) | | | | | | 78 / 74 |
| SS Run Support/Big Hitter (73) | | | | | | 73 / 71 |
| SS Smart/Productive (74) | | | | | | 62 / 62 |

(game / editor estimate, rounded). Over these 25 readings the estimate is within 2 for 16, within 3 for 20, worst 4.8 (Tillman under Prototype); the root-mean-square error is 2.3. The two size numbers and the stand-ins were fitted to these same readings, so the figures are in-sample. Leaving one player out at a time, the root-mean-square error was 3.0 and the worst 8.6 (Tillman under Prototype, a body the rest of the fit hadn't seen), then 6.0 (Archuleta under Prototype). More players and positions would tighten it.

## Not known

- **The game's exact overall formula.** The structure above fits, but only the `OIN` and `OAT` scores are known from the files. How learning, durability, potential, production and size are scored is guessed from the readings. In particular the size score has only been seen for six bodies, all cornerbacks and one safety.
- Free safeties and every non-defensive-back position: no readings yet, so the estimate there is unchecked.
- Whether potential and production (`OPTW`, `OPDW`) use the same ratings as skills; the displayed potential (POT) also changes with the preset, so it is computed the same way from projected ratings.
