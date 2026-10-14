# HC09 database field reference (from the community config)

Generated from the **HC09 Detailed Config.xml** (made by JHamilton9 in 2020 for the EA Generic DB Editor; shared in the Operation Sports "Head Coach 09 XML config file" thread). It names 383 of the 679 fields it defines, groups them by the screen they appear on, and gives value lists for 48 drop-down fields. The labels are community-written, **not developer-confirmed, and some are wrong** (see TDPB below), so treat a label as a lead to test in-game, not as proof. The raw value lists are in [`hc09_value_lists.json`](hc09_value_lists.json).

## What it independently confirms in this editor

- **Coach position codes (`COPS`)**: the config's list is `0 HC, 1 OC, 2 DC, 3 STC, 4 QBC, 5 RBC, 6 WRC, 7 OLC, 8 LBC, 9 DLC, 10 DBC` - identical to the mapping the editor uses.
- **Coach playbooks (`CPID` / `CDID`)**: the lists have 46 offensive and 43 defensive playbooks, indexed exactly like the playbook list in the game files (a playbook's `BGID` within its side). Confirms where the Playbooks tab reads and writes a team's playbooks.
- **Personality (`PTId`)**: the 17 names and their order match the editor's mapping (the config spells it "Superstar").
- **Names of fields flagged earlier**: `PHGT` Height, `PWGT` Weight, `PCOL` College (with a 297-entry list), `HDAp` Overall Approval, `PLAC/PRAC/PHDC/PLLC/PTRC` body-part health, `PFPB` Pro Bowl, `PJEN` Jersey Number, `PSTY` Throwing Style. `HDAp` is on the **coach table** (and club officials and players' contract view), not on a team table.
- `TMSA` is labelled "Team Salaries".

## Where the config and the editor disagree

| Field | Editor says | Config says | Notes |
|---|---|---|---|
| `PPBS` | Pass Block Power | Pass Block Strength | same meaning, different word (the attribute is `PassBlockPowerRating` in the other lookup sheet) |
| `PPBF` | Pass Block Finesse | Pass Block Footwork | same meaning (`PassBlockFinesseRating`) |
| `PRBF` | Run Block Finesse | Run Block Footwork | same meaning (`RunBlockFinesseRating`) |
| `SKPX` | Play Call Max | Play Call Potential | "potential" = the max of the pair; consistent |
| `SKSM` | Strategy Max | Strategy Potential | consistent |
| `SKCM` | Chemistry Max | Chemistry Potential | consistent |
| `SKPA` | Perf. Input A | Performance Potential | **conflict worth testing**: the editor found Performance = MIN(SKPA, SKPF) in-game; the config calls SKPA "Performance Potential" and SKPF "Performance Current" |
| `SKPF` | Perf. Input B | Performance Current | see SKPA; the editor's in-game tests take priority |
| `TDPB` | not used | "Defense Playbook" | **Label is wrong.** Values are only {0,1,3,4,5,6} and teams with the same scheme share one (the 3-4 teams share 1, the Tampa-2 teams share 3), so it is a scheme family, not a playbook index. A team's real defensive playbook is `COCH.CDID`. |
| `OSPP` | 3 = Spread, 4 = Power Running (checked in game) | 3 = "Speed", 4 = "Power Run" | **Label is wrong** for value 3; see "Checked in the game: Team Philosophy" below |
| `TOPB` | offense, by `PLAB.BORD` | "Offensive Playbook" | Matches the coordinators for 28 of 32 teams; the coaches' `CPID` is the real assignment. |

### Checked in the game: Team Philosophy

Changing the three playcall settings on the game's Team Philosophy screen and saving moved exactly three fields, in the **`TPHS`** table (34 rows, keyed by `TGID`). That table, not the coach rows, is what the screen reads: the same field codes also sit on each coach's `COCH` row, but editing those did not change the screen. (The config files the philosophy fields under a table it calls `TPHL` and names `TPHS` "Team Health"; in a real save the philosophy columns are in `TPHS`. `TPHL` has the same 111-column layout with lower-case names and was not examined.)

| Field | In-game name | Checked values | Config says |
|---|---|---|---|
| `NHPP` | No Huddle Philosophy | 0 Heavily, 1 Balanced, 2 Rarely | same |
| `OPPP` | Offensive Playbook Control | 0 Head Coach, 1 Offensive Coordinator | "Off Call Preference": 0 HC, 1 OC (same meaning, different words) |
| `OSPP` | Offensive Scheme | 0 West Coast Normal, **3 Spread**, **4 Power Running** | 3 is "Speed" - **wrong**; 4 is "Power Run" (wording); 1 and 2 are still the config's names, unchecked |

The editor's **Team Philosophy...** button (Coach tab) edits `TPHS`. Every other name in it is the config's and has not been checked.

The config has no name for 11 fields the editor already edits (`PLJM`, `SKTD`, `SKTM`, `SKNG`, `SKNM`, `TSIE`, `TSIM`, `TSRH`, `TSRM`, `TSFR`, `TSFM`); those come from the editor's own in-game testing.

## Value lists

The number in front of each label is the value stored in the save. Checked against a real save: every stored value in 14 coach fields (`CRPP CBPP DEPP QBPP OSPP DSPP CDTY OPPP DPPP NHPP COPS PTId CFDA CFFA`) falls inside its list, with none outside. Small lists are shown in full; `PNid` (3,585 names), `PCOL` (297 colleges) and the team lists are in the JSON file.

- `CDTY` **Def Philosophy**: 5 3-4; 95 4-3
- `CFDA` **Draft Player**: 0 User; 1 CPU
- `CFDP` **Sign Draft Picks**: 0 User; 1 CPU
- `CFFA` **Sign FAs**: 0 User; 1 CPU
- `CFFR` **Fill Rosters**: 0 User; 1 CPU
- `CFRP` **Re-sign Players**: 0 User; 1 CPU
- `CFRR` **Depth Chart**: 0 User; 1 CPU
- `CFUC` **User Control**: 0 False; 1 True
- `DPPP` **Def Call Preference**: 0 HC; 1 DC
- `OPPP` **Off Call Preference**: 0 HC; 1 OC
- `BZPP` **Blitz Phil**: 0 Heavy; 1 Normal; 2 Light
- `CVPP` **Coverage Phil**: 0 Man; 1 Cover 2; 2 Zone
- `DMPP` **Defining Moment Phil**: 0 Aggressive; 1 Conservative; 2 Balanced
- `DSPP` **Def Scheme**: 0 3-4; 1 4-3; 2 4-6
- `KKPP` **K Phil**: 75 Power; 76 Accuracy; 77 Balanced
- `KPPP` **P Phil**: 78 Power; 79 Accuracy; 80 Balanced
- `NHPP` **No Huddle Phil**: 0 Heavily; 1 Balanced; 2 Rarely
- `FBPP` **FB Phil**: 11 Ball Carrier; 12 Blocking; 13 Receiving; 14 Balanced
- `CBPP` **CB Phil**: 60 Balanced; 61 Man; 62 Strong; 63 Prototype; 64 Cover 2
- `CRPP` **C Phil**: 35 Size; 36 Run Block; 37 Pass Block; 38 Zone Block; 39 Balanced
- `DEPP` **DE Phil**: 40 Balanced; 41 Prototype; 42 Speed; 43 Run Stopper; 44 3-4
- `DTPP` **DT Phil**: 45 Balanced; 46 Prototype; 47 One-Gap; 48 Run Stopper; 49 3-4
- `FSPP` **FS Phil**: 65 Balanced; 66 Man Coverage; 67 Centerfielder; 68 Prototype; 69 Run Support
- `GDPP` **G Phil**: 30 Size; 31 Run Block; 32 Pass Block; 33 Zone Block; 34 Balanced
- `MLPP` **MLB Phil**: 55 Balanced; 56 Coverage; 57 Power; 58 Tackler; 59 Prototype
- `OLPP` **OLB Phil**: 50 Balanced; 51 Cover 2; 52 Run Stopper; 53 3-4 Pass Rush; 54 Prototype
- `OSPP` **Off Scheme**: 0 West Coast Normal; 1 West Coast Heavy Pass; 2 Vertical Passing; 3 Speed (the game shows 3 as Spread); 4 Power Run (the game shows 4 as Power Running)
- `PNPs` **Club Title**: 11 GM; 12 Owner; 13 Trainer; 14 ; 15 
- `QBPP` **QB Phil**: 0 Mobile/Speed; 1 Strong Arm/Tools; 2 Pure Passer; 3 Field General; 4 Balanced
- `SsPP` **SS Phil**: 70 Balanced; 71 Coverage; 72 Prototype; 73 Run Support; 74 Smart
- `TEPP` **TE Phil**: 20 Playmaker; 21 H-Back; 22 Balanced; 23 Soft Hands; 24 Blocking
- `TKPP` **OT Phil**: 25 Size; 26 Run Block; 27 Pass Block; 28 Zone Block; 29 Balanced
- `WRPP` **WR Phil**: 15 Strong; 16 Tall; 17 Speed; 18 Route-Runner; 19 Balanced
- `HBPP` **HB Phil**: 5 Speed; 6 Moves; 7 Power; 8 Receiving; 9 Workhorse; 10 Balanced
- `GDow` **Day of Week**: 0 Thursday; 1 Friday; 2 Saturday; 3 Sunday; 4 Monday; 5 Tuesday; 6 Wednesday
- `PPGR` **Position Group**: 0 QB; 1 RB; 2 WR; 3 TE; 4 OL; 5 DL; 6 LB; 7 DB; 8 K; 9 P
- `COPS` **Position**: 0 HC; 1 OC; 2 DC; 3 STC; 4 QBC; 5 RBC; 6 WRC; 7 OLC; 8 LBC; 9 DLC; 10 DBC
- `PTId` **Personality**: 0 Commander; 1 Superstar; 2 Traditionalist; 3 Loyalist; 4 Guru; 5 Lone Wolf; 6 Ambassador; 7 Promoter; 8 Headliner; 9 Captain; 10 Analyst; 11 Optimist; 12 Stoic; 13 Virtuoso; 14 Anchor; 15 Titan; 16 Ally
- `PPOS` **Position**: 0 QB; 1 HB; 2 FB; 3 WR; 4 TE; 5 LT; 6 LG; 7 C; 8 RG; 9 RT; 10 LE; 11 RE; 12 DT; 13 LOLB; 14 MLB; 15 ROLB; 16 CB; 17 FS; 18 SS; 19 K; 20 P; 21 KR; 22 PR; 23 KOS; 24 LS; 25 3DB
- `GATG` **Away Team** - 40 entries (see JSON)
- `GHTG` **Home Team** - 40 entries (see JSON)
- `TRV1` **Rival 1** - 40 entries (see JSON)
- `TRV2` **Rival 2** - 40 entries (see JSON)
- `TRV3` **Rival 3** - 40 entries (see JSON)
- `CDID` **Defensive Playbook** - 43 entries (see JSON)
- `CPID` **Offensive Playbook** - 46 entries (see JSON)
- `PCOL` **College** - 297 entries (see JSON)
- `PNid` **Non-Player ID** - 3585 entries (see JSON)

## Fields by table and screen

Only fields the config names are listed; `?` marks fields it defines but leaves unnamed.

### COCH - Coach Basics
`CFNM` First Name, `CLNM` Last Name, `CSXP` Portrait ID, `TGID` Team ID, `TOID` Team Official ID, `COPS` Position [11], `CSPC` Coach Specialty, `CFUC` User Control [2], `HDAp` Overall Approval, `CCYT` Yrs w/ this Team, `CSAL` Salary, `CCLN` Contract Length, `CLTF` Last Team, `CAGE` Age, `CETH` Ethics, `CSKI` Skin Color, `CHGT` Height, `PTId` Personality [17], `PNid` Non-Player ID [3585].

### COCH - Gameday Skills
`CFNM` First Name, `CLNM` Last Name, `SKPT` Skill Points, `SKST` Strategy Current, `SKSM` Strategy Potential, `SKPC` Play Call Current, `SKPX` Play Call Potential, `SKPF` Performance Current, `SKPA` Performance Potential, `SKCR` Chemistry Current, `SKCM` Chemistry Potential, `CDVP` Career Current.

### COCH - Planning
`CFNM` First Name, `CLNM` Last Name, `CPID` Offensive Playbook [46], `OSPP` Off Scheme [5], `COTA` CPU Off Playcall Aggress, `CRBT` RB Strat, `OPPP` Off Call Preference [2], `SRHP` Start Young HB, `SRQP` Start Rookie QB, `COTR` Sim Off RunPass Ratio, `CDID` Defensive Playbook [43], `DSPP` Def Scheme [3], `CDTY` Def Philosophy [2], `CDTA` Def Playcall Aggress, `DPPP` Def Call Preference [2], `CDTR` Sim Def RunPass Ratio.

### COCH - Coach Ratings
`CFNM` First Name, `CLNM` Last Name, `CCHM` Chemistry, `CKNW` Knowledge, `CMOT` Motivation, `POVS` Overall Score, `COFF` Coach Offense, `CDEF` Coach Defense, `CRQB` QB Rating, `CRRB` RB Rating, `CRWR` WR Rating, `CROL` OL Rating, `CRDL` DL Rating, `CRLB` LB Rating, `CRDB` DB Rating, `CRKS` K Rating, `CRPS` P Rating.

### COCH - Coach Philosophies
`CFNM` First Name, `CLNM` Last Name, `NHPP` No Huddle Phil [3], `QBPP` QB Phil [5], `HBPP` HB Phil [6], `FBPP` FB Phil [4], `WRPP` WR Phil [5], `TEPP` TE Phil [5], `TKPP` OT Phil [5], `GDPP` G Phil [5], `CRPP` C Phil [5], `BZPP` Blitz Phil [3], `CVPP` Coverage Phil [3], `DEPP` DE Phil [5], `DTPP` DT Phil [5], `OLPP` OLB Phil [5], `MLPP` MLB Phil [5], `CBPP` CB Phil [5], `FSPP` FS Phil [5], `SsPP` SS Phil [5], `KKPP` K Phil [3], `KPPP` P Phil [3], `DMPP` Defining Moment Phil [3].

### COCH - Responsibilities
`CFNM` First Name, `CLNM` Last Name, `CFDA` Draft Player [2], `CFDP` Sign Draft Picks [2], `CFFA` Sign FAs [2], `CFFR` Fill Rosters [2], `CFRP` Re-sign Players [2], `CFRR` Depth Chart [2].

### COCH - Record
`CFNM` First Name, `CLNM` Last Name, `CCWI` Career Wins, `CCLO` Career Losses, `CCTI` Career Ties, `CCWS` Winning Seasons, `CCPM` HC Playoff Appearances, `CCPW` Playoff Wins, `CCPL` Playoff Losses, `CSBW` SB Wins, `CSBL` SB Losses.

### COCH - Coach Unknowns
`CFNM` First Name, `CLNM` Last Name.

Unnamed: `CAAB`, `CCTC`, `CHSD`, `CFRE`, `CAPH`, `DBPH`, `FBPH`, `HBPH`, `LBPH`, `QBPH`, `TEPH`, `DLPH`, `OLPH`, `KPPH`, `WRPH`, `CFSH`, `CFHL`, `CWPL`, `BMCP`, `CRCP`, `DBFP`, `FBFP`, `HBFP`, `LBFP`, `QBFP`, `TEFP`, `DLFP`, `OLFP`, `KPFP`, `WRFP`, `CBMP`, `FBMP`, `HBMP`, `QBMP`, `GDMP`, `DEMP`, `TEMP`, `KKMP`, `TKMP`, `MLMP`, `OLMP`, `KPMP`, `CRMP`, `WRMP`, `FSMP`, `SSMP`, `DTMP`, `BNPP`, `CRRP`, `BPSP`, `IPSP`, `CLTR`, `JOBS`, `DBFS`, `FBFS`, `HBFS`, `LBFS`, `QBFS`, `TEFS`, `DLFS`, `OLFS`, `KPFS`, `WRFS`, `DBHS`, `FBHS`, `HBHS`, `LBHS`, `QBHS`, `TEHS`, `DLHS`, `OLHS`, `KPHS`, `WRHS`, `CTJS`, `CFEX`, `CHTY`, `COTY`, `CBSZ`, `PHRd`, `CThg`, `PNPt`, `PNCw`, `CTgw`

### TEAM - Team Basic Info
`TLNA` Team Location Name, `TDNA` Team Name, `TSNA` Team Short Name, `TMNC` Medium Nickname, `TMSA` Team Salaries, `TGID` Team ID, `TOID` Team Official ID, `FRID` Franchise ID, `TORD` Team Roster Order, `CYID` City ID, `TTYP` Team Type, `LGID` League ID, `CGID` Conference ID, `DGID` Division ID, `TRV1` Rival 1 [40], `TRV2` Rival 2 [40], `TRV3` Rival 3 [40], `TLGL` Team Logo, `TLGS` Secondary Logo, `TBCR` Primary Red, `TBCB` Primary Blue, `TBCG` Primary Green, `TB2R` Secondary Red, `TB2B` Secondary Blue, `TB2G` Secondary Green, `TDAN` Announcer Database.

### TEAM - Team Stadium
`TLNA` Team Location Name, `TDNA` Team Name, `SGID` Stadium ID, `SID1` Stadium Open Roof ID, `TEZ1` End Zone 1, `TEZ2` End Zone 2, `TMFL` Mid-Field Logo, `TAth` Thanksgiving Host, `TAss` Shares Stadium.

### TEAM - Team Off / Def
`TLNA` Team Location Name, `TDNA` Team Name, `TOPB` Offensive Playbook, `TDPB` Defense Playbook, `TROV` Rating Overall, `TROF` Offense Rating, `TRDE` Defense Rating, `TRST` ST Rating, `TRQB` QB Rating, `TRRB` RB Rating, `TWRR` WR Rating, `TROL` OL Rating, `TRDL` DL Rating, `TRLB` LB Rating, `TRDB` DB Rating.

### TEAM - Team Win Record
`TLNA` Team Location Name, `TDNA` Team Name, `DISN` Division Standing, `TPSW` Prior Season Wins, `TPSL` Prior Season Losses, `TPST` Prior Season Ties, `TREP` Team Reputation.

### TEAM - Team Unknowns
`TLNA` Team Location Name, `TDNA` Team Name.

Unnamed: `TLSA`, `TLPB`, `TLSB`, `TLTB`, `TSID`, `TCHE`, `TTSE`, `TLPG`, `TLSG`, `TLTG`, `TFTL`, `TCDO`, `TSHO`, `TUHO`, `TFLO`, `TAUO`, `TCRP`, `TGRP`, `TLPR`, `TLSR`, `TLTR`, `TVIS`, `TVQS`, `TGPT`, `TUAW`, `TSOW`, `TCTX`

### PLAY - Player Info
`TGID` Team ID, `PFNA` Player First Name, `PLNA` Player Last Name, `PGID` Player ID, `POID` Player Original ID, `PSXP` Portrait ID, `PPOS` Position [26], `PBMO` Birth Month, `PBDA` Birth Day, `PAGE` Player Age, `PCOL` College [297], `PHTN` Hometown, `PHSN` Home State, `PPTI` Acquired From, `PDRO` Draft Round, `PDPI` Round Pick, `PFPB` Pro Bowl.

### PLAY - Player Appearance
`PFNA` Player First Name, `PLNA` Player Last Name, `BSAA` Arm Definition, `BSBA` Butt Definition, `BSCA` Calf Definition, `BSFA` Foot Definition, `BSGA` Gut Definition, `BSPA` Pad Definition, `BSSA` Shoulder Definition, `BSTA` Thigh Definition, `BSWA` Waist Definition, `PGID` Player ID, `TGID` Team ID, `POID` Player Original ID, `PGHE` Face, `PUHE` Cyberface, `PCPH` Skin Color, `PSKI` Skin Color ID, `PTAL` Tattoo Left, `PHCL` Hair Color, `PHAN` Preferred Hand, `PTAR` Tattoo Right, `BSAT` Arm Size, `BSBT` Butt Size, `BSCT` Calf Size, `BSFT` Foot Size, `PHGT` Height, `BSGT` Gut Size, `PWGT` Weight, `BSST` Shoulder Size, `BSTT` Thigh Size, `BSWT` Waist Size, `PTId` Personality [17].

### PLAY - Equipment
`PFNA` Player First Name, `PLNA` Player Last Name, `PMPC` Mouthpiece, `PGID` Player ID, `TGID` Team ID, `POID` Player Original ID, `PLHA` Left Hand, `TLHA` Left Hand 2, `PRHA` Right Hand, `TRHA` Right Hand 2, `PBRE` Nasal Strip, `PEYE` Eye Paint, `PLSH` Left Shoe, `PRSH` Right Shoe, `PLTH` Left Knee, `PRTH` Right Knee, `PNEK` Neck Pad, `PFMK` Facemask, `PLEL` Left Elbow 1, `TLEL` Left Elbow 2, `PREL` Right Elbow 1, `TREL` Right Elbow 2, `PSPL` Left Ankle, `PGSL` Arm Sleeves, `PTSL` Arm Sleeves 2, `PHLM` Helmet, `PJEN` Jersey Number, `PLKN` Left Knee, `PRKN` Right Knee, `PJER` Sleeves 3, `PSPR` Right Ankle, `PLWR` Left Wrist, `TLWR` Left Wrist 2, `PRWR` Right Wrist, `TRWR` Right Wrist 2, `PVIS` Visor, `BSPT` Shoulder Pad Size, `PJTY` 1st Initial Jersey.

### PLAY - Player Style
`PFNA` Player First Name, `PLNA` Player Last Name, `PGID` Player ID, `TGID` Team ID, `PCEL` Celebration Chance, `PEPS` Celebration, `PSTY` Throwing Style.

### PLAY - Player Ratings
`PFNA` Player First Name, `PLNA` Player Last Name, `PGID` Player ID, `TGID` Team ID, `PPOS` Position [26], `POPS` Original Position ID, `PTEN` Tendency, `POVR` Overall, `PSPD` Speed, `PSDX` Speed Max, `PAGI` Agility, `PAGX` Agility Max, `PACC` Acceleration, `PACX` Acceleration Max, `PSTR` Strength, `PSTX` Strength Max, `PAWR` Awareness, `PAWX` Awareness Max, `PSTA` Stamina, `PINJ` Injury, `PINX` Injury Max, `PLTR` Trucking, `PLTX` Trucking Max, `PELU` Elusiveness, `PELX` Elusiveness Max, `PBCV` Ball Carrier Vision, `PBCX` Ball Carrier Vision Max, `PLSA` Stiff Arm, `PLSX` Stiff Arm Max, `PLSM` Spin Move, `PLJX` Juke Move Max, `PCAR` Carrying, `PCAX` Carry Max, `PTHP` Throw Power, `PTPX` Throw Power Max, `PTHA` Throw Accuracy, `PTAX` Throw Accuracy Max, `PCTH` Catching, `PCTX` Catch Max, `PLSC` Spectacular Catch, `PSCX` Spectacular Catch Max, `PLCI` Catch in Traffic, `PLCX` Catch in Traffic Max, `PLRR` Route Running, `PRRX` Route Running Max, `PLRL` Release, `PRLX` Release Max, `PJMP` Jumping, `PJMX` Jump Max, `PPBK` Pass Block, `PPBX` Pass Block Max, `PRBK` Run Block, `PRBX` Run Block Max, `PLIB` Impact Block, `PIBX` Impact Block Max, `PRBS` Run Block Strength, `PRSX` Run Block Strength Max, `PRBF` Run Block Footwork, `PRFX` Run Block Footwork Max, `PPBS` Pass Block Strength, `PPSX` Pass Block Strength Max, `PPBF` Pass Block Footwork, `PPFX` Pass Block Footwork Max, `PTAK` Tackling, `PTKX` Tackle Max, `PLHT` Hit Power, `PLHX` Hit Power Max, `PLPm` Power Moves, `PPMX` Power Moves Max, `PFMS` Finesse Moves, `PFMX` Finesse Moves Max, `PBSG` Block Shedding, `PBSX` Block Shedding Max, `PLPU` Pursuit, `PPUX` Pursuit Max, `PLPR` Play Recognition, `PPRX` Play Recognition Max, `PLMC` Man Coverage, `PLMX` Man Coverage Max, `PLZC` Zone Coverage, `PLZX` Zone Coverage Max, `PLPE` Press Coverage, `PKPR` Kick Power, `PKPX` Kick Power Max, `PKAC` Kick Accuracy, `PKAX` Kick Accuracy Max, `PKRT` Kick Return, `PKRX` Kick Return Max, `PLRN` Learning, `PLRX` Learning Max, `PTGH` Toughness, `PTGX` Toughness Max, `PCAF` Fatigue 1, `PSEF` Fatigue 2, `PCUF` Fatigue 3.

Unnamed: `PSAX`, `PSMx`, `PLJM`, `PPEX`, `PRSx`

### PLAY - Contract Info
`PFNA` Player First Name, `PLNA` Player Last Name, `TGID` Team ID, `PCON` Contract Years, `PCYL` Contract Yrs Left, `PTSA` Total Salary, `PSBO` Signing Bonus, `PCSA` Current Salary Total, `PSA0` Salary Year 1, `PSB0` Sign Bonus Year 1, `PSA1` Salary Year 2, `PSB1` Sign Bonus Year 2, `PSA2` Salary Year 3, `PSB2` Sign Bonus Year 3, `PSA3` Salary Year 4, `PSB3` Sign Bonus Year 4, `PSA4` Salary Year 5, `PSB4` Sign Bonus Year 5, `PSA5` Salary Year 6, `PSB5` Sign Bonus Year 6, `PSA6` Salary Year 7, `PSB6` Sign Bonus Year 7, `PVCO` V Contract Years, `PVTS` V Total Salary, `PVSB` V Signing Bonus, `PGID` Player ID, `PROL` Player Role ID, `PIMP` Importance, `PIMX` Importance Max, `PFHO` Holdout, `PMOR` Morale, `PMOX` Morale Max, `PCMT` Comment, `PYWT` Years with Team, `HDAp` Overall Approval.

### PLAY - Player Health
`PFNA` Player First Name, `PLNA` Player Last Name, `PGID` Player ID, `TGID` Team ID, `PHDC` Head Health, `PHDX` Head Health Max, `PLAC` Left Arm Health, `PLAX` Left Arm Health Max, `PRAC` Right Arm Health, `PRAX` Right Arm Health Max, `PTRC` Torso Health, `PTRX` Torso Health Max, `PLLC` Left Leg Health, `PRLc` Right Leg Health, `PRLx` Right Leg Health Max.

Unnamed: `PLLX`

### PLAY - Player Unknowns
`PFNA` Player First Name, `PLNA` Player Last Name.

Unnamed: `PUND`, `PRSE`, `PUCL`, `PSTM`, `PLES`

### GMVW - GMVW
`TGID` Team ID, `CBPP` CB Phil [5], `FBPP` FB Phil [4], `HBPP` HB Phil [6], `QBPP` QB Phil [5], `GDPP` G Phil [5], `DEPP` DE Phil [5], `TEPP` TE Phil [5], `KKPP` K Phil [3], `TKPP` OT Phil [5], `MLPP` MLB Phil [5], `OLPP` OLB Phil [5], `KPPP` P Phil [3], `CRPP` C Phil [5], `WRPP` WR Phil [5], `FSPP` FS Phil [5], `DTPP` DT Phil [5], `SsPP` SS Phil [5], `CDVP` Career Current, `POVS` Overall Score, `SKPT` Skill Points, `PTId` Personality [17], `PNid` Non-Player ID [3585].

Unnamed: `GMAB`, `SKTD`, `SKNG`, `GMPH`, `SKNM`, `SKTM`, `RFAP`, `CRCP`, `ESCP`, `PRDP`, `GTDP`, `TDFP`, `FTGP`, `IWKP`, `CBMP`, `FBMP`, `HBMP`, `QBMP`, `GDMP`, `DEMP`, `TEMP`, `KKMP`, `TKMP`, `MLMP`, `OLMP`, `KPMP`, `CRMP`, `WRMP`, `FSMP`, `GSMP`, `SSMP`, `DTMP`, `CINP`, `GCPP`, `GSPP`, `RSPP`, `TMSP`, `RSSP`, `DFTP`, `GFTP`, `NGTP`, `BTTP`

### TRVW - Trainers
`TGID` Team ID, `CDVP` Career Current, `POVS` Overall Score, `SKPT` Skill Points, `PTId` Personality [17], `PNid` Non-Player ID [3585].

Unnamed: `TRAB`, `TSIE`, `DBPH`, `FBPH`, `HBPH`, `LBPH`, `QBPH`, `TEPH`, `DLPH`, `OLPH`, `KPPH`, `TRPH`, `WRPH`, `TSRH`, `TRCI`, `TRSI`, `TSFM`, `TRGM`, `TSIM`, `TSRM`, `TRSM`, `CRCP`, `DBFP`, `FBFP`, `HBFP`, `LBFP`, `QBFP`, `TEFP`, `DLFP`, `OLFP`, `KPFP`, `WRFP`, `IPSP`, `TSFR`, `DBFS`, `FBFS`, `HBFS`, `LBFS`, `QBFS`, `TEFS`, `DLFS`, `OLFS`, `KPFS`, `WRFS`, `DBHS`, `FBHS`, `HBHS`, `LBHS`, `QBHS`, `TEHS`, `DLHS`, `OLHS`, `KPHS`, `WRHS`

### OWNR - Owners
`PTId` Personality [17], `PNid` Non-Player ID [3585].

Unnamed: `ONAB`, `ONPH`, `DCCP`, `OCCP`, `PCCP`, `TRCP`, `GmCP`

### Club Officials - Club Officials
`TGID` Team ID, `TOID` Team Official ID, `POVS` Overall Score, `HDAp` Overall Approval, `PTId` Personality [17], `PNid` Non-Player ID [3585], `PNFs` First Name, `PNMl` Mid Name, `PNLn` Last Name, `PNPs` Club Title [5], `SKPT` Skill Points.

Unnamed: `PEBS`, `PTJS`, `PSHC`, `PSHT`, `PCYT`, `PHRd`, `PNFe`, `PNAg`, `PNSi`, `PNCt`, `PNHt`, `PNPt`, `PNWt`

### GMSK - GMSK
`PPGR` Position Group [10], `PNid` Non-Player ID [3585].

Unnamed: `SKSC`, `SKRE`, `SKRM`, `SKSX`

### TPHL - Team Philosophies
111 fields (1 named); mostly per-position preference and health tables, see the config.

### TPHS - Team Health
111 fields (29 named); mostly per-position preference and health tables, see the config.

### DCHT - Depth Chart
`TGID` Team ID, `PPOS` Position [26], `ddep` Depth, `PGID` Player ID.

Unnamed: `DCLK`

### INJY - Injuries
`PGID` Player ID, `TGID` Team ID, `INJL` Injury Length, `INIR` Injured Reserve, `INJT` Injury Type.

Unnamed: `IJSK`, `INJR`, `INTT`, `RHBU`, `ITUt`

### DRPP - Draft
`PGID` Player ID, `TGID` Team ID, `PDRO` Draft Round, `PDPI` Round Pick, `DPNM` Overall Pick.

### SCHD - Schedule
`SEYR` Season Year, `SESI` Seasons IN, `SEWN` Week Num, `SGNM` Game Num, `GATG` Away Team [40], `GHTG` Home Team [40], `GDow` Day of Week [7], `GTOD` Time of Day, `SEST` Preseason, `GFTG` Thanksgiving, `GSTA` Playoffs, `SGID` Stadium ID, `SEWT` Weight.

## What could be built next (ranked)

1. **Coach game plan** (built as the **Team Philosophy...** button, on `TPHS` rather than `COCH`; see "Checked in the game" above): offensive scheme `OSPP` (West Coast Normal/Heavy, Vertical Passing, ...), defensive scheme `DSPP` (3-4 / 4-3 / 4-6), `CDTY` defensive philosophy, who calls plays (`OPPP` HC or OC, `DPPP` HC or DC), CPU play-call aggression (`COTA`, `CDTA`), simulated run/pass ratios (`COTR`, `CDTR`), RB strategy `CRBT`, start young HB / rookie QB (`SRHP`, `SRQP`). Every field has a name and most have value lists, so this is an editor that shows words instead of numbers. Needs an in-game check of what each does.
2. **Coach philosophies** (23 fields, each with a short list: QB "Mobile/Speed / Strong Arm/Tools / Pure Passer...", blitz, coverage, no-huddle, kicker, ...).
3. **Who handles what** (`COCH` Responsibilities): User / CPU for drafting, signing draft picks and free agents, filling rosters, re-signing, depth chart (`CFDA`, `CFDP`, `CFFA`, `CFFR`, `CFRP`, `CFRR`), plus `CFUC` User Control.
4. **Player info with names**: College (297-name list), position names, height, weight, home state/town, jersey number, Pro Bowl flag, throwing style, body-part health (all named above).
5. **Names for the cosmetic editor**: the Player Appearance (33 fields), Equipment (38) and Player Style views name the appearance and gear fields the earlier cosmetic-editor idea needs.
6. **Team info**: primary/secondary team colors as RGB (`TBCR/TBCG/TBCB`, `TB2R/TB2G/TB2B`), three rivals (`TRV1-3`, team list), stadium and end-zone/mid-field logos, Thanksgiving host, shared stadium, team reputation `TREP`, prior-season record, team-position ratings `TROV/TROF/TRDE/...` (probably calculated).
7. Club officials, owners and trainers: names and personality, mostly already reachable.

Nothing here has been tested in-game; each item above should be checked on a copy of a save before it is trusted.
