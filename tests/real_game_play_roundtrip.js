'use strict';

const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { createReadStream } = require('node:fs');

const bridge = path.join(__dirname, '..', 'hc09-bridge', 'bridge.js');
const TABLES = 'PBPL,PLYL,PLYS,PLPD,PLRD,PLCM,SETP,SETG,SGFF,PBAI,PSLO,ARTO,PSLD,ARTD';

function parseArgs(argv) {
    const out = {};
    for (let i = 0; i < argv.length; i++) {
        if (!argv[i].startsWith('--')) throw new Error('Unexpected argument: ' + argv[i]);
        out[argv[i].slice(2)] = argv[++i];
    }
    return out;
}

function runBridge(args) {
    const result = spawnSync(process.execPath, [bridge, ...args], {
        encoding: 'utf8',
        maxBuffer: 32 * 1024 * 1024,
    });
    if (result.error) throw result.error;
    if (result.status !== 0) {
        throw new Error('bridge ' + args.join(' ') + ' failed:\n' + (result.stderr || result.stdout));
    }
    const output = (result.stdout || '').trim();
    try { return JSON.parse(output); }
    catch (_) { throw new Error('Bridge did not return JSON for ' + args[0] + ': ' + output.slice(0, 1200)); }
}

function parseCsv(text) {
    const rows = [];
    let row = [], value = '', quoted = false;
    for (let i = 0; i < text.length; i++) {
        const ch = text[i];
        if (quoted) {
            if (ch === '"' && text[i + 1] === '"') { value += '"'; i++; }
            else if (ch === '"') quoted = false;
            else value += ch;
        } else if (ch === '"') quoted = true;
        else if (ch === ',') { row.push(value); value = ''; }
        else if (ch === '\n') { row.push(value.replace(/\r$/, '')); rows.push(row); row = []; value = ''; }
        else value += ch;
    }
    if (value.length || row.length) { row.push(value.replace(/\r$/, '')); rows.push(row); }
    if (!rows.length) return [];
    const headers = rows.shift();
    return rows.filter(r => r.length === headers.length).map(r =>
        Object.fromEntries(headers.map((h, i) => [h, r[i]]))
    );
}

function sha256(file) {
    return new Promise((resolve, reject) => {
        const hash = crypto.createHash('sha256');
        const stream = createReadStream(file);
        stream.on('error', reject);
        stream.on('data', chunk => hash.update(chunk));
        stream.on('end', () => resolve(hash.digest('hex')));
    });
}

function csvPath(folder, table, base) {
    return path.join(folder, table.toLowerCase() + '_' + base + '.csv');
}

async function main() {
    const args = parseArgs(process.argv.slice(2));
    if (!args.asts) {
        throw new Error('Usage: node tests/real_game_play_roundtrip.js --asts "C:\\path\\qkl_boot.ast,C:\\path\\qkl_fe2ig.ast"');
    }
    const originals = String(args.asts).split(',').map(p => path.resolve(p.trim()));
    if (originals.length < 2) throw new Error('Pass both qkl_boot.ast and qkl_fe2ig.ast.');
    for (const file of originals) {
        if (!fs.existsSync(file) || !fs.statSync(file).isFile()) throw new Error('AST archive not found: ' + file);
    }
    if (!fs.existsSync(bridge)) throw new Error('Bridge not found: ' + bridge);

    const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'hc09-game-play-roundtrip-'));
    const backupDir = path.join(tempRoot, 'backups');
    const scanDir = path.join(tempRoot, 'scan');
    const editedDir = path.join(tempRoot, 'edited');
    const copies = originals.map((file, i) => {
        const dest = path.join(tempRoot, i + '_' + path.basename(file));
        fs.copyFileSync(file, dest);
        return dest;
    });
    const initialHashes = await Promise.all(copies.map(sha256));
    const configPath = path.join(tempRoot, 'entry-patch.json');
    let applied = false;
    let restored = false;

    try {
        const scan = runBridge([
            'play-sets-scan', '--asts', copies.join(','), '--out-dir', scanDir, '--tables', TABLES,
        ]);
        assert.ok(scan.copies && scan.copies.length, 'No populated play-set database entries were found.');
        const bootCopies = scan.copies.filter(c => path.basename(c.ast).toLowerCase() === 'qkl_boot.ast');
        assert.ok(bootCopies.length, 'The scan did not find a play database in qkl_boot.ast.');
        const master = bootCopies.reduce((best, c) =>
            !best || (c.tables.PLYS || 0) > (best.tables.PLYS || 0) ? c : best, null);
        assert.ok(master.tables && master.tables.PLYS, 'The qkl_boot.ast scan did not find populated PLYS rows.');

        const setpFile = csvPath(scanDir, 'SETP', master.base);
        const setpRows = parseCsv(fs.readFileSync(setpFile, 'utf8'));
        const row = setpRows.find(r =>
            r.SETL !== undefined && r.poso !== undefined && Number.isFinite(Number(r.artx))
        );
        assert.ok(row, 'No editable SETP alignment row was found in the master database.');
        const matches = setpRows.filter(r => r.SETL === row.SETL && r.poso === row.poso);
        assert.equal(matches.length, 1, 'The selected SETP row key is not unique.');
        const before = Number(row.artx);
        const after = before === 32767 ? before - 1 : before + 1;
        const target = {
            ast: master.ast,
            index: master.index,
            start: master.start,
            size: master.size,
            edits: [{
                table: 'SETP',
                match: { SETL: Number(row.SETL), poso: Number(row.poso) },
                expect: { artx: before },
                set: { artx: after },
            }],
        };
        const config = { backupDir, targets: [target] };
        fs.writeFileSync(configPath, JSON.stringify(config, null, 2));

        const dry = runBridge(['entry-patch', 'dry', '--config', configPath]);
        assert.equal(dry.mode, 'dry');
        assert.equal(dry.results.length, 1);

        const appliedResult = runBridge(['entry-patch', 'apply', '--config', configPath]);
        applied = true;
        assert.equal(appliedResult.mode, 'apply');
        assert.equal(appliedResult.results[0].written, true);

        const extracted = path.join(tempRoot, 'patched-entry.db');
        runBridge(['entry-locate', '--ast', master.ast, '--index', String(master.index), '--out', extracted]);
        const exported = runBridge(['export', '--db', extracted, '--out', editedDir, '--tables', 'SETP']);
        assert.equal(exported.exported.length, 1);
        const afterRows = parseCsv(fs.readFileSync(path.join(editedDir, 'setp.csv'), 'utf8'));
        const changed = afterRows.filter(r => r.SETL === row.SETL && r.poso === row.poso);
        assert.equal(changed.length, 1);
        assert.equal(Number(changed[0].artx), after, 'The edited SETP value did not read back.');

        const restoreResult = runBridge(['entry-patch', 'restore', '--config', configPath]);
        restored = true;
        applied = false;
        assert.equal(restoreResult.mode, 'restore');
        assert.equal(restoreResult.results[0].restored, true);

        const finalHashes = await Promise.all(copies.map(sha256));
        assert.deepEqual(finalHashes, initialHashes, 'The temporary AST archives did not return byte-for-byte to their original state.');

        console.log(JSON.stringify({
            ok: true,
            archivesScanned: originals.map(file => path.basename(file)),
            playDatabaseCopiesFound: scan.copies.length,
            testedEntry: { archive: path.basename(master.ast), index: master.index },
            reversibleChange: { table: 'SETP', key: { SETL: row.SETL, poso: row.poso }, field: 'artx', before, temporaryValue: after },
            dryRunPassed: true,
            editedValueReadBack: true,
            restoredByteForByte: true,
            originalArchivesWritten: false,
        }, null, 2));
    } finally {
        if (applied && !restored) {
            try {
                runBridge(['entry-patch', 'restore', '--config', configPath]);
                console.error('The temporary archive entry was restored during cleanup.');
            } catch (error) {
                console.error('Could not restore the temporary archive copy: ' + error.message);
            }
        }
        fs.rmSync(tempRoot, { recursive: true, force: true });
    }
}

main().catch(error => {
    console.error('REAL GAME PLAY ROUNDTRIP FAILED: ' + (error.stack || error));
    process.exitCode = 1;
});
