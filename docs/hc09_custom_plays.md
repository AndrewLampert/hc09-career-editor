# Custom plays and playbooks (Create-a-Play) in an HC09 save

What was found by opening a career save and the profile save beside it, and what is still unknown. Checked on one real save pair: a career (`BLUS30128-CAREER-...`) and the profile it was made with (`BLUS30128-PROFILE-...`, a 320 KB `USR-DATA` with 43 tables).

## Where things live

- **The profile save holds the definitions and the names.** Its `PLAB` table names the custom playbooks, `SETL` names the custom sets, `PBPL` names the custom plays. Each custom play also has 11 rows in `PLYS` and `SETP`, and `SETG` holds the positions: 14 plays gave 154 `PLYS`, 154 `SETP` and 158 `SETG` rows. Smaller tables (`PLCM`, `PLPD`, `PLRD`, `PBAI`, `SGFF`) have a handful of rows. What the columns of these definition tables mean has not been worked out.
- **The career save only holds links.** Its `PGPL`, `PGSS`, `PGSL` and `PGFM` rows say which set and play is in which playbook, exactly like stock plays. Its own `PLAB`, `SETL` and `PBPL` tables are empty, so a custom playbook or play has no name there.
- **The profile also carries its own copy of the playbook tables** (`PGPL` had 10,687 rows against the career's 10,628). They are independent files.

## Custom playbooks are Playbooks 1 to 10

The game allows up to 10 custom playbooks. In the profile's `PLAB` they have `PBGI` 1 to 10 (the playbook id, `BOKL` in the career) and `BGID` 46 to 55. In the example, offensive: Collage, Run and shoot, run, West Cost, Run, Spred Option, ZONE BLOCK, Modern and Army Run; defensive: Created Playbook. The 98 playbooks of a career are these 10 plus the game's own.

**Each custom playbook starts as a copy of one of the game's playbooks**, and other plays and formations, stock or custom, are added to it. Custom plays and custom playbooks are separate things: a custom playbook doesn't need any custom plays, and the custom plays don't have to be together. In the example only 3 of the 10 (Playbooks 1, 8 and 9) hold custom plays, and no game playbook holds any. By play overlap, the base of several of them is clear:

| Custom playbook | Closest game playbook | Overlap |
|---|---|---|
| Modern | Payton Spread Attack | 99% of each |
| ZONE BLOCK | Shanahan Zone Block | 82% of the custom book, 99% of the stock one |
| West Cost | Martz Air Attack | 83% / 99% |
| Army Run | Sanders Army Run | 85% / 95% |
| Run and shoot | Run and Shoot | 77% / 78% |
| Created Playbook (defense) | Cardinals Blitz | 93% / 100% |

The others are looser (heavily changed): `run` looks like Steelers Smashmouth and `Run` like Texans Power Run, and `Collage` and `Spred Option` have only about a third to two thirds in common with College Attack.

**The profile's names belong to the career's slots.** Before any playbook edit, Playbooks 1 to 10 held exactly the same plays in the career as in the profile (no play on only one side). The game's own playbooks differ by about one play each between the two files; that is separate from the custom ones. The editor checks this on every load: a custom playbook is only named when at least 80% of its plays in the profile are in the same-numbered playbook of the career. A playbook that fails (say it was rebuilt in the game after the career was started) keeps its generic name and the status line lists it, so a name never sits on the wrong playbook.

## Which playbook a team plays

Every coach row has an offensive (`CPID`) and a defensive (`CDID`) playbook, so a team holds one for its **head coach** and one for each **coordinator** per side. The editor treats the **head coach's** as the team's playbook: it is the one chosen on the game's New Career Playbook Select screen, and it is the one the player calls from. The coordinators hold their own (listed beside it for reference, and marked `(OC)` / `(DC)` in the playbook table where they differ). In the 10 careers checked, a head coach's playbook differs from the coordinator's on roughly a third of teams (92 of 320 offenses, 116 of 320 defenses), so reading only the coordinators, as the editor used to, showed the wrong playbook for the player's own team.

The **Playbook Control** team philosophy (`OPPP` offense, `DPPP` defense in `TPHS`; 0 = Head Coach, 1 = Coordinator) looks as if it decides which coach's playbook is played, but players report that it makes no visible difference (the coordinators call the plays in a sim either way), so the editor does not offer it as a choice on the Playbooks tab; it is still editable under Team Philosophy on the Coach tab. This is not confirmed in the game.

A **custom** playbook choice is stored on the **head coach's row only** (`CPID` 46 to 55 offense, 52 defense in the example; the coordinators keep a game playbook, and `TEAM.TOPB` / `TDPB` stay on the game's). In all 9 careers checked where a head coach holds a custom playbook, the Playbook Control of that side was Head Coach, so the editor sets that too when it gives a team a custom playbook, to match the game's own state.

## Custom plays

The 14 custom plays in the example are each in a set named `Created`, which sits under the special formation **8190** ("Created Plays"), in Playbooks 1, 8 and 9 (29 links in all). `PLTP` (play type) varies from play to play. The profile and the career agreed on all of this.

## What the editor does with it

The Playbooks tab finds the profile next to the career (`<TITLE>-PROFILE-*`, choosing the one whose custom plays match the career's links), reads `PLAB`, `SETL` and `PBPL` from it, **read-only**, and uses those names only for ids the game does not already name. **Profile save...** points it at a profile by hand. Nothing is written to the profile.

Add plays still refuses to copy custom sets, plays and formations: a reporter found that copying them broke flipping and put punts in the Gun.

## Idea: making custom plays outside the game

The set called `Created` and the special formation 8190 ("Created Plays") are where the game files its custom plays, so they are the natural slot for plays made outside the game and written back into the profile and career. The catch is that a play has to be **legal**, meaning the game accepts it and it can work, so the rules and limits have to be learned first.

What a custom play is made of, from the example: in the profile, one `PBPL` row (name, play type) and one `SETL` row (the set), 11 `SETP` rows, 11 `PLYS` rows and `SETG` rows for the positions, plus rows in the smaller tables for some play types (`PLCM`, `PLPD`, `PLRD`); in the career, three link rows (`PGPL`, `PGSS`, `PGSL`) per playbook it is in.

The game archive (`qkl_boot.ast`) has these same tables but **empty**, so there are no stock plays to learn the rules from. The only definitions available are the player's own custom plays (14 in the example). Everything else has to come from in-game tests: make a play in the game, save, and compare the profile before and after (the profile is a second file to compare), then change one thing at a time.

A sensible order: work out what each column means from the existing plays and from small in-game experiments; write a checker for the rules, like the playbook one that was verified on all 98 playbooks; start by **cloning and slightly editing an existing custom play** rather than building one from nothing; and always back up and run `verify-db` after writing. Writing the profile is a new kind of risk, since so far the editor only reads it.

**Update:** the tables are not empty everywhere. The game's master play database (`qkl_boot.ast` entry 40, see [hc09_play_data.md](hc09_play_data.md)) holds all 3,099 stock plays with their sets, assignments and route art, so the stock plays can be read and the editor's **Play creator** (prototype) builds a custom play from one of them in copies of the profile and career, see [hc09_play_creator.md](hc09_play_creator.md). The profile holds link rows too (`PGPL` 29 for the 14 custom plays), not only the career. Still untested in the game.

## Idea for later: sharing and swapping custom playbooks

Not started. Three levels, easiest first:

1. **A playbook made only of the game's own plays and formations** (most custom playbooks start as a copy of a game playbook and add more game plays). Every copy of the game has those plays, so such a playbook could be shared as a small recipe: its name, its side, and the list of formation / set / play links. Importing it would write the link rows (`PGPL`, `PGSS`, `PGSL`, `PGFM`) into one of the receiver's custom slots (Playbooks 1 to 10) and its name into their profile. Two things are missing: the editor can only add rows today, so replacing a slot's contents needs row removal (or reuse of the table's spare slots) with the row counts and checksums kept right; and it would be the first time the editor writes the profile.
2. **A playbook that includes custom plays** also needs the play definitions moved (`PBPL`, `SETL`, `PLYS`, `SETP`, `SETG` and the small tables, 11 rows per play), with the set and play ids renumbered so they don't collide with the receiver's own custom plays. That needs the meaning of those columns worked out first.
3. **Swapping whole profiles** is the same as 2 for everything at once.

Still to find out: when a career is started, how the game copies the profile's playbooks into it and which side wins when they disagree; and what the game does with a custom playbook whose links are in the career but whose definitions are not in the profile. Both can be tested in the game on a copy of a save. Every write needs a backup first and `verify-db` afterwards.

## Not known

- Whether copying a custom play's links into another playbook works in the game, and why it broke for the reporter. The definitions are not in the career, so the links alone should be enough, but the formation they sit under may matter. Needs an in-game test on a copy of a save.
- How the game picks the profile's definitions up when a career runs, and what happens when the career is loaded with a different profile.
- The meaning of the `PLYS`, `SETP` and `SETG` columns.
- What the game stores when a team is given a custom playbook. The Team playbooks picker does not offer them.
