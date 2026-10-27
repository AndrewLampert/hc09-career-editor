#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');
const zlib = require('zlib');
const crypto = require('crypto');
const os = require('os');
// The libraries the bridge needs (madden-file-tools and what it uses) are shipped in vendor/node_modules, so no `npm install`, no internet and no compiler are needed.
// They are looked up there first. See vendor/README.md.
const vendorDir = path.join(__dirname, 'vendor', 'node_modules');
if (fs.existsSync(vendorDir)) module.paths.unshift(vendorDir);
const DBHelperFactory = require('madden-file-tools/helpers/DBHelperFactory');
const HC09Helper = require('madden-file-tools/helpers/HC09Helper');
const TDBParser = require('madden-file-tools/streams/TDBParser');
const ASTParser = require('madden-file-tools/streams/ASTParser');
const { Readable } = require('stream');

const DEFAULT_TABLES = ['PLAY', 'DRPK', 'SLRI', 'TRVW', 'COCH', 'GMVW', 'GMSK', 'CSKL', 'TEAM', 'cINF', 'TPHS', 'PSSK'];

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

// ---------- Xbox 360 / Xenia saves ----------
// A save made on the Xbox 360 (Xenia keeps it as an ordinary file, usually named *.mc02) is wrapped in the game's own "MC02" memory-card container: the letters MC02, a 28-byte
// header whose 32-bit big-endian value at offset 8 is the length of a metadata chunk that follows it, then the database (it starts with "DB"). The database therefore starts at
// 28 + that length. This is the rule of the community's MC02 <-> DB converter. The header and the chunk are never changed: the database is read and written in place, exactly as
// the PS3 career save's own header is (HC09Helper), so a made file keeps its size.
const MC02_MAGIC = 'MC02';
const MC02_HEADER_SIZE = 28;
const TDB_SIGNATURE = Buffer.from([0x44, 0x42, 0x00, 0x08, 0x01, 0x00, 0x00, 0x00]);      // how the databases of this game start

// Where the database starts inside an MC02 file, -1 when the file is not MC02, or throws when it is MC02 and holds no database.
function mc02DataStart(filePath) {
    const fd = fs.openSync(filePath, 'r');
    try {
        const head = Buffer.alloc(12);
        if (fs.readSync(fd, head, 0, 12, 0) < 12 || head.toString('latin1', 0, 4) !== MC02_MAGIC) return -1;
        const size = fs.fstatSync(fd).size;
        const start = MC02_HEADER_SIZE + head.readUInt32BE(8);
        const mark = Buffer.alloc(2);
        if (start + 2 <= size && fs.readSync(fd, mark, 0, 2, start) === 2 && mark.readUInt16BE(0) === 0x4442) return start;
        // the header does not point at a database: look for where one starts (the converter falls back to the first "DB" too)
        const all = fs.readFileSync(filePath);
        const found = all.indexOf(TDB_SIGNATURE);
        if (found >= 0) return found;
        throw new Error('This is an MC02 file (an Xbox 360 / Xenia save) but no database was found in it.');
    } finally {
        fs.closeSync(fd);
    }
}

class MC02Helper extends HC09Helper {
    load(filePath) {
        this._filePath = filePath;
        this._dataStart = mc02DataStart(filePath);
        return new Promise((resolve, reject) => {
            const stream = fs.createReadStream(filePath, { start: this._dataStart });
            this._parser = new TDBParser();
            stream.on('error', reject);
            stream.on('end', () => {
                this._file = this._parser.file;
                resolve(this._file);
            });
            stream.pipe(this._parser);
        });
    }
}

async function openDb(dbPath) {
    const helper = mc02DataStart(dbPath) >= 0 ? new MC02Helper() : await DBHelperFactory.createHelper(dbPath);
    await helper.load(dbPath);
    return helper;
}

// Table header layout (see madden-file-tools' TDBParser): bytes 0-3 prior-table
// CRC, 20-21 maxRecords, 22-23 currentRecords, 36-39 header CRC, where the
// header CRC is ~crc32_be over bytes 4..0x24. Checked against all 208 tables of
// a real save, so a table whose row count is changed can have its header CRC
// recomputed exactly.
const TDBCRC = require('madden-file-tools/services/CRC');
const tdbUtil = require('madden-file-tools/services/utilService');
const tdbCrc = new TDBCRC();
const crcOf = (buf) => tdbUtil.toUint32(~tdbCrc.crc32_be(0, buf, buf.length));
const emptyBuf = Buffer.alloc(0);

function rewriteHeaderCrc(table) {
    const hb = table.headerBuffer;
    hb.writeUInt32BE(crcOf(hb.slice(4, 0x24)), 0x24);
}

// Structural self-check of an opened DB: every table header checksum, the
// prior-CRC chain between consecutive tables, the end-of-file checksum and
// row counts within capacity. A save we wrote that fails this is not safe to
// hand to the game.
// The file header of a game database entry holds the entry's own size (bytes 8-11) and a checksum of the first 0x14 bytes (at 0x14). The library's writer does not keep the size right after a
// table has changed its length (a rename in a compressed string table, a grown table): the stock entries of the play databases all have size == length, so every entry this bridge writes gets
// the real length and a matching checksum.
function fixDbHeader(buf) {
    buf.writeUInt32BE(buf.length, 8);
    buf.writeUInt32BE(crcOf(buf.slice(0, 0x14)), 0x14);
    return buf;
}
function dbHeaderIsConsistent(buf) {
    return buf.readUInt32BE(8) === buf.length && crcOf(buf.slice(0, 0x14)) === buf.readUInt32BE(0x14);
}
function verifyDbStructure(helper) {
    const tables = helper.file.tables;
    const issues = [];
    tables.forEach((t, i) => {
        const hb = t.headerBuffer;
        if (!hb) return;
        if (crcOf(hb.slice(4, 0x24)) !== hb.readUInt32BE(0x24)) issues.push(`header checksum wrong: ${t.name}`);
        if (t.header.currentRecords > t.header.maxRecords) issues.push(`more rows than capacity: ${t.name}`);
        if (i > 0) {
            const prev = tables[i - 1];
            const expected = crcOf(Buffer.concat([prev.fieldDefinitionBuffer || emptyBuf, prev.dataBuffer || emptyBuf]));
            if (expected !== hb.readUInt32BE(0)) issues.push(`checksum chain broken: ${prev.name} -> ${t.name}`);
        }
    });
    const last = tables[tables.length - 1];
    const eof = crcOf(Buffer.concat([last.fieldDefinitionBuffer || emptyBuf, last.dataBuffer || emptyBuf]));
    if (eof !== helper.file.eofCrcBuffer.readUInt32BE(0)) issues.push('end-of-file checksum wrong');
    return issues;
}

async function cmdVerifyDb(args) {
    const helper = await openDb(args.db);
    const issues = verifyDbStructure(helper);
    console.log(JSON.stringify({ ok: issues.length === 0, tables: helper.file.tables.length, issues }));
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
    // Tables the CSV may GROW (rows beyond what the save has are written into
    // the table's spare allocated slots). Anything not listed here keeps the old
    // strictly-position-matched behaviour, so an ordinary save can never append.
    const appendTables = new Set(args['allow-append'] ? String(args['allow-append']).split(',') : []);
    const shrinkTables = new Set(args['allow-shrink'] ? String(args['allow-shrink']).split(',') : []);       // tables that may end up with FEWER rows than the save has (links taken out)

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
        let records = table.records;

        let updatedRows = 0;
        let updatedFields = 0;
        let appendedRows = 0;
        const warnings = [];

        if (appendTables.has(tableName) && dataRows.length > records.length) {
            const max = table.header.maxRecords;
            if (dataRows.length > max || table._records.length < dataRows.length) {
                // Refuse the whole table rather than write a partial/over-capacity one.
                results.push({
                    table: tableName, status: 'append-over-capacity-skipped', rows: 0, fieldsChanged: 0,
                    warnings: [`CSV has ${dataRows.length} rows but the table can hold ${Math.min(max, table._records.length)}`],
                });
                continue;
            }
            appendedRows = dataRows.length - records.length;
            for (let i = records.length; i < dataRows.length; i++) {
                // The spare slots hold leftover memory, not zeros (including the bits no field covers). The game's own
                // new rows are all zero, so start from that and let the fields below fill the row.
                table._records[i].recordBuffer.fill(0);
                table._records[i].isPopulated = true;
            }
            table.header.currentRecords = dataRows.length;
            table.headerBuffer.writeUInt16BE(dataRows.length, 22);
            rewriteHeaderCrc(table);
            records = table.records;
        }

        if (shrinkTables.has(tableName) && dataRows.length < records.length) {
            // Rows taken out: the table keeps its capacity and its first rows, the count goes down and the freed rows are zeroed (the CSV holds the rows that stay, in order).
            for (let i = dataRows.length; i < table._records.length; i++) {
                table._records[i].recordBuffer.fill(0);
                table._records[i].isPopulated = false;
            }
            appendedRows = dataRows.length - records.length;                       // negative: how many rows went
            table.header.currentRecords = dataRows.length;
            table.headerBuffer.writeUInt16BE(dataRows.length, 22);
            rewriteHeaderCrc(table);
            records = table.records;
        }

        // Rows are matched to records by pure position (see cmdImport's own
        // docs) - if this table has an identity-looking column (PGID, PNid,
        // TGID, etc.), catch the common case of a reordered/resorted CSV by
        // comparing its value against what's already stored at that position
        // BEFORE any fields get overwritten.
        const idColIdx = headers.findIndex((h) => /id$/i.test(h));

        dataRows.forEach((rowValues, rowIdx) => {
            const record = records[rowIdx];
            if (!record) {
                warnings.push(`row ${rowIdx}: no matching record in table (table has ${records.length} records)`);
                return;
            }

            if (idColIdx !== -1) {
                const idColName = headers[idColIdx];
                const idField = record.fields[idColName];
                if (idField && String(idField.value) !== String(rowValues[idColIdx])) {
                    warnings.push(
                        `row ${rowIdx}: ${idColName} in the CSV (${rowValues[idColIdx]}) doesn't match the record ` +
                        `currently at that position (${idField.value}) - this row's edits may be landing on the ` +
                        `wrong record if the CSV was reordered before importing`
                    );
                }
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
                    const maxValue = field.definition && field.definition.maxValue;
                    if (typeof maxValue === 'number' && (n < 0 || n > maxValue)) {
                        warnings.push(`row ${rowIdx} col ${colName}: ${n} is out of range (0-${maxValue} for this field), skipped`);
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

        results.push({ table: tableName, status: 'ok', rows: updatedRows, fieldsChanged: updatedFields, appendedRows, warnings });
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
        let fileStream = null;
        // Resolving on a match without tearing anything down leaves the
        // parser (and, for a file source, the underlying read) running in
        // the background for the rest of the archive even though nothing is
        // listening anymore - confirmed via direct measurement: on a 344MB
        // archive, resolving after reading just the first ~8% still went on
        // to read the other ~92% afterward. That's wasted on every call,
        // and worst on the ~2GB portrait archive this also extracts from.
        parser.on('compressed-file', ({ stream, toc }) => {
            if (toc.index !== index) { stream.resume(); return; }
            resolved = true;
            bufferFromReadable(stream).then((buf) => {
                resolve(buf);
                parser.destroy();
                if (fileStream) fileStream.destroy();
            }, reject);
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
            fileStream = fs.createReadStream(source);
            fileStream.pipe(parser);
        }
    });
}

function readToc(source) {
    return new Promise((resolve, reject) => {
        const parser = new ASTParser();
        parser.extract = false;
        let fileStream = null;
        // The 'toc' event fires as soon as the parser has read the archive's
        // table of contents, well before it has streamed the rest of the
        // (possibly huge) file. Resolving here without tearing anything down
        // would leave that read running in the background for no reason -
        // destroy both ends once we have what we came for.
        parser.on('toc', (tocs) => {
            resolve(tocs);
            parser.destroy();
            if (fileStream) fileStream.destroy();
        });
        parser.on('error', reject);
        if (Buffer.isBuffer(source)) {
            const s = new Readable();
            s._read = () => {};
            s.push(source);
            s.push(null);
            s.pipe(parser);
        } else {
            fileStream = fs.createReadStream(source);
            fileStream.pipe(parser);
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

// ---------- Game-shipped DB extraction (qkl_boot.ast) ----------
// On the PS3 release, qkl_boot.ast's top-level entry 46 is a full EA DB file
// (716 tables, a superset of the save's). That index is PS3-specific -
// other platforms/rips pack the archive's entries in a different order, so
// entry 46 there can be something else entirely (confirmed: a Xbox 360 rip
// throws "table PLYT not found in entry 46" - a valid DB was extracted, just
// not the right one). Rather than trust a hardcoded index, this streams
// through the whole archive ONCE, trying each entry in turn as a candidate
// DB, and stops at the first one that both opens as a DB and actually
// contains the requested table. --top-index, if given, is tried first as a
// shortcut (fast path when it's already known to be correct) but is no
// longer required.
// Streams the AST once, testing each top-level entry against tableName.
// Returns { index, helper } for the first hit. Completion is driven by
// having processed every entry the TOC says exists (fetched up front via a
// separate, cheap readToc pass) rather than the parser's own 'end' event -
// in practice that event doesn't reliably fire once the very last entry has
// been streamed, which would otherwise leave this hanging forever on a
// genuine not-found case instead of failing with a clear error.
// An entry qualifies when it holds every requested table (with rows, if requireRows) and, if requireFields
// is given, each of those tables has all of those fields. The field check
// matters because two entries can carry a table of the same name with
// different columns (e.g. PLAB, the playbook name list, exists in two entries
// but only one has the PBGI playbook-ID column).
async function entryHasTables(helper, tableNames, requireFields, requireRows) {
    for (const name of tableNames) {
        if (!helper.file.tables.some((t) => t.name === name)) return false;
        if (requireFields.length) {
            const have = helper.file[name].fieldDefinitions.map((f) => f.name);
            if (!requireFields.every((f) => have.includes(f))) return false;
        }
        if (requireRows) {
            // Some entries carry an empty copy of a table with the same columns
            // (the real PLAB playbook list has 89 rows; another entry's has none).
            await helper.file[name].readRecords();
            if (!helper.file[name].records.length) return false;
        }
    }
    return true;
}

async function findShippedTableEntry(astPath, tableNames, requireFields, requireRows) {
    const totalEntries = (await readToc(astPath)).length;

    return new Promise((resolve, reject) => {
        const parser = new ASTParser();
        let settled = false;
        let pending = Promise.resolve();
        let processedCount = 0;

        const finish = (err, result) => {
            if (settled) return;
            settled = true;
            if (err) reject(err); else resolve(result);
            parser.destroy();
        };

        // Each candidate entry gets written to its own temp file only long
        // enough for openDb() to load it - deleted immediately afterward
        // (win or lose) rather than accumulating every checked entry's bytes
        // in the temp dir for the whole scan. Safe to delete right away:
        // the DB helper reads everything it needs during load(), not lazily
        // from disk when readRecords() is called later.
        const checkEntry = (index, rawBuf) => {
            const tmpPath = path.join(
                require('os').tmpdir(),
                `hc09_shipped_db_${process.pid}_${index}_${Math.random().toString(36).slice(2)}.db`,
            );
            fs.writeFileSync(tmpPath, rawBuf);
            return openDb(tmpPath)
                .then(async (helper) => ((await entryHasTables(helper, tableNames, requireFields, requireRows)) ? helper : null))
                .catch(() => null)
                .finally(() => {
                    try { fs.unlinkSync(tmpPath); } catch (e) { /* best effort */ }
                });
        };

        const wanted = tableNames.join('+');
        parser.on('compressed-file', ({ stream, toc }) => {
            if (settled) { stream.resume(); return; }
            const index = toc.index;
            pending = pending.then(async () => {
                if (settled) { stream.resume(); return; }
                const rawBuf = await bufferFromReadable(stream);
                if (settled) return;
                const helper = await checkEntry(index, rawBuf);
                processedCount++;
                if (helper) {
                    finish(null, { index, helper });
                } else if (processedCount >= totalEntries) {
                    finish(new Error(`table ${wanted} not found in any of ${totalEntries} entries of ${path.basename(astPath)}`));
                }
            }).catch((e) => finish(e));
        });
        parser.on('error', (e) => finish(e));
        parser.on('end', () => {
            // Usually redundant with the processedCount check above, but kept
            // as a safety net in case totalEntries and the live entry count
            // ever disagree (e.g. a differently-structured archive).
            pending.finally(() => {
                if (!settled) {
                    finish(new Error(`table ${wanted} not found in any entry of ${path.basename(astPath)}`));
                }
            });
        });

        fs.createReadStream(astPath).pipe(parser);
    });
}

async function cmdShippedTableExport(args) {
    const astPath = args.ast;
    const preferredIndex = args['top-index'] !== undefined ? parseInt(args['top-index'], 10) : undefined;
    // --table NAME --out file.csv  (one table), or
    // --tables A,B,C --out-dir DIR (several tables that live in the same entry; DIR/<name>.csv each)
    const tableNames = String(args.tables || args.table).split(',').map((t) => t.trim()).filter(Boolean);
    const requireFields = args['require-fields'] ? String(args['require-fields']).split(',') : [];
    const requireRows = Boolean(args['require-rows']);
    const outDir = args['out-dir'];
    if (!outDir && tableNames.length !== 1) throw new Error('--out-dir is required when exporting more than one table');

    // Fast path: if the caller already knows the right index (e.g. the PS3
    // default of 46, or one remembered from a previous run on this install),
    // try it directly first without a full scan.
    let index = preferredIndex;
    let helper;
    if (preferredIndex !== undefined) {
        try {
            const raw = await extractEntry(astPath, preferredIndex);
            const tmpPath = path.join(require('os').tmpdir(), `hc09_shipped_db_${process.pid}_fast.db`);
            fs.writeFileSync(tmpPath, raw);
            try {
                const h = await openDb(tmpPath);
                if (await entryHasTables(h, tableNames, requireFields, requireRows)) helper = h;
            } finally {
                try { fs.unlinkSync(tmpPath); } catch (e) { /* best effort */ }
            }
        } catch (e) {
            // fall through to full scan below
        }
    }

    if (!helper) {
        const found = await findShippedTableEntry(astPath, tableNames, requireFields, requireRows);
        index = found.index;
        helper = found.helper;
    }

    const exported = [];
    for (const tableName of tableNames) {
        const table = helper.file[tableName];
        await table.readRecords();
        const headers = table.fieldDefinitions.map((f) => f.name);
        const rows = table.records.map((record) => {
            const obj = {};
            for (const h of headers) {
                const field = record.fields[h];
                obj[h] = field ? field.value : '';
            }
            return obj;
        });
        const outPath = outDir ? path.join(outDir, tableName.toLowerCase() + '.csv') : args.out;
        fs.mkdirSync(path.dirname(outPath), { recursive: true });
        writeCsv(outPath, headers, rows);
        exported.push({ table: tableName, records: rows.length, out: outPath });
    }
    const first = exported[0];
    console.log(JSON.stringify({ table: first.table, records: first.records, out: first.out, exported, entryIndex: index }));
}

// ---------- Play data inside the game's archives (sets, formations, personnel) ----------
// The play databases are DB entries stored as plain bytes in qkl_boot.ast and qkl_fe2ig.ast. Several entries hold the same
// sets (the master in qkl_boot.ast, a compact copy next to it, and smaller copies in qkl_fe2ig.ast), and the game was
// confirmed to read at least one of them: a same-size edit of a set's SETP rows (a slot's position EPos and depth DPos) moved a
// tight end into a receiver's spot. So the tool edits every copy in place, writing only the bytes that change, and keeps the
// original entry in a backup directory the first time an entry is touched. Opening an entry with the DB library and saving it
// unchanged gives back the same bytes, which is checked before every write.

const sha256 = (buf) => crypto.createHash('sha256').update(buf).digest('hex');

function mergeRanges(a, b) {
    const ranges = [];
    let start = -1;
    for (let i = 0; i <= a.length; i++) {
        const differs = i < a.length && a[i] !== b[i];
        if (differs && start < 0) start = i;
        if (!differs && start >= 0) { ranges.push({ offset: start, length: i - start }); start = -1; }
    }
    const merged = [];
    for (const r of ranges) {
        const last = merged[merged.length - 1];
        if (last && r.offset - (last.offset + last.length) <= 8) last.length = r.offset + r.length - last.offset;
        else merged.push({ ...r });
    }
    return merged;
}

async function openEntryBuffer(buf) {
    const tmp = path.join(os.tmpdir(), `hc09_entry_${process.pid}_${Math.random().toString(36).slice(2)}.db`);
    fs.writeFileSync(tmp, buf);
    const helper = await openDb(tmp);
    return { helper, tmp };
}

function readEntryAt(astPath, start, size) {
    const fd = fs.openSync(astPath, 'r');
    try {
        const buf = Buffer.alloc(size);
        fs.readSync(fd, buf, 0, size, start);
        return buf;
    } finally {
        fs.closeSync(fd);
    }
}

// Lists the DB entries of the archives that hold play sets: a table SETP with rows and the columns SETL, poso, EPos, DPos.
// Entries with the same tables but no rows (the blank career template, schema-only copies) are skipped. Writes, for each entry,
// its SETP rows as CSV, and (when present and filled) SETL, FORM, PBAI, SPKF into --out-dir.
async function cmdPlaySetsScan(args) {
    const outDir = args['out-dir'];
    fs.mkdirSync(outDir, { recursive: true });
    // --tables A,B: also (or instead) export these tables of each entry that has them filled (default: the ones the personnel tool uses)
    const wantedTables = args.tables ? ['SETP', ...String(args.tables).split(',').map((t) => t.trim()).filter((t) => t && t !== 'SETP')]
        : ['SETP', 'SETL', 'FORM', 'PBAI', 'SPKF'];
    const copies = [];
    for (const astPath of String(args.asts).split(',').map((s) => s.trim()).filter(Boolean)) {
        const tocs = await readToc(astPath);
        const fd = fs.openSync(astPath, 'r');
        try {
            for (const toc of tocs) {
                if (toc.fileSizeInt < 1000 || toc.fileSizeInt > 40e6) continue;
                const head = Buffer.alloc(2);
                fs.readSync(fd, head, 0, 2, toc.startPositionInFile);
                if (head[0] !== 0x44 || head[1] !== 0x42) continue;   // "DB"
                const raw = Buffer.alloc(toc.fileSizeInt);
                fs.readSync(fd, raw, 0, raw.length, toc.startPositionInFile);
                if (raw.indexOf('PTES') < 0) continue;                // the table name SETP, stored reversed
                let opened;
                try { opened = await openEntryBuffer(raw); } catch (e) { continue; }
                try {
                    const helper = opened.helper;
                    if (!helper.file.tables.some((t) => t.name === 'SETP')) continue;
                    const setp = helper.file.SETP;
                    const fields = setp.fieldDefinitions.map((f) => f.name);
                    if (!['SETL', 'poso', 'EPos', 'DPos'].every((f) => fields.includes(f))) continue;
                    await setp.readRecords();
                    if (setp.records.length === 0) continue;
                    const base = `${path.basename(astPath, '.ast')}_${toc.index}`;
                    const tables = {};
                    for (const name of wantedTables) {
                        if (!helper.file.tables.some((t) => t.name === name)) continue;
                        const table = helper.file[name];
                        await table.readRecords();
                        if (table.records.length === 0) continue;
                        const headers = table.fieldDefinitions.map((f) => f.name);
                        const rows = table.records.map((r) => { const o = {}; for (const h of headers) o[h] = r.fields[h] ? r.fields[h].value : ''; return o; });
                        writeCsv(path.join(outDir, `${name.toLowerCase()}_${base}.csv`), headers, rows);
                        tables[name] = rows.length;
                    }
                    copies.push({ ast: astPath, file: path.basename(astPath), index: toc.index, start: toc.startPositionInFile, size: toc.fileSizeInt, base, fields, rows: setp.records.length, tables });
                } finally {
                    try { fs.unlinkSync(opened.tmp); } catch (e) { /* best effort */ }
                }
            }
        } finally {
            fs.closeSync(fd);
        }
    }
    console.log(JSON.stringify({ copies, outDir }));
}

function writeIntoArchiveAt(astPath, writes) {
    // Windows refuses (EBUSY / EPERM / EACCES) when the emulator has the file open.
    let fd;
    try {
        fd = fs.openSync(astPath, 'r+');
        for (const w of writes) fs.writeSync(fd, w.buf, 0, w.buf.length, w.position);
        fs.fsyncSync(fd);
    } catch (e) {
        if (['EBUSY', 'EPERM', 'EACCES'].includes(e.code)) {
            throw new Error(`Could not write to ${path.basename(astPath)} (${e.code}). Close the game / emulator first, and make sure the file is not read-only.`);
        }
        throw e;
    } finally {
        if (fd !== undefined) fs.closeSync(fd);
    }
}

function checkEntryPlace(toc, target) {
    if (!toc || toc.startPositionInFile !== target.start || toc.fileSizeInt !== target.size) {
        throw new Error(`${path.basename(target.ast)} entry ${target.index} is not where it was scanned (a different version of the file?); nothing written`);
    }
}

// A value of an entry-patch edit is a number or, for a text column (a play's name), a string: text is compared without the padding the game's fixed-width text carries.
function sameValue(have, want) {
    if (typeof want === 'string') return String(have).replace(/ +$/, '') === want;
    return Number(have) === Number(want);
}

async function patchEntry(target, mode, backupDir) {
    const added = loadAddPlayRecord(backupDir, target.ast);
    if (added && added.active && target.start >= added.originalLength) {
        throw new Error(`${path.basename(target.ast)} #${target.index} is a copy made by Add a play: put the game files back first (or change the play through Add a play), nothing written`);
    }
    const tocs = await readToc(target.ast);
    checkEntryPlace(tocs.find((t) => t.index === target.index), target);
    const raw = readEntryAt(target.ast, target.start, target.size);
    const { helper, tmp } = await openEntryBuffer(raw);
    const out = path.join(os.tmpdir(), `hc09_entry_out_${process.pid}_${Math.random().toString(36).slice(2)}.db`);
    try {
        await helper.save(out);
        const rawHeaderStale = !dbHeaderIsConsistent(raw);           // an earlier version of the tools (a rename in entry 46, a grown entry) left a size and checksum that do not match the entry
        const unchanged = fs.readFileSync(out);
        const same = rawHeaderStale ? Buffer.compare(fixDbHeader(Buffer.from(unchanged)), fixDbHeader(Buffer.from(raw))) === 0 : Buffer.compare(unchanged, raw) === 0;
        if (!same) {
            throw new Error(`${path.basename(target.ast)} #${target.index}: saving the entry unchanged does not reproduce it byte for byte; nothing written`);
        }
        const done = [];
        for (const e of target.edits) {
            const table = helper.file[e.table];
            if (table.records.length === 0) await table.readRecords();
            const hits = table.records.filter((r) => Object.entries(e.match).every(([k, v]) => sameValue(r.fields[k].value, v)));
            if (hits.length !== 1) throw new Error(`${e.table} ${JSON.stringify(e.match)}: ${hits.length} rows match (expected 1); nothing written`);
            const rec = hits[0];
            for (const [k, v] of Object.entries(e.expect || {})) {
                if (!sameValue(rec.fields[k].value, v)) throw new Error(`${e.table} ${JSON.stringify(e.match)} ${k} is ${rec.fields[k].value}, expected ${v}; nothing written`);
            }
            const change = {};
            for (const [k, v] of Object.entries(e.set)) { change[k] = [rec.fields[k].value, v]; rec.fields[k].value = v; }
            done.push({ table: e.table, match: e.match, change });
        }
        await helper.save(out);
        const patched = fixDbHeader(fs.readFileSync(out));
        if (patched.length !== raw.length) {
            const playbookNameChanges = done
                .filter((edit) => edit.table === 'PPPN')
                .flatMap((edit) => Object.entries(edit.change)
                    .filter(([field]) => field === 'PPPM')
                    .map(([, values]) => values));
            if (patched.length > raw.length && playbookNameChanges.length > 0) {
                const growth = patched.length - raw.length;
                throw new Error(
                    `${path.basename(target.ast)} #${target.index}: the requested playbook-name edits need ${growth} more byte${growth === 1 ? '' : 's'} ` +
                    `in the Huffman-compressed PPPN table, but game-file entries cannot grow in place; nothing written. ` +
                    `Try a name that compresses to fewer bytes, or keep the existing playbook name.`
                );
            }
            throw new Error(`${path.basename(target.ast)} #${target.index}: the patched entry has a different length (${raw.length} to ${patched.length} bytes); nothing written`);
        }
        const check = await openEntryBuffer(patched);
        try {
            // A text column that the database keeps in a compressed string pool (a Huffman table) is written again as a whole, so most of the table's bytes change: every other value of the
            // edited tables must then read back exactly as before.
            const textTables = [...new Set(target.edits.filter((e) => Object.values(e.set).some((v) => typeof v === 'string')).map((e) => e.table))];
            for (const name of textTables) {
                const before = helper.file[name];
                const after = check.helper.file[name];
                await after.readRecords();
                if (before.records.length !== after.records.length) throw new Error(`${name} has a different number of rows after the change; nothing written`);
                const edited = new Map();
                for (const e of target.edits.filter((x) => x.table === name)) {
                    const hit = before.records.findIndex((r) => Object.entries(e.match).every(([k, v]) => sameValue(r.fields[k].value, v)));
                    edited.set(hit, new Set(Object.keys(e.set)));
                }
                for (let i = 0; i < before.records.length; i++) {
                    for (const k of Object.keys(before.records[i].fields)) {
                        if (edited.has(i) && edited.get(i).has(k)) continue;
                        const a = String(before.records[i].fields[k].value).replace(/ +$/, '');
                        const b = String(after.records[i].fields[k].value).replace(/ +$/, '');
                        if (a !== b) throw new Error(`${name} row ${i} ${k} would change from "${a}" to "${b}" without being edited; nothing written`);
                    }
                }
            }
            for (const e of target.edits) {
                const table = check.helper.file[e.table];
                await table.readRecords();
                const rec = table.records.find((r) => Object.entries(e.match).every(([k, v]) => sameValue(r.fields[k].value, v)));
                for (const [k, v] of Object.entries(e.set)) {
                    if (!sameValue(rec.fields[k].value, v)) throw new Error(`${e.table}.${k} did not read back as ${v}; nothing written`);
                }
            }
        } finally { try { fs.unlinkSync(check.tmp); } catch (x) { /* best effort */ } }
        const ranges = mergeRanges(raw, patched);
        const changed = ranges.reduce((n, r) => n + r.length, 0);
        const nValues = target.edits.reduce((n, e) => n + Object.keys(e.set).length, 0);
        const nText = target.edits.reduce((n, e) => n + Object.values(e.set).filter((v) => typeof v === 'string').length, 0);
        if (nText === 0 && changed > 64 + 16 * nValues) throw new Error(`${changed} bytes would change for ${nValues} values; nothing written`);
        const result = { file: path.basename(target.ast), index: target.index, done, changedBytes: changed, written: false };
        if (mode === 'apply' && changed > 0) {
            fs.mkdirSync(backupDir, { recursive: true });
            const base = path.join(backupDir, `${path.basename(target.ast)}.entry${target.index}`);
            if (!fs.existsSync(base + '.orig')) {
                fs.writeFileSync(base + '.orig', raw);
                fs.writeFileSync(base + '.json', JSON.stringify({ ast: path.resolve(target.ast), index: target.index, start: target.start, size: target.size, sha256: sha256(raw) }, null, 2));
            }
            writeIntoArchiveAt(target.ast, ranges.map((r) => ({ position: target.start + r.offset, buf: patched.slice(r.offset, r.offset + r.length) })));
            if (Buffer.compare(readEntryAt(target.ast, target.start, target.size), patched) !== 0) {
                throw new Error('the archive does not hold the patched bytes after writing; restore it from the backup');
            }
            result.written = true;
        }
        return result;
    } finally {
        for (const f of [tmp, out]) { try { fs.unlinkSync(f); } catch (x) { /* best effort */ } }
    }
}

async function restoreEntry(target, backupDir) {
    const base = path.join(backupDir, `${path.basename(target.ast)}.entry${target.index}`);
    if (!fs.existsSync(base + '.json')) return { file: path.basename(target.ast), index: target.index, restored: false, reason: 'no backup' };
    const info = JSON.parse(fs.readFileSync(base + '.json', 'utf8'));
    const orig = fs.readFileSync(base + '.orig');
    if (sha256(orig) !== info.sha256) throw new Error(`${path.basename(base)}.orig is damaged (checksum mismatch); nothing written`);
    const tocs = await readToc(target.ast);
    checkEntryPlace(tocs.find((t) => t.index === info.index), { ast: target.ast, index: info.index, start: info.start, size: info.size });
    writeIntoArchiveAt(target.ast, [{ position: info.start, buf: orig }]);
    const same = Buffer.compare(readEntryAt(target.ast, info.start, info.size), orig) === 0;
    return { file: path.basename(target.ast), index: target.index, restored: true, identical: same };
}

// ---------- EXPERIMENT: rows for tables that have no room (the game's play database is exactly full) ----------
// entry-grow --in <entry.db> --out <grown.db> --grow PBPL=1,PLYS=11 [--fill rows.json]: gives each table that many more (zeroed) rows; --fill {table: [{column: value}, ...]} writes values into the new rows by making its record area bigger; the file gets bigger by that much and every
// offset, size and checksum is rewritten. entry-relocate --ast <archive> --index <n> --in <entry.db>: puts a (bigger) entry at the end of the archive and points the table of contents at it
// (an entry has no room to grow where it is: the archive's entries follow each other without a gap). Nothing here is used by the editor; the tests try it on scratch copies to find out whether
// the game's tables CAN be given rows, and the game itself has to say whether it accepts the result.
async function cmdEntryGrow(args) {
    const raw = fs.readFileSync(args.in);
    const { helper, tmp } = await openEntryBuffer(raw);
    const report = { before: raw.length, tables: [] };
    try {
        for (const spec of String(args.grow).split(',').filter(Boolean)) {
            const [name, n] = spec.split('=');
            const k = Number(n);
            const t = helper.file[name];
            if (!t) throw new Error(`no table ${name}`);
            await t.readRecords();
            const h = t.header;
            report.tables.push({ table: name, allocation: h.dataAllocationType, lengthBytes: h.lengthBytes, maxRecords: h.maxRecords, currentRecords: h.currentRecords, indexCount: h.indexCount, indexBytes: t.indexBuffer ? t.indexBuffer.length : 0, grownBy: k });
            growTable(t, k);
            await t.readRecords();                                   // the records again, now with the new ones
        }
        if (args.fill) {
            const fill = JSON.parse(fs.readFileSync(args.fill, 'utf8'));
            for (const [name, rows] of Object.entries(fill)) {
                const t = helper.file[name];
                const grown = report.tables.find((r) => r.table === name);
                if (!grown || rows.length > grown.grownBy) throw new Error(`${name}: ${rows.length} rows to fill but the table grew by ${grown ? grown.grownBy : 0}`);
                const recs = t.records.slice(grown.currentRecords);
                rows.forEach((row, i) => {
                    for (const [k, v] of Object.entries(row)) recs[i].fields[k].value = v;
                });
            }
        }
        await helper.save(args.out);
        fs.writeFileSync(args.out, fixDbHeader(fs.readFileSync(args.out)));
        report.after = fs.statSync(args.out).size;
        const check = await openDb(args.out);
        report.issues = verifyDbStructure(check);
        report.rows = {};
        for (const r of report.tables) {
            const t = check.file[r.table];
            await t.readRecords();
            report.rows[r.table] = t.records.length;
        }
    } finally {
        try { fs.unlinkSync(tmp); } catch (x) { /* best effort */ }
    }
    console.log(JSON.stringify(report));
}

async function cmdEntryRelocate(args) {
    const tocs = await readToc(args.ast);
    const t = tocs.find((x) => x.index === Number(args.index));
    if (!t) throw new Error(`${path.basename(args.ast)} has no entry ${args.index}`);
    const data = fs.readFileSync(args.in);
    // A zero 'uncompressed size' in the table of contents means "stored as it is". The game treats an entry whose field is not zero as a different kind of entry: v4/v5 had it set to the entry's size
    // for entries 40, 42 and 46 and the game crashed in its save thread (the first Quick Save of a new career). This command only moves entries that are stored as they are and never writes the field.
    if (t.uncompressedSizeInt !== 0) throw new Error(`entry ${args.index} of ${path.basename(args.ast)} has an uncompressed size (${t.uncompressedSizeInt}): compressed entries are not relocated`);
    const fd = fs.openSync(args.ast, 'r+');
    try {
        const head = Buffer.alloc(0x30);
        fs.readSync(fd, head, 0, 0x30, 0);
        const shift = head.readInt8(33 + 5);
        const unit = Math.pow(2, shift);
        const sizes = [0, 1, 2, 3, 4].map((i) => head.readInt8(33 + i));       // widths of: unknown1, id, startPosition, fileSize, uncompressedSize
        const tocStart = head.readInt32LE(16);
        const additional = head.readInt8(40) * 4;
        const descLen = head.readInt8(44);
        const rowLen = sizes.reduce((a, b) => a + b, 0) + descLen + 1;
        const rowStart = tocStart + additional + t.index * rowLen + 1;
        const size = fs.fstatSync(fd).size;
        const newStart = Math.ceil(size / unit) * unit;
        if (newStart / unit >= Math.pow(256, sizes[2])) throw new Error('the new position does not fit the start position field of the table of contents');
        fs.writeSync(fd, Buffer.alloc(newStart - size), 0, newStart - size, size);
        fs.writeSync(fd, data, 0, data.length, newStart);
        const put = (fieldIndex, value) => {
            const off = rowStart + sizes.slice(0, fieldIndex).reduce((a, b) => a + b, 0);
            const b = Buffer.alloc(sizes[fieldIndex]);
            b.writeUIntLE(value, 0, sizes[fieldIndex]);
            fs.writeSync(fd, b, 0, b.length, off);
        };
        put(2, newStart / unit);
        put(3, data.length);
        fs.fsyncSync(fd);
        console.log(JSON.stringify({ index: t.index, oldStart: t.startPositionInFile, oldSize: t.fileSizeInt, newStart, newSize: data.length, shift, widths: sizes }));
    } finally {
        fs.closeSync(fd);
    }
    const moved = (await readToc(args.ast)).find((x) => x.index === t.index);
    if (moved.fileSizeInt !== data.length || moved.uncompressedSizeInt !== 0) throw new Error(`the table of contents row of entry ${t.index} is wrong after the move (size ${moved.fileSizeInt}, uncompressed ${moved.uncompressedSizeInt}); restore the archive`);
}

// entry-locate --ast <archive> --index <n> [--out file]: where entry n is (start, size) so that entry-patch can address it; with --out the entry is written out as a database file.
async function cmdEntryLocate(args) {
    const tocs = await readToc(args.ast);
    const t = tocs.find((x) => x.index === Number(args.index));
    if (!t) throw new Error(`${path.basename(args.ast)} has no entry ${args.index}`);
    const res = { file: path.basename(args.ast), ast: args.ast, index: t.index, start: t.startPositionInFile, size: t.fileSizeInt };
    if (args.out) fs.writeFileSync(args.out, readEntryAt(args.ast, res.start, res.size));
    console.log(JSON.stringify(res));
}

// entry-patch <apply|dry|restore> --config file.json
// config: { backupDir, targets: [ { ast, index, start, size, edits: [ { table, match, expect, set } ] } ] }
async function cmdEntryPatch(args) {
    const mode = args._mode;
    const cfg = JSON.parse(fs.readFileSync(args.config, 'utf8'));
    const results = [];
    // check every entry before writing any of them
    if (mode !== 'restore') for (const t of cfg.targets) await patchEntry(t, 'dry', cfg.backupDir);
    for (const t of cfg.targets) results.push(mode === 'restore' ? await restoreEntry(t, cfg.backupDir) : await patchEntry(t, mode, cfg.backupDir));
    console.log(JSON.stringify({ mode, results }));
}

// ---------- The Create-A-Play pictures (qkl_interface.ast): the field the play diagrams are drawn on and the receiver number sprites ----------
// The user's own copy of the game is read at run time and the pictures are kept in a cache folder on the user's computer; none of the game's art is part of the editor.
// qkl_interface.ast is a list of nested BGFA archives (one per screen: textures as DDS, the screen's layout as Apt). The Create-A-Play screen is recognised by its
// contents (a layout that mentions "createaplay", one 512x512 texture, at least six 32x32 ones) so a copy of the game that orders the entries differently is found too;
// entry 548 is only the place tried first (PS3 USA).

const CRC_TABLE = (() => {
    const t = new Uint32Array(256);
    for (let n = 0; n < 256; n++) {
        let c = n;
        for (let k = 0; k < 8; k++) c = (c & 1) ? (0xedb88320 ^ (c >>> 1)) : (c >>> 1);
        t[n] = c >>> 0;
    }
    return t;
})();

function crc32(buf) {
    let c = 0xffffffff;
    for (let i = 0; i < buf.length; i++) c = CRC_TABLE[(c ^ buf[i]) & 0xff] ^ (c >>> 8);
    return (c ^ 0xffffffff) >>> 0;
}

function pngChunk(type, data) {
    const len = Buffer.alloc(4);
    len.writeUInt32BE(data.length);
    const td = Buffer.concat([Buffer.from(type, 'latin1'), data]);
    const crc = Buffer.alloc(4);
    crc.writeUInt32BE(crc32(td));
    return Buffer.concat([len, td, crc]);
}

// rgba: Buffer of width*height*4. A PNG Tk can load by itself (8 bit, RGBA).
function encodePng(width, height, rgba) {
    const ihdr = Buffer.alloc(13);
    ihdr.writeUInt32BE(width, 0);
    ihdr.writeUInt32BE(height, 4);
    ihdr[8] = 8; ihdr[9] = 6; ihdr[10] = 0; ihdr[11] = 0; ihdr[12] = 0;
    const raw = Buffer.alloc((width * 4 + 1) * height);
    for (let y = 0; y < height; y++) {
        raw[y * (width * 4 + 1)] = 0;
        rgba.copy(raw, y * (width * 4 + 1) + 1, y * width * 4, (y + 1) * width * 4);
    }
    return Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), pngChunk('IHDR', ihdr), pngChunk('IDAT', zlib.deflateSync(raw, { level: 9 })), pngChunk('IEND', Buffer.alloc(0))]);
}

function unpack565(c) {
    return [Math.round(((c >> 11) & 31) * 255 / 31), Math.round(((c >> 5) & 63) * 255 / 63), Math.round((c & 31) * 255 / 31)];
}

// The first (largest) level of a DDS with DXT1, DXT3 or DXT5 blocks as RGBA.
function decodeDds(buf) {
    if (buf.length < 128 || buf.slice(0, 4).toString('latin1') !== 'DDS ') throw new Error('not a DDS texture');
    const height = buf.readUInt32LE(12);
    const width = buf.readUInt32LE(16);
    const fourcc = buf.slice(84, 88).toString('latin1');
    if (!['DXT1', 'DXT3', 'DXT5'].includes(fourcc)) throw new Error('unsupported texture format ' + fourcc);
    const out = Buffer.alloc(width * height * 4);
    const blockBytes = fourcc === 'DXT1' ? 8 : 16;
    let off = 128;
    for (let by = 0; by < height; by += 4) {
        for (let bx = 0; bx < width; bx += 4) {
            const colorOff = off + (fourcc === 'DXT1' ? 0 : 8);
            const c0 = buf.readUInt16LE(colorOff);
            const c1 = buf.readUInt16LE(colorOff + 2);
            const a = unpack565(c0);
            const b = unpack565(c1);
            const pal = [a, b];
            let threeColor = false;
            if (c0 > c1 || fourcc !== 'DXT1') {
                pal.push(a.map((v, i) => Math.floor((2 * v + b[i]) / 3)), a.map((v, i) => Math.floor((v + 2 * b[i]) / 3)));
            } else {
                pal.push(a.map((v, i) => Math.floor((v + b[i]) / 2)), [0, 0, 0]);
                threeColor = true;
            }
            const bits = buf.readUInt32LE(colorOff + 4);
            let alpha = null;
            if (fourcc === 'DXT5') {
                const a0 = buf[off];
                const a1 = buf[off + 1];
                const table = [a0, a1];
                if (a0 > a1) for (let i = 1; i <= 6; i++) table.push(Math.floor(((7 - i) * a0 + i * a1) / 7));
                else { for (let i = 1; i <= 4; i++) table.push(Math.floor(((5 - i) * a0 + i * a1) / 5)); table.push(0, 255); }
                const abits = BigInt(buf.readUInt32LE(off + 2)) | (BigInt(buf.readUInt16LE(off + 6)) << 32n);
                alpha = (i) => table[Number((abits >> BigInt(3 * i)) & 7n)];
            } else if (fourcc === 'DXT3') {
                alpha = (i) => ((buf.readUInt16LE(off + 2 * (i >> 2)) >> (4 * (i & 3))) & 15) * 17;
            }
            for (let py = 0; py < 4; py++) {
                for (let px = 0; px < 4; px++) {
                    const x = bx + px;
                    const y = by + py;
                    if (x >= width || y >= height) continue;
                    const i = py * 4 + px;
                    const idx = (bits >>> (2 * i)) & 3;
                    const o = (y * width + x) * 4;
                    out[o] = pal[idx][0]; out[o + 1] = pal[idx][1]; out[o + 2] = pal[idx][2];
                    out[o + 3] = alpha ? alpha(i) : (threeColor && idx === 3 ? 0 : 255);
                }
            }
            off += blockBytes;
        }
    }
    return { width, height, rgba: out };
}

// Every sub-entry of a nested BGFA archive held in memory: [{index, data}] (deflated ones inflated).
function parseNestedArchive(buf) {
    return new Promise((resolve) => {
        const subs = [];
        const parser = new ASTParser();
        let total = -1;
        let done = 0;
        let finished = false;
        const finish = () => {
            if (finished) return;
            finished = true;
            parser.destroy();
            resolve(subs.sort((x, y) => x.index - y.index));
        };
        const step = () => { done++; if (total >= 0 && done >= total) finish(); };
        parser.on('toc', (t) => { total = t.length; if (total === 0) finish(); });
        parser.on('compressed-file', ({ stream, toc }) => {
            bufferFromReadable(stream).then((raw) => {
                let data = raw;
                if (data.length > 2 && data[0] === 0x78 && (data[1] === 0xda || data[1] === 0x9c || data[1] === 0x01)) {
                    try { data = zlib.inflateSync(data); } catch (e) { /* keep as is */ }
                }
                subs.push({ index: toc.index, data });
                step();
            }, step);
        });
        parser.on('error', finish);
        const s = new Readable();
        s._read = () => {};
        s.push(buf);
        s.push(null);
        s.pipe(parser);
    });
}

const isDds = (d) => d.length >= 128 && d.slice(0, 4).toString('latin1') === 'DDS ';

// The Create-A-Play screen's textures if these sub-entries are that screen: {field, small: [...]} else null.
function playCreatorSignature(subs) {
    const dds = subs.filter((s) => isDds(s.data)).map((s) => ({ ...s, w: s.data.readUInt32LE(16), h: s.data.readUInt32LE(12) }));
    const field = dds.filter((d) => d.w === 512 && d.h === 512);
    const small = dds.filter((d) => d.w === 32 && d.h === 32);
    const named = subs.some((s) => !isDds(s.data) && s.data.toString('latin1').toLowerCase().includes('createaplay'));
    return named && field.length === 1 && small.length >= 6 ? { field: field[0], small } : null;
}

// One streaming pass over the archive (the entries are small), stopping at the first screen that matches.
function scanForPlayCreator(astPath) {
    return new Promise((resolve, reject) => {
        const parser = new ASTParser();
        let total = -1;
        let done = 0;
        let settled = false;
        let stream = null;
        const settle = (v) => { if (settled) return; settled = true; parser.destroy(); if (stream) stream.destroy(); resolve(v); };
        const step = () => { done++; if (total >= 0 && done >= total) settle(null); };
        parser.on('toc', (t) => { total = t.length; });
        parser.on('compressed-file', ({ stream: entry, toc }) => {
            bufferFromReadable(entry).then(async (raw) => {
                if (settled) return;
                if (raw.slice(0, 4).toString('latin1') === 'BGFA') {
                    const sig = playCreatorSignature(await parseNestedArchive(raw));
                    if (sig) { settle({ index: toc.index, sig }); return; }
                }
                step();
            }, step);
        });
        parser.on('error', reject);
        stream = fs.createReadStream(astPath);
        stream.pipe(parser);
    });
}

// The field's visible part in the 512x512 texture (measured from its pixels: the sidelines are the bright columns 6-16 and 477-487, the green ends at row 282) and
// how it maps to the play diagram's units: x 0 to 180 across it, y 0 to 104 down it (checked against the in-game thumbnails).
const FIELD_CROP = [6, 6, 486, 282];

// ui-assets --ast <qkl_interface.ast> --out-dir <dir> [--top-index N]: field.png (the field the plays are drawn on), num1.png to num5.png (the receiver numbers)
async function cmdUiAssets(args) {
    const astPath = args.ast;
    const outDir = args['out-dir'];
    if (!astPath || !outDir) throw new Error('ui-assets needs --ast and --out-dir');
    fs.mkdirSync(outDir, { recursive: true });
    const first = args['top-index'] ? parseInt(args['top-index'], 10) : 548;
    let found = null;
    try {
        const raw = await extractEntry(astPath, first);
        if (raw.slice(0, 4).toString('latin1') === 'BGFA') {
            const sig = playCreatorSignature(await parseNestedArchive(raw));
            if (sig) found = { index: first, sig };
        }
    } catch (e) { /* not there: scan */ }
    if (!found) found = await scanForPlayCreator(astPath);
    if (!found) {
        console.log(JSON.stringify({ found: false }));
        return;
    }
    const { sig } = found;
    const field = decodeDds(sig.field.data);
    const [x0, y0, x1, y1] = FIELD_CROP;
    const w = x1 - x0;
    const h = y1 - y0;
    const crop = Buffer.alloc(w * h * 4);
    for (let y = 0; y < h; y++) field.rgba.copy(crop, y * w * 4, ((y0 + y) * field.width + x0) * 4, ((y0 + y) * field.width + x1) * 4);
    for (let i = 3; i < crop.length; i += 4) crop[i] = 255;
    const files = [];
    fs.writeFileSync(path.join(outDir, 'field.png'), encodePng(w, h, crop));
    files.push({ name: 'field.png', width: w, height: h });
    // the 32x32 pieces in the screen's order: the first is the marker, the next five are the receiver numbers 1 to 5
    for (let n = 1; n <= 5; n++) {
        const sprite = decodeDds(sig.small[n].data);
        fs.writeFileSync(path.join(outDir, `num${n}.png`), encodePng(sprite.width, sprite.height, sprite.rgba));
        files.push({ name: `num${n}.png`, width: sprite.width, height: sprite.height });
    }
    const manifest = { entry: found.index, crop: FIELD_CROP, units: [180, 104], files, sourceSize: fs.statSync(astPath).size };
    fs.writeFileSync(path.join(outDir, 'manifest.json'), JSON.stringify(manifest));
    console.log(JSON.stringify({ found: true, ...manifest, outDir }));
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

// ---------- ADD A PLAY: new rows in the game's own play database ----------
// Every table of the game's play database is exactly full and the archive's entries follow each other without a gap, so a play is added by making copies of the entries with bigger tables, putting
// them at the END of qkl_boot.ast and pointing the table of contents at them. Proven in the game (RPCS3: the play showed in the playbook, ran, and could be flipped and have its routes changed like
// any stock play) as long as the 'uncompressed size' of the table-of-contents row stays 0 (see entry-relocate: with it set the game crashed in its save thread).
//   add-play --ast <qkl_boot.ast> --spec spec.json --backup-dir <dir> [--dry]
//     spec = { rows: { "40": { PBPL: [ {column: value} ], PLYS: [...], PLPD, PLRD, PLCM, PBAI }, "42": { PBPL, PLYS }, "46": { PPPN: [ {BOKL, PLYL, PPPM} ] }, "47": { PGPL: [ {BOKL, SETL, PLYL, PLTP} ] } },
//              plays: [ anything the editor wants to get back from add-play-state ] }
//     The spec holds the rows of ALL the plays that are to be in the game files: the archive is first put back to the state before the first add (the original table-of-contents rows and archive length,
//     kept in <dir>/<archive>.addplay.json), then every entry is built again from the untouched originals, so the file grows by the four entries once, not once per add, and editing an added play is a rebuild.
//   add-play-state --ast <qkl_boot.ast> --backup-dir <dir>      what is added now (the 'plays' of the last spec)
//   add-play-restore --ast <qkl_boot.ast> --backup-dir <dir>    the original table-of-contents rows back and the archive cut to its original length: byte for byte the file before the first add.
// Each entry is checked before anything is written: the structure (checksums, offsets, sizes), every table read back row by row, every table that was not touched byte for byte.
const ADD_PLAY_ENTRIES = [40, 42, 46, 47];
const ADD_PLAY_PLACE = {                       // per entry: table -> the columns its rows are sorted by (the game's own order, checked at run time: a table that is not sorted gets the rows at its end)
    40: { PBPL: ['PLYL'], PLYS: ['PLYL', 'poso'], PLPD: ['PLYL'], PLRD: ['PLYL'], PLCM: ['PLYL'], PBAI: ['BOKL'] },
    42: { PBPL: ['PLYL'], PLYS: ['PLYL', 'poso'] },
    46: { PPPN: ['BOKL', 'PLYL'] },
    47: { PGPL: ['BOKL', 'SETL', 'PLYL'] },
};
const ADD_PLAY_UNIQUE = (table) => table !== 'PBAI';       // PBAI has several rows per book and play (the CPU's chances per situation)

function tocGeometry(astPath) {
    const fd = fs.openSync(astPath, 'r');
    try {
        const head = Buffer.alloc(0x30);
        fs.readSync(fd, head, 0, 0x30, 0);
        const sizes = [0, 1, 2, 3, 4].map((i) => head.readInt8(33 + i));       // widths of: unknown1, id, startPosition, fileSize, uncompressedSize
        const unit = Math.pow(2, head.readInt8(33 + 5));
        const tocStart = head.readInt32LE(16);
        const additional = head.readInt8(40) * 4;
        const rowLen = sizes.reduce((a, b) => a + b, 0) + head.readInt8(44) + 1;
        return { unit, sizes, rowLen, rowOffset: (idx) => tocStart + additional + idx * rowLen };
    } finally { fs.closeSync(fd); }
}
function readTocRows(astPath, geo, indexes) {
    const fd = fs.openSync(astPath, 'r');
    try {
        const rows = {};
        for (const idx of indexes) {
            const b = Buffer.alloc(geo.rowLen);
            fs.readSync(fd, b, 0, geo.rowLen, geo.rowOffset(idx));
            rows[idx] = b.toString('hex');
        }
        return rows;
    } finally { fs.closeSync(fd); }
}
function writeTocRows(fd, geo, rows) {
    for (const [idx, hex] of Object.entries(rows)) fs.writeSync(fd, Buffer.from(hex, 'hex'), 0, geo.rowLen, geo.rowOffset(Number(idx)));
}
function addPlayRecordPath(backupDir, ast) { return path.join(backupDir, `${path.basename(ast)}.addplay.json`); }
function loadAddPlayRecord(backupDir, ast) {
    if (!backupDir) return null;
    const p = addPlayRecordPath(backupDir, ast);
    return fs.existsSync(p) ? JSON.parse(fs.readFileSync(p, 'utf8')) : null;
}
function saveAddPlayRecord(backupDir, ast, rec) {
    fs.mkdirSync(backupDir, { recursive: true });
    fs.writeFileSync(addPlayRecordPath(backupDir, ast), JSON.stringify(rec, null, 2));
}

// The tables of an entry must sit where the definitions say: the library's writer works out the offsets after a table changed its length, so every entry is checked.
function verifyLayout(helper, buf) {
    const f = helper.file;
    const base = f.headerBuffer.length + f.definitionBuffer.length;
    const issues = [];
    let pos = base;
    f.tables.forEach((t) => {
        const def = f.definitions.find((d) => d.name === t.name);
        if (!def) issues.push(`no definition for ${t.name}`);
        else if (def.offset !== pos - base) issues.push(`the definition of ${t.name} says offset ${def.offset} but the table starts at ${pos - base}`);
        pos += t.headerBuffer.length + t.fieldDefinitionBuffer.length + (t.dataBuffer ? t.dataBuffer.length : 0) + (t.indexBuffer ? t.indexBuffer.length : 0);
    });
    pos += f.eofCrcBuffer.length;
    if (pos !== buf.length) issues.push(`the tables add up to ${pos} bytes, the entry has ${buf.length}`);
    if (!dbHeaderIsConsistent(buf)) issues.push('the file header does not hold the entry\'s size and checksum');
    return issues;
}

function growTable(t, k) {
    const h = t.header;
    const lb = h.lengthBytes;
    const area = lb * h.maxRecords;
    t.dataBuffer = Buffer.concat([t.dataBuffer.slice(0, area), Buffer.alloc(lb * k), t.dataBuffer.slice(area)]);
    h.maxRecords += k;
    h.currentRecords += k;
    t.headerBuffer.writeUInt16BE(h.maxRecords, 20);
    t.headerBuffer.writeUInt16BE(h.currentRecords, 22);
    if (t._extraDataBufferOffset >= 0) t._extraDataBufferOffset = lb * h.maxRecords;
    rewriteHeaderCrc(t);
}
const cellText = (v) => String(v).replace(/[\s\0]+$/, '');
const sameCell = (a, b) => (typeof a === 'string' || typeof b === 'string') ? cellText(a) === cellText(b) : Number(a) === Number(b);
const keyCompare = (a, b, keys) => { for (const k of keys) { const d = Number(a[k]) - Number(b[k]); if (d) return d; } return 0; };
const isSortedBy = (rows, keys) => rows.every((r, i) => i === 0 || keyCompare(rows[i - 1], r, keys) <= 0);

// One entry: the rows of its tables in their sorted places. Returns { buf, report }. NOTE: a table's .records is a getter that copies the array: take it once, never index it in a loop.
async function buildAddPlayEntry(raw, place, rowsByTable) {
    const { helper, tmp } = await openEntryBuffer(raw);
    const original = await openEntryBuffer(raw);
    const out = path.join(os.tmpdir(), `hc09_addplay_${process.pid}_${Math.random().toString(36).slice(2)}.db`);
    const temps = [tmp, original.tmp, out];
    const report = {};
    try {
        const expected = {};
        for (const [tname, keys] of Object.entries(place)) {
            const added = (rowsByTable || {})[tname];
            if (!added || added.length === 0) continue;
            const t = helper.file[tname];
            if (!t) throw new Error(`the entry has no table ${tname}`);
            if (t.records.length === 0) await t.readRecords();
            const h = t.header;
            if (h.indexCount) throw new Error(`${tname} has an index that would have to be kept in step: not supported`);
            const oldCount = h.currentRecords;
            const free = h.maxRecords - oldCount;
            const oldRecs = t.records.slice(0, oldCount);
            const names = Object.keys(oldRecs[0].fields);
            const extra = names.filter((n) => 'extraDataBuffer' in oldRecs[0].fields[n]);          // the columns whose text sits in the table's string area (the playbooks' names)
            const valuesOf = (rec) => Object.fromEntries(names.map((n) => [n, rec.fields[n].value]));
            const cur = oldRecs.map(valuesOf);
            const oldExtra = extra.length ? oldRecs.map((r) => extra.map((n) => ({ buf: r.fields[n].extraDataBuffer, off: r.fields[n].extraDataOffset }))) : null;
            const rows = added.map((r) => {
                for (const c of Object.keys(r)) if (!names.includes(c)) throw new Error(`${tname} has no column ${c}`);
                return Object.fromEntries(names.map((n) => [n, r[n] === undefined ? 0 : r[n]]));
            });
            if (ADD_PLAY_UNIQUE(tname)) {
                for (const r of rows) if (cur.some((c) => keyCompare(c, r, keys) === 0)) throw new Error(`${tname} already has a row for ${keys.map((k) => `${k} ${r[k]}`).join(', ')}`);
            }
            const sorted = isSortedBy(cur, keys);
            const items = cur.map((v, o) => ({ o, v }));                          // o: the row's place before, -1 for a new row
            for (const r of rows) {
                let i = items.length;
                if (sorted) while (i > 0 && keyCompare(items[i - 1].v, r, keys) > 0) i--;
                if (extra.length && i === 0) throw new Error(`${tname}: a row at the very start of a compressed table is not supported`);
                items.splice(i, 0, { o: -1, v: r });
            }
            if (rows.length > free) growTable(t, rows.length - free);              // adds the rows to the capacity and the count
            h.currentRecords = oldCount + rows.length;                             // inside the capacity the count is all that changes
            t.headerBuffer.writeUInt16BE(h.currentRecords, 22);
            rewriteHeaderCrc(t);
            await t.readRecords();                                                 // the records again, now with the new (zeroed) ones
            const recs = t.records.slice(0, h.currentRecords);
            if (recs.length !== items.length) throw new Error(`${tname}: ${recs.length} rows after growing, expected ${items.length}`);
            if (extra.length) {                                                    // reading the table again cut the text of the last old row by the zero offsets of the new rows: put every old text back
                recs.forEach((rec, i) => {
                    if (i < oldCount) extra.forEach((n, j) => { rec.fields[n].extraDataBuffer = oldExtra[i][j].buf; rec.fields[n].extraDataOffset = oldExtra[i][j].off; });
                });
            }
            const have = recs.map(valuesOf);
            let written = 0;
            items.forEach((item, i) => {
                let touched = false;
                for (const n of names) {
                    if (extra.includes(n) && item.o >= 0) {                        // an old row's text moves with its row
                        const j = extra.indexOf(n);
                        if (item.o !== i) { recs[i].fields[n].extraDataBuffer = oldExtra[item.o][j].buf; recs[i].fields[n].extraDataOffset = oldExtra[item.o][j].off; recs[i].fields[n].isChanged = true; touched = true; }
                    } else if (!sameCell(have[i][n], item.v[n])) { recs[i].fields[n].value = item.v[n]; touched = true; }
                }
                if (touched) written++;
            });
            expected[tname] = { names, final: items.map((x) => x.v), keys };
            report[tname] = { rows: oldCount, added: rows.length, placed: sorted ? 'sorted' : 'at the end', rowsWritten: written, capacity: h.maxRecords };
        }
        await helper.save(out);
        const buf = fixDbHeader(fs.readFileSync(out));
        // ---- everything is checked before anything is written
        const check = await openEntryBuffer(buf);
        temps.push(check.tmp);
        const issues = verifyDbStructure(check.helper).concat(verifyLayout(check.helper, buf));
        for (const [tname, e] of Object.entries(expected)) {
            const t = check.helper.file[tname];
            await t.readRecords();
            const recs = t.records.slice(0, t.header.currentRecords);
            if (recs.length !== e.final.length) { issues.push(`${tname}: ${recs.length} rows read back, expected ${e.final.length}`); continue; }
            let bad = 0;
            for (let i = 0; i < e.final.length && bad < 3; i++) {
                for (const n of e.names) {
                    if (!sameCell(recs[i].fields[n].value, e.final[i][n])) { issues.push(`${tname} row ${i} ${n}: read back "${recs[i].fields[n].value}", expected "${e.final[i][n]}"`); bad++; break; }
                }
            }
        }
        for (const ot of original.helper.file.tables) {
            if (expected[ot.name]) continue;
            const nt = check.helper.file[ot.name];
            const same = (a, b) => (a || emptyBuf).equals(b || emptyBuf);
            if (!nt || !same(ot.headerBuffer.slice(4), nt.headerBuffer.slice(4)) || !same(ot.fieldDefinitionBuffer, nt.fieldDefinitionBuffer) || !same(ot.dataBuffer, nt.dataBuffer) || !same(ot.indexBuffer, nt.indexBuffer)) {
                issues.push(`the table ${ot.name} was not touched but is not the same`);
            }
        }
        if (issues.length) throw new Error('the grown entry does not check out: ' + issues.slice(0, 6).join('; '));
        return { buf, report };
    } finally {
        for (const f of temps) { try { fs.unlinkSync(f); } catch (x) { /* best effort */ } }
    }
}

async function addPlayRestore(ast, backupDir) {
    const rec = loadAddPlayRecord(backupDir, ast);
    if (!rec || !rec.active) return { restored: false, reason: 'nothing was added' };
    const geo = tocGeometry(ast);
    const size = fs.statSync(ast).size;
    if (size < rec.originalLength) throw new Error(`${path.basename(ast)} is shorter (${size}) than it was before the first add (${rec.originalLength}): not restoring`);
    const fd = fs.openSync(ast, 'r+');
    try {
        writeTocRows(fd, geo, rec.rows);
        fs.ftruncateSync(fd, rec.originalLength);
        fs.fsyncSync(fd);
    } finally { fs.closeSync(fd); }
    const back = readTocRows(ast, geo, Object.keys(rec.rows).map(Number));
    for (const [idx, hex] of Object.entries(rec.rows)) if (back[idx] !== hex) throw new Error(`the table of contents row of entry ${idx} is not back as it was`);
    if (fs.statSync(ast).size !== rec.originalLength) throw new Error('the archive is not back to its original length');
    rec.active = false;
    rec.plays = [];
    delete rec.addedRows;
    saveAddPlayRecord(backupDir, ast, rec);
    return { restored: true, length: rec.originalLength };
}

function addPlayRowFields(geo, hex) {
    const row = Buffer.from(hex, 'hex');
    let o = 1;
    const f = geo.sizes.map((w) => { const v = w && w <= 6 ? row.readUIntLE(o, w) : 0; o += w; return v; });          // the 8 byte id is not needed
    return { start: f[2] * geo.unit, size: f[3], uncompressed: f[4] };
}

async function cmdAddPlay(args) {
    if (!args.ast || !args.spec || !args['backup-dir']) throw new Error('add-play needs --ast, --spec and --backup-dir');
    const ast = args.ast;
    const backupDir = args['backup-dir'];
    const spec = JSON.parse(fs.readFileSync(args.spec, 'utf8'));
    const geo = tocGeometry(ast);
    let rec = loadAddPlayRecord(backupDir, ast);
    // Where the ORIGINAL entries are: they stay where they were (the grown copies are written after them), so they can be read while the grown ones are in use, and nothing is touched until every new
    // entry is built and checked: an add that cannot be done leaves the archive exactly as it was.
    let originalRows, originalLength;
    if (rec && rec.active) {
        const now = readTocRows(ast, geo, ADD_PLAY_ENTRIES);
        for (const idx of ADD_PLAY_ENTRIES) {
            if (rec.addedRows[idx] !== undefined && now[idx] !== rec.addedRows[idx]) throw new Error(`entry ${idx} of ${path.basename(ast)} was changed after the last add (outside the editor?): put the game files back from your own copy first`);
        }
        originalRows = rec.rows;
        originalLength = rec.originalLength;
    } else {
        originalRows = readTocRows(ast, geo, ADD_PLAY_ENTRIES);
        originalLength = fs.statSync(ast).size;
    }
    const built = {};
    const report = {};
    for (const idx of ADD_PLAY_ENTRIES) {
        const orig = addPlayRowFields(geo, originalRows[idx]);
        if (orig.uncompressed !== 0) throw new Error(`entry ${idx} has an uncompressed size (${orig.uncompressed}): not a plain database entry`);
        const rows = (spec.rows || {})[idx];
        if (!rows || Object.values(rows).every((r) => !r || r.length === 0)) continue;
        const raw = readEntryAt(ast, orig.start, orig.size);
        const b = await buildAddPlayEntry(raw, ADD_PLAY_PLACE[idx], rows);
        built[idx] = b.buf;
        report[idx] = { before: raw.length, after: b.buf.length, tables: b.report };
    }
    if (args.dry) { console.log(JSON.stringify({ dry: true, entries: report })); return; }
    if (Object.keys(built).length === 0) { console.log(JSON.stringify({ added: 0, entries: {} })); return; }
    if (rec && rec.active) await addPlayRestore(ast, backupDir);             // the state before the first add; the record of the originals stays
    // the record of the original state comes first, so that a put-back is possible whatever happens next
    rec = { ast: path.resolve(ast), originalLength, rows: originalRows, active: false, plays: [], savedAt: new Date().toISOString() };
    saveAddPlayRecord(backupDir, ast, rec);
    try {
        const fd = fs.openSync(ast, 'r+');
        try {
            let size = originalLength;
            for (const idx of Object.keys(built).map(Number)) {
                const data = built[idx];
                const start = Math.ceil(size / geo.unit) * geo.unit;
                if (start / geo.unit >= Math.pow(256, geo.sizes[2])) throw new Error('the new position does not fit the start position field of the table of contents');
                fs.writeSync(fd, Buffer.alloc(start - size), 0, start - size, size);
                fs.writeSync(fd, data, 0, data.length, start);
                size = start + data.length;
                const row = Buffer.from(originalRows[idx], 'hex');
                row.writeUIntLE(start / geo.unit, 1 + geo.sizes.slice(0, 2).reduce((a, b) => a + b, 0), geo.sizes[2]);
                row.writeUIntLE(data.length, 1 + geo.sizes.slice(0, 3).reduce((a, b) => a + b, 0), geo.sizes[3]);       // the uncompressed size stays as it was: 0
                fs.writeSync(fd, row, 0, row.length, geo.rowOffset(idx));
            }
            fs.fsyncSync(fd);
        } finally { fs.closeSync(fd); }
        const after = await readToc(ast);
        for (const idx of Object.keys(built).map(Number)) {
            const t = after.find((x) => x.index === idx);
            if (t.fileSizeInt !== built[idx].length || t.uncompressedSizeInt !== 0 || Buffer.compare(readEntryAt(ast, t.startPositionInFile, t.fileSizeInt), built[idx]) !== 0) throw new Error(`entry ${idx} is not what was written`);
            report[idx].start = t.startPositionInFile;
        }
    } catch (e) {
        rec.active = true;                                    // so that the restore below knows there is something to undo
        rec.addedRows = {};
        saveAddPlayRecord(backupDir, ast, rec);
        try { await addPlayRestore(ast, backupDir); } catch (x) { e.message += ` (and putting the file back failed: ${x.message})`; }
        throw e;
    }
    rec.active = true;
    rec.plays = spec.plays || [];
    rec.addedRows = readTocRows(ast, geo, ADD_PLAY_ENTRIES);
    saveAddPlayRecord(backupDir, ast, rec);
    console.log(JSON.stringify({ added: (spec.plays || []).length, entries: report, archiveBytes: fs.statSync(ast).size, originalLength }));
}

async function cmdAddPlayState(args) {
    const rec = loadAddPlayRecord(args['backup-dir'], args.ast);
    console.log(JSON.stringify({ active: Boolean(rec && rec.active), plays: rec && rec.active ? rec.plays : [], originalLength: rec ? rec.originalLength : null, length: fs.statSync(args.ast).size }));
}

async function cmdAddPlayRestore(args) {
    console.log(JSON.stringify(await addPlayRestore(args.ast, args['backup-dir'])));
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
        } else if (cmd === 'verify-db') {
            await cmdVerifyDb(args);
        } else if (cmd === 'shipped-table-export') {
            await cmdShippedTableExport(args);
        } else if (cmd === 'play-sets-scan') {
            await cmdPlaySetsScan(args);
        } else if (cmd === 'ui-assets') {
            await cmdUiAssets(args);
        } else if (cmd === 'selftest') {
            // The libraries above loaded, or this line would not be reached. Used by the launchers.
            console.log(JSON.stringify({ ok: true, node: process.version, vendored: fs.existsSync(vendorDir) }));
        } else if (cmd === 'entry-locate') {
            await cmdEntryLocate(args);
        } else if (cmd === 'entry-grow') {
            await cmdEntryGrow(args);
        } else if (cmd === 'entry-relocate') {
            await cmdEntryRelocate(args);
        } else if (cmd === 'add-play') {
            await cmdAddPlay(args);
        } else if (cmd === 'add-play-state') {
            await cmdAddPlayState(args);
        } else if (cmd === 'add-play-restore') {
            await cmdAddPlayRestore(args);
        } else if (cmd === 'entry-patch') {
            args._mode = rest.find((a) => !a.startsWith('--'));
            if (!['apply', 'dry', 'restore'].includes(args._mode)) throw new Error('entry-patch needs apply, dry or restore as its first argument');
            await cmdEntryPatch(args);
        } else {
            console.error('Usage:');
            console.error('  node bridge.js inspect --db <path>');
            console.error('  node bridge.js fields --db <path> --table <name>');
            console.error('  node bridge.js export --db <path> --out <dir> [--tables PLAY,DRPK,...]');
            console.error('  node bridge.js import --db <path> --in <dir> [--out <path>] [--tables PLAY,DRPK,...] [--allow-append PGPL,...] [--allow-shrink PGPL,...]');
            console.error('  node bridge.js verify-db --db <path>');
            console.error('  node bridge.js portrait-extract-archive --ast <path> --top-index <N> --out <path>');
            console.error('  node bridge.js portrait-lookup --archive <path> --shortid <N> --out <path>');
            console.error('  node bridge.js portrait-list --archive <path>');
            console.error('  node bridge.js shipped-table-export --ast <qkl_boot.ast> [--top-index <N>] [--require-fields A,B] [--require-rows] (--table <NAME> --out <csv> | --tables A,B --out-dir <dir>)');
            console.error('  node bridge.js play-sets-scan --asts <qkl_boot.ast>,<qkl_fe2ig.ast> --out-dir <dir> [--tables SETL,PLYS,...]');
            console.error('  node bridge.js ui-assets --ast <qkl_interface.ast> --out-dir <dir> [--top-index <N>]');
            console.error('  node bridge.js entry-patch <apply|dry|restore> --config <json>');
            console.error('  node bridge.js entry-locate --ast <archive> --index <n> [--out <file>]');
            console.error('  node bridge.js selftest');
            process.exit(1);
        }
    } catch (err) {
        console.error('ERROR:', err.stack || err);
        process.exit(1);
    }
}

main();
