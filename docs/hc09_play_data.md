# The game's play data (sets, formations, personnel)

What the play databases in the game's archives hold, how the editor's **Set personnel** tool changes a set's personnel, and what was checked in the game. Companion documents: `hc09_gamedata_findings.md` (the other shipped tables) and `hc09_position_presets.md`.

## Where the sets are

Several DB entries, stored as plain bytes (no compression) in `qkl_boot.ast` and `qkl_fe2ig.ast` (PS3 USA release), hold the same sets. Opening an entry with the DB library and saving it unchanged gives back the same bytes, so a same-size edit can be written over the same byte range.

| Archive, entry | What it is |
|---|---|
| `qkl_boot.ast` 40 (1,174,304 bytes) | the **master**: 240 sets (185 offensive, 41 defensive, 14 special teams), `SETP` 2,640 rows, 3,099 playbook plays (`PBPL`), 666 playbook formations (`PBFM`), `PBAI` 27,035 (which playbook uses which set), assignments `PLYS` 34,089, `SPKF` / `SPKG` |
| `qkl_boot.ast` 42 (205,764) | a compact copy of `SETP` (`SETL`, `x___`, `y___`, `poso`, `DPos`, `EPos`) and `PBPL`, which looks like the data the game uses while playing |
| `qkl_fe2ig.ast` 1674, 1675, 1676, 1677, 1678, 1679 | smaller copies (7 to 177 and 147 sets), with the same set ids and names; 1676 (177 sets, 1,947 slot rows) is the entry the community calls `File01676` (Create-A-Play's data); they hold `FORM` (formation names) |
| `qkl_boot.ast` 34 and `qkl_fe2ig.ast` 1815 (4,113,596 bytes, identical) | the blank 208-table career template: the tables exist but have no rows |
| `qkl_boot.ast` 46 and `qkl_fe2ig.ast` 1816 | the shipped 716-table database (presets, enums, names), see `hc09_gamedata_findings.md` |

The fe2ig copies differ from the master in 14 slot rows (the halfback / fullback order of sets 431 to 437), so they are the newer data and the tool never writes one copy's values into another unchecked.

## One slot of a set

A set has 11 rows in `SETP`, one per slot:

| Column | Meaning |
|---|---|
| `SETL` | the set |
| `poso` | slot 0 to 10 |
| `EPos` | the slot's position, the player table's `PPOS` codes: 0 QB, 1 HB, 2 FB, 3 WR, 4 TE, 5 to 9 the line (LT LG C RG RT), defense 10 LE, 11 RE, 12 DT, 13 LOLB, 14 MLB, 15 ROLB, 16 CB, 17 FS, 18 SS |
| `DPos` | the depth: 1 is first string, so WR3 is `EPos` 3 with `DPos` 3, and the player is the depth chart's entry at index `DPos` - 1 for that position |
| `SGT_` | the kind of spot (1 QB, 15 to 19 the skill spots, 4 the line); the play assignments belong to it |
| `fmtx`, `fmty` (master) / `x___`, `y___` | where the slot lines up (the quarterback is at x 182, the line at y 22) |
| `opnm`, `odep` (master only) | repeat `EPos` and `DPos` in all 2,640 rows |

The plays' routes and assignments (`PLYS`) belong to the slot, not to the position. Changing slot 6 from WR3 to TE1 keeps its route and puts a different player in it.

Offensive sets by personnel (running backs and tight ends, then receivers): 11 (3 WR) 39 sets, 21 (2 WR) 38, 10 (4 WR) 23, 22 (1 WR) 18, 12 (2 WR) 16, 20 (3 WR) 13, 00 (5 WR) 11, 01 (4 WR) 6, 31 6, 32 5, 23 4, 30 3, others 1 each. Defensive sets are labelled DL-LB-DB.

`SPKF` / `SPKG` are the Quick Sub packages ("Backup QB", "WR Swap", "HB Slot", "TE Slot", ...): per set, a name and a few slots with their own `EPos` / `DPos`. They override single slots when the user picks a package and are **not** changed by the tool.

## What was checked in the game

Set 32 ("5WR", Shotgun, three receivers on the right, no back) had its fifth receiver (slot 2) changed from WR5 to TE1 in the four copies that hold it (boot 40 and 42, fe2ig 1675 and 1676). In a quick game as the Cowboys the shotgun showed #82, Jason Witten, in the inner right slot where Miles Austin (#19, their WR5) would line up, with no running back, receivers #81 and #17 beside him on the right and #83 and Patrick Crayton on the left. So same-size edits to these entries reach RPCS3 (unlike the preset weights in the shipped database, which the game ignored, see `hc09_position_presets.md`). Which of the four copies the game reads was not separated, so the tool edits every copy that holds a set.

## The tool

**Playbooks tab, Set personnel...** (needs `qkl_boot.ast`; `qkl_fe2ig.ast` is used when found; a save is only needed for player names).

- The list shows a side's sets with formation, personnel, how many playbooks use the set and whether it differs from stock. Filters: side, personnel, playbook, name, changed only.
- A set's panel lists its 11 slots (where each lines up, its position now and in stock) and a position box for the skill slots (HB, FB, WR, TE; on defense every defensive position). The quarterback and the line are not changed. A slot moved to another position goes last in that position's depth; if that leaves a gap in the position it came from, the others are renumbered (and a note says so).
- **Show player names for** (a team box, starting on the team being edited): who lines up in each slot from the loaded save's depth chart (`DCHT`, read from the save file), who a change would replace and who would come in, who is the stock occupant, and a note when one player is listed for two slots of the set (he can only play one). A position with nobody listed says so.
- **Apply to the game files** writes the change into every copy holding the set. Each copy is changed from its own current values (a check fails the write if it differs from what was scanned), and only the changed bytes are written (a few per slot). **Reset this set to stock** and **Restore all to stock...** write the originals back.
- **Bulk change...** applies one rule to the sets shown: in sets with at least N of a position and at most M of another, change the last slots of the first position (highest depth first) to the second. At least 4 WR, at most 0 TE, change 1 WR to TE turns every 10 set into 11 and every 00 set into 01.
- Before the first write to an entry its original is saved, with a checksum, in `Documents\hc09-game-file-backup` (`<archive>.entry<index>.orig` and `.json`); the backup is never overwritten. Stock for the list is read from those backups. The tool refuses to write while RPCS3 is running, checks every entry before it writes any, checks that an unchanged entry saves back byte for byte, and reads each write back. Tested on copies of both archives: change, reset and restore-all gave byte-identical files.

Not done: routes and assignments, names, alignment (`SETG`, `fmtx` / `fmty`), creating sets or plays (that would need the archive's entries to grow), the quarterback and line slots, the Quick Sub packages.
