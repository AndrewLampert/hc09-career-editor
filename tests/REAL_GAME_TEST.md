# Real-game file roundtrip test

This is an opt-in integration test for a real NFL Head Coach 09 career save and, optionally, the game's play-data archive. It is deliberately not part of ordinary CI because CI does not contain licensed game files.

## What it does

- Reads the supplied PS3 save or Xenia MC02 save.
- Checks the database structure and discovers every table.
- Exports every table from a temporary copy of the save.
- Finds one unsigned numeric field that is not an obvious key, changes it by one value in the temporary copy, imports it, and checks that exactly that one exported cell changed.
- Restores the original exported table to the temporary save, verifies the database again, and confirms every exported table is byte-for-byte identical to the initial export.
- Confirms the supplied original save's SHA-256 did not change.
- If --asts is supplied, scans the real AST archive(s) for populated play-set database entries. This scan is read-only.

The original save and AST archives are never written. The temporary save and extracted CSVs are deleted when the test finishes.

## Run on Windows

Run from the repository root in PowerShell. Close the game and emulator first so the save/archive files are not being written by another process.

For an RPCS3 PS3 save folder, pass the folder containing USR-DATA. The script locates that file automatically:

\`\`\`powershell
node tests\real_game_roundtrip.js --save "C:\path\to\BLUS30128-CAREER-TEST" --asts "C:\path\to\qkl_boot.ast"
\`\`\`

For a Xenia save:

\`\`\`powershell
node tests\real_game_roundtrip.js --save "C:\path\to\career.mc02" --asts "C:\path\to\qkl_boot.ast"
\`\`\`

To scan both play-data archives, pass both paths as a comma-separated --asts value:

\`\`\`powershell
node tests\real_game_roundtrip.js --save "C:\path\to\BLUS30128-CAREER-TEST" --asts "C:\path\to\qkl_boot.ast,C:\path\to\qkl_fe2ig.ast"
\`\`\`

A successful run prints JSON with ok: true, the save helper type, number of tables checked, the reversible field edit and restore, and the number of populated play-set entries found. A failure prints the exact stage that failed. Do not use a save that is actively being changed by the game.
