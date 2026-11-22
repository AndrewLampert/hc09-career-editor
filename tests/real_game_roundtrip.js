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
        const afterDir = path.join(tempRoot, 'after');
        fs.copyFileSync(sourceSave, workingSave);

        const beforeCheck = jsonCommand('verify-db', ['--db', workingSave]);
        if (!beforeCheck.ok) {
            throw new Error('Original save copy failed structural validation: ' + JSON.stringify(beforeCheck.issues));
        }

        const inspect = runBridge('inspect', ['--db', workingSave]);
        const tables = tableNamesFromInspect(inspect);
        fs.mkdirSync(beforeDir);
        fs.mkdirSync(afterDir);

        const tableArg = tables.join(',');
        const exportedBefore = jsonCommand('export', ['--db', workingSave, '--out', beforeDir, '--tables', tableArg]);
        if (!exportedBefore.exported || exportedBefore.exported.length !== tables.length) {
            throw new Error('Not every database table was exported.');
        }

        const imported = jsonCommand('import', ['--db', workingSave, '--in', beforeDir, '--tables', tableArg]);
        const importFailures = (imported.results || []).filter((item) =>
            item.status !== 'ok' || (item.warnings && item.warnings.length));
        if (importFailures.length) {
            throw new Error('Import reported skipped tables or warnings: ' + JSON.stringify(importFailures.slice(0, 10)));
        }

        const afterCheck = jsonCommand('verify-db', ['--db', workingSave]);
        if (!afterCheck.ok) {
            throw new Error('Rewritten save failed structural validation: ' + JSON.stringify(afterCheck.issues));
        }
        const exportedAfter = jsonCommand('export', ['--db', workingSave, '--out', afterDir, '--tables', tableArg]);
        if (!exportedAfter.exported || exportedAfter.exported.length !== tables.length) {
            throw new Error('Not every rewritten database table was exported for comparison.');
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
                rowsReimported: (imported.results || []).reduce((sum, item) => sum + (item.rows || 0), 0),
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
