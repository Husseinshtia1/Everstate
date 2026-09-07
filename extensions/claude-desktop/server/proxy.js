"use strict";

const fs = require("fs");
const path = require("path");
const { spawn } = require("child_process");

function fatal(message) {
  process.stderr.write(`[everstate-capture] ${message}\n`);
  process.exit(2);
}

const command = (process.env.EVERSTATE_MCP_COMMAND || "").trim();
const allowedRoot = (process.env.EVERSTATE_ALLOWED_ROOT || "").trim();
const everstateHome = (process.env.EVERSTATE_HOME || "").trim();

if (!command) {
  fatal("EVERSTATE_MCP_COMMAND is not configured.");
}
if (!path.isAbsolute(command)) {
  fatal("Everstate MCP executable must be an absolute path.");
}
if (!fs.existsSync(command)) {
  fatal(`Everstate MCP executable does not exist: ${command}`);
}
if (!allowedRoot) {
  fatal("EVERSTATE_ALLOWED_ROOT is not configured.");
}
if (!path.isAbsolute(allowedRoot)) {
  fatal("Project root must be an absolute path.");
}
if (!fs.existsSync(allowedRoot) || !fs.statSync(allowedRoot).isDirectory()) {
  fatal(`Configured project root does not exist or is not a directory: ${allowedRoot}`);
}
if (!everstateHome) {
  fatal("EVERSTATE_HOME is not configured.");
}
if (!path.isAbsolute(everstateHome)) {
  fatal("Everstate home must be an absolute path.");
}
if (!fs.existsSync(everstateHome) || !fs.statSync(everstateHome).isDirectory()) {
  fatal(`Configured Everstate home does not exist or is not a directory: ${everstateHome}`);
}

// Never invoke a shell. The selected executable is launched directly so project
// names, spaces, or metacharacters cannot become shell syntax.
const child = spawn(command, [], {
  stdio: ["pipe", "pipe", "pipe"],
  env: {
    ...process.env,
    EVERSTATE_ALLOWED_ROOT: allowedRoot,
    EVERSTATE_HOME: everstateHome,
  },
  shell: false,
});

process.stdin.pipe(child.stdin);
child.stdout.pipe(process.stdout);
child.stderr.pipe(process.stderr);

child.on("error", (error) => {
  fatal(`Failed to start Everstate MCP runtime: ${error.message}`);
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.stderr.write(`[everstate-capture] child exited via signal ${signal}\n`);
    process.exit(1);
  }
  process.exit(code == null ? 1 : code);
});

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => {
    if (!child.killed) {
      child.kill(signal);
    }
  });
}
