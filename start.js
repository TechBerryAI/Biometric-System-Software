#!/usr/bin/env node
/**
 * Thin wrapper so `node start.js` works from the repository root.
 * Real implementation: scripts/start.js
 */
const { spawnSync } = require("child_process");
const path = require("path");

const script = path.join(__dirname, "scripts", "start.js");
const result = spawnSync(process.execPath, [script, ...process.argv.slice(2)], {
  stdio: "inherit",
  env: process.env,
});
process.exit(result.status === null ? 1 : result.status);
