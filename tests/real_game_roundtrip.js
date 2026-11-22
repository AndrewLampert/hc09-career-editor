#!/usr/bin/env node
'use strict';

// Optional real-file integration check. It never edits the supplied originals:
// a temporary copy of the save is exported, imported unchanged, and verified.
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const { spawnSync } = require('node:child_process');

const root = path.resolve(__dirname, '..');
const bridge = path.join(root, 'hc09-bridge', 'bridge.js');

function argsOf(argv) {
    const args = {};
    for (let i = 0; i < argv.length; i++) {
        if (!argv[i].startsWith('--')) throw new Error('Unexpected argument: ' + argv[i]);
        const key = argv[i].slice(2);
        if (!argv[i + 1] || argv[i + 1].startsWith('--')) {
            args[key] = true;
        } else {
            args[key] = argv[++i];
        }
    }
    return args;
}

function sha256(file) {
    return crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
}

function runBridge(command, args) {
    const result = spawnSync(process.execPath, [bridge, command, ...args], {
        cwd: root,
        encoding: 'utf8',
        maxBuffer: 64 * 1024 * 1024,
        windowsHide: true,
    });
    if (result.error) throw result.error;
    if (result.status !== 0) {
        throw new Error(command + ' failed (' + result.status + '):\n' + (result.stderr || result.stdout));
    }
    return result.stdout.trim();
}

function jsonCommand(command, args) {
    const output = runBridge(command, args);
    try { return JSON.parse(output); }
    catch (error) { throw new Error(command + ' did not return valid JSON: ' + output.slice(0, 2000)); }
}

function tableNamesFromInspect(output) {
    const names = [];
    for (const line of output.split(/\r?\n/)) {
        const match = line.match(/^  ([^:]+): \d+ records, fields:/);
        if (match) names.push(match[1].trim());
    }
    if (!names.length) throw new Error('Could not discover database table names from bridge inspect output.');
    return names;
}

function compareCsvDirectories(before, after) {
    const left = fs.readdirSync(before).filter((name) => name.endsWith('.csv')).sort();
    const right = fs.readdirSync(after).filter((name) => name.endsWith('.csv')).sort();
    if (JSON.stringify(left) !== JSON.stringify(right)) {
        throw new Error('The table list changed after the write/readback cycle.');
    }
    const differences = [];
    for (const name of left) {
        if (!fs.readFileSync(path.join(before, name)).equals(fs.readFileSync(path.join(after, name)))) {
            differences.push(name);
        }
    }
    if (differences.length) {
        throw new Error('Exported table data changed after an unchanged roundtrip: ' + differences.join(', '));
    }
    return left.length;
}

function parseCsv(text) {
    const rows = [];
    let row = [];
    let field = '';
    let quoted = false;
    for (let i = 0; i < text.length; i++) {
        const ch = text[i];
        if (quoted) {
            if (ch === '"' && text[i + 1] === '"') { field += '"'; i++; }
            else if (ch === '"') quoted = false;
            else field += ch;
        } else if (ch === '"' && field.length === 0) quoted = true;
        else if (ch === ',') { row.push(field); field = ''; }
        else if (ch === '\n') { row.push(field.replace(/\r$/, '')); rows.push(row); row = []; field = ''; }
        else field += ch;
    }
    if (field.length || row.length) { row.push(field.replace(/\r$/, '')); rows.push(row); }
    return rows;
}

function csvCell(value) {
    const text = String(value === undefined || value === null ? '' : value);
    return /[",\r\n]/.test(text) ? '"' + text.replace(/"/g, '""') + '"' : text;
}

function writeCsv(file, rows) {
    fs.writeFileSync(file, rows.map((row) => row.map(csvCell).join(',')).join('\r\n') + '\r\n', 'utf8');
}

function findReversibleField(tables, exportDir, workingSave) {
    const excluded = /^(PLYL|BOKL|SETL|SETP|PGID|TGID|SPF_|SGF_|poso)$/i;
    for (const table of tables) {
        let output;
        try { output = runBridge('fields', ['--db', workingSave, '--table', table]); }
        catch (error) { continue; }
        const definitions = new Map();
        for (const line of output.split(/\r?\n/)) {
            const parts = line.split('\t');
            if (parts.length < 4) continue;
            const type = Number((parts[1].match(/type=(\d+)/) || [])[1]);
            const bits = Number((parts[3].match(/bits=(\d+)/) || [])[1]);
            if (type === 3 && bits > 0 && bits <= 16 && !/id$/i.test(parts[0]) && !excluded.test(parts[0])) {
                definitions.set(parts[0], bits);
            }
        }
        const file = path.join(exportDir, table.toLowerCase() + '.csv');
        if (!fs.existsSync(file)) continue;
        const rows = parseCsv(fs.readFileSync(file, 'utf8'));
        if (rows.length < 2) continue;
        const headers = rows[0];
        for (const [field, bits] of definitions) {
            const col = headers.indexOf(field);
            if (col < 0) continue;
            const current = Number(rows[1][col]);
            const max = (2 ** bits) - 1;
            if (!Number.isInteger(current) || current < 0 || current > max) continue;
            const changed = current === 0 ? 1 : current - 1;
            return { table, field, row: 0, col, current: String(current), changed: String(changed), rows };
        }
    }
    throw new Error('No suitable unsigned numeric field (1-16 bits, non-key) was found for the reversible test edit.');
}

function assertOnlyExpectedChange(beforeDir, editedDir, edit) {
    const files = fs.readdirSync(beforeDir).filter((name) => name.endsWith('.csv')).sort();
    const editedFiles = fs.readdirSync(editedDir).filter((name) => name.endsWith('.csv')).sort();
    if (JSON.stringify(files) !== JSON.stringify(editedFiles)) throw new Error('Table list changed during the temporary edit.');
    let differences = 0;
    for (const name of files) {
        const before = parseCsv(fs.readFileSync(path.join(beforeDir, name), 'utf8'));
        const after = parseCsv(fs.readFileSync(path.join(editedDir, name), 'utf8'));
        if (before.length !== after.length) throw new Error('Row count changed unexpectedly in ' + name);
        for (let r = 0; r < before.length; r++) {
            if (before[r].length !== after[r].length) throw new Error('Column count changed unexpectedly in ' + name);
            for (let col = 0; col < before[r].length; col++) {
                const expected = name === edit.table.toLowerCase() + '.csv' && r === edit.row + 1 && col === edit.col
                    ? edit.changed : before[r][col];
                if (after[r][col] !== expected) {
                    throw new Error('Unexpected data change in ' + name + ' row ' + r + ' column ' + col);
                }
                if (after[r][col] !== before[r][col]) differences++;
            }
        }
    }
    if (differences !== 1) throw new Error('Expected exactly one temporary field change; observed ' + differences);
}

function main() {
    const args = argsOf(process.argv.slice(2));
    if (!args.save || args.save === true) {
        throw new Error('Usage: node tests/real_game_roundtrip.js --save <career-save> [--asts <qkl_boot.ast>[,<qkl_fe2ig.ast>]]');
    }
    const sourceSave = path.resolve(args.save);
    if (!fs.existsSync(sourceSave) || !fs.statSync(sourceSave).isFile()) {
        throw new Error('Save file not found: ' + sourceSave);
    }
    if (!fs.existsSync(bridge)) throw new Error('Bridge not found: ' + bridge);

    const originalHash = sha256(sourceSave);
    const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'hc09-real-roundtrip-'));
    try {
        const workingSave = path.join(tempRoot, path.basename(sourceSave));
        const beforeDir = path.join(tempRoot, 'before');
        const editedDir = path.join(tempRoot, 'edited');
        const afterDir = path.join(tempRoot, 'after');
        fs.copyFileSync(sourceSave, workingSave);

        const beforeCheck = jsonCommand('verify-db', ['--db', workingSave]);
        if (!beforeCheck.ok) {
            throw new Error('Original save copy failed structural validation: ' + JSON.stringify(beforeCheck.issues));
        }

        const inspect = runBridge('inspect', ['--db', workingSave]);
        const tables = tableNamesFromInspect(inspect);
        fs.mkdirSync(beforeDir);
        fs.mkdirSync(editedDir);
        fs.mkdirSync(afterDir);

        const tableArg = tables.join(',');
        const exportedBefore = jsonCommand('export', ['--db', workingSave, '--out', beforeDir, '--tables', tableArg]);
        if (!exportedBefore.exported || exportedBefore.exported.length !== tables.length) {
            throw new Error('Not every database table was exported.');
        }

        const edit = findReversibleField(tables, beforeDir, workingSave);
        const editedRows = edit.rows.map((row) => row.slice());
        editedRows[edit.row + 1][edit.col] = edit.changed;
        const editDir = path.join(tempRoot, 'edit-input');
        fs.mkdirSync(editDir);
        writeCsv(path.join(editDir, edit.table.toLowerCase() + '.csv'), editedRows);

        const editedImport = jsonCommand('import', [
            '--db', workingSave, '--in', editDir, '--tables', edit.table,
        ]);
        const editFailures = (editedImport.results || []).filter((item) =>
            item.status !== 'ok' || (item.warnings && item.warnings.length));
        if (editFailures.length) throw new Error('Temporary edit import failed: ' + JSON.stringify(editFailures));

        const editedCheck = jsonCommand('verify-db', ['--db', workingSave]);
        if (!editedCheck.ok) {
            throw new Error('Save failed structural validation after temporary edit: ' + JSON.stringify(editedCheck.issues));
        }
        const editedExport = jsonCommand('export', ['--db', workingSave, '--out', editedDir, '--tables', tableArg]);
        if (!editedExport.exported || editedExport.exported.length !== tables.length) {
            throw new Error('Not every table was exported after the temporary edit.');
        }
        assertOnlyExpectedChange(beforeDir, editedDir, edit);

        // Restore the original exported row in the temporary save, then prove
        // the complete set of table values is back to its starting state.
        const restoredImport = jsonCommand('import', [
            '--db', workingSave, '--in', beforeDir, '--tables', edit.table,
        ]);
        const restoreFailures = (restoredImport.results || []).filter((item) =>
            item.status !== 'ok' || (item.warnings && item.warnings.length));
        if (restoreFailures.length) throw new Error('Temporary edit restore failed: ' + JSON.stringify(restoreFailures));

        const afterCheck = jsonCommand('verify-db', ['--db', workingSave]);
        if (!afterCheck.ok) {
            throw new Error('Restored save failed structural validation: ' + JSON.stringify(afterCheck.issues));
        }
        const exportedAfter = jsonCommand('export', ['--db', workingSave, '--out', afterDir, '--tables', tableArg]);
        if (!exportedAfter.exported || exportedAfter.exported.length !== tables.length) {
            throw new Error('Not every restored table was exported for comparison.');
        }
        const comparedTables = compareCsvDirectories(beforeDir, afterDir);

        if (sha256(sourceSave) !== originalHash) {
            throw new Error('The supplied original save changed; this should never happen.');
        }

        let archiveResult = null;
        if (args.asts) {
            const astPaths = String(args.asts).split(',').map((p) => path.resolve(p.trim()));
            for (const astPath of astPaths) {
                if (!fs.existsSync(astPath) || !fs.statSync(astPath).isFile()) {
                    throw new Error('AST archive not found: ' + astPath);
                }
            }
            const archiveOut = path.join(tempRoot, 'archive-scan');
            archiveResult = jsonCommand('play-sets-scan', [
                '--asts', astPaths.join(','), '--out-dir', archiveOut,
            ]);
            if (!archiveResult.copies || archiveResult.copies.length === 0) {
                throw new Error('The AST archive scan found no populated play-set database entries.');
            }
        }

        console.log(JSON.stringify({
            ok: true,
            save: {
                original: sourceSave,
                originalSha256Unchanged: true,
                helper: beforeCheck.helper || null,
                tables: tables.length,
                tablesCompared: comparedTables,
                reversibleEdit: { table: edit.table, field: edit.field, originalValue: edit.current, temporaryValue: edit.changed, restored: true },
                structureValidBeforeAndAfter: true,
                roundtripDataIdentical: true,
            },
            archives: archiveResult ? {
                filesScanned: String(args.asts).split(',').length,
                populatedPlaySetEntries: archiveResult.copies.length,
            } : null,
            temporaryCopy: 'removed',
        }, null, 2));
    } finally {
        fs.rmSync(tempRoot, { recursive: true, force: true });
    }
}

try {
    main();
} catch (error) {
    console.error('REAL-FILE TEST FAILED: ' + (error.stack || error));
    process.exitCode = 1;
}
