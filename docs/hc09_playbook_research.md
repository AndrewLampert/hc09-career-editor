# Read-only playbook inventory

This is the first, non-destructive step toward understanding the shipped playbooks. It joins the game's master play records to the book-to-play / AI rows. It does not write to an AST archive, profile, or career save.

## 1. Export the master play data

Run from the editor repository root. Close RPCS3 first so the archives are not locked.

```powershell
node .\hc09-bridge\bridge.js play-sets-scan --asts "C:\path\to\qkl_boot.ast,C:\path\to\qkl_fe2ig.ast" --out-dir ".\playbook-research\tables" --tables PBPL,SETL,FORM,PBAI,PLYS,PSLO,PSLD,ARTO,ARTD,PLPD,PLRD,PLCM,SETG,SGFF,PBFM
```

The scanner looks for database entries containing populated `SETP` tables and exports each table it finds. For the known PS3 USA master database, the expected primary prefix is `qkl_boot_40`. Do not assume the same entry numbers on a different regional build or a modified archive: inspect the scan's JSON output and confirm the entry whose `PBPL`, `PBAI`, and `SETL` counts look like the master database.

The separate shipped playbook-name table (`PPPN`) may be in an entry that does not contain `SETP`, so the scan above will not necessarily export it. If its entry has been confirmed for this build, export it separately:

```powershell
node .\hc09-bridge\bridge.js shipped-table-export --ast "C:\path\to\qkl_boot.ast" --top-index 46 --table PPPN --out ".\playbook-research\tables\pppn.csv" --require-fields BOKL,PLYL,PPPM
```

Only use `--top-index 46` if that index is confirmed for the archive being examined. Otherwise omit it and let the bridge locate the table by its fields.

## 2. Build the inventory

```powershell
python .\hc09_playbook_index.py --dir ".\playbook-research\tables" --prefix qkl_boot_40 --pppn ".\playbook-research\tables\pppn.csv" --out ".\playbook-research\index"
```

Outputs:
- `playbook_index.csv`: one row per book/play link, with master name, optional playbook-specific name, formation, set, play type, AI groups and weights.
- `playbooks.json`: the same data grouped by numeric book ID.
- `diagnostics.json`: missing play/set links and duplicate book/play links.

The `PBAI` rows are preserved individually because their AI-group and weight values are useful evidence. They are not collapsed into a single guessed score.

## 3. What to verify before editing

1. Confirm the detected master entry and table counts against the R16 archive, not just a stock HC09 archive.
2. Pick one book ID and compare its exported play list with the corresponding book in the game's UI.
3. Check a play whose playbook-specific name differs from its master `PBPL.name`.
4. Check formation/set joins and all `PBAI` AI-group rows.
5. Compare R16 exports with a clean stock archive to identify exactly which book links, plays, names, and weights the roster patch changed.

Do not edit `PBAI`, `PBPL`, or linked play tables until those checks pass. R16 may retain the same schemas as HC09, but that is a hypothesis to verify against the actual R16 files.
