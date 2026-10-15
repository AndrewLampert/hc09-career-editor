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
  the game's Team Philosophy screen (offensive and defensive scheme, no-huddle, playbook
  control, position philosophies), by name rather than number.
- **Playbooks** - browse every playbook with real play, set and formation names; find
  which playbooks contain a play; change a team's offensive or defensive playbook; and
  **add plays** to your team's playbook by copying a play, a whole set or a whole
  formation from another one (200-play limit per playbook, special teams not counted;
  plays made in-game are never copied). A team has a head coach's playbook and a coordinator's
  for each side and plays one of them; the tab shows which is in use and has a *Played by*
  switch (it sets the Playbook Control team philosophy for you). Offense and Defense are
  shown one at a time. Playbooks 1-10 (your custom playbooks) and the plays you made in the
  game are named from your profile save, found next to your career and only read.
- **Toolbar** - *Trade Players (Safe Swap)*, *Sign Free Agent...*, *Player Type Fit...*
  (read-only: estimates each player's overall under one of the game's team position presets,
  such as Cover 2 or Man Coverage CB, from the game's own weights and ranks them. It is an
  estimate: typically within 2 to 3 points of the Evaluate Roster screen where it was checked,
  for cornerbacks and a strong safety; other positions are unchecked), the recent-saves list,
  and *Options* (modern UI, dark mode).

**What has been checked in the game:** switching a team's playbook, adding a single play
or a whole formation to a playbook, and Team Philosophy (the playcall settings and the QB,
CB, FS, SS, kicker and punter philosophies were written with the editor and read off the
game's screen, and changed in game and read back). **Not yet:** whether the AI calls added
plays in a game, flipping and special teams after adds, and the running back, receiver,
tight end, line and linebacker philosophies. The names for what isn't checked come from a
community field list ([docs/hc09_field_reference.md](docs/hc09_field_reference.md)) whose
labels are sometimes wrong, so try changes on a copy of your save.

## How it works

NFL Head Coach 09 (and various Madden/NCAA titles of the same era) store career
data in a `TDB`-format binary database. This project has two pieces:

- **`guiHC09.py`** — the Tkinter GUI where you actually browse/edit players, trades,
  contracts, staff, playbooks, and the salary cap.
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

```bash
cd hc09-bridge
npm install
cd ..
python guiHC09.py
```

## Usage

1. Click **Load Save File** and pick your career's `USR-DATA` file (in RPCS3, that's
   under `dev_hdd0/home/00000001/savedata/<CAREER-NAME>/USR-DATA`).
   The first time you load a save it asks which team is yours and remembers the answer;
   switch teams any time from the list on the left.
2. Edit players, stats, contracts, trades, picks, staff, playbooks, or the salary cap.
3. Click **Save to File** — changes are written straight back into `USR-DATA`,
   after backing up the previous version to `USR-DATA.bak`.

Try changes on a copy of your save first. **Reload from File** discards unsaved edits.

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
