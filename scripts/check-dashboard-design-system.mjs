#!/usr/bin/env node
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const repoRoot = resolve(fileURLToPath(new URL('..', import.meta.url)));
const dashboardRoot = join(repoRoot, 'apps/dashboard-react');
const srcRoot = join(dashboardRoot, 'src');
const scope = readScope();

const requiredFiles = [
  'src/themes/tokens.css',
  'src/themes/light.css',
  'src/themes/dark.css',
];

const themeColorFiles = new Set([
  'src/themes/light.css',
  'src/themes/dark.css',
]);

const foundationFiles = [
  'src/index.css',
  ...requiredFiles,
  ...listFiles(join(srcRoot, 'shared/components/ui')).filter((file) => file.endsWith('.tsx')),
].map((file) => file.startsWith(srcRoot) ? file : join(dashboardRoot, file));

const allFiles = listFiles(srcRoot).filter((file) => /\.(css|tsx?)$/.test(file));
const filesToCheck = scope === 'all' ? allFiles : foundationFiles;
const failures = [];

for (const requiredFile of requiredFiles) {
  const absolute = join(dashboardRoot, requiredFile);
  try {
    statSync(absolute);
  } catch {
    failures.push(`Missing required theme file: ${requiredFile}`);
  }
}

for (const file of filesToCheck) {
  const rel = normalize(relative(dashboardRoot, file));
  const text = readFileSync(file, 'utf8');
  const allowsRawColor = themeColorFiles.has(rel);

  if (!allowsRawColor) {
    assertNoPattern(rel, text, /#[0-9a-fA-F]{3,8}\b/g, 'raw hex color');
    assertNoPattern(rel, text, /\brgba?\(/g, 'raw rgb/rgba color');
    assertNoPattern(rel, text, /\bhsla?\(/g, 'raw hsl/hsla color');
  }

  assertNoPattern(rel, text, /\bradar\b|color-radar|bg-radar|text-radar|border-radar/gi, 'retired radar color token');
  assertNoPattern(rel, text, /transition\s*:\s*all\b|transition-all/g, 'transition-all');
  assertNoPattern(rel, text, /Terminal|terminal|Orbitron|VT323|Share Tech Mono|scanline|CRT/g, 'terminal decorative style');
  assertNoPattern(rel, text, /tracking-\[-|letter-spacing\s*:\s*-/g, 'negative letter spacing');
  assertNoPattern(rel, text, /#05070b|#000000\b|#000\b/gi, 'banned near-black background');
}

if (scope === 'all') {
  const cssFiles = allFiles.filter((file) => file.endsWith('.css'));
  const cssTotal = cssFiles.reduce((sum, file) => sum + statSync(file).size, 0);

  for (const file of cssFiles) {
    const size = statSync(file).size;
    if (size > 20 * 1024) {
      failures.push(`${normalize(relative(dashboardRoot, file))} exceeds 20KB (${size} bytes)`);
    }
  }

  if (cssTotal > 60 * 1024) {
    failures.push(`total handwritten CSS exceeds 60KB (${cssTotal} bytes)`);
  }
}

if (failures.length > 0) {
  console.error(`Dashboard design-system ${scope} check failed:`);
  for (const failure of failures) {
    console.error(`- ${failure}`);
  }
  process.exit(1);
}

console.log(`Dashboard design-system ${scope} check passed.`);

function readScope() {
  const arg = process.argv.find((value) => value.startsWith('--scope='));
  const value = arg?.split('=')[1] ?? 'foundation';
  if (value !== 'foundation' && value !== 'all') {
    console.error(`Unsupported scope: ${value}`);
    process.exit(2);
  }
  return value;
}

function listFiles(dir) {
  const entries = readdirSync(dir, { withFileTypes: true });
  return entries.flatMap((entry) => {
    const absolute = join(dir, entry.name);
    if (entry.isDirectory()) {
      return listFiles(absolute);
    }
    return [absolute];
  });
}

function assertNoPattern(rel, text, pattern, label) {
  const matches = [...text.matchAll(pattern)];
  for (const match of matches) {
    const line = lineNumber(text, match.index ?? 0);
    failures.push(`${rel}:${line} contains ${label} (${match[0]})`);
  }
}

function lineNumber(text, index) {
  return text.slice(0, index).split('\n').length;
}

function normalize(value) {
  return value.split('\\').join('/');
}
