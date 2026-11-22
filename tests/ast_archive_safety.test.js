'use strict';

const assert = require('node:assert/strict');
const { Readable } = require('node:stream');
const test = require('node:test');

const ASTParser = require('../hc09-bridge/vendor/node_modules/madden-file-tools/streams/ASTParser');

function makeArchive(entries) {
    const headerSize = 0x30;
    const rowSize = 25; // separator + 4 + 8 + 4 + 4 + 4 byte fields
    const tocLength = entries.length * rowSize;
    const tocOffset = 0x40;
    const dataStart = tocOffset + tocLength;
    const header = Buffer.alloc(headerSize);
    header.write('BGFA1.05', 0, 'latin1');
    header.writeInt32LE(entries.length, 12);
    header.writeInt32LE(tocOffset, 16);
    header.writeInt32LE(tocLength, 24);
    [4, 8, 4, 4, 4].forEach((length, i) => header.writeInt8(length, 33 + i));
    header.writeInt8(0, 38); // byte-aligned TOC offsets
    header.writeInt8(0, 40); // no additional TOC prefix
    header.writeInt8(0, 44); // no description

    let nextData = dataStart;
    const rows = [];
    const payloads = [];
    for (const item of entries) {
        const data = Buffer.from(item.data);
        const row = Buffer.alloc(rowSize);
        row[0] = 1; // entry separator
        Buffer.from('TEST').copy(row, 1);
        Buffer.from(item.id || [1, 2, 3, 4, 5, 6, 7, 8]).copy(row, 5);
        row.writeUInt32LE(nextData, 13);
        row.writeUInt32LE(data.length, 17);
        row.writeUInt32LE(0, 21); // uncompressed entry
        rows.push(row);
        payloads.push(data);
        nextData += data.length;
    }
    return Buffer.concat([header, Buffer.alloc(tocOffset - headerSize), ...rows, ...payloads]);
}

function parseArchive(buffer, extract = true) {
    return new Promise((resolve, reject) => {
        const parser = new ASTParser();
        parser.extract = extract;
        let toc = [];
        let done = false;
        let pending = 0;
        const payloads = [];

        function finishIfReady() {
            if (done && pending === 0) resolve({ toc, payloads });
        }

        parser.on('toc', (entries) => { toc = entries; });
        parser.on('compressed-file', ({ stream, toc: entry }) => {
            pending += 1;
            const chunks = [];
            stream.on('data', (chunk) => chunks.push(chunk));
            stream.on('error', reject);
            stream.on('end', () => {
                payloads.push({ index: entry.index, data: Buffer.concat(chunks) });
                pending -= 1;
                finishIfReady();
            });
        });
        parser.on('error', reject);
        parser.on('done', () => {
            done = true;
            finishIfReady();
        });
        Readable.from([buffer]).pipe(parser);
    });
}

test('AST reader parses a valid archive and extracts exact entry bytes', async () => {
    const archive = makeArchive([{ data: Buffer.from('qkl archive payload') }]);
    const result = await parseArchive(archive);
    assert.equal(result.toc.length, 1);
    assert.equal(result.toc[0].index, 0);
    assert.equal(result.toc[0].fileSizeInt, Buffer.byteLength('qkl archive payload'));
    assert.equal(result.payloads.length, 1);
    assert.equal(result.payloads[0].data.toString(), 'qkl archive payload');
});

test('AST reader preserves separate entries that share the same ID', async () => {
    const duplicateId = [9, 8, 7, 6, 5, 4, 3, 2];
    const archive = makeArchive([
        { id: duplicateId, data: Buffer.from('first') },
        { id: duplicateId, data: Buffer.from('second') },
    ]);
    const result = await parseArchive(archive);
    assert.equal(result.toc.length, 2);
    assert.deepEqual(result.toc.map((entry) => entry.index), [0, 1]);
    assert.deepEqual(result.toc.map((entry) => entry.id.toString('hex')),
        [Buffer.from(duplicateId).toString('hex'), Buffer.from(duplicateId).toString('hex')]);
    assert.deepEqual(result.payloads.map((entry) => entry.data.toString()), ['first', 'second']);
});

test('AST TOC-only mode reads the directory without extracting large payloads', async () => {
    const archive = makeArchive([
        { data: Buffer.alloc(256 * 1024, 0x5a) },
        { data: Buffer.from('another entry') },
    ]);
    const result = await parseArchive(archive, false);
    assert.equal(result.toc.length, 2);
    assert.deepEqual(result.payloads, []);
});
