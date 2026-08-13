#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');
const zlib = require('zlib');
const DBHelperFactory = require('madden-file-tools/helpers/DBHelperFactory');
const ASTParser = require('madden-file-tools/streams/ASTParser');
const { Readable } = require('stream');

const DEFAULT_TABLES = ['PLAY', 'DRPK', 'SLRI', 'TRVW', 'COCH', 'GMVW', 'GMSK', 'CSKL', 'TEAM', 'cINF'];

function csvEscape(value) {
    if (value === null || value === undefined) return '';
    const s = String(value);
    if (/[",\r\n]/.test(s)) {
        return '"' + s.replace(/"/g, '""') + '"';
    }
    return s;
}

function writeCsv(filePath, headers, rows) {
    const lines = [headers.map(csvEscape).join(',')];
    for (const row of rows) {
        lines.push(headers.map((h) => csvEscape(row[h])).join(','));
    }
    fs.writeFileSync(filePath, lines.join('\r\n') + '\r\n', 'utf8');
}

// Minimal RFC4180 CSV parser (handles quoted fields with , " and newlines)
function parseCsv(text) {
    const rows = [];
    let row = [];
    let field = '';
    let inQuotes = false;
    let i = 0;

    // strip BOM
    if (text.charCodeAt(0) === 0xFEFF) text = text.slice(1);

    while (i < text.length) {
        const c = text[i];

        if (inQuotes) {
            if (c === '"') {
                if (text[i + 1] === '"') {
                    field += '"';
                    i += 2;
                    continue;
                }
                inQuotes = false;
                i++;
                continue;
            }
            field += c;
            i++;
            continue;
        }

        if (c === '"') {
            inQuotes = true;
            i++;
            continue;
        }
        if (c === ',') {
            row.push(field);
            field = '';
            i++;
            continue;
        }
        if (c === '\r') {
            i++;
            continue;
        }
        if (c === '\n') {
            row.push(field);
            field = '';
            rows.push(row);
            row = [];
            i++;
            continue;
        }
        field += c;
        i++;
    }

    if (field.length > 0 || row.length > 0) {
        row.push(field);
        rows.push(row);
    }

    // drop trailing empty row from final newline
    if (rows.length && rows[rows.length - 1].length === 1 && rows[rows.length - 1][0] === '') {
        rows.pop();
    }

    return rows;
}

function tableFileName(tableName) {
    return tableName.toLowerCase() + '.csv';
}

async function openDb(dbPath) {
    const helper = await DBHelperFactory.createHelper(dbPath);
    await helper.load(dbPath);
    return helper;
}

async function cmdInspect(args) {
    const dbPath = args.db;
    const helper = await openDb(dbPath);
    const tableNames = helper.file.tables.map((t) => t.name);
    console.log(`Helper: ${helper.constructor.name}`);
    console.log(`Tables (${tableNames.length}):`);

    for (const name of tableNames) {
        const table = helper.file[name];
        await table.readRecords();
        const fieldNames = table.fieldDefinitions.map((f) => f.name);
        console.log(`  ${name}: ${table.records.length} records, fields: ${fieldNames.join(', ')}`);
    }
}

async function cmdFields(args) {
    const dbPath = args.db;
    const tableName = args.table;
    const helper = await openDb(dbPath);
    const table = helper.file[tableName];
    if (!table) {
        console.error(`No such table: ${tableName}`);
        process.exit(1);
    }
    const defs = table.fieldDefinitions.map((f) => ({
        name: f.name,
        type: f.type,
        offset: f.offset,
        bits: f.bits,
    }));
    defs.sort((a, b) => a.offset - b.offset);
    for (const d of defs) {
        console.log(`${d.name}\ttype=${d.type}\toffset=${d.offset}\tbits=${d.bits}`);
    }
}

async function cmdExport(args) {
    const dbPath = args.db;
    const outDir = args.out;
    const tables = args.tables ? args.tables.split(',') : DEFAULT_TABLES;

    if (!fs.existsSync(outDir)) fs.mkdirSync(outDir, { recursive: true });

    const helper = await openDb(dbPath);
    const availableTables = new Set(helper.file.tables.map((t) => t.name));
    const exported = [];
    const skipped = [];

    for (const tableName of tables) {
        if (!availableTables.has(tableName)) {
            skipped.push(tableName);
            continue;
        }

        const table = helper.file[tableName];
        if (table.records.length === 0) {
            await table.readRecords();
        }

        const headers = table.fieldDefinitions.map((f) => f.name);
        const rows = table.records.map((record) => {
            const obj = {};
            for (const h of headers) {
                const field = record.fields[h];
                obj[h] = field ? field.value : '';
            }
            return obj;
        });

        const outFile = path.join(outDir, tableFileName(tableName));
        writeCsv(outFile, headers, rows);
        exported.push({ table: tableName, file: outFile, records: rows.length });
    }

    console.log(JSON.stringify({ exported, skipped }, null, 2));
}

async function cmdImport(args) {
    const dbPath = args.db;
    const inDir = args.in;
    // Only treat --out as a real "save as" target if it's actually a different
    // path. HC09Helper.save(outputFile) clones _filePath -> outputFile by
    // reading and writing the same stream pipeline; if outputFile === the file
    // we already have open, that clone races a read against the in-place
    // write and corrupts the file. Saving in place must call save(null).
    const outPath = (args.out && path.resolve(args.out) !== path.resolve(dbPath)) ? args.out : null;
    const tables = args.tables ? args.tables.split(',') : DEFAULT_TABLES;

    const helper = await openDb(dbPath);
    const availableTables = new Set(helper.file.tables.map((t) => t.name));
    const results = [];

    for (const tableName of tables) {
        const csvPath = path.join(inDir, tableFileName(tableName));
        if (!fs.existsSync(csvPath)) {
            results.push({ table: tableName, status: 'no-csv-skipped' });
            continue;
        }
        if (!availableTables.has(tableName)) {
            results.push({ table: tableName, status: 'no-such-table-skipped' });
            continue;
        }

        const table = helper.file[tableName];
        if (table.records.length === 0) {
            await table.readRecords();
        }

        const text = fs.readFileSync(csvPath, 'utf8');
        const parsed = parseCsv(text);
        if (parsed.length === 0) {
            results.push({ table: tableName, status: 'empty-csv-skipped' });
            continue;
        }

        const headers = parsed[0];
        const dataRows = parsed.slice(1);
        const records = table.records;

        let updatedRows = 0;
        let updatedFields = 0;
        const warnings = [];

        dataRows.forEach((rowValues, rowIdx) => {
            const record = records[rowIdx];
            if (!record) {
                warnings.push(`row ${rowIdx}: no matching record in table (table has ${records.length} records)`);
                return;
            }

            headers.forEach((colName, colIdx) => {
                const field = record.fields[colName];
                if (!field) {
                    return; // unknown column, ignore
                }

                const csvValue = rowValues[colIdx];
                const currentValue = field.value;

                let newValue;
                if (typeof currentValue === 'number') {
                    if (csvValue === '' || csvValue === undefined) return; // don't blank out numeric fields
                    const n = Number(csvValue);
                    if (Number.isNaN(n)) {
                        warnings.push(`row ${rowIdx} col ${colName}: '${csvValue}' is not numeric, skipped`);
                        return;
                    }
                    newValue = n;
                } else {
                    newValue = csvValue === undefined ? '' : csvValue;
                }

                if (newValue !== currentValue) {
                    field.value = newValue;
                    updatedFields++;
                }
            });

            updatedRows++;
        });

        results.push({ table: tableName, status: 'ok', rows: updatedRows, fieldsChanged: updatedFields, warnings });
    }

    await helper.save(outPath);
    console.log(JSON.stringify({ savedTo: outPath || dbPath, results }, null, 2));
}

// ---------- Portrait extraction (qkl_fe2ig.ast player/coach portraits) ----------
// See docs on the "PSXP" save field: the top-level AST entry (index 1777 for
// player portraits, 1775 for coach/owner portraits) is itself a nested BGFA
// archive of ~3580 headshots, one per shortId. PSXP equals a sub-entry's
// shortId, NOT its storage-order index.

function bufferFromReadable(readable) {
    return new Promise((resolve, reject) => {
        const chunks = [];
        readable.on('data', (c) => chunks.push(c));
        readable.on('end', () => resolve(Buffer.concat(chunks)));
        readable.on('error', reject);
    });
}

// Extract one top-level-index entry's raw bytes from an AST source (either a
// file path to stream from disk, or an in-memory Buffer to re-pipe).
function extractEntry(source, index) {
    return new Promise((resolve, reject) => {
        const parser = new ASTParser();
        let resolved = false;
        parser.on('compressed-file', ({ stream, toc }) => {
            if (toc.index !== index) { stream.resume(); return; }
            resolved = true;
            bufferFromReadable(stream).then(resolve, reject);
        });
        parser.on('error', reject);
        parser.on('end', () => { if (!resolved) reject(new Error(`entry index ${index} not found`)); });
        if (Buffer.isBuffer(source)) {
            const s = new Readable();
            s._read = () => {};
            s.push(source);
            s.push(null);
            s.pipe(parser);
        } else {
            fs.createReadStream(source).pipe(parser);
        }
    });
}

function readToc(source) {
    return new Promise((resolve, reject) => {
        const parser = new ASTParser();
        parser.extract = false;
        parser.on('toc', (tocs) => resolve(tocs));
        parser.on('error', reject);
        if (Buffer.isBuffer(source)) {
            const s = new Readable();
            s._read = () => {};
            s.push(source);
            s.push(null);
            s.pipe(parser);
        } else {
            fs.createReadStream(source).pipe(parser);
        }
    });
}

// One-time (per game install), slow: pulls the ~55MB nested portrait archive
// out of the ~2GB qkl_fe2ig.ast and caches it to --out so later lookups never
// have to touch the multi-GB file again.
async function cmdPortraitExtractArchive(args) {
    const astPath = args.ast;
    const topIndex = parseInt(args['top-index'], 10);
    const outPath = args.out;

    const raw = await extractEntry(astPath, topIndex);
    if (raw.slice(0, 8).toString('latin1') !== 'BGFA1.05') {
        throw new Error(`entry ${topIndex} doesn't look like a nested BGFA archive (bad magic)`);
    }
    fs.writeFileSync(outPath, raw);
    console.log(JSON.stringify({ bytes: raw.length, out: outPath }));
}

// Fast, repeated: looks up one shortId within the already-cached nested
// archive blob, decompresses it (sub-entries are raw zlib-deflate streams),
// and writes the resulting DDS bytes to --out.
async function cmdPortraitLookup(args) {
    const archivePath = args.archive;
    const shortId = parseInt(args.shortid, 10);
    const outPath = args.out;

    const archiveBuf = fs.readFileSync(archivePath);
    const tocs = await readToc(archiveBuf);
    const match = tocs.find((t) => t.shortId === shortId);
    if (!match) {
        console.log(JSON.stringify({ found: false }));
        return;
    }

    const subRaw = await extractEntry(archiveBuf, match.index);
    let ddsBytes = subRaw;
    if (subRaw.slice(0, 2).toString('hex') === '78da') {
        ddsBytes = zlib.inflateSync(subRaw);
    }
    fs.writeFileSync(outPath, ddsBytes);
    console.log(JSON.stringify({ found: true, size: ddsBytes.length, out: outPath }));
}

// Lists every shortId present in a cached archive - lets the picker UI browse
// existing portraits without guessing valid IDs.
async function cmdPortraitList(args) {
    const archivePath = args.archive;
    const archiveBuf = fs.readFileSync(archivePath);
    const tocs = await readToc(archiveBuf);
    const shortIds = tocs.map((t) => t.shortId).sort((a, b) => a - b);
    console.log(JSON.stringify({ shortIds }));
}

function parseArgs(argv) {
    const args = {};
    for (let i = 0; i < argv.length; i++) {
        const a = argv[i];
        if (a.startsWith('--')) {
            const key = a.slice(2);
            const next = argv[i + 1];
            if (next !== undefined && !next.startsWith('--')) {
                args[key] = next;
                i++;
            } else {
                args[key] = true;
            }
        }
    }
    return args;
}

async function main() {
    const [, , cmd, ...rest] = process.argv;
    const args = parseArgs(rest);

    try {
        if (cmd === 'inspect') {
            await cmdInspect(args);
        } else if (cmd === 'fields') {
            await cmdFields(args);
        } else if (cmd === 'export') {
            await cmdExport(args);
        } else if (cmd === 'import') {
            await cmdImport(args);
        } else if (cmd === 'portrait-extract-archive') {
            await cmdPortraitExtractArchive(args);
        } else if (cmd === 'portrait-lookup') {
            await cmdPortraitLookup(args);
        } else if (cmd === 'portrait-list') {
            await cmdPortraitList(args);
        } else {
            console.error('Usage:');
            console.error('  node bridge.js inspect --db <path>');
            console.error('  node bridge.js fields --db <path> --table <name>');
            console.error('  node bridge.js export --db <path> --out <dir> [--tables PLAY,DRPK,...]');
            console.error('  node bridge.js import --db <path> --in <dir> [--out <path>] [--tables PLAY,DRPK,...]');
            console.error('  node bridge.js portrait-extract-archive --ast <path> --top-index <N> --out <path>');
            console.error('  node bridge.js portrait-lookup --archive <path> --shortid <N> --out <path>');
            console.error('  node bridge.js portrait-list --archive <path>');
            process.exit(1);
        }
    } catch (err) {
        console.error('ERROR:', err.stack || err);
        process.exit(1);
    }
}

main();
