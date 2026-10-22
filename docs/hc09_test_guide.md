# Testing guide: the Play creator and the route numbers

For people helping to test, on their own copy of the game (PS3 USA in RPCS3). Everything is done from the editor; you never edit a file by hand. **Nothing here has been tried in the game yet, so your answers are the first.**

Two parts. **Part A** tests the custom plays the Play creator makes (about 10 minutes in the editor and then the game; **T7, the moved player, is the one that matters most for what we can build next**). **Part B** tests what the numbers inside a route mean, which decides whether making your own routes is possible at all (about 40 minutes for the main tests, B1 to B5; B6 to B9 are a bonus). You can do Part A without Part B and the other way round.

## 0. Before you start (10 minutes, once)

1. **Get the newest editor** (the `main` branch of the editor's GitHub page: `git pull` if you cloned it, or download the zip again) and start it with `Start HC09 Editor.bat` (the launcher checks Python and Node and installs what the bridge needs the first time).
2. **Close RPCS3.** Keep it closed whenever you press an Add, Apply or Put-back button; start it again only to look at the result, and close it again before the next button.
3. **Make your own copy of the saves**, by hand, as well as the editor's automatic backups: copy the whole `BLUS30128-PROFILE-HEADCOACH` folder (in RPCS3's `dev_hdd0/home/00000001/savedata/`) and the folder of the career you will use somewhere safe. The profile is shared by every career and holds all your custom plays, so this copy matters.
4. In the editor, press **Saves...** (or Load Save File) and open the career you will test with. The editor finds the game files by itself; if it asks for `qkl_boot.ast`, point it at the one in RPCS3's `NFL Head Coach 09 (USA)/PS3_GAME/USRDIR` folder.

**What the editor changes, and how to undo it**

| Part | What changes | Backup | Undo |
|---|---|---|---|
| A | your profile save and your career save (the two `USR-DATA` files), only when you press **Add the seven test plays to my game** (or **Add to my game** in the Play creator) | `Documents\hc09-test-backups\<date and time>\` (both files, every time) | **Put my saves back** in the same window (all the way back, or one step), or copy your own copies back |
| B | a few numbers of one route in `qkl_boot.ast` (the game's play database), only when you press **Apply this test** | the first time, the original entry in `Documents\hc09-game-file-backup\` | **Put the route back to the game's own** in the Route test window, which restores the numbers exactly (tested byte for byte) |

If anything looks wrong or the game will not start: close RPCS3, press the undo button, and tell us what happened.

## Part A: the custom plays (the Test plays window)

One button makes all seven test plays and adds them to your game; you then try them in the game and write down what you saw, in the same window. About 10 minutes in the editor, the rest in the game.

**First, make your team use the custom playbook** (otherwise the game never offers the test plays and "it is not in my playbook" would only mean your team plays another one): Playbooks tab, **Team playbooks** box, choose your team, and on the Offense row press **Change...** and pick a custom playbook (1 to 10); then **Save to File**. The Test plays window says which custom playbook it is going to use: the one your team plays if it plays a custom one, otherwise custom playbook 1 (and then it tells you your team does not play it yet).

**In the editor** (RPCS3 closed, your career loaded):

1. Playbooks tab, **Test plays (testers)...** (a few seconds to read the game's plays).
2. Press **Add the seven test plays to my game** and say yes to the one question. The editor makes the seven plays, checks them, saves your own two files in `Documents\hc09-test-backups` and puts the new ones in place (about a minute). If it says it could not find your profile save, press **Details...** and pick the `USR-DATA` in the `BLUS30128-PROFILE-...` folder.
3. Start RPCS3 and the game, load the career: open the offensive playbook, go to the custom playbook, then **Created Plays**.

**If the game crashes or will not load the career with the seven in** (the editor adds them together, so a crash cannot be pinned on one play): close RPCS3, press **Put my saves back...** and **Yes**, then press **Add only T1 (the control)** and see whether the career loads with that one alone. Tell us which of the two worked.

If you changed your team's playbook in the Playbooks tab while the window was open, the window picks that playbook when you press the button (unless you chose one by hand under **Details...**); the question it asks says which playbook and whether your team plays it. The editor also names the team (the one picked at the top of the editor), so check that it is yours.

The seven plays are copies of **Slants** (formation Singleback, set Big) with one thing changed each, so that what the game does with each kind of change can be told apart:

| Test | What it is | What to look at |
|---|---|---|
| **T1 Slants** | the control: nothing changed | does the game accept a custom play at all? Does it run like the original Slants? Where does WR1, the wide receiver on the right, stand before the snap? (write it down: this is what T7 is compared with) |
| **T2 Slants PA** | changed to a play-action pass | the quarterback turns and fakes the handoff, the linemen fire out as if to run block and then pass block, the back fakes taking the ball, the receivers run their routes and the quarterback throws |
| **T3 Slants Run** | changed to a handoff run | the quarterback hands off, a back takes the ball and runs, the linemen run block, the receivers block downfield instead of running routes |
| **T4 To Triple** | changed to a triple option (no triple option uses this set, so the assignments come from other formations) | the quarterback runs the option (rides, then keeps or pitches), a back takes a pitch; does anything stand still or run into the wrong place? |
| **T5 WR Out** | one receiver's route: WR1 runs an out, medium | WR1 runs up the field, then toward the sideline |
| **T6 Reads** | the quarterback's reads: WR1 first, TE1 second | on the play's diagram in the playbook the numbers 1 to 5 stand on the receivers in that order; with no pressure the quarterback looks to WR1 first |
| **T7 Moved WR** (important) | one player's place: WR1 stands 7 yards from the middle instead of out by the sideline | before the snap WR1 stands about 7 yards from the middle of the field (near the hash marks, inside the numbers); the diagram shows him moved; if the game flips plays, the whole formation is the mirror image. **This is the one that matters most for what we can build next.** |

**In the game**, for every test play: is it listed, with its name and a diagram that looks like the original? Can you call it without the game crashing or freezing? Run it two or three times and look at what the table says. Anything odd (players standing still, wrong formation, missing players, strange camera)?

**Write the answers in the window** (step 2 of the Test plays window): pick a test in the list and answer its questions with the drop-downs and the text lines. The answers are saved as you give them, so closing the editor loses nothing. When you are done press **Copy my answers for Discord** and paste into the chat (or **Save my answers to a file**: `Documents\hc09-test-results\play-test-results.txt`; the state is in `play-test.json` in the same folder). Screenshots of the playbook screen (Created Plays) and of anything odd are welcome.

When you are done, close RPCS3 and press **Put my saves back...** in the Test plays window, then **Yes** to get your files from before the first install (if you want to keep the test plays, skip this).

**Making one play by hand** (not part of the test): Playbooks tab, **Play creator...**, pick a play, change what you like, press **Make custom play...** and then **Add to my game** (one question; the same backups and the same Put my saves back). **Details...** has the files, the output folder and the playbook if you want to choose them yourself, and **Only make the files** makes the two copies without changing your game.

## Part B: the route numbers (the Route test window)

**Why:** a route is a short list of steps: `8(68,32,254) 9(2,1,0) 8(200,42,254) 10` means *run a leg, cut, run a leg, finish*. We do not know what the numbers mean (how far, which way, which side), and we do not know whether the game reads the file the editor can change. If we know both, the editor could one day let you build a route; if the game ignores the edit, that idea is dead and we must look elsewhere. Seven simple tests settle it.

**How:** Playbooks tab, **Route test (testers)...**. The window changes **one route** (the *Post* that *WR Post*, *FL Post*, *Cross Up* and others use; it is used by 58 receivers in 42 of the game's playbooks) one number at a time and tells you, for each test, what to look at.

**Which receiver to watch.** Several receivers run deep breaking routes in the same play, and only the one who runs this route changes. In the plays with the most playbooks it is:

| Play (set, formation) | the receiver |
|---|---|
| FL Post (Normal, I Form) | WR1, wide on the right |
| Cross Up (Normal Slot, Singleback) | WR1, wide on the right |
| Panther Cross (4WR, Shotgun) | WR1, wide on the right |
| WR Option (Slot Strong, Singleback) | WR3, wide on the right |
| Play Action (Normal, I Form) | WR1, wide on the right |
| WR Post (Normal, I Form) | WR1, wide on the right |

(The window prints this list for your own copy of the game, with the playbooks that have each play.) **If a test seems to change nothing, check B0 and that test again with a second play from the list before you report "no change"**; a receiver you did not watch is the usual reason. For every test:

1. Close RPCS3. Select the test in the list and press **1. Apply this test**.
2. Start the game and a quick game (**Play Now**) with a team whose playbook has one of the plays the window lists (WR Post, FL Post, Cross Up ... most playbooks have one; if yours has none, choose another team). On offense, call the play.
3. Run it three or four times and watch the receiver named in the list above for that play (the one with the long run up the field and a break). The replay helps. **Count yards using the field's yard lines: how many yards past the line of scrimmage does he run before he breaks?** Which way does he break? How far does he run after the break?
4. Close the game, fill in the form in the window (**2. Your answer**) and press **Save my answer**. It keeps your answers even if you close the editor.

**The order** (the window shows the same list):

| Test | What it changes | What we learn |
|---|---|---|
| **B0** | nothing (the control) | how the stock route runs: stem depth, break direction, run after the break. Do this first, it is what the others are compared with. |
| **B1** | the stem's first number 68 to **136** | **does the game read the edited file at all, and is that number a length?** If the receiver runs about twice as far before he breaks: yes to both. If nothing is different: no. Tell us right away. |
| **B2** | the second leg's second number 42 to **16** | is it a direction? which way does the break turn? |
| **B3** | the same number 42 to **64** | which way do bigger numbers turn it (opposite to B2?) |
| **B4** | the cut's first number 2 to **1** | does it turn the cut to the other side? |
| **B5** | the cut's second number 1 to **5** | sharper, rounder, a different angle, a stop first? |
| **B6 to B9** (bonus) | second leg's length 200 to 60; stem heading 32 to 16; third number 254 to 127; cut second number 1 to 2 | more of the same questions |
| **B10** | nothing (the control again) | **did Put the route back work?** The route should run exactly as in B0. Press *Put the route back to the game's own* before this test. |

Measure in yards as well as you can; "about twice as far", "turned toward the middle at about 45 degrees" are good answers. If you cannot tell, say so. A short video of B0, B1 and B3 (the receiver and the yard lines) helps a lot if you can make one; it is optional.

**Sending the results:** in the Route test window press **Copy my answers for Discord** and paste into the chat (the answers are also saved in `Documents\hc09-test-results\route-test.json`). Screenshots of the playbook screen (Created Plays) and of anything odd are welcome.

## What the answers decide

| If we see ... | it means ... | next |
|---|---|---|
| **B1: nothing changed** | the game does not read routes from this file, so the in-place idea cannot work this way | find the copy the game does read (this is the important result; stop here and tell us) |
| **B1: the stem is longer, B6: the second leg is shorter** | the file is read and the first number is a length | measure yards per unit from B0 and B1 (68 against 136) |
| **B2 and B3 break in two different directions** | the second number of a leg is a direction, 32 straight on | the lab can draw a break at any angle: needs a few more points to calibrate |
| **B4 flips the side, B5 changes sharpness** | the cut's numbers are side and sharpness | the lab can build a cut |
| **everything responds as above, and T1 to T3 work** | writing routes in place is possible | we build the route lab (draw a route, match it to the nearest one the game has, give up one of the game's single-use routes only if you insist), with these numbers |
| **B1 works but the numbers behave in no pattern** | the file is read but we cannot yet say how | more tests with a simpler route |
| **the game will not load the career with all seven, but loads it with T1 alone** | one of T2 to T7 breaks the game (T4, with assignments from other formations, is the likeliest) | add them one at a time from the Play creator (Add to my game) and tell us which one breaks it |
| **T1 fails** | custom plays made by the editor are not accepted at all | fix that first; Part B still answers the route question |
| **T7: he lines up at the new place** | the game reads the new play's own alignment from the profile, so players can be moved without touching a game file | keep and extend it (also the flipped version, the motion groups) |
| **T7: he lines up where T1 has him, but the diagram shows him moved** | the game takes the on-field alignment from its own sets, not from the profile | the same edit has to be made in the game files: a new test series like Part B |
| **T7: he lines up somewhere else** (mirrored, further back ...) | the yards mean something else than we think | tell us where (yards from the middle and from the line) |
| **T1 works, T2/T3 do not** | changing the kind of a play is the problem | tell us which player does what |

## If something goes wrong

- **The Route test says the file is in use:** close RPCS3 (and anything else that has `qkl_boot.ast` open) and press the button again.
- **The game will not start or crashes after a test:** close RPCS3, press **Put the route back to the game's own** (Part B) or **Put my saves back...** (Part A, in the Test plays window), and tell us the test number and what you saw. If the editor itself will not open the files, copy your own copy of the saves back and, for `qkl_boot.ast`, restore `Documents\hc09-game-file-backup\qkl_boot.ast.entry40.orig` with **Restore all to stock** in *Set personnel* (that puts the whole entry back, so it also undoes any Set personnel changes you made).
- **The game will not load the career with the seven test plays in:** Put my saves back, then Add only T1 (see Part A).
- **RPCS3 is running:** the editor refuses to add plays or put saves back while it runs (it rewrites the saves when it closes).
- **The editor says the career has unsaved changes:** save them (Save to File) or throw them away (Reload from File) and press the button again; the editor loads the career again after adding the plays, so it must not hold changes of its own.
