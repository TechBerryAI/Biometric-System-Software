#!/usr/bin/env node
/**
 * Thin wrapper so `node start-vm.js` works from the repository root.
 * Real implementation: scripts/start-vm.js
 */
const { spawn } = require("child_process");
const path = require("path");

const script = path.join(__dirname, "scripts", "start-vm.js");
const child = spawn(process.execPath, [script, ...process.argv.slice(2)], {
  stdio: "inherit",
  env: process.env,
});
// Forward stop signals so the runner can shut its services down gracefully.
for (const signal of ["SIGINT", "SIGTERM", "SIGHUP"]) {
  process.on(signal, () => {
    try {
      child.kill(signal);
    } catch {
      /* already exited */
    }
  });
}
child.on("exit", (code, signal) => process.exit(code === null ? (signal ? 1 : 0) : code));
