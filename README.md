# HC09 Career Editor

A Tkinter GUI for editing NFL Head Coach 09 career saves (players, stats, contracts,
draft picks, salary cap, trainers, coaches, GMs, playbooks) that reads and writes
**directly** to the game's binary save file (`USR-DATA` on PS3). No manual CSV
export/import through HC09Editor required.

## What you can do

- **Players** - browse every team's roster and find a player on any team. Team-wide
  buttons: *Set Team Bonus Min* (folds each year's bonus into that year's salary and
  zeroes the bonus, so the cap hit per year is unchanged but cutting or trading the
  player no longer carries a bonus penalty), *Max Team Staff*, and *Apply Motivator
  Boost to Team*. A cap panel edits the team's salary cap.
- **Player Editor** - edit ratings (current and max), name, age and contract years, or
  any raw column; edit a contract; change a player's personality (one of the 17 types);
  apply a Motivator Boost; view the portrait and assign any of the game's existing
  portraits to a player.
- **Draft Picks** - reassign draft picks to another team.
- **Trainer / Coach / GM** - edit staff skills and development, or max out the selected
  person's stats. The default vertical layout shows one column per person: click a
  name at the top to select them, click a stat to sort by it. The Coach tab also edits
  a coach's position and personality, and a team's **Team Philosophy** - the data behind
  the game's Team Philosophy screen, by name rather than number, in five tabs: the game plan
  (schemes, no-huddle, playbook control, blitzing, coverage, who to bench or start), the
  position philosophies, the GM and staff settings (trading, drafting, scouting, contracts,
  hire control), roster minimums, and the health and fatigue substitution settings. The names
  are the game's own, read from its data. Each of the Trainer, Coach and GM tabs also has
  **Special skills...**: the staff member's special skills (Improved Tackling, Draft Intuition,
  Off Season Rehab, ...) as tick boxes, with the game's names and descriptions and only the skills
  the game offers that role (a head coach 44, a coordinator 28 or 23, a trainer 4, ...), and
  **Max Special Skills**, which gives the selected person all of them. The Coach tab also has
  **Max All Coaches**: one click maxes every coach shown (My Team: your whole staff) - skills,
  development, skill points and all their special skills.
- **Playbooks** - browse every playbook with real play, set and formation names; find
  which playbooks contain a play; change a team's offensive or defensive playbook; and
  **add plays** to your team's playbook by copying a play, a whole set or a whole
  formation from another one (200-play limit per playbook, special teams not counted;
  plays made in-game are never copied). A team's playbook is its head coach's (the one chosen
  at New Career Playbook Select); the coordinators' are listed beside it. Offense and Defense
  are shown one at a time. Playbooks 1-10 (your custom playbooks) and the plays you made in the
  game are named from your profile save, found next to your career and only read.
  **Set personnel...** lists the game's own sets with their personnel (11, 10, 00, 4-3-4, ...) and
  changes a set's slot positions, e.g. a fifth receiver into a tight end, one set or many with a
  bulk rule, with player names from your team's depth chart if a save is loaded. Unlike everything
  else here it **changes the game's own files** (`qkl_boot.ast` and `qkl_fe2ig.ast`, a few bytes per
  slot, in every copy that holds the set): the original of each entry is backed up first in
  `Documents\hc09-game-file-backup`, *Reset* and *Restore all* put it back, and the game must be
  closed. It applies to every save and game mode. See [docs/hc09_play_data.md](docs/hc09_play_data.md).
  **Play creator...** (a prototype; click a player on the field and pick what he does from a list in a coach's words: routes by name and depth, blocks, zones; drag him to move him) shows every play of the game (offense, defense, special teams)
  with where each player lines up and what he does, drawn from the game's own route art on the game's
  own field picture (read from your copy of the game, never shipped with the editor), with the pass
  reads numbered 1 to 5: blocks, routes with arrowheads, defensive zones, and the **option plays**
  (Triple Option, Speed Option, ...) the in-game Create-A-Play does not offer. Every offensive play is
  shown with its **kind** (dropback pass, play action, handoff, toss, option ...), and **Change play
  type...** turns a play into another kind and changes every player that does not fit it (the
  quarterback, the linemen, the backs, receivers' routes kept where the kind has routes), so that the
  play works as that kind. Any slot can be given any of the game's assignments, and
  **Make custom play...** (offense only for now; it is switched off, with a note, for defense and special
  teams) writes the result as a custom play into *copies* of your profile and career saves. It has
  been tried in RPCS3 (nine test plays ran, a moved receiver stood where the editor put him; see docs/hc09_game_test_results.md), but it still writes your saves, so keep backups. **Change in game files...** changes the game's own play itself, in place, in `qkl_boot.ast` and `qkl_fe2ig.ast` (backed up, **Put the game files back** restores them), so that the game treats it as a normal play (a custom play is a "created play": no flip, hot routes or adjustments, little use by the CPU); it cannot add plays, and a formation is shared by all its plays. Not tried in the game yet. **Plays I made** (second entry of the Playbook list) opens the custom plays of your profile so that you can change them (**Save changes...**: into the play itself, or as a new play next to it). **Pass reads...** sets the order the quarterback looks to his receivers, and **Move players...** puts the offensive players somewhere else on the field (both are written into the new play's own rows in your profile). See [docs/hc09_play_creator.md](docs/hc09_play_creator.md).
  **Add to my game** (the button of the save window) does it in one go: it makes the play, puts it into
  your profile and career after saving them, and picks the custom playbook your team plays (else the first);
  **Put my saves back** undoes it. What the game tests of this found is in [docs/hc09_game_test_results.md](docs/hc09_game_test_results.md).
- **Game reference...** (toolbar) - four read-only panels from the game's own tables, read from your game
  files once: what the injury table gives for a position, an Injury rating, a hurt body part and a hard hit
  (a level from 0 to 4, not a percentage); the draft pick value chart with a small calculator that adds up
  the picks you type; the chances a player accepts, walks away or sets an ultimatum from head coach
  approval, his overall, the counter offers so far and the gap to his package; and which ratings an
  injured leg, arm, head or torso lowers for each position. Nothing is changed in a save, and none of the
  tables has been checked against a match yet; see
  [docs/hc09_gamedata_findings.md](docs/hc09_gamedata_findings.md).
- **Toolbar** - *Trade Players (Safe Swap)*, *Sign Free Agent...*, *Player Type Fit...*
  (rebuilds each player's overall under one of the game's team position presets,
  such as Cover 2 or Man Coverage CB, with the game's own formulas, and ranks them; select a
  player to see his seven grades. It is an estimate: within 1 point of the Evaluate Roster screen
  for 51 of the 55 readings checked and never more than 3 off (cornerbacks, safeties, defensive
  tackles); Size is approximated; other positions are unchecked on the screen. The **?** next
  to the preset list breaks down what the selected preset weights, beside Balanced, and
  *Edit weights...* lets you change any of those weights for the editor's own estimate (for
  example copying Play Recognition, Awareness and Learning from Balanced into the One Gap DT
  and Speed Rusher DE types, which the game barely weighs those ratings in), and save the result
  as a preset of your own under a name you choose. The game, your saves and your game files are
  not changed. *Include players of positions that can switch* lists only positions that can really
  play the preset's position (CB / FS / SS, OLB / MLB / DE / DT, OT / OG / C, TE / FB / HB, QB / WR)),
  the recent-saves list,
  and *Options* (modern UI, dark mode).

**What has been checked in the game:** switching a team's playbook, adding a single play
or a whole formation to a playbook, and Team Philosophy (the playcall settings and the QB,
CB, FS, SS, DT, kicker and punter philosophies were written with the editor and read off the
game's screen, and changed in game and read back). **Not yet:** whether the AI calls added
plays in a game, flipping and special teams after adds, the other position philosophies, and
the GM and staff, roster minimum, health and fatigue settings: their names and values are the
game's own (read from its data, see
[docs/hc09_field_reference.md](docs/hc09_field_reference.md)), but which field is which was
matched from that data and has not been confirmed on the game's screen. Try changes on a copy
of your save.

## How it works

NFL Head Coach 09 (and various Madden/NCAA titles of the same era) store career
data in a `TDB`-format binary database. This project has two pieces:

- **`guiHC09.py`** — the Tkinter GUI where you actually browse/edit players, trades,
  contracts, staff, playbooks, and the salary cap (with `hc09_plays.py` beside it, which
  reads the game's plays for the play creator, and `hc09_reference.py` for the Game reference window).
- **`hc09-bridge/`** — a small headless Node.js CLI that reads/writes that binary
  format via [`madden-file-tools`](https://www.npmjs.com/package/madden-file-tools)
  (the same library used by [bep713/hc09-editor](https://github.com/bep713/hc09-editor)).
  The GUI shells out to it to export tables into memory on Load, and to write
  edited tables back into the save on Save.

Every Save first copies the existing save file to `<file>.bak` before writing, so
you always have the previous version to fall back to.

## Requirements

- Python 3.9+ (stdlib only — Tkinter, csv, subprocess, etc. No pip installs needed.)
- [Node.js](https://nodejs.org/) 18+, available on your `PATH` (used only to run the
  bridge script; the GUI itself doesn't need it to start).
- *Optional, for names and portraits:* your own copy of the game's files (the
  `PS3_GAME/USRDIR` folder). Player Type Fit and the Playbooks tab read the presets' weights and
  play, formation and playbook names from `qkl_boot.ast`; the editor asks you to locate
  it the first time and keeps a local cache. The portrait viewer reads `qkl_fe2ig.ast`
  (use **Locate Game Files...** in the Player Editor tab). The Playbooks tab also reads your
  profile save (the `...-PROFILE-...` folder beside your career) to name custom playbooks and
  plays; use **Profile save...** if it isn't found. Nothing is ever written to it. No game
  data is included in this repository.

## Setup

**Windows, the easy way:** double-click **`Start HC09 Editor.bat`**. It checks that Python 3.9+ (with Tk) and
Node.js 18+ are installed (and tells you where to get them if not), checks that the bridge starts, and opens the
editor without a console window. `"Start HC09 Editor.bat" --check` only reports what it found.
On Linux / macOS use `./start-hc09-editor.sh` (same checks, `--check` too).

**Nothing has to be installed besides Python and Node.js:** the libraries the bridge uses are shipped in
`hc09-bridge/vendor` (see `hc09-bridge/vendor/README.md`), so there is no `npm install`, no internet needed and no
Visual Studio or build tools (an older version needed them through the `lz4` package, which compiles code; it is now
a small plain-JavaScript stand-in). If you saw a Visual Studio or `npm` error, update the editor (download it
again) and start it again; an old `hc09-bridge/node_modules` folder is simply not used any more.

By hand:

```bash
python guiHC09.py
```

## Usage

1. Click **Saves...** to see the career saves the editor found (in RPCS3's `savedata` folders: the ones your
   recent saves live in, any folder you add with *Look in another folder...*, the usual places, or *Search this
   computer*), newest first, and open one with a double-click. Or click **Load Save File** and pick your career's
   `USR-DATA` file (in RPCS3, that's under `dev_hdd0/home/00000001/savedata/<CAREER-NAME>/USR-DATA`; the dialog starts
   there). **Options... > Reopen my last save when the editor starts** loads the most recent one on its own. The
   game's files (`qkl_boot.ast`, `qkl_fe2ig.ast`) are found the same way, through RPCS3's own `config/games.yml`, so
   the editor only asks you to locate them if that fails.
   **Xenia (Xbox 360) saves** open the same way: click **Load Save File** and pick the save's `.mc02` file. The game
   keeps those inside its own `MC02` wrapper (a header and a metadata block before the database); the editor reads and writes the database in place and
   leaves the wrapper alone, as the community's MC02 <-> DB converter does. **Saves...** also looks for Xenia's `content` folder (in the folders of your
   recent saves, any folder you add with *Look in another folder...*, the usual places, or *Search this computer*), lists the careers it finds there marked
   *(Xenia)*, and finds the profile that goes with a career by what is in it (a career has 208 tables, a profile 43), so Add to my game can fill both in. This was written
   from how Xenia is known to lay out its files (`content/<profile id>/45410841/<type>/<package>/<file>`, each save one extensionless MC02 file in a folder of the same name,
   such as `CAREER-ME/CAREER-ME`) and checked only against copies of our own saves: Xenia Canary and Xenia Edge are the ones meant (a portable copy, with `content` next to the
   program, can be anywhere: the editor also asks Windows where a running Xenia is). If yours are elsewhere, pick the files by hand (Details... in the save windows). Back up the files first. Xbox 360 files taken straight out of a console package (STFS) have to be
   extracted first (for example with Modio), and PS3 files decrypted, as the community guides say.
   **HC09 for PC** (the Xbox 360 game recompiled to run natively, such as ibukun5588/nfl-head-coach-09-pc and tools81/nfl-head-coach-09-static-recomp) keeps the same MC02 saves in a
   flat folder, `Documents\NFL Head Coach 09\Saves\1.0` and `\1.2` (one folder per save, named `CAREER-<name>`, holding a file of the same name), or under `build\userdata\content`
   in the other port's install folder. **Saves...** looks there too, marks the careers *(HC09 PC 1.2)*, leaves the `Backups` folder out and pairs a career with the profile
   of the same game version; **Look in another folder...** takes the `Saves` folder (or the folder that holds it). This was written from the two projects' README pages and
   not checked against a real install, and whether the PC versions accept an edited save is untested: close the game first and back up the folder.
   The first time you load a save it asks which team is yours and remembers the answer;
   switch teams any time from the list on the left.
2. Edit players, stats, contracts, trades, picks, staff, playbooks, or the salary cap.
3. Click **Save to File** — changes are written straight back into `USR-DATA`,
   after backing up the previous version to `USR-DATA.bak`.

Try changes on a copy of your save first. **Reload from File** discards unsaved edits.

## Updates

A few seconds after it starts, the editor asks GitHub (read-only, one request, at most once an hour,
silent if you are offline) whether your copy is behind the `main` branch, and if so shows a banner
above the tabs: **What's new...** lists what changed, **Skip this version** hides it until there is
something newer, **Dismiss** hides it for now. If your copy is a git clone on `main` with no changes
of your own, the *What's new* window also offers **Update now** (a `git pull --ff-only`, then a
restart); otherwise it tells you how to update (`git pull`, or download the zip again; run
nothing to install: the bridge's libraries ship in the repository). A zip download is recognised by comparing
its files with the ones on GitHub, a clone by the commit it is on, so nobody has to bump a version
number. **Options... > Check for a newer version when the editor starts** turns the check off, and
**Check for updates now** asks immediately. The check is in `hc09_update.py`.

## Format notes / known limitations

- The TDB format pre-allocates a fixed number of record "slots" per table
  (`maxRecords`), and each table currently uses some subset of them
  (`currentRecords`). Rows can be **edited** freely. Rows can't be removed, and new
  rows are only added in one place: **Add plays** in the Playbooks tab fills the
  playbook tables' unused pre-allocated slots (and refuses if there aren't enough).
  After a save that added rows the tool re-checks the file's structure and restores
  the backup automatically if the check fails. Adding rows to any other table, such as
  players, isn't supported — see
  [bep713/hc09-editor#5](https://github.com/bep713/hc09-editor/issues/5) for
  background on why this is hard to do safely.
- The salary cap field (`SCAD`) is a **signed** 32-bit int in-game, even though
  it looks like it should hold up to `4,294,967,295`. Setting it above
  `2,147,483,647` (0x7FFFFFFF) wraps it negative. The GUI clamps to that value.
- Field codes (`PFNA`, `PPOS`, `TGID`, stat codes, etc.) aren't documented
  anywhere official — the mappings in this repo (`STAT_META`,
  `PLAYER_MAX_HARDCODED`, `TEAM_NAMES`, etc.) were reverse-engineered by hand.
  [docs/hc09_field_reference.md](docs/hc09_field_reference.md) collects the names and
  value lists from a community config; its labels are community-written and some are
  wrong, so treat them as leads to test.

## Credits

- [bep713/hc09-editor](https://github.com/bep713/hc09-editor) and
  [bep713/madden-file-tools](https://github.com/bep713/madden-file-tools) for
  reverse-engineering and open-sourcing the TDB file format parser this project
  depends on.
- JHamilton9's community *HC09 Detailed Config.xml* (for the EA Generic DB Editor) for
  field names and value lists, summarised in
  [docs/hc09_field_reference.md](docs/hc09_field_reference.md).

## License

MIT — see [LICENSE](LICENSE).
