# Testing guide: the Play creator and the route numbers

For people helping to test, on their own copy of the game (PS3 USA in RPCS3). Everything is done from the editor; you never edit a file by hand. Part A has been run once (RPCS3, 2026-10-26, results below); Part B has first results too (see its section).

Two parts. **Part A** tests the custom plays the Play creator makes (about 10 minutes in the editor and then the game; **T7, the moved player, is the one that matters most for what we can build next**). **Part B** tests what the numbers inside a route mean, which decides whether making your own routes is possible at all (about 40 minutes for the main tests, B1 to B5; B6 to B9 are a bonus). You can do Part A without Part B and the other way round.

## 0. Before you start (10 minutes, once)

1. **Get the newest editor** (the `main` branch of the editor's GitHub page: `git pull` if you cloned it, or download the zip again) and start it with `Start HC09 Editor.bat` (the launcher checks Python and Node and installs what the bridge needs the first time).
2. **Close RPCS3.** Keep it closed whenever you press an Add, Apply or Put-back button; start it again only to look at the result, and close it again before the next button.
3. **Make your own copy of the saves**, by hand, as well as the editor's automatic backups: copy the whole `BLUS30128-PROFILE-HEADCOACH` folder (in RPCS3's `dev_hdd0/home/00000001/savedata/`) and the folder of the career you will use somewhere safe. The profile is shared by every career and holds all your custom plays, so this copy matters.
4. In the editor, press **Saves...** (or Load Save File) and open the career you will test with. The editor finds the game files by itself; if it asks for `qkl_boot.ast`, point it at the one in RPCS3's `NFL Head Coach 09 (USA)/PS3_GAME/USRDIR` folder.

**What the editor changes, and how to undo it**

| Part | What changes | Backup | Undo |
|---|---|---|---|
| A | your profile save and your career save (the two `USR-DATA` files), only when you press **Add the nine test plays to my game** (or **Add to my game** in the Play creator) | `Documents\hc09-test-backups\<date and time>\` (both files, every time) | **Put my saves back** in the same window (all the way back, or one step), or copy your own copies back |
| B | a few numbers of one route in the game's two copies of its play database (`qkl_boot.ast` and the in-game copy in `qkl_fe2ig.ast`), only when you press **Apply this test** | the first time, the original of each entry in `Documents\hc09-game-file-backup\` | **Put the route back to the game's own** in the Route test window, which restores the numbers exactly (tested byte for byte) |

If anything looks wrong or the game will not start: close RPCS3, press the undo button, and tell us what happened.

## Part A: the custom plays (the Test plays window)

One button makes all nine test plays and adds them to your game; you then try them in the game and write down what you saw, in the same window. About 10 minutes in the editor, the rest in the game.

**First, make your team use the custom playbook** (otherwise the game never offers the test plays and "it is not in my playbook" would only mean your team plays another one): Playbooks tab, **Team playbooks** box, choose your team, and on the Offense row press **Change...** and pick a custom playbook (1 to 10); then **Save to File**. The Test plays window says which custom playbook it is going to use: the one your team plays if it plays a custom one, otherwise custom playbook 1 (and then it tells you your team does not play it yet).

**In the editor** (RPCS3 closed, your career loaded):

1. Playbooks tab, **Test plays (testers)...** (a few seconds to read the game's plays).
2. Press **Add the nine test plays to my game** and say yes to the one question. The editor makes the seven plays, checks them, saves your own two files in `Documents\hc09-test-backups` and puts the new ones in place (about a minute). If it says it could not find your profile save, press **Details...** and pick the `USR-DATA` in the `BLUS30128-PROFILE-...` folder. **On Xenia (Xbox 360)** open your career from **Saves...** (Xenia saves are marked *(Xenia)*; if yours is not listed press *Look in another folder...* and pick Xenia's folder, the one that holds `content`, or load the `.mc02` with **Load Save File**). The profile is found next to it by what is in it; if the window says it could not find it, pick your profile's `.mc02` in **Details...**. If the editor cannot find your saves, tell us where Xenia keeps them (the folder path and what the folders under `content` are called).
3. Start RPCS3 and the game, load the career: open the offensive playbook, go to the custom playbook, then **Created Plays**.

**If the game crashes or will not load the career with the nine in** (the editor adds them together, so a crash cannot be pinned on one play): close RPCS3, press **Put my saves back...** and **Yes**, then press **Add only T1 (the control)** and see whether the career loads with that one alone. Tell us which of the two worked.

If you changed your team's playbook in the Playbooks tab while the window was open, the window picks that playbook when you press the button (unless you chose one by hand under **Details...**); the question it asks says which playbook and whether your team plays it. The editor also names the team (the one picked at the top of the editor), so check that it is yours.

The nine plays are copies of **Slants** (formation Singleback, set Big) with one thing changed each (T9 two), so that what the game does with each kind of change can be told apart:

| Test | What it is | What to look at |
|---|---|---|
| **T1 Slants** | the control: nothing changed | does the game accept a custom play at all? Does it run like the original Slants? Where does WR2, the wide receiver alone on the left, stand before the snap? (write it down: this is what T7 is compared with) |
| **T2 Slants PA** | changed to a play-action pass | the quarterback turns and fakes the handoff, the linemen fire out as if to run block and then pass block, the back fakes taking the ball, the receivers run their routes and the quarterback throws |
| **T3 Slants Run** | changed to a handoff run | the quarterback hands off, a back takes the ball and runs, the linemen run block, the receivers block downfield instead of running routes |
| **T4 To Triple** | changed to a triple option (no triple option uses this set, so the assignments come from other formations) | the quarterback runs the option (rides, then keeps or pitches), a back takes a pitch; does anything stand still or run into the wrong place? |
| **T5 WR Out** | one receiver's route: WR2 (alone on the left) runs an out, medium | WR2 runs up the field, then toward the sideline |
| **T6 Reads** | the quarterback's reads: WR2 first, TE2 (next to him) second | on the play's diagram in the playbook the numbers 1 to 5 stand on the receivers in that order; with no pressure the quarterback looks to WR2 first |
| **T7 Moved WR** (important) | one player's place: WR2, the receiver alone on the left, stands 9 yards from the middle instead of 15 | before the snap WR2 stands about 9 yards from the middle of the field (between the hash marks and the numbers, about 4 yards outside the tight end); the diagram shows him moved; if the game flips plays, the whole formation is the mirror image. **This is the one that matters most for what we can build next.** |
| **T8 QB Rollout Right** | the quarterback's named option "Rollout right" instead of the usual dropback (everything else as T1) | after the snap the quarterback runs out to the right and throws while moving; the receivers still run their slants. This is the "rollout" you can pick for the quarterback in the Play creator |
| **T9 PA Boot Left** | a play-action pass (as T2) whose quarterback is "Play-action boot left" | the quarterback fakes the handoff, then runs out to the left and throws on the move; the back fakes, the linemen fire out and then pass block |

**In the game**, for every test play: is it listed, with its name and a diagram that looks like the original? Can you call it without the game crashing or freezing? Run it two or three times and look at what the table says. Anything odd (players standing still, wrong formation, missing players, strange camera)?

**Write the answers in the window** (step 2 of the Test plays window): pick a test in the list and answer its questions with the drop-downs and the text lines. The answers are saved as you give them, so closing the editor loses nothing. When you are done press **Copy my answers for Discord** and paste into the chat (or **Save my answers to a file**: `Documents\hc09-test-results\play-test-results.txt`; the state is in `play-test.json` in the same folder). Screenshots of the playbook screen (Created Plays) and of anything odd are welcome.

When you are done, close RPCS3 and press **Put my saves back...** in the Test plays window, then **Yes** to get your files from before the first install (if you want to keep the test plays, skip this).

**First results of Part A (RPCS3, 2026-10-26, a new Cowboys career, custom playbook Collage).** All nine plays were listed under Created Plays, could be called and ran. Per test:

| Test | Result |
|---|---|
| T1 control | works like Slants. WR2 (alone on the left, 15 yards out) stood "pretty close to the outside hash, about the same distance the receiver on the right is from his sideline". |
| T2 play-action | the quarterback turns and fakes, the back fakes, the receivers run their routes and he throws. The linemen pass block and stay behind the line (they do not fire out first): they have the assignments of the game's own play-action play of that set, so the test's wording ("fire out as if to run block, then pass block") was an assumption, not a failure. |
| T3 handoff run | everything as expected: handoff, a back runs, the linemen run block, the receivers block downfield. **A pass converted to a run works.** |
| T4 triple option (a set with no triple option) | runs as an option (the quarterback rides the back and hands off or keeps to the right) but there is **no pitch man**: the set has one back, the option kind's pitch goes to a second back. The converter should warn when a set lacks the players a kind needs. The editor now warns about this. |
| T5 route | WR2 (the left receiver) runs an out. |
| T6 reads | the tester could only see which route the game colours (the first read), not the numbers: it was the receiver on the right (WR1), not WR2. **Found why:** the colour follows `PBPL.vpos`, the primary receiver, which a copied play keeps from the play it was copied from (Slants: the right receiver); in the game's own plays it is the slot of the read with the highest chance. The editor now sets it from the reads. To test again: T6 (made again) should colour WR2's route. |
| T7 moved receiver | **works.** He stood about 9 yards from the middle, the diagram showed him moved. The flip could not be tried. "A little hitch before he cuts in" is the slant's cut (the control T1 has it too, to be confirmed). |
| T8 rollout right | the quarterback rolls out to the right and the receivers run their routes; he throws on the move "partly" (it depends on the pressure). |
| T9 play-action boot left | fakes the handoff, the back fakes; he rolls out to the left only "partly": it looks like the play-action animation followed by a move backwards rather than to the side. The same step list is the game's own "Play-action boot left", so compare it with a stock boot play (PA Boot Lt) in the same set. |

What this settles: custom plays made by the editor load, appear and run; the kind of play can be changed (pass to run, pass to play-action); routes and the quarterback's option can be chosen; and **a player can be moved on the field by writing the yards into the play's own set**.

What the first runs found, and the editor now does: the game plays a career from the career's own copy of the custom plays' rows; a custom play's set, play, slot and group numbers must not be numbers of the game's own play database (sets 66 to 74 are the game's Stop Clock ... Punt Return Normal and misbehaved or crashed RPCS3); the profile can hold only 100 alignment groups.

**Changing a play you made** (optional, after the nine): Play creator, Playbook list, **Plays I made**, pick one of the test plays (T7 Moved WR is a good one), drag a player somewhere else or give someone another job, press **Save changes...** and **Save changes to this play** (one question). Close the editor's window if you like, start the game and look at the same play: it should have the new change and nothing else; the play must not appear twice. If you press **Save as a new play** instead, the changed play is added next to the first one. Tell us if the game shows the old version, shows both, or does not load the career.

**Making one play by hand** (not part of the test): Playbooks tab, **Play creator...**, pick a play, change what you like, press **Make custom play...** and then **Add to my game** (one question; the same backups and the same Put my saves back). **Details...** has the files, the output folder and the playbook if you want to choose them yourself, and **Only make the files** makes the two copies without changing your game.

## Part B: the route numbers (the Route test window)

**Why:** a route is a short list of steps: `8(68,32,254) 9(2,1,0) 8(200,42,254) 10` means *run a leg, cut, run a leg, finish*. The game's own route data suggests what the numbers mean (below), but nobody has seen it in the game, and we do not know whether the game reads the file the editor can change. If we know both, the editor could one day let you build a route; if the game ignores the edit, that idea is dead and we must look elsewhere. Seven simple tests settle it.

**What the game's code and data say the numbers mean (your tests confirm or refute it).** In a leg `8(first, second, third)`: the **first number is its length in yards**, (n >> 3) + (n & 7) / 7, so 68 is 8.6 yards, 136 is 17, 200 is 25 and 60 is 7.6; the **second number is a heading** in degrees, n x 2.8125, so 0 is to the right, 32 (90 degrees) straight upfield, 42 is 118, 16 is 45, 64 is 180 (to the left) and 96 is 270 (back toward the quarterback); the **third number is how hard he runs** (n / 255, capped at full effort): 254 is full, 127 half. In the cut `9(side, kind)`: the first number is the side the cut turns to (1 right, 2 left) and the second picks the angle of the cut's **animation** (1 and 23: 45 degrees, 2 and 14: 90, 3: 22, 4: 67, 22: 135, **5 and most other numbers: a full turn back, about 180**). The cut does not move the receiver along the route, the leg after it does, by its own heading: that is why a cut that does not match the next leg looks glitchy. So the stock Post is a first leg of about 9 yards, a left cut of 45 degrees and a long second leg of 25 yards.

**What the first tester found** (Xbox 360 build, master copy only, quick game; the code we read is the PS3's, from the same source, and it predicted what he saw): the longer stem (B1) put the break at 17 yards, which also shows the game reads edits to the master copy; heading 64 (B3) gave a flat In, heading 16 on the stem (B7) a diagonal start; changing only the cut (B2 heading, B4 side, B9 sharpness) gave glitchy routes that plant for one cut and then run another; cut 5 (B5) gave a Curl-like stop before the post break; B6 and B8 showed nothing because the throw came before the second leg was run; the play's picture stayed the stock one in every test. B11 to B14 follow from that.

**The picture of the play does not change.** The play's diagram on the play-call screen and in the playbook is drawn from separate art data, not from the step numbers these tests edit. The first tester saw the stock Mid Post picture in every test while the receiver ran something else: that is expected, so judge by watching the play run. (Create-A-Play's own route arrow did change in some of his tests; say what it shows if you look.)

**A glitch is a result.** Changing one number can make a route that does two things at once (the receiver plants for one cut and then runs another way), and that is exactly what some of these tests are meant to show. Pick "yes, but glitchy" in the form and describe both halves in your own words ("plants for a cut to the left, then heads to the sideline"). If you are unsure whether it is a glitch or an unusual route, just describe what you saw.

**Hold the ball for B6, B8 and B11.** When the quarterback throws, the receivers stop running their routes. To watch a whole route do not throw: wait with the ball (a team with a strong offensive line, like the Cowboys, gives you the time) and watch the receiver, or use the replay.

**How:** Playbooks tab, **Route test (testers)...**. The window changes **one route** (the *Post* that *WR Post*, *FL Post*, *Cross Up* and others use; it is used by 58 receivers in 42 of the game's playbooks) one number at a time and tells you, for each test, what to look at.

**Which copy it changes (Write to).** The game keeps its plays in more than one place. The editor now writes the test's numbers into both the master copy of the play database (`qkl_boot.ast`) and the in-game copy that holds the Create-A-Play plays (`qkl_fe2ig.ast`), because the game's code seems to read the in-game one when it sets a play up, and we do not know which one a quick game uses. The **Write to** box next to the buttons can limit a test to **In-game copy only** or **Master copy only**. Use the default (**Both copies**) for B0 to B5. **If a change shows up in Both, repeat that one test once with In-game copy only and once with Master copy only** (press Apply, check the same play) and tell us which of the three showed it: that tells us which copy the game reads. **What we expect (a guess from reading the game's code, to be checked, not a fact):** a play you call in a **Play Now** game (a play from a team's playbook) is served by the master copy, so it should change with **Master only** and not with **In-game copy only**; a play you run from **Create-A-Play** is served by the in-game copy, so it should change with **In-game copy only**. If your result is different, that is exactly what we want to hear about. The in-game copy only holds the Create-A-Play plays, so test it with the **Create-A-Play** switch below. Whichever you choose, the copies you did *not* choose are put back to the game's own, so a test never leaves a half-changed route. The window's first line says where the route is changed right now, and **Put the route back to the game's own** puts every copy back. (If the editor cannot find the in-game copy, the box is greyed out and shows *Master copy only*, which is what the test did before.)

**Which play to test with.** The window picks it for you; it is in step 2 of every test: the team to play as, that team's **base playbook** (the game's own, never a custom one), the exact play with its **PLYL** (the play's id in the game files), its formation and set (several sets are called "Normal"), and where the receiver lines up (for example *WR1, wide on the right, about 15 yards right of the middle and 2 yards behind the line, closest to the sideline*). Several receivers run deep breaking routes in the same play, and only the one who runs this route changes, so watch that one. The window first looks for a team with a **strong offensive line** (the Cowboys): with a weak line the pass rush reaches the quarterback before the receiver breaks and there is no route to watch (a tester found the Bears' line barely held the rush that long, and the Cowboys, with a loaded offense, much better). If none of those has a good play for this (an ordinary pass that throws to that receiver), it uses your team, then another team, and names a few more teams that have the same play. **Use the same play for every test.** **Playbooks give the same play different names**: the window calls it by the name your playbook shows on the play-call screen and says what the master list calls it. For example play 546 (*FL Post* in the master list) is *22 Z Post* in the Bears' playbook and *Scat Rt 568 H Flat* in the Cowboys' (Garrett Pass Attack), and no stock playbook calls it *FL Post*. Go by the PLYL, the formation, the set and the receiver, not by the name.

**Create-A-Play instead of a quick game.** The window's **Test with** switch (top right) has two choices: **Play Now** (the default, described above) and **Create-A-Play**. With Create-A-Play, step 2 names an existing play from the game's own Create-A-Play list (it holds one play for each set; the route is used in 14 of them) with its PLYL, formation and set, and where the receiver lines up. The play is always one that is also in at least one of the game's own named playbooks, never a custom one only. The name shown in Create-A-Play can differ a little from the playbook name (24 of its 177 plays end in "(1)"): go by the formation, the set and the receiver. **We do not know the menu wording or how to run a play from Create-A-Play yet**: if you use it, tell us what the menus are called and how you ran the play, and we will fix the text. The switch is greyed out when the editor cannot read Create-A-Play's plays (they are in `qkl_fe2ig.ast`).

The route is the *Post* that *WR Post*, *FL Post*, *Cross Up* and others use; it is used by 58 receivers in 42 of the game's playbooks. **Copy all plays that use this route** (bottom left of the window) copies every one of them with its PLYL, formation, receiver and all its playbooks, if you want to choose another. **If a test seems to change nothing, check B0 and that test again with a second play before you report "no change"**; a receiver you did not watch is the usual reason. For every test:

1. Close RPCS3. Select the test in the list and press **1. Apply this test**.
2. Start the game and a quick game (**Play Now**) as the team step 2 of the window names, and play offense. Call the play it names.
3. Run it three or four times and watch the receiver step 2 names (the one with the long run up the field and a break). The replay helps. **Count yards using the field's yard lines: how many yards past the line of scrimmage does he run before he breaks?** **Which route does he run?** (the form lists the names: Go, Hitch or Curl, Comeback, Out, In or Dig, Slant, Post, Corner, Flat) How far does he run after the break?
4. Close the game, fill in the form in the window (**2. Your answer**) and press **Save my answer**. It keeps your answers even if you close the editor.

**The order** (the window shows the same list):

| Test | What it changes | What we learn |
|---|---|---|
| **B0** | nothing (the control) | how the stock route runs: stem depth, break direction, run after the break. Do this first, it is what the others are compared with. |
| **B1** | the stem's first number 68 to **136** | **does the game read the edited file at all, and is that number a length?** If the receiver runs about twice as far before he breaks (17 yards instead of 9): yes to both. If nothing is different: no. Tell us right away. |
| **B2** | the second leg's second number 42 to **16** | is it a heading? 118 to 45 degrees; seen once: a glitchy plant-then-outside cut. |
| **B3** | the same number 42 to **64** | which way do bigger numbers turn it (opposite to B2?) By the numbers 64 is 180 degrees, back along the line. |
| **B4** | the cut's first number 2 to **1** | does it turn the cut to the other side? |
| **B5** | the cut's second number 1 to **5** | the code says 5 is a full turn back (about 180 degrees); seen once: a curl-like stop before the post break. |
| **B6** (bonus) | second leg's length 200 to 60 (25 to 7.6 yards) | **hold the ball**; is the length in yards for the second leg too? (not seen yet) |
| **B7** (bonus) | stem heading 32 to 16 (90 to 45 degrees) | seen once: a diagonal start |
| **B8** (bonus) | second leg's third number 254 to 127 (full to half effort) | **hold the ball**; not seen yet |
| **B9** (bonus) | cut second number 1 to 2 (45 to 90 degrees) | seen once: a glitchy 90-degree plant, then the post cut |
| **B11** (bonus) | the stem's third number 254 to 127 | does he reach the break later? **hold the ball** |
| **B12 to B14** (bonus) | cut and leg changed TOGETHER: a clean Corner (side 1, heading 16), a clean In (cut size 2, heading 64), a clean Curl (cut size 5, heading 96, 3 yards) | if the cut and the leg only have to agree, these are clean routes with no glitch: that is what the route lab will need |
| **B10** | nothing (the control again) | **did Put the route back work?** The route should run exactly as in B0. Press *Put the route back to the game's own* before this test. |

**Naming the route.** The form asks which route the receiver ran, not just which way he broke. The difference that matters most: a **Go** has no break at all (it is straight upfield the whole way), while a **Hitch or Curl** also starts straight upfield but then stops and turns back toward the quarterback, and a **Comeback** turns back toward the sideline. **Out** and **In or Dig** are sharp turns of about 90 degrees to the sideline or to the middle; **Corner** and **Post** are shallower (about 45 degrees) turns to the sideline or to the middle; a **Slant** is a diagonal toward the middle after a short run; a **Flat** goes straight to the sideline close to the line. Pick the closest name, and describe it in the notes if none fits. The stock route is a Post.

Measure in yards as well as you can; "about twice as far", "turned toward the middle at about 45 degrees" are good answers. If you cannot tell, say so. A short video of B0, B1 and B3 (the receiver and the yard lines) helps a lot if you can make one; it is optional.

**Sending the results:** in the Route test window press **Copy my answers for Discord** and paste into the chat (the answers are also saved in `Documents\hc09-test-results\route-test.json`). Screenshots of the playbook screen (Created Plays) and of anything odd are welcome.

## What the answers decide

| If we see ... | it means ... | next |
|---|---|---|
| **B1: nothing changed** | the game does not read routes from this file, so the in-place idea cannot work this way | find the copy the game does read (this is the important result; stop here and tell us) |
| **B1: the stem is longer, B6: the second leg is shorter** | the file is read and the first number is a length | check the yards against the formula (8.6 and 17 yards for 68 and 136) |
| **B2 and B3 break in two different directions** | the second number of a leg is a heading (32 = 90 degrees = straight upfield) | the lab can draw a break at any angle; the degrees formula only needs a couple of angles to confirm |
| **B4 flips the side, B5 changes sharpness** | the cut's numbers are the side and the angle of the cut animation (seen) | the lab sets the cut to match the next leg |
| **B12 to B14 run clean** | a cut that matches the next leg gives a clean new route | the route lab can build any route from legs and matching cuts |
| **B12 to B14 are still glitchy** | the cut and the leg are linked in a way we have not found | more tests, and a closer look at the cut code |
| **everything responds as above, and T1 to T3 work** | writing routes in place is possible | we build the route lab (draw a route, match it to the nearest one the game has, give up one of the game's single-use routes only if you insist), with these numbers |
| **B1 works but the numbers behave in no pattern** | the file is read but we cannot yet say how | more tests with a simpler route |
| **the game will not load the career with all nine, but loads it with T1 alone** | one of T2 to T9 breaks the game (T4, with assignments from other formations, is the likeliest) | add them one at a time from the Play creator (Add to my game) and tell us which one breaks it |
| **T1 fails** | custom plays made by the editor are not accepted at all | fix that first; Part B still answers the route question |
| **T7: he lines up at the new place** | the game reads the new play's own alignment from the profile, so players can be moved without touching a game file | keep and extend it (also the flipped version, the motion groups) |
| **T7: he lines up where T1 has him, but the diagram shows him moved** | the game takes the on-field alignment from its own sets, not from the profile | the same edit has to be made in the game files: a new test series like Part B |
| **T7: he lines up somewhere else** (mirrored, further back ...) | the yards mean something else than we think | tell us where (yards from the middle and from the line) |
| **T8 or T9: the quarterback just drops back (or does the plain play-action)** | the game does not read the quarterback's move numbers the way we think, or the named option is the plain one under another name | tell us what he did (which way, how far); the names of the options would need a second look |
| **T8 and T9 work** | the quarterback's options can be picked by name | keep going: edit the plays you made, then more options |
| **T1 works, T2/T3 do not** | changing the kind of a play is the problem | tell us which player does what |

## If something goes wrong

- **The Route test says the file is in use:** close RPCS3 (and anything else that has `qkl_boot.ast` or `qkl_fe2ig.ast` open) and press the button again.
- **The game will not start or crashes after a test:** close RPCS3, press **Put the route back to the game's own** (Part B) or **Put my saves back...** (Part A, in the Test plays window), and tell us the test number and what you saw. If the editor itself will not open the files, copy your own copy of the saves back and, for `qkl_boot.ast`, restore `Documents\hc09-game-file-backup\qkl_boot.ast.entry40.orig` with **Restore all to stock** in *Set personnel* (that puts the whole entry back, so it also undoes any Set personnel changes you made).
- **The game will not load the career with the nine test plays in:** Put my saves back, then Add only T1 (see Part A).
- **RPCS3 is running:** the editor refuses to add plays or put saves back while it runs (it rewrites the saves when it closes).
- **The editor says the career has unsaved changes:** save them (Save to File) or throw them away (Reload from File) and press the button again; the editor loads the career again after adding the plays, so it must not hold changes of its own.
