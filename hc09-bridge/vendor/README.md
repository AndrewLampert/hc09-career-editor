# vendor/node_modules

The libraries the bridge (`../bridge.js`) needs, shipped with the editor so that **no `npm install`, no internet and no compiler (no Visual Studio) are needed**. `bridge.js` looks here first; only Node.js 18+ has to be installed.

| Package | Version | Licence | What for |
|---|---|---|---|
| madden-file-tools | 2.4.13 | MIT | reads and writes the games' database and archive files |
| bit-buffer | 0.2.5 | MIT | used by madden-file-tools |
| crc-32 | 1.2.2 | Apache-2.0 | used by madden-file-tools |
| debug | 2.6.9 | MIT | used by madden-file-tools |
| ms | 2.0.0 | MIT | used by debug |
| leb | 0.3.0 | Apache-2.0 | used by madden-file-tools |
| stream-parser | 0.3.1 | MIT | used by madden-file-tools |
| lz4 | 0.6.5 (stand-in) | MIT | **not the real package**: `shims/lz4` copied here, a pure-JavaScript `decodeBlock` (the only lz4 function madden-file-tools calls). The real package compiles a native add-on and needs Visual Studio on Windows. |

Each package keeps its own licence file next to its code.

## Updating

This is the tree `npm install` makes in `../` (see `../package.json` and `../package-lock.json`), minus `.bin`. To update a library: run `npm install` in a scratch copy of `hc09-bridge`, copy the changed package folders here, keep `lz4` as the copy of `../shims/lz4`, and run the test suite (`bridge_install_test.py` checks that this folder has no compiled add-on, that `lz4` equals the stand-in and that every package has a licence file).
