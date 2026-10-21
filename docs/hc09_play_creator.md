# Plays as data: the play designer prototype

What a play is in the game's files, what the editor's **Play designer** shows and builds from it, and what is known (and not known) about writing a custom play outside the game. Companion documents: `hc09_play_data.md` (sets and personnel), `hc09_custom_plays.md` (custom plays and playbooks in a save).

**Status: prototype.** Reading and drawing the game's plays is checked against the game's own diagrams. Making a custom play writes rows that follow what the in-game Create-A-Play wrote, passes the bridge's structure check and reads back correctly, but **it has not been tried in the game yet** (a test plan is at the end).

## A play, table by table

All of this is in the master play database (`qkl_boot.ast` entry 40; `qkl_fe2ig.ast` 1674 to 1679 hold subsets, see `hc09_play_data.md`).

| Table | One row is | Notes |
|---|---|---|
| `PBPL` | a play: `PLYL` (id), `SETL` (the set it is run from), `PLYT` (play type), `name`, `motn` (pre-snap motion), `PLF_`, `risk`, `vpos`, `SITT` | 3,099 plays: 2,513 offense, 549 defense, 37 special teams |
| `SETL` / `SETP` / `SETG` / `SGFF` | the set (alignment): 11 `SETP` slots with `poso`, `EPos`, `DPos`, `artx` / `arty` (where each lines up in the diagram's units, x about 0 to 180, y about 0 to 128); `SETG` the alignments of pre-snap motion variants (floats, in yards, stored as the raw 32 bits), `SGFF` the alignment groups | 240 sets: 185 offense, 41 defense, 14 special teams |
| `PLYS` | one slot of a play: `PSAL` (what the player does), `ARTL` (the route drawing), `PLRR` (a role code), `poso` | 34,089 rows; 11 per play |
| `PSLO` / `PSLD` | the **step lists**: rows (`PSAL`, `step`, `code`, `val1`, `val2`, `val3`), each list ending with code 255; `PSLO` for offense, `PSLD` for defense | 1,138 offense lists, 403 defense lists |
| `ARTO` / `ARTD` | the **route art**: up to 12 numbered records per `ARTL` (`sp`, `ls`, `at`, `ct`, `lt`, `au`, `av`, `ax`, `ay`) | 941 offense, 487 defense |
| `PLPD` | pass plays: the read order (5 x percent + receiver slot) | |
| `PLRD` | run plays: the hole | |
| `PLCM` | play combinations (option decisions) | |
| `PBAI` | which playbook (`BOKL`) holds which play | |

### Id spaces: `PSLO` and `PSLD` overlap

The two step-list tables number their lists separately but share ids: **138 ids (2182 to 2343, not contiguous) are in both tables with identical lists**, and so overlap `ARTO` / `ARTD` in 117 ids. Anything keyed by `PSAL` or `ARTL` alone silently takes the defense table's rows for an offense play. The editor keys everything by side (`hc09_plays.PlayLibrary.steps[side]`, `art_rows[side]`); special-teams sets use whichever table most of their plays' ids are only in (special-teams plays use both tables, some slots from `PSLO` and others from `PSLD`).

**The 138 shared lists are exactly the ones no stock play uses**, on both sides (offense 138 of 1,138 unused, defense 138 of 403). They are short and generic (`15`, `14`, `28`, `29`, `41(24,104,255) 2`, `8(104,32,254) 2` ...). The profile used for testing (the user's own) has 14 custom plays (154 `PLYS` rows) using **60 different `PSAL` ids: 22 of the shared 138 and 38 ordinary ones** (all blocking and route lists that stock plays also use), none of them with option codes. So the in-game Create-A-Play builds from the shared lists *and* from ordinary ones; which exact set it offers per position is not known. Their `ARTL` is not derivable from the `PSAL`: the profile pairs list 2182 with art 233 and list 2183 with art 225 and so on, one art per route shape.

### Step codes

Read from the data (which plays use which code), not from the game's code, so **likely**:

| Code | Reading |
|---|---|
| 8 | run a route leg |
| 9 | cut (turn) |
| 10 | end of route |
| 12, 18, 25, 26 and others | not identified |
| 14 | run block; 15 block |
| 22 | curl / flat zone (defense); 23 deep zone; 24 hook zone |
| 41 | pass rush |
| **36, 37, 42, 43** | **option steps**: 42 and 43 are in 100% of their uses in option plays, 36 and 37 in 96%; 42 is the read, 43 the pitch path |
| 255 | end of list |

261 offensive plays contain these codes (46 distinct names: Triple Option, Triple Option Rev / Cntr / Pass, Tri(-) Option Pass, Option Pass, Speed Option, Jet Option, QB Slot Option, Power Option, Shovel Option, Quick Option, TE / HB / FB / WR options ...), in 61 step lists. **None of them is among the 138 shared lists and none is in the profile's custom plays**: the in-game editor is reported not to offer option plays, and the game's own plays prove the engine supports them, so they can be assigned in a custom play from the designer.

### The art

Art columns are signed integers of different widths (`ART_BITS` in `hc09_plays.py`, from the table definition); the bridge exports them as raw unsigned numbers, so they are sign-extended when read (an `ay` of 251 in 8 bits is -5). `(ax, ay)` are absolute offsets from the player's art position (`artx`, `arty`); the route is the position followed by each used record (`sp` not 0). `at` 1 is an arrowhead. On defense a record with `ct` 3 is a **zone** (an oval with a line to it): code 23 deep (blue), 22 curl / flat (pink), 24 hook (yellow). Checked against the in-game diagrams: *Pass Deep* gives four deep zones at the top, two curl / flat and a hook; *Slants* WR1 goes up the field and then in (offsets `(0,-24) (0,-26) (-18,-40)`).

## The designer (Playbooks tab, Play designer...)

- Lists every play (Offense, Defense or Special teams), filtered by playbook, name or formation, option plays only; draws the alignment and the routes or zones, lists each slot's step list in the game's own numbers with a hint for the codes above.
- **Change this slot...** opens the assignment library: every step list of that side, by kind of player, option reads only, only the lists no stock play uses, steps containing a text. A step list is drawn with the art the stock plays use with it most (or, for the lists no stock play uses, the pairing found in your profile's custom plays); a list with no known art cannot be used for a slot.
- **Make custom play...** (offense, for now) writes the play, with the changed slots, into **copies** of a profile save and a career save in a folder you choose; your own saves are never touched. Rows (`hc09_plays.build_custom_play`): `PBPL` and `SETL` in formation 8190 ("Created Plays", `SITT` 2 / 0), 11 `SETP` (the stock set's slots with its diagram coordinates in both `fmtx` / `artx` and `fmty` / `arty`), the stock set's `SGFF` groups with their `SETG` rows, 11 `PLYS`, and the `PLPD` / `PLRD` / `PLCM` row of the stock play; ids come after the profile's own (`SETL` 66 and `PLYL` 28 are next in the test profile). Every `PSAL` / `ARTL` is one of the game's own. The play is put into the chosen custom playbook 1 to 10 by `PGPL`, `PGSS`, `PGSL` rows (and a `PGFM` row if that playbook has no "Created Plays" formation yet), written to **both** saves: the profile holds them too (its 14 custom plays are linked by 29 `PGPL` rows, next to the playbooks' stock plays), so both are copied. The files are written with the bridge's append import (zero-filled slots), `verify-db` must pass on both.
- Nothing in this tool changes the game's archives.

Tested on copies (`plays_test.py`, outside the repository): all 3,099 plays decode and draw; stock option plays are recognised; a custom play made from *Slants* with an option read in slot 2 writes 1 `PBPL`, 1 `SETL`, 11 `SETP`, 9 `SGFF`, 24 `SETG`, 11 `PLYS`, 1 `PLPD` and reads back with the same positions and the one changed assignment; the old rows are unchanged; a second play takes the next ids; the output folder is refused if it would overwrite the saves; the real profile, career and game files are byte-identical afterwards.

## Not known, and risks (what to watch in the first game test)

- **Whether the game accepts it.** The rows copy the layout of the plays the game wrote itself, but a field the editor does not understand (`PLRR` role codes, `risk`, `vpos`, `SITT`, `arti` / `opnm` / `tabo` / `flas` of `SETP`) could matter. Copies of the stock set's values are used wherever possible.
- **Option reads in a custom play.** `PLCM` (the play combination) is copied from the stock play, but whether the option decision needs more than the step lists and `PLCM` (the `PLPD` read order, the `PLRR` of the quarterback and the pitch man) is not known. A custom play with an option step list in a non-option play may do nothing or leave the quarterback standing.
- **Roles.** `PLRR` goes with the step list in the stock plays (the designer copies the most common one); mixing an assignment with a role it never has may confuse the AI.
- **Motion groups** (`SETG`): copied with the set, but a slot's assignment is not changed with the motion.
- **Ids.** Custom ids (`SETL` up to 511, `PLYL` up to 16,383) can equal stock ids; the game files its custom plays in the profile, and the career links by `SETL` / `PLYL`, as the game does for its own custom plays.
- **Defensive custom plays**: not made here (the profile's `PLAB` has `BOFF` for the playbook type; the rows would be the same on the defense tables).
- Names of the in-game route menu entries, what the 138 lists are in the in-game menu, and the exact meaning of each step code (the table above is read from the data).

## A test plan for the game

1. Close RPCS3. Back up the **whole** profile folder (`BLUS30128-PROFILE-HEADCOACH`; there is one for every career, so the change reaches all of them and it holds all your real custom plays) and the career's folder. If you can, try it with a career you do not mind losing.
2. Play designer, pick *Slants*, change one receiver to an ordinary list (for example a deep route), **Make custom play...** with the profile and career picked, a new output folder, playbook 1.
3. Copy the two `USR-DATA` files over the profile's and the career's. Start the game, load the career, open the playbook under *Created Plays*: the play should be listed with its name and the diagram of the set.
4. Run it. Look at: the alignment (the same as the stock set), the changed receiver's route, the others unchanged.
5. Only then try an option read in a pass play and a whole option play copy (*Speed Option* without changes, then with a changed back).
6. If anything is off, the useful reports are: does the play show in the playbook, does the diagram show, does the game crash on selecting or on snapping, and what the player did.
