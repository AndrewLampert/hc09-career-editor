'use strict';

function validateAstHeader(header) {
    const entryLength = Number(header.individualTOCLength) + 1;
    const tableLength = Number(header.tableOfContentsLength) - Number(header.tableOfContentsAdditionalOffset);
    const declaredCount = Number(header.numberOfFiles);

    if (!Number.isSafeInteger(entryLength) || entryLength <= 1 ||
        !Number.isSafeInteger(tableLength) || tableLength < 0 ||
        tableLength % entryLength !== 0) {
        throw new Error('The archive has a damaged or incomplete table of contents.');
    }

    const actualCount = tableLength / entryLength;
    if (!Number.isSafeInteger(declaredCount) || declaredCount < 0 ||
        declaredCount !== actualCount) {
        throw new Error(
            `The archive header declares ${declaredCount} entries, but its table of contents contains ${actualCount}.`
        );
    }
    return actualCount;
}

module.exports = { validateAstHeader };
