#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import ts from "typescript";

const ROOT = path.resolve(import.meta.dirname, "..");
const SRC_DIR = path.join(ROOT, "src");
const CATALOG_FILE = path.join(SRC_DIR, "i18n", "catalog.ts");

function extractPlaceholders(str) {
  const found = new Set();
  const re = /\{([a-zA-Z0-9_]+)\}/g;
  let m;
  while ((m = re.exec(str)) !== null) {
    found.add(m[1]);
  }
  return [...found].sort();
}

function getAllTsFiles(dir) {
  const out = [];
  for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, ent.name);
    if (ent.isDirectory()) {
      if (ent.name === "i18n") continue;
      out.push(...getAllTsFiles(full));
    } else if (ent.isFile() && ent.name.endsWith(".ts") && !ent.name.endsWith(".d.ts")) {
      out.push(full);
    }
  }
  return out.sort();
}

function parseCatalogEntries() {
  if (!fs.existsSync(CATALOG_FILE)) {
    return null;
  }
  const text = fs.readFileSync(CATALOG_FILE, "utf8");
  const sf = ts.createSourceFile(CATALOG_FILE, text, ts.ScriptTarget.Latest, true);
  const entries = new Map();

  function readObjProp(objLit, name) {
    for (const prop of objLit.properties) {
      if (ts.isPropertyAssignment(prop)) {
        const pname = ts.isIdentifier(prop.name)
          ? prop.name.text
          : ts.isStringLiteral(prop.name)
            ? prop.name.text
            : "";
        if (pname === name) {
          if (ts.isStringLiteral(prop.initializer) || ts.isNoSubstitutionTemplateLiteral(prop.initializer)) {
            return prop.initializer.text;
          }
        }
      }
    }
    return undefined;
  }

  function visit(node) {
    if (ts.isVariableDeclaration(node) && node.name.getText(sf) === "EN_CATALOG" && node.initializer) {
      let expr = node.initializer;
      while (ts.isAsExpression(expr) || ts.isSatisfiesExpression(expr)) {
        expr = expr.expression;
      }
      if (ts.isObjectLiteralExpression(expr)) {
        for (const prop of expr.properties) {
          if (!ts.isPropertyAssignment(prop)) continue;
          const key = ts.isStringLiteral(prop.name)
            ? prop.name.text
            : ts.isIdentifier(prop.name)
              ? prop.name.text
              : "";
          if (!key) continue;
          if (ts.isStringLiteral(prop.initializer) || ts.isNoSubstitutionTemplateLiteral(prop.initializer)) {
            entries.set(key, { text: prop.initializer.text });
          } else if (ts.isObjectLiteralExpression(prop.initializer)) {
            entries.set(key, {
              text: readObjProp(prop.initializer, "text") ?? "",
              one: readObjProp(prop.initializer, "one"),
              hint: readObjProp(prop.initializer, "hint"),
            });
          }
        }
      }
    }
    ts.forEachChild(node, visit);
  }
  visit(sf);
  return entries;
}

function collectCallSites(files) {
  const calls = [];
  for (const file of files) {
    const srcText = fs.readFileSync(file, "utf8");
    const sf = ts.createSourceFile(file, srcText, ts.ScriptTarget.Latest, true);
    const rel = path.relative(ROOT, file);

    function visit(node) {
      if (ts.isCallExpression(node)) {
        const fnName = ts.isIdentifier(node.expression) ? node.expression.text : "";
        if ((fnName === "t" || fnName === "tCount") && node.arguments.length >= 1) {
          const arg0 = node.arguments[0];
          const line = sf.getLineAndCharacterOfPosition(node.getStart(sf)).line + 1;
          if (ts.isStringLiteral(arg0)) {
            const passedVars = [];
            const varsArgIdx = fnName === "tCount" ? 2 : 1;
            const varsArg = node.arguments[varsArgIdx];
            if (varsArg && ts.isObjectLiteralExpression(varsArg)) {
              for (const p of varsArg.properties) {
                if (ts.isPropertyAssignment(p) && ts.isIdentifier(p.name)) {
                  passedVars.push(p.name.text);
                } else if (ts.isShorthandPropertyAssignment(p)) {
                  passedVars.push(p.name.text);
                }
              }
            }
            calls.push({ file: rel, line, fn: fnName, key: arg0.text, passedVars, hasDynamicVars: Boolean(varsArg && !ts.isObjectLiteralExpression(varsArg)) });
          }
        }
      }
      ts.forEachChild(node, visit);
    }
    visit(sf);
  }
  return calls;
}

function scanHtmlCandidateStrings(files) {
  const results = [];
  const skipTags = /<\/?(style|script|svg|path)\b/i;
  for (const file of files) {
    const srcText = fs.readFileSync(file, "utf8");
    const sf = ts.createSourceFile(file, srcText, ts.ScriptTarget.Latest, true);
    const rel = path.relative(ROOT, file);
    const fileHits = [];

    function checkText(raw, pos) {
      if (!raw || raw.length < 2) return;
      if (/^\s*$/.test(raw)) return;
      if (skipTags.test(raw)) return;
      // Extract HTML text segments & attribute values like title="..." placeholder="..." aria-label="..."
      const attrRe = /\b(title|placeholder|aria-label)="([^"${}]+)"/g;
      let am;
      while ((am = attrRe.exec(raw)) !== null) {
        const val = am[2].trim();
        if (/[A-Za-z]{2,}/.test(val)) {
          const line = sf.getLineAndCharacterOfPosition(pos).line + 1;
          fileHits.push({ line, kind: `attr:${am[1]}`, text: val });
        }
      }
      const stripped = raw
        .replace(/<[^>]+>/g, "\n")
        .split("\n")
        .map((s) => s.replace(/\s+/g, " ").trim())
        .filter((s) => s.length >= 2 && /[A-Za-z]{2,}/.test(s) && !/^https?:\/\//.test(s));
      for (const seg of stripped) {
        const line = sf.getLineAndCharacterOfPosition(pos).line + 1;
        fileHits.push({ line, kind: "html-text", text: seg.slice(0, 120) });
      }
    }

    function visit(node) {
      if (ts.isNoSubstitutionTemplateLiteral(node) || ts.isTemplateHead(node) || ts.isTemplateMiddle(node) || ts.isTemplateTail(node)) {
        if (node.text.includes("<") || node.text.includes('placeholder="') || node.text.includes('title="') || node.text.includes('aria-label="')) {
          checkText(node.text, node.getStart(sf));
        }
      }
      ts.forEachChild(node, visit);
    }
    visit(sf);
    if (fileHits.length > 0) {
      results.push({ file: rel, count: fileHits.length, samples: fileHits });
    }
  }
  return results;
}

const args = process.argv.slice(2);
const modeCheck = args.includes("--check");
const modeScan = args.includes("--scan") || !modeCheck;
const files = getAllTsFiles(SRC_DIR);

if (modeScan) {
  const hits = scanHtmlCandidateStrings(files);
  let total = 0;
  for (const h of hits) {
    total += h.count;
    console.log(`${h.file}: ${h.count} inline UI fragments`);
  }
  console.log(`Total scanned fragments: ${total}`);
  if (args.includes("--dump")) {
    for (const h of hits) {
      console.log(`\n=== ${h.file} ===`);
      for (const s of h.samples) {
        console.log(`  L${s.line} [${s.kind}] ${s.text}`);
      }
    }
  }
}

if (modeCheck) {
  const catalog = parseCatalogEntries();
  if (!catalog) {
    console.error("ERROR: src/i18n/catalog.ts or EN_CATALOG not found.");
    process.exit(1);
  }
  const calls = collectCallSites(files);
  const errors = [];
  const usedKeys = new Set();

  for (const [k, entry] of catalog.entries()) {
    if (!entry.text) {
      errors.push(`Empty text in EN_CATALOG["${k}"]`);
    }
    if (/[\u2014\u2013]/.test(entry.text) || (entry.one && /[\u2014\u2013]/.test(entry.one))) {
      errors.push(`Disallowed em/en dash in EN_CATALOG["${k}"]`);
    }
    if (entry.one) {
      const pText = extractPlaceholders(entry.text).join(",");
      const pOne = extractPlaceholders(entry.one).join(",");
      if (pText !== pOne) {
        errors.push(`Plural placeholder mismatch in EN_CATALOG["${k}"]: text=[${pText}] one=[${pOne}]`);
      }
    }
  }

  for (const call of calls) {
    usedKeys.add(call.key);
    const entry = catalog.get(call.key);
    if (!entry) {
      errors.push(`${call.file}:${call.line} unknown key "${call.key}"`);
      continue;
    }
    if (!call.hasDynamicVars) {
      const req = extractPlaceholders(entry.text).filter((v) => !(call.fn === "tCount" && v === "count"));
      for (const v of req) {
        if (!call.passedVars.includes(v)) {
          errors.push(`${call.file}:${call.line} missing var "{${v}}" for "${call.key}"`);
        }
      }
    }
  }

  const unused = [...catalog.keys()].filter((k) => !usedKeys.has(k));
  console.log(`Catalog keys: ${catalog.size}, call sites: ${calls.length}, unused: ${unused.length}, errors: ${errors.length}`);
  if (errors.length > 0) {
    for (const err of errors) console.error("ERROR:", err);
    process.exit(1);
  }
}
