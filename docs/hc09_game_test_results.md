# Game tests: what they found

Two sets of tests were run in the game with help from testers, using buttons that the editor had for the purpose. **Both are done and the buttons were removed** (the code, `hc09_playtest.py`, `hc09_routetest.py` and the two windows in `guiHC09.py`, is in the git history: `git show 3f3be93:hc09_playtest.py`). This file keeps what they found.

| Tests | Game | What | Result |
|---|---|---|---|
| **A: custom plays**, nine test plays T1 to T9 | PS3 USA in RPCS3, 2026-10-26, a new Cowboys career on the custom playbook Collage | does the game accept, list and run the plays this editor makes, and what do the changes do | **works**, see below |
| **B: route numbers**, B0 to B14 | Xbox 360 build, the first tester | what the numbers of a route step mean, and whether the game reads edits to its play database | length and heading settled, see below |

## A: the custom plays (RPCS3)

All nine plays were made from **Slants** (formation Singleback, set Big: one back, two tight ends, a wide receiver alone on each side) with one thing changed each, added to the custom playbook with the editor's *Add to my game* path, and tried in the game. All nine were listed under Created Plays, could be called and ran.

| Test | What it was | Result |
|---|---|---|
| T1 control | nothing changed | works like Slants. WR2 (alone on the left, 15 yards out) stood "pretty close to the outside hash, about the same distance the receiver on the right is from his sideline". |
| T2 play-action | made a play-action pass | the quarterback turns and fakes, the back fakes, the receivers run their routes and he throws. The linemen pass block and stay behind the line (they do not fire out first): they have the assignments of the game's own play-action play of that set. |
| T3 handoff run | made a handoff run | handoff, a back runs, the linemen run block, the receivers block downfield. **A pass converted to a run works.** |
| T4 triple option (a set with no triple option) | made a triple option | runs as an option (the quarterback rides the back and hands off or keeps to the right) but **no pitch man**: the set has one back and the option's pitch goes to a second back. The editor now warns when a set lacks the players a kind needs. |
| T5 route | WR2 runs an out | works. |
| T6 reads | the left receiver read first | the game coloured the right receiver's route (the first read; the progression numbers are not visible outside the game's own progression screen). **Cause found:** the colour follows `PBPL.vpos`, the slot of the read with the highest chance (true for 1,170 of the game's 1,184 plays with reads); a copied play kept the original's value. The editor now sets it from the reads. |
| T7 moved receiver | WR2 moved from 15 to 9 yards from the middle | **works**: he stood about 9 yards from the middle and the diagram showed him moved. The flip could not be tried. The "little hitch before he cuts in" is the slant's cut. |
| T8 rollout right | the quarterback's named option | rolls out to the right, receivers run their routes; throws on the move "partly" (pressure). |
| T9 play-action boot left | the quarterback's named option | fakes the handoff; rolls out left only partly (mostly backward). The step list is the game's own "Play-action boot left": a gameplay limit, left as it is. |

After the fixes the tester also changed a play he had made with *Plays I made → Save changes to this play* and edited one in the game's own Create-A-Play: both work.

**What this settles:** plays made by the editor load, appear and run; the kind of play can be changed (pass to run, pass to play-action); routes and the quarterback's option can be chosen; **a player can be moved on the field by writing his yards into the play's own set** (`SETG`, no game file touched).

**What the first runs found, all handled by the editor now:**
- **The career needs its own copy of the custom plays.** The game plays a career from the career's copy of the definition rows (`PBPL`, `SETL`, `SETP`, `SETG`, `SGFF`, `PLYS`, `PLPD`, `PLRD`, `PLCM`), which it makes from the profile when a custom playbook is chosen at New Career; plus the playbook's own `PLAB` row. Without them the plays showed one name, one picture and eleven quarterbacks on one spot. See [hc09_custom_plays.md](hc09_custom_plays.md).
- **A custom play's set, play, slot and group numbers must not be numbers of the game's own play database.** The game reads its own set of that number instead: custom sets 66 to 74 were the game's Stop Clock, Twin TE WR, QB Kneel, Onside Return, FakePuntDirectSnap, Punt Max Protect and Punt Return Normal; they showed those names, lined up as a punt return and crashed RPCS3 when edited. Sets 67 and 72 worked. The game picks numbers its data lacks; so does the editor.
- **The profile holds only 100 alignment groups** (`SGFF`): a new play copies only the normal alignment unless it has pre-snap motion.
- **The first read** (`PBPL.vpos`) follows the reads, see T6.

## B: the numbers of a route (Xbox 360, the first tester)

A route is a short list of steps: `8(68,32,254) 9(2,1,0) 8(200,42,254) 10` means *run a leg, cut, run a leg, finish*. The tests changed one number of one route (the *Post* that *WR Post*, *FL Post*, *Cross Up* and others use) in the game's play database and the tester watched a receiver run it.

**What the numbers mean** (from the game's code, read in Ghidra, and confirmed where marked): in a leg `8(first, second, third)` the **first number is its length in yards**, (n >> 3) + (n & 7) / 7 (68 is 8.6 yards, 136 is 17, 200 is 25) *confirmed*; the **second is a heading**, n x 2.8125 degrees (0 right, 32 straight upfield, 64 left, 96 back) *confirmed*; the **third is how hard he runs**, n / 255 capped at full effort *not confirmed*. In the cut `9(side, kind)` the first number is the side (1 right, 2 left) and the second picks the angle of the cut's **animation** (1 and 23: 45 degrees, 2 and 14: 90, 3: 22, 4: 67, 22: 135, 5 and most others: a full turn back), *confirmed as animation only*: the cut does not move the receiver, the leg after it does by its own heading, so a cut that does not match the next leg looks glitchy.

**What the tester saw:** the longer stem (B1) put the break at 17 yards, which also shows **the game reads edits to the master copy of its play database**; heading 64 (B3) gave a flat In, heading 16 on the stem (B7) a diagonal start; changing only the cut (B2, B4, B9) gave glitchy routes that plant for one cut and then run another; cut 5 (B5) gave a Curl-like stop before the post break; B6 and B8 showed nothing because the throw came before the second leg was run. **The play's picture did not change in any test:** it is drawn from separate art data, not from the steps.

**Status: parked.** Settled: choosing among the game's own routes works (A, T5), and a leg's length and heading and the cut's animation mean what the code says. Not settled: the third number as speed and cuts that match the next leg running clean (B6, B8, B11 to B14, the receiver must be watched while the quarterback holds the ball). They matter only for *building* routes from numbers, which the editor does not do: the play creator works with the game's own routes, the game's route tables are full (a new route would need free rows in the step and the art tables), and a route's picture comes from separate art data. If a route lab is wanted later the tests above are the starting point and the details are in [hc09_play_creator.md](hc09_play_creator.md) (*Making your own routes and steps*) and [hc09_game_internals.md](hc09_game_internals.md).

## C: plays added to the game files, and formations of their own (RPCS3, 2026-10-28 and 29)

Each run used a copy of the game with the editor's **Add a play...** applied, the matching profile, and a NEW Cowboys career with the Wishbone playbook; the game was simmed past Friday 8/8/2008 12:00 PM (the day the game builds the plays of both sides for week 1) to the first game. A crash there is `TibMemcardPS3 ... Access violation reading location 0x0`.

**The cause of most crashes: the ids of the added plays.** The game builds a sorted list of plays from the compact copy and reads only its first 3,099 rows (the stock count). Added plays with ids below the stock maximum 7459 (the first version used 7455 to 7458) push stock plays out of that list, and the game crashes when it asks for the one it lost (Man Blitz, 7459). With ids above 7459 the list is exactly the stock plays. See the paragraph "Why the id must be above 7459" in [hc09_play_creator.md](hc09_play_creator.md).

| Copy | Ids | Result |
|---|---|---|
| one play (PA Test) in the stock formation, CPU rows | 7455 | plays |
| two plays in two different stock formations | 7455, 7456 | plays |
| two plays in the SAME stock formation, CPU rows (also: the second only in playbooks the career does not use; without compact-copy rows; in different playbooks) | 7455 to 7457 | **crash** |
| two plays in the same stock formation, **no CPU rows** | **7460, 7461** | **plays** |
| a set row only (id 499, no slots), one play | 7455 | plays |
| the slot rows of a new set only in the compact copy (entry 42) | | crash |
| one new formation (id 499 or 501, whole set in the main database, nothing in the compact copy), nobody moved: lines up like stock, snaps, flips, hot routes, handoff | 7455, 7458 | plays |
| the same with the left receiver moved next to the left tackle and a changed route | 7455, 7458 | plays; he stands there |
| two new formations with ids 499 and 495 (rows inserted before a stock row) | 7455, 7457, 7458 | crash |
| two or three new formations with ids 501 to 503 (after every stock row), a different player moved in each | 7455 to 7458 | plays; each play lines up with its own moved player |
| two plays in ONE new formation (501) plus a second new formation (502), **ids above 7459**, no CPU rows | **7460 to 7462** | **plays** |

What the runs fix: a new set's rows go into the main database only, **after** the stock rows (set ids 501 to 511, then the free ids below 500: a formation at id 84 worked in RPCS3 on 2026-10-31, so about 230 formations of your own); its slot rows must not go into the compact copy; an added play has an id above 7459 and no CPU rows. The earlier "two plays in one formation crash" runs were the ids, not the formation: plays that share a formation work. One run with an unmoved copy at 501 and a moved one at 502 showed the moved receiver at his stock place; it did not come back in later runs and is unexplained.

## D: converting "Plays I made" into game plays (RPCS3, 2026-10-29)

New Cowboys career with the playbook "Payton Spread Attack" (278), simmed past Friday 8/8 12:00 PM, then the plays tried in the game. Each copy converted 11 of the profile's 25 custom plays (ids 7460 to 7470, one formation each).

| Copy | What was different | Result |
|---|---|---|
| v11b | the formation was a copy of the custom set (placeholder slot columns), the play family kept the custom play's | reached the game; plays lined up wrong or ran another play (a play-action toss ran as a run only); **editing one in the game's own editor crashed the game** (LoopSimulation thread, a read of address 0x63c) |
| v11c | the formation is a copy of the stock look-alike formation with the custom places, the family is a stock play's | reached the game; **flipping a play and calling it froze the game** (the audio kept playing; every flipped place was 0.0 / 0.0) |
| v11d | the flipped places follow the game's rule | **reached the game; the plays worked** (they lined up, ran and flipped) |
| v11e | all 18 convertible plays, in 9 formations (plays with the same lineup share one) | **reached the game; all the plays worked** (the plays that share a formation lined up, ran their own routes and flipped) |

What the runs fix: build a converted play's formation from the stock look-alike formation with only the custom places on it, take the play family from stock plays of the same kind, and compute the flipped places from the flip partner. Added plays cannot be edited in the game's own play editor.

**Formation at a free id below 500 (v12a, 2026-10-31).** One play (PA Middle with the second receiver moved to the sideline, 22 yards) in a new formation at id 84, a gap in the game's own set numbering, its slot, group and package ids appended above all ids in use: the game reached game day after Fri 8/8 12:00 PM, the receiver stood at the sideline and the play ran. (The editor takes the highest free id below 500 first, to stay clear of the low ids the game gives the custom plays made in it; that choice is the next test.) So the earlier rule that new formation rows must come after every stock row (ids above 500) was an artefact of the play-id bug fixed in #73, and the formation limit is about 230, not 11. Not tried: many such formations in one game, a flip of the play.
