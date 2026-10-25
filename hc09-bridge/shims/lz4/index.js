'use strict';
// A stand-in for the `lz4` npm package that needs no compiler.
//
// The real package compiles a native add-on when it is installed (node-gyp), which on Windows needs Visual Studio's C++ build tools. madden-file-tools requires it, but
// the only thing it ever calls is LZ4.decodeBlock (streams/CompressedLegacyFileReader.js), and the HC09 files this editor reads are compressed with zlib, so the
// editor does not need the compiled version at all. This file implements decodeBlock in plain JavaScript; everything else throws a clear error.

// Decode one LZ4 block. input: Buffer holding the whole block (or from sIdx to eIdx), output: a Buffer large enough for the decoded data.
// Returns the number of decoded bytes, or a negative number (minus the input offset where it went wrong) like the native version does.
function decodeBlock(input, output, sIdx, eIdx) {
    let i = sIdx || 0;
    const end = eIdx === undefined ? input.length : eIdx;
    let j = 0;
    while (i < end) {
        const token = input[i++];

        // literals
        let literals = token >> 4;
        if (literals === 15) {
            let extra;
            do {
                if (i >= end) return -i;
                extra = input[i++];
                literals += extra;
            } while (extra === 255);
        }
        if (literals > 0) {
            if (i + literals > end || j + literals > output.length) return -i;
            for (let k = 0; k < literals; k++) output[j++] = input[i++];
        }
        if (i >= end) break;                                    // the last sequence has literals only

        // match: a 16-bit little-endian offset back into the output, then a length
        if (i + 2 > end) return -i;
        const offset = input[i] | (input[i + 1] << 8);
        i += 2;
        if (offset === 0 || offset > j) return -(i - 2);
        let matchLength = token & 0x0f;
        if (matchLength === 15) {
            let extra;
            do {
                if (i >= end) return -i;
                extra = input[i++];
                matchLength += extra;
            } while (extra === 255);
        }
        matchLength += 4;
        if (j + matchLength > output.length) return -i;
        let from = j - offset;
        for (let k = 0; k < matchLength; k++) output[j++] = output[from++];     // byte by byte: the match may overlap what it writes
    }
    return j;
}

function notAvailable() {
    throw new Error('LZ4 compression is not available in this build of the bridge (the compiler-free lz4 stand-in only decodes blocks).');
}

module.exports = {
    decodeBlock,
    encodeBound: notAvailable,
    encodeBlock: notAvailable,
    encodeBlockHC: notAvailable,
    encode: notAvailable,
    decode: notAvailable,
    createEncoderStream: notAvailable,
    createDecoderStream: notAvailable,
};
