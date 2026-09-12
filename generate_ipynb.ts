/**
 * Writes Indian_Equity_Quantitative_Engine.ipynb from the current TypeScript.
 * run_checks.sh regenerates and byte-compares the result, so the shipped
 * notebook can never drift from python/engine.py.
 */
import fs from 'node:fs';
import { NOTEBOOK_FILENAME, serializeNotebook } from './src/utils/colabNotebookGenerator';

const output = serializeNotebook();
fs.writeFileSync(NOTEBOOK_FILENAME, output);
console.log(`Wrote ${NOTEBOOK_FILENAME} (${output.length} bytes)`);
