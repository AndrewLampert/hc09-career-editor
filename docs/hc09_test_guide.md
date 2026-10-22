# Testing guide: the Play creator and the route numbers

For people helping to test, on their own copy of the game (PS3 USA in RPCS3). Everything is done from the editor; you never edit a file by hand. **Nothing here has been tried in the game yet, so your answers are the first.**

Two parts. **Part A** tests the custom plays the Play creator makes (about 40 minutes). **Part B** tests what the numbers inside a route mean, which decides whether making your own routes is possible at all (about 40 minutes for the main tests, B1 to B5; B6 to B9 are a bonus). You can do Part A without Part B and the other way round.

## 0. Before you start (10 minutes, once)

1. **Get the newest editor** (the `main` branch of the editor's GitHub page: `git pull` if you cloned it, or download the zip again) and start it with `Start HC09 Editor.bat` (the launcher checks Python and Node and installs what the bridge needs the first time).
2. **Close RPCS3.** Keep it closed whenever you press an Apply or Install button; start it again only to look at the result, and close it again before the next button.
3. **Make your own copy of the saves**, by hand, as well as the editor's automatic backups: copy the whole `BLUS30128-PROFILE-HEADCOACH` folder (in RPCS3's `dev_hdd0/home/00000001/savedata/`) and the folder of the career you will use somewhere safe. The profile is shared by every career and holds all your custom plays, so this copy matters.
4. In the editor, press **Saves...** (or Load Save File) and open the career you will test with. The editor finds the game files by itself; if it asks for `qkl_boot.ast`, point it at the one in RPCS3's `NFL Head Coach 09 (USA)/PS3_GAME/USRDIR` folder.

**What the editor changes, and how to undo it**

| Part | What changes | Backup | Undo |
|---|---|---|---|
| A | your profile save and your career save (the two `USR-DATA` files), only when you press **Install in my game** | `Documents\hc09-test-backups\<date and time>\` (both files, every time) | **Put my saves back** in the same window (all the way back, or one step), or copy your own copies back |
| B | a few numbers of one route in `qkl_boot.ast` (the game's play database), only when you press **Apply this test** | the first time, the original entry in `Documents\hc09-game-file-backup\` | **Put the route back to the game's own** in the Route test window, which restores the numbers exactly (tested byte for byte) |

If anything looks wrong or the game will not start: close RPCS3, press the undo button, and tell us what happened.

## Part A: the custom plays (do these in order)

For each test: make the play in the editor, press **Install in my game**, and look at the result in the game. You can make all of A1 to A4 first (each one is made from your files as they are, so the plays pile up in the same custom playbook), then start the game once and try them all.

**First, make your team use the custom playbook** (otherwise the game never offers the test plays and "it is not in my playbook" would only mean your team plays another one): Playbooks tab, **Team playbooks** box, choose your team, and on the Offense row press **Change...** and pick the custom playbook (1 to 10) you will add the test plays to; then **Save to File**. Use that same custom playbook number below. (Install in my game replaces the career file on disk and loads it again in the editor; it refuses while the open career has unsaved changes, so save first.)

**Setup in the editor:** Playbooks tab, **Play creator...** (a few seconds to read the game's plays). Show: Offense. Find: `slants`. Pick the **Slants** whose formation is **Singleback** and set is **Big**. When you press **Make custom play...** pick a custom playbook (1 to 10) that you do not mind adding to (press Find after the profile path is filled in), keep the suggested output folder, and press **Make the files**, then **Install in my game** and say yes.

| Test | In the Play creator | Name it |
|---|---|---|
| **A1** control | change nothing | `T1 Slants` |
| **A2** play action | **Change the kind of play...**, choose *Play-action pass*, **Change this play to this kind** (it copies a stock play action of the same set) | `T2 Slants PA` |
| **A3** handoff run | start again from Slants, **Change the kind of play...**, *Handoff run* | `T3 Slants Run` |
| **A4** no same-set example | start again from the same Slants (Singleback / Big), **Change the kind of play...**, *Triple option*; the window says its assignments come "from other formations" because no triple option uses that set, which is the case we want to see | `T4 To Triple` |
| **A5** (bonus) one player | start from Slants, click WR1 on the field, **Change what WR1 does...**, pick *Out, medium*, **Use this** | `T5 WR Out` |

**In the game** (RPCS3 started again, your career loaded; any way you normally try custom plays is fine: a career game, or Play Now with your custom playbook if the game lets you): open the offensive playbook, go to the custom playbook, then **Created Plays**. For every test play, answer:

1. Is the play listed, with its name? Does the play diagram look like the original (Slants / the kind you asked for)?
2. Can you call it? Does the game crash or freeze when you do?
3. Run it two or three times. What does each player do?
   - **A1:** like the original Slants?
   - **A2:** does the quarterback turn and fake the handoff, do the linemen fire out as if to run block, does the back fake taking the ball, and do the receivers run their routes and the quarterback throw?
   - **A3:** does the quarterback hand off, does a back take the handoff and run, do the linemen run block, do the receivers block downfield instead of running routes?
   - **A4:** does the quarterback run the option (ride, then keep or pitch), does a back take a pitch? Does anything stand still or run into the wrong place?
   - **A5:** does WR1 run an out route (up the field, then toward the sideline)?
4. Anything odd (players standing still, wrong formation, missing players, strange camera)?

**Write the answers like this** (copy this block into the chat, one per test):

```
A2 Slants PA
 - listed with its name and a matching diagram: yes / no
 - could be called, no crash: yes / no (what happened)
 - QB fakes then throws: yes / no
 - linemen fire out then pass block: yes / no / could not tell
 - back fakes the handoff: yes / no
 - routes run and a pass thrown: yes / no
 - anything odd:
```

When you are done with Part A, close RPCS3 and press **Put my saves back...** in the save window, then **Yes** to get your files from before the first install (if you want to keep the test plays, skip this).

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

**Sending the results:** in the Route test window press **Copy my answers for Discord** and paste into the chat (the answers are also saved in `Documents\hc09-test-results\route-test.json`). Send the Part A blocks as they are. Screenshots of the playbook screen (Created Plays) and of anything odd are welcome.

## What the answers decide

| If we see ... | it means ... | next |
|---|---|---|
| **B1: nothing changed** | the game does not read routes from this file, so the in-place idea cannot work this way | find the copy the game does read (this is the important result; stop here and tell us) |
| **B1: the stem is longer, B6: the second leg is shorter** | the file is read and the first number is a length | measure yards per unit from B0 and B1 (68 against 136) |
| **B2 and B3 break in two different directions** | the second number of a leg is a direction, 32 straight on | the lab can draw a break at any angle: needs a few more points to calibrate |
| **B4 flips the side, B5 changes sharpness** | the cut's numbers are side and sharpness | the lab can build a cut |
| **everything responds as above, and A1 to A3 work** | writing routes in place is possible | we build the route lab (draw a route, match it to the nearest one the game has, give up one of the game's single-use routes only if you insist), with these numbers |
| **B1 works but the numbers behave in no pattern** | the file is read but we cannot yet say how | more tests with a simpler route |
| **A1 fails** | custom plays made by the editor are not accepted at all | fix that first; Part B still answers the route question |
| **A1 works, A2/A3 do not** | changing the kind of a play is the problem | tell us which player does what |

## If something goes wrong

- **The Route test says the file is in use:** close RPCS3 (and anything else that has `qkl_boot.ast` open) and press the button again.
- **The game will not start or crashes after a test:** close RPCS3, press **Put the route back to the game's own** (Part B) or **Put my saves back...** (Part A), and tell us the test number and what you saw. If the editor itself will not open the files, copy your own copy of the saves back and, for `qkl_boot.ast`, restore `Documents\hc09-game-file-backup\qkl_boot.ast.entry40.orig` with **Restore all to stock** in *Set personnel* (that puts the whole entry back, so it also undoes any Set personnel changes you made).
- **RPCS3 is running:** the editor refuses to install or put saves back while it runs (it rewrites the saves when it closes).
