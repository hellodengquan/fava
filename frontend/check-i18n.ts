import { readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { join, relative } from "node:path";

const ROOT_DIR = join(import.meta.dirname, "..");
const FRONTEND_SRC_DIR = join(ROOT_DIR, "frontend", "src");
const TRANSLATIONS_DIR = join(ROOT_DIR, "src", "fava", "translations");

const args = process.argv.slice(2);
const strictMode = args.includes("--strict");
const reportPath = args.find((a) => a.startsWith("--report="))?.split("=")[1];

function walkDir(dir, exts) {
  const results = [];
  for (const entry of readdirSync(dir)) {
    const fullPath = join(dir, entry);
    const stat = statSync(fullPath);
    if (stat.isDirectory()) {
      results.push(...walkDir(fullPath, exts));
    } else if (exts.some((ext) => entry.endsWith(ext))) {
      results.push(fullPath);
    }
  }
  return results;
}

function extractI18nKeysFromSources(srcDir) {
  const files = walkDir(srcDir, [".svelte", ".ts"]);
  const keyToFiles = new Map();

  const singleQuotePattern = /_\(\s*'((?:[^'\\]|\\.)*)'\s*\)/g;
  const doubleQuotePattern = /_\(\s*"((?:[^"\\]|\\.)*)"\s*\)/g;
  const backtickPattern = /_\(\s*`((?:[^`\\]|\\.)*)`\s*\)/g;

  for (const file of files) {
    const content = readFileSync(file, "utf-8");
    const relPath = relative(ROOT_DIR, file);

    const patterns = [singleQuotePattern, doubleQuotePattern, backtickPattern];
    for (const pattern of patterns) {
      let match;
      while ((match = pattern.exec(content)) !== null) {
        const key = match[1]
          .replace(/\\n/g, "\n")
          .replace(/\\t/g, "\t")
          .replace(/\\'/g, "'")
          .replace(/\\"/g, '"')
          .replace(/\\`/g, "`")
          .replace(/\\\\/g, "\\");
        if (!keyToFiles.has(key)) {
          keyToFiles.set(key, []);
        }
        keyToFiles.get(key).push(relPath);
      }
    }
  }

  return keyToFiles;
}

function parsePoFile(poFilePath) {
  const content = readFileSync(poFilePath, "utf-8");
  const keys = new Map();
  let currentMsgid = null;
  let currentMsgstr = null;
  let isFuzzy = false;
  let isHeader = true;

  const lines = content.split("\n");

  for (const line of lines) {
    if (line.startsWith("#,") && line.includes("fuzzy")) {
      isFuzzy = true;
      continue;
    }
    if (line.startsWith("#")) {
      continue;
    }

    if (line.startsWith("msgid ")) {
      if (currentMsgid !== null && !isHeader) {
        keys.set(currentMsgid, { translation: currentMsgstr ?? "", isFuzzy });
      }
      isHeader = false;
      currentMsgid = extractPoString(line.slice(6));
      currentMsgstr = null;
      isFuzzy = false;
      continue;
    }

    if (line.startsWith("msgstr ")) {
      currentMsgstr = extractPoString(line.slice(7));
      continue;
    }

    if (line.startsWith('"') && currentMsgid !== null) {
      const continued = extractPoString(line);
      if (currentMsgstr === null) {
        currentMsgid += continued;
      } else {
        currentMsgstr += continued;
      }
    }
  }

  if (currentMsgid !== null && !isHeader) {
    keys.set(currentMsgid, { translation: currentMsgstr ?? "", isFuzzy });
  }

  return keys;
}

function extractPoString(s) {
  s = s.trim();
  if (s.startsWith('"') && s.endsWith('"')) {
    return s
      .slice(1, -1)
      .replace(/\\n/g, "\n")
      .replace(/\\t/g, "\t")
      .replace(/\\"/g, '"')
      .replace(/\\\\/g, "\\");
  }
  return s;
}

function getLanguageDirs(translationsDir) {
  const entries = readdirSync(translationsDir);
  return entries.filter((entry) => {
    const fullPath = join(translationsDir, entry);
    return (
      statSync(fullPath).isDirectory() &&
      entry !== "messages.pot" &&
      !entry.startsWith(".")
    );
  });
}

function checkMissingTranslations() {
  const frontendKeys = extractI18nKeysFromSources(FRONTEND_SRC_DIR);
  const languages = getLanguageDirs(TRANSLATIONS_DIR);

  const modeLabel = strictMode ? "STRICT" : "REPORT";
  console.log(`\n=== i18n Missing Translation Check [${modeLabel}] ===\n`);
  console.log(`Frontend i18n keys found: ${frontendKeys.size}`);
  console.log(`Languages to check: ${languages.join(", ")}\n`);

  const missingReport = new Map();
  let totalMissing = 0;
  let totalFuzzy = 0;

  for (const lang of languages) {
    const poFile = join(
      TRANSLATIONS_DIR,
      lang,
      "LC_MESSAGES",
      "messages.po",
    );
    let poKeys;
    try {
      poKeys = parsePoFile(poFile);
    } catch {
      console.warn(`  Warning: Could not parse ${poFile}`);
      continue;
    }

    const missing = [];
    const fuzzy = [];

    for (const [key, files] of frontendKeys) {
      const entry = poKeys.get(key);
      if (!entry) {
        missing.push({ key, files, reason: "key_not_found" });
      } else if (entry.translation === "") {
        missing.push({ key, files, reason: "translation_empty" });
      } else if (entry.isFuzzy) {
        fuzzy.push({ key, files });
      }
    }

    if (missing.length > 0 || fuzzy.length > 0) {
      missingReport.set(lang, { missing, fuzzy });
      totalMissing += missing.length;
      totalFuzzy += fuzzy.length;
    }
  }

  if (missingReport.size === 0) {
    console.log(
      "✅ All frontend i18n keys have translations in all languages!\n",
    );
    return 0;
  }

  for (const [lang, { missing, fuzzy }] of missingReport) {
    console.log(`\n--- Language: ${lang} ---`);

    if (missing.length > 0) {
      console.log(`\n  Missing translations (${missing.length}):`);
      for (const { key, files, reason } of missing) {
        const reasonLabel =
          reason === "key_not_found" ? "[NOT IN PO]" : "[EMPTY MSGSTR]";
        const oneLineKey = key.replace(/\n/g, "\\n");
        console.log(`    ${reasonLabel} "${oneLineKey}"`);
        console.log(`      Used in: ${[...new Set(files)].join(", ")}`);
      }
    }

    if (fuzzy.length > 0) {
      console.log(`\n  Fuzzy translations (${fuzzy.length}):`);
      for (const { key, files } of fuzzy) {
        const oneLineKey = key.replace(/\n/g, "\\n");
        console.log(`    [FUZZY] "${oneLineKey}"`);
        console.log(`      Used in: ${[...new Set(files)].join(", ")}`);
      }
    }
  }

  console.log(`\n=== Summary ===`);
  console.log(`Total missing translations: ${totalMissing}`);
  console.log(`Total fuzzy translations: ${totalFuzzy}`);
  console.log(
    `Languages with issues: ${[...missingReport.keys()].join(", ")}`,
  );

  if (reportPath) {
    const jsonReport = {
      generatedAt: new Date().toISOString(),
      totalFrontendKeys: frontendKeys.size,
      totalMissing,
      totalFuzzy,
      languages: Object.fromEntries(
        [...missingReport.entries()].map(([lang, { missing, fuzzy }]) => [
          lang,
          {
            missingCount: missing.length,
            fuzzyCount: fuzzy.length,
            missing: missing.map(({ key, files: f, reason }) => ({
              key,
              reason,
              files: [...new Set(f)],
            })),
            fuzzy: fuzzy.map(({ key, files: f }) => ({
              key,
              files: [...new Set(f)],
            })),
          },
        ]),
      ),
    };
    writeFileSync(reportPath, JSON.stringify(jsonReport, null, 2) + "\n");
    console.log(`\n📄 Report written to: ${reportPath}`);
  }

  if (strictMode) {
    console.log(
      `\n❌ [STRICT] Found ${totalMissing} missing + ${totalFuzzy} fuzzy translation(s). CI will fail.\n`,
    );
    return 1;
  }

  console.log(
    `\n⚠️  Found ${totalMissing} missing + ${totalFuzzy} fuzzy translation(s). Run with --strict to fail CI.\n`,
  );
  return 0;
}

const exitCode = checkMissingTranslations();
process.exit(exitCode);
