# Custom plays and playbooks (Create-a-Play) in an HC09 save

What was found by opening a career save and the profile save beside it, and what is still unknown. Checked on one real save pair: a career (`BLUS30128-CAREER-...`) and the profile it was made with (`BLUS30128-PROFILE-...`, a 320 KB `USR-DATA` with 43 tables).

## Where things live

- **The profile save holds the definitions and the names.** Its `PLAB` table names the custom playbooks, `SETL` names the custom sets, `PBPL` names the custom plays. Each custom play also has 11 rows in `PLYS` and `SETP`, and `SETG` holds the positions: 14 plays gave 154 `PLYS`, 154 `SETP` and 158 `SETG` rows. Smaller tables (`PLCM`, `PLPD`, `PLRD`, `PBAI`, `SGFF`) have a handful of rows. What the columns of these definition tables mean has not been worked out.
- **The career save only holds links.** Its `PGPL`, `PGSS`, `PGSL` and `PGFM` rows say which set and play is in which playbook, exactly like stock plays. Its own `PLAB`, `SETL` and `PBPL` tables are empty, so a custom playbook or play has no name there.
- **The profile also carries its own copy of the playbook tables** (`PGPL` had 10,687 rows against the career's 10,628). They are independent files.

## Custom playbooks are Playbooks 1 to 10

The game allows up to 10 custom playbooks. In the profile's `PLAB` they have `PBGI` 1 to 10 (the playbook id, `BOKL` in the career) and `BGID` 46 to 55. In the example, offensive: Collage, Run and shoot, run, West Cost, Run, Spred Option, ZONE BLOCK, Modern and Army Run; defensive: Created Playbook. The 98 playbooks of a career are these 10 plus the game's own.

## Custom plays

The 14 custom plays in the example are each in a set named `Created`, which sits under the special formation **8190** ("Created Plays"), in Playbooks 1, 8 and 9 (29 links in all). `PLTP` (play type) varies from play to play. The profile and the career agreed on all of this.

## What the editor does with it

The Playbooks tab finds the profile next to the career (`<TITLE>-PROFILE-*`, choosing the one whose custom plays match the career's links), reads `PLAB`, `SETL` and `PBPL` from it, **read-only**, and uses those names only for ids the game does not already name. **Profile save...** points it at a profile by hand. Nothing is written to the profile.

Add plays still refuses to copy custom sets, plays and formations: a reporter found that copying them broke flipping and put punts in the Gun.

## Not known

- Whether copying a custom play's links into another playbook works in the game, and why it broke for the reporter. The definitions are not in the career, so the links alone should be enough, but the formation they sit under may matter. Needs an in-game test on a copy of a save.
- How the game picks the profile's definitions up when a career runs, and what happens when the career is loaded with a different profile.
- The meaning of the `PLYS`, `SETP` and `SETG` columns.
- What the game stores when a team is given a custom playbook. The Team playbooks picker does not offer them.
