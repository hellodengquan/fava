import { mkdirSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from "node:fs";
import { join, relative } from "node:path";

const ROOT_DIR = join(import.meta.dirname, "..");
const FRONTEND_SRC_DIR = join(ROOT_DIR, "frontend", "src");
const TRANSLATIONS_DIR = join(ROOT_DIR, "src", "fava", "translations");
const POT_FILE = join(TRANSLATIONS_DIR, "messages.pot");

const args = process.argv.slice(2);
const strictMode = args.includes("--strict");
const reportPath = args.find((a) => a.startsWith("--report="))?.split("=")[1];
const selfTestMode = args.includes("--self-test");
const verboseMode = args.includes("--verbose");

function walkDir(dir: string, exts: string[]): string[] {
  const results: string[] = [];
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

function extractI18nKeysFromSources(srcDir: string): Map<string, string[]> {
  const files = walkDir(srcDir, [".svelte", ".ts"]);
  const keyToFiles = new Map<string, string[]>();

  const singleQuotePattern = /_\(\s*'((?:[^'\\]|\\.)*)'\s*\)/g;
  const doubleQuotePattern = /_\(\s*"((?:[^"\\]|\\.)*)"\s*\)/g;
  const backtickPattern = /_\(\s*`((?:[^`\\]|\\.)*)`\s*\)/g;

  for (const file of files) {
    const content = readFileSync(file, "utf-8");
    const relPath = relative(ROOT_DIR, file);

    const patterns = [singleQuotePattern, doubleQuotePattern, backtickPattern];
    for (const pattern of patterns) {
      let match: RegExpExecArray | null;
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
        keyToFiles.get(key)!.push(relPath);
      }
    }
  }

  return keyToFiles;
}

interface PoEntry {
  translation: string;
  isFuzzy: boolean;
}

function parsePoFile(poFilePath: string): Map<string, PoEntry> {
  const content = readFileSync(poFilePath, "utf-8");
  const keys = new Map<string, PoEntry>();
  let currentMsgid: string | null = null;
  let currentMsgstr: string | null = null;
  let currentIsFuzzy = false;
  let nextIsFuzzy = false;
  let isHeader = true;

  const lines = content.split("\n");

  for (const line of lines) {
    if (line.startsWith("#,") && line.includes("fuzzy")) {
      nextIsFuzzy = true;
      continue;
    }
    if (line.startsWith("#")) {
      continue;
    }

    if (line.startsWith("msgid ")) {
      if (currentMsgid !== null && !isHeader) {
        keys.set(currentMsgid, {
          translation: currentMsgstr ?? "",
          isFuzzy: currentIsFuzzy,
        });
      }
      isHeader = false;
      currentMsgid = extractPoString(line.slice(6));
      currentMsgstr = null;
      currentIsFuzzy = nextIsFuzzy;
      nextIsFuzzy = false;
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
    keys.set(currentMsgid, {
      translation: currentMsgstr ?? "",
      isFuzzy: currentIsFuzzy,
    });
  }

  return keys;
}

function parsePotFile(potFilePath: string): Set<string> {
  const keys = new Set<string>();
  let currentMsgid: string | null = null;
  let isHeader = true;

  const content = readFileSync(potFilePath, "utf-8");
  const lines = content.split("\n");

  for (const line of lines) {
    if (line.startsWith("#")) {
      continue;
    }

    if (line.startsWith("msgid ")) {
      if (currentMsgid !== null && !isHeader) {
        keys.add(currentMsgid);
      }
      isHeader = false;
      currentMsgid = extractPoString(line.slice(6));
      continue;
    }

    if (line.startsWith("msgstr ")) {
      continue;
    }

    if (line.startsWith('"') && currentMsgid !== null) {
      currentMsgid += extractPoString(line);
    }
  }

  if (currentMsgid !== null && !isHeader) {
    keys.add(currentMsgid);
  }

  return keys;
}

function extractPoString(s: string): string {
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

function getLanguageDirs(translationsDir: string): string[] {
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

interface TargetLangIssue {
  missing: { key: string; files: string[]; reason: string }[];
  fuzzy: { key: string; files: string[] }[];
}

interface CheckResult {
  frontendKeys: Map<string, string[]>;
  potKeys: Set<string>;
  missingFromPot: { key: string; files: string[] }[];
  targetLangReport: Map<string, TargetLangIssue>;
}

function runCheck(
  frontendKeys: Map<string, string[]>,
  potKeys: Set<string>,
  translationsDir: string,
  languages: string[],
): CheckResult {
  const missingFromPot: { key: string; files: string[] }[] = [];

  for (const [key, files] of frontendKeys) {
    if (!potKeys.has(key)) {
      missingFromPot.push({ key, files: [...new Set(files)] });
    }
  }

  const targetLangReport = new Map<string, TargetLangIssue>();

  for (const lang of languages) {
    const poFile = join(translationsDir, lang, "LC_MESSAGES", "messages.po");
    let poKeys: Map<string, PoEntry>;
    try {
      poKeys = parsePoFile(poFile);
    } catch {
      console.warn(`  Warning: Could not parse ${poFile}`);
      continue;
    }

    const missing: { key: string; files: string[]; reason: string }[] = [];
    const fuzzy: { key: string; files: string[] }[] = [];

    for (const key of potKeys) {
      if (!frontendKeys.has(key)) {
        continue;
      }
      const files = frontendKeys.get(key)!;
      const entry = poKeys.get(key);
      if (!entry) {
        missing.push({
          key,
          files: [...new Set(files)],
          reason: "key_not_found",
        });
      } else if (entry.translation === "") {
        missing.push({
          key,
          files: [...new Set(files)],
          reason: "translation_empty",
        });
      } else if (entry.isFuzzy) {
        fuzzy.push({ key, files: [...new Set(files)] });
      }
    }

    if (missing.length > 0 || fuzzy.length > 0) {
      targetLangReport.set(lang, { missing, fuzzy });
    }
  }

  return { frontendKeys, potKeys, missingFromPot, targetLangReport };
}

function printReport(result: CheckResult): void {
  const { frontendKeys, potKeys, missingFromPot, targetLangReport } = result;
  const numLangs = getLanguageDirs(TRANSLATIONS_DIR).length;

  console.log(`\n=== i18n Missing Translation Check ===\n`);
  console.log(`Frontend i18n keys found: ${frontendKeys.size}`);
  console.log(`Source template (.pot) keys: ${potKeys.size}`);
  console.log(`Languages to check: ${numLangs}\n`);

  console.log(`--- Source Template Check (.pot) ---`);
  if (missingFromPot.length === 0) {
    console.log(
      `✅ All frontend i18n keys are present in the source template.\n`,
    );
  } else {
    console.log(
      `❌ ${missingFromPot.length} frontend key(s) NOT FOUND in source template (.pot):\n`,
    );
    for (const { key, files } of missingFromPot) {
      const oneLineKey = key.replace(/\n/g, "\\n");
      console.log(`  [NOT IN .POT] "${oneLineKey}"`);
      console.log(`    Used in: ${files.join(", ")}`);
    }
    console.log("");
  }

  let totalMissing = 0;
  let totalFuzzy = 0;

  if (targetLangReport.size > 0) {
    console.log(`--- Target Language Translation Progress ---\n`);

    for (const [lang, { missing, fuzzy }] of targetLangReport) {
      totalMissing += missing.length;
      totalFuzzy += fuzzy.length;
      console.log(
        `  ${lang}: ${missing.length} missing, ${fuzzy.length} fuzzy`,
      );
    }

    console.log(
      `\n  Total across all target languages: ${totalMissing} missing, ${totalFuzzy} fuzzy`,
    );
    console.log(
      `  Note: Target language gaps are translation progress issues and do NOT fail strict mode.\n`,
    );
  } else {
    console.log(
      "✅ All target languages have complete translations for frontend keys.\n",
    );
  }

  console.log(`=== Summary ===`);
  console.log(`Source template gaps (CRITICAL): ${missingFromPot.length}`);
  console.log(`Total target language missing (INFO): ${totalMissing}`);
  console.log(`Total target language fuzzy (INFO): ${totalFuzzy}`);
}

function printDetailedTargetReport(
  targetLangReport: Map<string, TargetLangIssue>,
): void {
  console.log(`\n=== Detailed Target Language Report ===`);

  for (const [lang, { missing, fuzzy }] of targetLangReport) {
    console.log(`\n--- Language: ${lang} ---`);

    if (missing.length > 0) {
      console.log(`\n  Missing translations (${missing.length}):`);
      for (const { key, files, reason } of missing) {
        const reasonLabel =
          reason === "key_not_found" ? "[NOT IN PO]" : "[EMPTY MSGSTR]";
        const oneLineKey = key.replace(/\n/g, "\\n");
        console.log(`    ${reasonLabel} "${oneLineKey}"`);
        console.log(`      Used in: ${files.join(", ")}`);
      }
    }

    if (fuzzy.length > 0) {
      console.log(`\n  Fuzzy translations (${fuzzy.length}):`);
      for (const { key, files } of fuzzy) {
        const oneLineKey = key.replace(/\n/g, "\\n");
        console.log(`    [FUZZY] "${oneLineKey}"`);
        console.log(`      Used in: ${files.join(", ")}`);
      }
    }
  }
}

function generateJsonReport(
  result: CheckResult,
  reportPath: string,
): void {
  const { frontendKeys, potKeys, missingFromPot, targetLangReport } = result;

  const jsonReport = {
    generatedAt: new Date().toISOString(),
    totalFrontendKeys: frontendKeys.size,
    totalPotKeys: potKeys.size,
    sourceTemplate: {
      missingCount: missingFromPot.length,
      missing: missingFromPot.map(({ key, files }) => ({ key, files })),
    },
    targetLanguages: Object.fromEntries(
      [...targetLangReport.entries()].map(([lang, { missing, fuzzy }]) => [
        lang,
        {
          missingCount: missing.length,
          fuzzyCount: fuzzy.length,
          missing: missing.map(({ key, reason, files }) => ({
            key,
            reason,
            files,
          })),
          fuzzy: fuzzy.map(({ key, files }) => ({ key, files })),
        },
      ]),
    ),
  };

  writeFileSync(reportPath, JSON.stringify(jsonReport, null, 2) + "\n");
  console.log(`\n📄 JSON report written to: ${reportPath}`);
}

function determineExitCode(result: CheckResult): number {
  const { missingFromPot } = result;

  if (strictMode) {
    if (missingFromPot.length > 0) {
      console.log(
        `\n❌ [STRICT MODE FAIL] ${missingFromPot.length} frontend key(s) missing from source template (.pot). CI will fail.`,
      );
      console.log(
        "   These keys are used in the code but not registered in the translation template.",
      );
      console.log(
        "   Fix: Run 'make src/fava/translations/messages.pot' to update the template.\n",
      );
      return 1;
    }
    console.log(
      "\n✅ [STRICT MODE PASS] All frontend keys are present in the source template.",
    );
    console.log(
      "   Target language translation gaps are not considered errors in strict mode.\n",
    );
    return 0;
  }

  console.log("");
  return 0;
}

function runSelfTest(): void {
  console.log("Running self-test...\n");

  let passed = 0;
  let failed = 0;

  function assert(condition: boolean, message: string): void {
    if (condition) {
      console.log(`  ✅ ${message}`);
      passed++;
    } else {
      console.log(`  ❌ ${message}`);
      failed++;
    }
  }

  const mockFrontendKeys = new Map<string, string[]>([
    ["Hello World", ["src/a.ts"]],
    ["Goodbye", ["src/b.ts", "src/c.svelte"]],
    ["Orphan Key", ["src/orphan.ts"]],
    ["Multi\nLine", ["src/multi.ts"]],
  ]);

  const mockPotKeys = new Set(["Hello World", "Goodbye", "Multi\nLine"]);

  const mockLangs = ["complete-lang", "partial-lang", "partial-lang-2"];
  const mockTranslationsDir = join(
    import.meta.dirname,
    "..",
    "frontend",
    ".self-test-tmp",
  );

  try {
    rmSync(mockTranslationsDir, { recursive: true, force: true });

    for (const lang of mockLangs) {
      mkdirSync(join(mockTranslationsDir, lang, "LC_MESSAGES"), {
        recursive: true,
      });
    }

    writeFileSync(
      join(
        mockTranslationsDir,
        "complete-lang",
        "LC_MESSAGES",
        "messages.po",
      ),
      [
        `msgid ""`,
        `msgstr ""`,
        `"Project-Id-Version: test\\n"`,
        ``,
        `msgid "Hello World"`,
        `msgstr "Hallo Welt"`,
        ``,
        `msgid "Goodbye"`,
        `msgstr "Auf Wiedersehen"`,
        ``,
        `msgid "Multi\\nLine"`,
        `msgstr "Mehr\\nZeilig"`,
        ``,
      ].join("\n"),
    );

    writeFileSync(
      join(
        mockTranslationsDir,
        "partial-lang",
        "LC_MESSAGES",
        "messages.po",
      ),
      [
        `msgid ""`,
        `msgstr ""`,
        `"Project-Id-Version: test\\n"`,
        ``,
        `msgid "Hello World"`,
        `msgstr ""`,
        ``,
        `#, fuzzy`,
        `msgid "Goodbye"`,
        `msgstr "Tschüss"`,
        ``,
        `msgid "Multi\\nLine"`,
        `msgstr "Mehr\\nZeilig"`,
        ``,
      ].join("\n"),
    );

    writeFileSync(
      join(
        mockTranslationsDir,
        "partial-lang-2",
        "LC_MESSAGES",
        "messages.po",
      ),
      [
        `msgid ""`,
        `msgstr ""`,
        `"Project-Id-Version: test\\n"`,
        ``,
        `msgid "Hello World"`,
        `msgstr "Hola Mundo"`,
        ``,
      ].join("\n"),
    );

    const result = runCheck(
      mockFrontendKeys,
      mockPotKeys,
      mockTranslationsDir,
      mockLangs,
    );

    assert(
      result.missingFromPot.length === 1,
      "Should detect 1 key missing from .pot",
    );
    assert(
      result.missingFromPot[0].key === "Orphan Key",
      "'Orphan Key' should be identified as missing from .pot",
    );

    assert(
      result.targetLangReport.size === 2,
      "2 of 3 target languages should have issues",
    );
    assert(
      !result.targetLangReport.has("complete-lang"),
      "Complete language should NOT appear in report",
    );

    const partialLang = result.targetLangReport.get("partial-lang");
    assert(
      partialLang !== undefined,
      "Partial language should appear in report",
    );
    if (partialLang) {
      const helloEntry = partialLang.missing.find(
        (m) => m.key === "Hello World",
      );
      assert(
        helloEntry !== undefined && helloEntry.reason === "translation_empty",
        "Empty msgstr should be detected as missing in target language",
      );
      const goodbyeEntry = partialLang.fuzzy.find((f) => f.key === "Goodbye");
      assert(
        goodbyeEntry !== undefined,
        "Fuzzy entries should be detected in target language",
      );
    }

    const partialLang2 = result.targetLangReport.get("partial-lang-2");
    assert(
      partialLang2 !== undefined,
      "Partial language 2 should appear in report",
    );
    if (partialLang2) {
      const missingKeys = partialLang2.missing.map((m) => m.key);
      assert(
        missingKeys.includes("Goodbye"),
        "Key not present in .po should be detected as missing",
      );
      assert(
        !missingKeys.includes("Orphan Key"),
        "Keys missing from .pot should NOT appear in target language missing list",
      );
    }

    const multiLineInPot = result.missingFromPot.find(
      (m) => m.key === "Multi\nLine",
    );
    assert(
      multiLineInPot === undefined,
      "Multi-line keys should be parsed and matched correctly between .pot and frontend",
    );

    const partialLang2Orphan = partialLang2?.missing.find(
      (m) => m.key === "Orphan Key",
    );
    assert(
      partialLang2Orphan === undefined,
      "Orphan key (not in .pot) should not be reported as missing in target languages",
    );

    rmSync(mockTranslationsDir, { recursive: true, force: true });

    console.log(`\nSelf-test result: ${passed} passed, ${failed} failed`);
    if (failed > 0) {
      console.log("❌ Some self-tests failed!\n");
      process.exit(1);
    } else {
      console.log("✅ All self-tests passed!\n");
      process.exit(0);
    }
  } catch (err) {
    console.error("Self-test error:", err);
    process.exit(1);
  }
}

function main(): void {
  if (selfTestMode) {
    runSelfTest();
    return;
  }

  const frontendKeys = extractI18nKeysFromSources(FRONTEND_SRC_DIR);
  const potKeys = parsePotFile(POT_FILE);
  const languages = getLanguageDirs(TRANSLATIONS_DIR);

  const result = runCheck(frontendKeys, potKeys, TRANSLATIONS_DIR, languages);

  printReport(result);

  if (verboseMode || reportPath) {
    printDetailedTargetReport(result.targetLangReport);
  }

  if (reportPath) {
    generateJsonReport(result, reportPath);
  }

  const exitCode = determineExitCode(result);
  process.exit(exitCode);
}

main();
