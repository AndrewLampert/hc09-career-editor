# HC09 Career Editor

A Tkinter GUI for editing NFL Head Coach 09 career saves (players, stats, contracts,
draft picks, salary cap, trainers, coaches, GMs) that reads and writes **directly**
to the game's binary save file (`USR-DATA` on PS3). No manual CSV export/import
through HC09Editor required.

## How it works

NFL Head Coach 09 (and various Madden/NCAA titles of the same era) store career
data in a `TDB`-format binary database. This project has two pieces:

- **`guiHC09.py`** — the Tkinter GUI where you actually browse/edit players, trades,
  contracts, staff, and the salary cap.
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
2. Edit players, stats, contracts, trades, picks, staff, or the salary cap.
3. Click **Save to File** — changes are written straight back into `USR-DATA`,
   after backing up the previous version to `USR-DATA.bak`.

## Format notes / known limitations

- The TDB format pre-allocates a fixed number of record "slots" per table
  (`maxRecords`), and each table currently uses some subset of them
  (`currentRecords`). Rows can be **edited** freely, but new rows can't be
  added or removed through this tool — that's a limitation of the underlying
  file format, not the GUI. (Some tables do have unused pre-allocated slots —
  see [bep713/hc09-editor#5](https://github.com/bep713/hc09-editor/issues/5) for
  background on why this is hard to do safely.)
- The salary cap field (`SCAD`) is a **signed** 32-bit int in-game, even though
  it looks like it should hold up to `4,294,967,295`. Setting it above
  `2,147,483,647` (0x7FFFFFFF) wraps it negative. The GUI clamps to that value.
- Field codes (`PFNA`, `PPOS`, `TGID`, stat codes, etc.) aren't documented
  anywhere official — the mappings in this repo (`STAT_META`,
  `PLAYER_MAX_HARDCODED`, `TEAM_NAMES`, etc.) were reverse-engineered by hand.

## Credits

- [bep713/hc09-editor](https://github.com/bep713/hc09-editor) and
  [bep713/madden-file-tools](https://github.com/bep713/madden-file-tools) for
  reverse-engineering and open-sourcing the TDB file format parser this project
  depends on.

## License

MIT — see [LICENSE](LICENSE).
