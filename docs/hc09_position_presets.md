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
- `PEOW` (seven group weights `OPDW OINW OLNW ODRW OATW OPTW OSZW`), `PEDW` (`CUHW CHLW CFTW`), `PESW` (`HTSW WTSW`, height and weight): these look like the scouting factors of the Evaluate Roster screen (athleticism, learning, durability, potential, size). Not used by the editor.
- `PORC` (21 rows, one per position, weights stored as IEEE floats) is the per-position side. Not used by the editor.

Each weight column names a player rating (`ACCW` acceleration, `MCVW` man coverage, `HPWW` hit power, ...); the editor's pairing is by name, and each was checked against which position groups use it (hit power is heavy for MLB, SS and OLB; route running for WR and TE; power move for DT and DE). `RNSW` is zero for every preset.

The weights read like the in-game names. For the five CB presets: Man Coverage/Ballhawk weighs man coverage 31 and zone coverage 0; Cover 2 the reverse; Strong/Press/Run Support weighs tackling, pursuit and press; Prototype has the most ratings at the maximum weight.

## What the editor does with it

**Player Type Fit** lists a position's presets (with the team's current preset beside each player, from `TPHS`) and ranks players by the **weighted average of their ratings** under the preset's `PEAW` and `PEIW` weights. This is a fit score, **not the game's overall**.

## Not known

- **The game's overall formula.** On the test career's Bears the fit is close to the stored overall for some players (Vasher 90.9 against 90, Tillman 88.8 against 88) and far for others (Graham 74.7 against 84, Archuleta 63 to 69 against 80), and over all teams the correlation was weak (about 0.1 to 0.6 by position). It may be that stored overalls were computed under a different preset than the current one, or that the formula also uses `PEOW`, `PEDW`, `PESW` and `PORC`. Exact in-game readings (one player's overall under each preset) are needed to settle it.
- Whether the in-game overall is the same for every team or depends on the team's own preset.
- Whether height and weight (`PESW`) should be part of a fit.
