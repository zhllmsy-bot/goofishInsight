#!/usr/bin/env node
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const repoRoot = resolve(fileURLToPath(new URL('..', import.meta.url)));
const dashboardRoot = join(repoRoot, 'apps/dashboard-react');
const srcRoot = join(dashboardRoot, 'src');
const scope = readScope();

const requiredThemeFiles = [
  'src/themes/tokens.css',
  'src/themes/light.css',
  'src/themes/dark.css',
];

const requiredProjectFiles = [
  '../../docs/39-goofish-insight-ui-constitution-v2-20260426.md',
  '../../.github/pull_request_template.md',
];

const themeColorFiles = new Set([
  'src/themes/light.css',
  'src/themes/dark.css',
]);

const allowedThemeColors = new Set([
  '#FAFAF9',
  '#FFFFFF',
  '#F4F4F2',
  '#EAEAE7',
  '#E5E5E2',
  '#1A1A17',
  '#60605B',
  '#9A9A92',
  '#0066FF',
  '#0A7F3F',
  '#C8342B',
  '#0E0E0C',
  '#161613',
  '#1E1E1B',
  '#28282A',
  '#2E2E2B',
  '#EDEDE8',
  '#A5A59E',
  '#6C6C66',
  '#3B8AFF',
  '#3FBF6A',
  '#EA5B52',
]);

const floatingLayerFiles = new Set([
  'src/shared/components/ui/dialog.tsx',
  'src/shared/components/ui/dropdown-menu.tsx',
  'src/shared/components/ui/select.tsx',
  'src/shared/components/ui/sheet.tsx',
  'src/shared/components/ui/sonner.tsx',
  'src/shared/components/ui/tooltip.tsx',
]);

const allowedUiPrimitiveFiles = new Set([
  'badge.tsx',
  'button.tsx',
  'card.tsx',
  'checkbox.tsx',
  'dialog.tsx',
  'dropdown-menu.tsx',
  'input.tsx',
  'radio-group.tsx',
  'select.tsx',
  'sheet.tsx',
  'skeleton.tsx',
  'sonner.tsx',
  'switch.tsx',
  'table.tsx',
  'tabs.tsx',
  'tooltip.tsx',
]);

const foundationFiles = [
  'src/index.css',
  ...requiredThemeFiles,
  ...listFiles(join(srcRoot, 'shared/components/ui')).filter((file) => file.endsWith('.tsx')),
].map((file) => file.startsWith(srcRoot) ? file : join(dashboardRoot, file));

const allFiles = listFiles(srcRoot).filter((file) => /\.(css|tsx?)$/.test(file));
const filesToCheck = scope === 'all' ? allFiles : foundationFiles;
const failures = [];

for (const requiredFile of requiredThemeFiles) {
  const absolute = join(dashboardRoot, requiredFile);
  try {
    statSync(absolute);
  } catch {
    failures.push(`Missing required theme file: ${requiredFile}`);
  }
}

for (const requiredFile of requiredProjectFiles) {
  const absolute = join(dashboardRoot, requiredFile);
  try {
    statSync(absolute);
  } catch {
    failures.push(`Missing required project UI gate file: ${requiredFile}`);
  }
}

for (const file of listFiles(join(srcRoot, 'shared/components/ui')).filter((item) => item.endsWith('.tsx'))) {
  const name = file.split('/').pop();
  if (!allowedUiPrimitiveFiles.has(name)) {
    failures.push(`src/shared/components/ui/${name} is not in the UI primitive whitelist`);
  }
}

assertTokenContract();

for (const file of filesToCheck) {
  const rel = normalize(relative(dashboardRoot, file));
  const text = readFileSync(file, 'utf8');
  const allowsRawColor = themeColorFiles.has(rel);

  if (!allowsRawColor) {
    assertNoPattern(rel, text, /#[0-9a-fA-F]{3,8}\b/g, 'raw hex color');
    assertNoPattern(rel, text, /\brgba?\(/g, 'raw rgb/rgba color');
    assertNoPattern(rel, text, /\bhsla?\(/g, 'raw hsl/hsla color');
    assertNoPattern(rel, text, /\boklch\(/g, 'raw oklch color');
  } else {
    for (const match of text.matchAll(/#[0-9a-fA-F]{3,8}\b/g)) {
      const color = match[0].toUpperCase();
      if (!allowedThemeColors.has(color)) {
        failures.push(`${rel}:${lineNumber(text, match.index ?? 0)} contains color outside the v2 palette (${match[0]})`);
      }
    }
  }

  assertNoPattern(rel, text, /\bradar\b|color-radar|bg-radar|text-radar|border-radar/gi, 'retired radar color token');
  assertNoPattern(rel, text, /\b(linear|radial|conic)-gradient\(/g, 'gradient background');
  assertNoPattern(rel, text, /transition\s*:\s*all\b|transition-all/g, 'transition-all');
  assertNoPattern(rel, text, /Terminal|terminal|Orbitron|VT323|Share Tech Mono|scanline|CRT/g, 'terminal decorative style');
  assertNoPattern(rel, text, /tracking-\[-|letter-spacing\s*:\s*-/g, 'negative letter spacing');
  assertNoPattern(rel, text, /#05070b|#000000\b|#000\b/gi, 'banned near-black background');
  assertNoPattern(rel, text, /template:[^'"\s]*\|/g, 'debug template string');
  assertNoPattern(rel, text, /[✅❌⚠️🚀]/gu, 'emoji UI marker');
  assertNoPattern(rel, text, /style=\{\{[^}]*\b(color|background|borderColor|border-color)\b/gs, 'inline color style');
  assertNoPattern(rel, text, /\bborder-2\b|border:\s*2px\b/g, '2px border');

  if (floatingLayerFiles.has(rel)) {
    assertNoPattern(rel, text, /shadow-\[var\(--shadow-(md|lg)\)\]/g, 'large floating shadow');
  } else if (!rel.startsWith('src/themes/')) {
    assertNoPattern(rel, text, /\bbox-shadow\b|shadow-\[var\(--shadow-/g, 'box shadow outside floating layer');
  }
}

if (scope === 'all') {
  const cssFiles = allFiles.filter((file) => file.endsWith('.css'));
  const cssTotal = cssFiles.reduce((sum, file) => sum + statSync(file).size, 0);

  for (const file of cssFiles) {
    const size = statSync(file).size;
    if (size > 15 * 1024) {
      failures.push(`${normalize(relative(dashboardRoot, file))} exceeds 15KB (${size} bytes)`);
    }
  }

  if (cssTotal > 40 * 1024) {
    failures.push(`total handwritten CSS exceeds 40KB (${cssTotal} bytes)`);
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

function assertTokenContract() {
  const tokens = readFileSync(join(dashboardRoot, 'src/themes/tokens.css'), 'utf8');
  const expectations = [
    ['--font-sans', '"Inter Variable", "PingFang SC", "Microsoft YaHei", system-ui'],
    ['--font-mono', '"JetBrains Mono Variable", "SF Mono", ui-monospace'],
    ['--topbar-height', '56px'],
    ['--opportunity-row-height', '56px'],
    ['--motion-fast', '120ms'],
    ['--motion-base', '200ms'],
    ['--motion-slow', '320ms'],
  ];

  for (const [name, value] of expectations) {
    const pattern = new RegExp(`${escapeRegExp(name)}\\s*:\\s*${escapeRegExp(value)}\\s*;`);
    if (!pattern.test(tokens)) {
      failures.push(`src/themes/tokens.css must set ${name}: ${value}`);
    }
  }
}

function lineNumber(text, index) {
  return text.slice(0, index).split('\n').length;
}

function normalize(value) {
  return value.split('\\').join('/');
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
