#!/usr/bin/env node
/**
 * Unified cross-platform hook dispatcher for Satz-Browser (Antigravity & Claude Code).
 *
 * Resolves REPO_ROOT from import.meta.url so cwd differences (.agents/ vs repo root)
 * and Windows Store python3.exe stubs never break hook execution.
 */

import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const HOOK_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(HOOK_DIR, "..", "..", "..");
const WIN_APPS_MARKER = `${path.sep}windowsapps${path.sep}`;

function isClaudePayloadText(stdinText) {
  try {
    const parsed = JSON.parse(stdinText || "{}");
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return false;
    }
    for (const key of ["hook_event_name", "tool_name", "tool_input", "stop_hook_active"]) {
      if (Object.prototype.hasOwnProperty.call(parsed, key)) {
        return true;
      }
    }
    if (
      Object.prototype.hasOwnProperty.call(parsed, "prompt") &&
      !Object.prototype.hasOwnProperty.call(parsed, "lastUserInput") &&
      !Object.prototype.hasOwnProperty.call(parsed, "hookEventName")
    ) {
      return true;
    }
  } catch {
    // Non-JSON stdin defaults to host prompt fallback rather than silent denial.
  }
  return false;
}

function emitNoop(hookName = "", stdinText = "") {
  if (hookName === "pre_tool_guard" && !isClaudePayloadText(stdinText)) {
    process.stdout.write(`${JSON.stringify({ decision: "ask" })}\n`);
    return;
  }
  process.stdout.write("{}\n");
}

function readStdinText() {
  try {
    return fs.readFileSync(0, "utf8");
  } catch {
    return "{}";
  }
}

function isUsableExecutable(candidate) {
  if (!candidate) return false;
  if (process.platform === "win32" && candidate.toLowerCase().includes(WIN_APPS_MARKER)) {
    return false;
  }
  try {
    return fs.existsSync(candidate) && fs.statSync(candidate).isFile();
  } catch {
    return false;
  }
}

function resolveFromPathWin(cmdName) {
  try {
    const res = spawnSync("where.exe", [cmdName], {
      encoding: "utf8",
      timeout: 2000,
      windowsHide: true,
    });
    if (res.status !== 0 || !res.stdout) return null;
    const lines = res.stdout
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean);
    for (const line of lines) {
      if (isUsableExecutable(line)) {
        return line;
      }
    }
  } catch {
    // Ignore PATH probe errors.
  }
  return null;
}

function resolvePythonExecutable() {
  const envPy = process.env.SATZ_PYTHON;
  if (envPy && isUsableExecutable(envPy)) {
    return envPy;
  }

  const isWin = process.platform === "win32";
  const localAppData = process.env.LOCALAPPDATA || "";
  const fileCandidates = isWin
    ? [
        path.join(REPO_ROOT, ".venv", "Scripts", "python.exe"),
        path.join(REPO_ROOT, "..", "sgs", ".venv", "Scripts", "python.exe"),
        localAppData ? path.join(localAppData, "Programs", "Python", "Python312", "python.exe") : "",
        localAppData ? path.join(localAppData, "Programs", "Python", "Python313", "python.exe") : "",
        localAppData ? path.join(localAppData, "Programs", "Python", "Python311", "python.exe") : "",
        "C:\\Python312\\python.exe",
      ]
    : [
        path.join(REPO_ROOT, ".venv", "bin", "python3"),
        path.join(REPO_ROOT, ".venv", "bin", "python"),
        path.join(REPO_ROOT, "..", "sgs", ".venv", "bin", "python3"),
        path.join(REPO_ROOT, "..", "sgs", ".venv", "bin", "python"),
        "/opt/homebrew/bin/python3",
        "/usr/local/bin/python3",
        "/usr/bin/python3",
      ];

  for (const candidate of fileCandidates) {
    if (isUsableExecutable(candidate)) {
      return candidate;
    }
  }

  if (isWin) {
    return resolveFromPathWin("python") || resolveFromPathWin("python3");
  }
  return "python3";
}

function main() {
  const hookName = (process.argv[2] || "").trim();
  if (!/^[a-z0-9_]+$/.test(hookName)) {
    process.stderr.write(`[satz-hook] Invalid hook name: ${hookName}\n`);
    emitNoop();
    return;
  }

  const stdinText = readStdinText();
  const scriptPath = path.join(HOOK_DIR, `${hookName}.py`);
  if (!fs.existsSync(scriptPath)) {
    process.stderr.write(`[satz-hook:${hookName}] Missing hook script: ${scriptPath}\n`);
    emitNoop(hookName, stdinText);
    return;
  }

  const pythonExe = resolvePythonExecutable();
  if (!pythonExe) {
    process.stderr.write(`[satz-hook:${hookName}] No usable Python interpreter found.\n`);
    emitNoop(hookName, stdinText);
    return;
  }

  const result = spawnSync(pythonExe, [scriptPath], {
    cwd: REPO_ROOT,
    input: stdinText || "{}",
    encoding: "utf8",
    timeout: 12000,
    windowsHide: true,
    env: {
      ...process.env,
      PYTHONUTF8: "1",
      PYTHONIOENCODING: "utf-8",
      PYTHONDONTWRITEBYTECODE: "1",
      SATZ_REPO_ROOT: REPO_ROOT,
    },
  });

  if (result.error || result.status !== 0) {
    const errMsg = result.error ? result.error.message : (result.stderr || `exit ${result.status}`);
    process.stderr.write(`[satz-hook:${hookName}] ${String(errMsg).trim()}\n`);
    emitNoop(hookName, stdinText);
    return;
  }

  const out = (result.stdout || "").trim();
  if (!out) {
    emitNoop(hookName, stdinText);
    return;
  }

  try {
    const parsed = JSON.parse(out);
    process.stdout.write(`${JSON.stringify(parsed)}\n`);
  } catch {
    process.stderr.write(`[satz-hook:${hookName}] Non-JSON hook stdout ignored.\n`);
    emitNoop(hookName, stdinText);
  }
}

main();
