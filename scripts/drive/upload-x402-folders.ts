/**
 * Upload x402-mcp folder structure to Google Drive and collect remote tree
 * in the SAME Playwright session (no global search).
 * Target: /Forge/MCP_Projects/x402-micropayments/
 */
import fs from 'fs/promises';
import path from 'path';
import { parseArgs } from 'util';
import { withDriveContext, requireAuthenticatedDrive } from './create-drive-context.js';

const { values } = parseArgs({
  options: {
    staging: { type: 'string', short: 's' },
    output: { type: 'string', short: 'o', default: 'drive-folders-result.json' },
    listing: { type: 'string', short: 'l', default: '' },
    remote: { type: 'string', short: 'r', default: '' },
    manifest: { type: 'string', short: 'm', default: '' },
    'collect-only': { type: 'boolean', default: false },
  },
});

const TARGET_FOLDER = 'x402-micropayments';
const PARENT_PATH = 'Forge/MCP_Projects';
const PATH_SEGMENTS = ['Forge', 'MCP_Projects', TARGET_FOLDER];
const REQUIRED_TOP = ['code', 'tests', 'docs', 'manifests', 'deployment', 'screenshots', 'scripts'];

const REQUIRED_PROOF_PATHS = [
  'code/app/main.py',
  'deployment/Dockerfile',
  'scripts/run_goal_verification.ps1',
  'scripts/verify_docker.py',
  'scripts/build_drive_staging.py',
  'scripts/capture_goal_evidence.py',
];

/** Subfolders to drill into after opening a top-level dir. */
const NESTED: Record<string, string[]> = {
  code: ['app'],
  scripts: ['drive'],
};

const UI_NOISE =
  /advanced search|catch me up|clear selection|close|support|sort by|view details|trashed|to do|^type$|unsupported item|help center|clear filters|ask google|list view|grid view/i;

type ListingEntry = { name: string; path: string; source: string };

function normalizeItemName(name: string): string {
  return name
    .replace(/\s*\(\d+\)$/, '')
    .replace(/\s+Text$/i, '')
    .replace(/\s+Compressed archive$/i, '')
    .trim();
}

function isLikelyDriveItem(name: string): boolean {
  const base = normalizeItemName(name);
  if (!base || base === 'Keith Severson' || UI_NOISE.test(base)) return false;
  if (
    REQUIRED_TOP.includes(base) ||
    base === 'app' ||
    base === 'drive' ||
    base === 'DRIVE_STAGING_MANIFEST.txt' ||
    base === 'Dockerfile' ||
    base.startsWith('.env') ||
    base.startsWith('__')
  ) {
    return true;
  }
  return /\.[a-z0-9]+$/i.test(base);
}

/** Drive sometimes surfaces dunder names without underscores in labels. */
function nameMatches(expected: string, actual: string): boolean {
  const e = normalizeItemName(expected).toLowerCase();
  const a = normalizeItemName(actual).toLowerCase();
  if (e === a) return true;
  if (e.replace(/_/g, '') === a.replace(/_/g, '')) return true;
  if (e.endsWith(a) || a.endsWith(e)) return true;
  return false;
}

async function walkStaging(staging: string): Promise<ListingEntry[]> {
  const entries: ListingEntry[] = [];

  async function walkDir(dirPath: string, relPrefix: string): Promise<void> {
    const items = await fs.readdir(dirPath, { withFileTypes: true });
    for (const item of items) {
      const rel = relPrefix ? `${relPrefix}/${item.name}` : item.name;
      const full = path.join(dirPath, item.name);
      if (item.isDirectory()) {
        await walkDir(full, rel);
      } else {
        entries.push({ name: item.name, path: rel.replace(/\\/g, '/'), source: 'local_staging_walk' });
      }
    }
  }

  for (const dir of REQUIRED_TOP) {
    await walkDir(path.join(staging, dir), dir);
  }

  return entries.sort((a, b) => a.path.localeCompare(b.path));
}

async function loadManifestLines(manifestPath: string): Promise<string[]> {
  try {
    const text = await fs.readFile(manifestPath, 'utf-8');
    return text
      .split('\n')
      .map((l) => l.trim())
      .filter((l) => l && !l.startsWith('==='));
  } catch {
    return [];
  }
}

function folderNameCandidates(name: string): string[] {
  return [name, name.replace(/_/g, ' '), name.replace(/ /g, '_'), `${name} (1)`, `${name} (2)`];
}

let targetFolderUrl: string | null = null;

function isFolderViewUrl(url: string): boolean {
  return /\/folders\/[a-zA-Z0-9_-]+/.test(url) && !url.includes('/search');
}

async function dismissSearchOverlay(page: import('playwright').Page): Promise<void> {
  await page.keyboard.press('Escape').catch(() => {});
  await page.waitForTimeout(400);
}

async function loadCachedFolderUrl(scratch: string): Promise<string | null> {
  try {
    const cached = await fs.readFile(path.join(scratch, 'drive_target_folder_url.txt'), 'utf-8');
    const url = cached.trim();
    return url && isFolderViewUrl(url) ? url : null;
  } catch {
    return null;
  }
}

async function saveCachedFolderUrl(scratch: string, url: string): Promise<void> {
  await fs.writeFile(path.join(scratch, 'drive_target_folder_url.txt'), url, 'utf-8');
}

async function gotoFolderHref(page: import('playwright').Page, href: string, scratch: string): Promise<string> {
  const url = href.startsWith('http') ? href : `https://drive.google.com${href}`;
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 90000 });
  await page.waitForTimeout(3500);
  if (isFolderViewUrl(page.url())) {
    targetFolderUrl = page.url();
    await saveCachedFolderUrl(scratch, page.url());
    return page.url();
  }
  throw new Error(`href did not open folder view: ${url}`);
}

async function openFolderSegment(page: import('playwright').Page, segment: string): Promise<boolean> {
  for (const cand of folderNameCandidates(segment)) {
    const byTooltip = page.locator(`[data-tooltip="${cand}"]`).first();
    if (await byTooltip.isVisible().catch(() => false)) {
      await byTooltip.scrollIntoViewIfNeeded().catch(() => {});
      await byTooltip.dblclick({ timeout: 15000 });
      await page.waitForTimeout(4000);
      return true;
    }

    const escaped = cand.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const rows = page.getByRole('row').filter({ hasText: new RegExp(escaped, 'i') });
    const count = await rows.count();
    for (let i = 0; i < Math.min(count, 8); i++) {
      const row = rows.nth(i);
      const text = await row.innerText().catch(() => '');
      if (/\.(md|py|ps1|json|png|txt|toml|zip|example)\b/i.test(text)) continue;
      if (await row.isVisible().catch(() => false)) {
        await row.dblclick({ timeout: 15000 });
        await page.waitForTimeout(4000);
        return true;
      }
    }
  }
  return false;
}

async function navigateByPath(page: import('playwright').Page, scratch: string): Promise<string | null> {
  await page.goto('https://drive.google.com/drive/my-drive', {
    waitUntil: 'domcontentloaded',
    timeout: 90000,
  });
  await page.waitForTimeout(3000);

  for (const segment of PATH_SEGMENTS) {
    if (!(await openFolderSegment(page, segment))) {
      await page.goto(
        `https://drive.google.com/drive/search?q=${encodeURIComponent(`"${segment}" type:folder`)}`,
        { waitUntil: 'domcontentloaded', timeout: 90000 },
      );
      await page.waitForTimeout(3500);
      if (!(await openFolderSegment(page, segment))) {
        return null;
      }
    }
  }

  if (isFolderViewUrl(page.url())) {
    targetFolderUrl = page.url();
    await saveCachedFolderUrl(scratch, page.url());
    return page.url();
  }
  return null;
}

async function navigateToTargetFolder(page: import('playwright').Page, scratch: string): Promise<string> {
  const cached = targetFolderUrl ?? (await loadCachedFolderUrl(scratch));
  if (cached && isFolderViewUrl(cached)) {
    await page.goto(cached, { waitUntil: 'domcontentloaded', timeout: 90000 });
    await page.waitForTimeout(3000);
    if (isFolderViewUrl(page.url())) {
      targetFolderUrl = page.url();
      return page.url();
    }
  }

  const byPath = await navigateByPath(page, scratch);
  if (byPath) return byPath;

  const queries = [
    `${PARENT_PATH}/${TARGET_FOLDER}`,
    `type:folder "${TARGET_FOLDER}"`,
    TARGET_FOLDER,
  ];

  for (const searchQuery of queries) {
    await page.goto(
      `https://drive.google.com/drive/search?q=${encodeURIComponent(searchQuery)}`,
      { waitUntil: 'domcontentloaded', timeout: 90000 },
    );
    await page.waitForTimeout(3500);
    await dismissSearchOverlay(page);

    const folderLinks = page.locator(`a[href*="/folders/"]`).filter({
      hasText: new RegExp(TARGET_FOLDER, 'i'),
    });
    const linkCount = await folderLinks.count();
    for (let i = 0; i < Math.min(linkCount, 5); i++) {
      const href = await folderLinks.nth(i).getAttribute('href');
      if (!href) continue;
      try {
        return await gotoFolderHref(page, href, scratch);
      } catch {
        // try next candidate link
      }
    }

    const folderRow = page.getByRole('row', { name: new RegExp(TARGET_FOLDER, 'i') }).first();
    if (await folderRow.isVisible().catch(() => false)) {
      await folderRow.dblclick({ timeout: 15000 });
      await page.waitForTimeout(4500);
      if (isFolderViewUrl(page.url())) {
        targetFolderUrl = page.url();
        await saveCachedFolderUrl(scratch, page.url());
        return page.url();
      }
    }
  }

  return ensureFolderPath(page, scratch);
}

async function listVisibleItemNames(page: import('playwright').Page): Promise<string[]> {
  const names: string[] = [];

  const selectors = [
    '[role="gridcell"][data-tooltip]',
    '[role="gridcell"][aria-label]',
    '[data-tooltip]',
    'div[aria-label]',
    '[role="option"][aria-label]',
  ];
  for (const sel of selectors) {
    const nodes = page.locator(sel);
    const count = await nodes.count().catch(() => 0);
    for (let i = 0; i < Math.min(count, 200); i++) {
      const node = nodes.nth(i);
      const tooltip = (await node.getAttribute('data-tooltip').catch(() => null)) ?? '';
      const aria = (await node.getAttribute('aria-label').catch(() => null)) ?? '';
      const text = (await node.innerText().catch(() => ''))?.split('\n')[0]?.trim() ?? '';
      for (const raw of [tooltip, aria, text]) {
        const candidate = normalizeItemName(raw);
        if (candidate && isLikelyDriveItem(candidate)) names.push(candidate);
      }
    }
  }

  const rows = page.getByRole('row');
  const rowCount = await rows.count().catch(() => 0);
  for (let i = 0; i < Math.min(rowCount, 120); i++) {
    const text = await rows.nth(i).innerText().catch(() => '');
    const first = (text.split('\n')[0] ?? '').trim();
    if (first && first !== 'Keith Severson' && !/^name$/i.test(first)) {
      names.push(normalizeItemName(first));
    }
  }

  return [...new Set(names)].filter((n) => isLikelyDriveItem(n));
}

async function openItemByName(page: import('playwright').Page, name: string, isFolder: boolean): Promise<boolean> {
  for (const cand of folderNameCandidates(name)) {
    const byTooltip = page.locator(`[data-tooltip="${cand}"]`).first();
    if (await byTooltip.isVisible().catch(() => false)) {
      await byTooltip.scrollIntoViewIfNeeded().catch(() => {});
      await byTooltip.dblclick({ timeout: 15000 });
      await page.waitForTimeout(3000);
      return true;
    }

    const escaped = cand.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const rows = page.getByRole('row').filter({ hasText: new RegExp(escaped, 'i') });
    const count = await rows.count();
    for (let i = 0; i < Math.min(count, 10); i++) {
      const row = rows.nth(i);
      const text = await row.innerText().catch(() => '');
      if (!isFolder && /\.(md|py|ps1|json|png|txt|toml|example)\b/i.test(text)) {
        return false;
      }
      if (isFolder && /\.(md|py|ps1|json|png|txt|toml|example)\b/i.test(text) && !/folder/i.test(text)) {
        continue;
      }
      if (await row.isVisible().catch(() => false)) {
        await row.scrollIntoViewIfNeeded().catch(() => {});
        await row.dblclick({ timeout: 15000 });
        await page.waitForTimeout(3000);
        return true;
      }
    }
  }
  return false;
}

async function openFolderByName(page: import('playwright').Page, name: string): Promise<boolean> {
  return openItemByName(page, name, true);
}

async function gotoResilient(
  page: import('playwright').Page,
  url: string,
  timeout = 120_000,
): Promise<void> {
  let lastErr: unknown;
  for (let attempt = 1; attempt <= 3; attempt++) {
    try {
      await page.goto(url, { waitUntil: 'domcontentloaded', timeout });
      await page.waitForTimeout(2000);
      return;
    } catch (err) {
      lastErr = err;
      console.error(`goto attempt ${attempt} failed for ${url}: ${(err as Error).message}`);
      await page.waitForTimeout(2000 * attempt);
    }
  }
  // Final attempt with looser wait condition
  try {
    await page.goto(url, { waitUntil: 'commit', timeout });
    await page.waitForTimeout(4000);
  } catch {
    throw lastErr;
  }
}

async function returnToTargetRoot(page: import('playwright').Page, scratch: string): Promise<void> {
  if (targetFolderUrl && isFolderViewUrl(targetFolderUrl)) {
    await gotoResilient(page, targetFolderUrl);
    return;
  }

  const crumb = page.getByRole('link', { name: new RegExp(TARGET_FOLDER, 'i') }).first();
  if (await crumb.isVisible().catch(() => false)) {
    await crumb.click();
    await page.waitForTimeout(2500);
    if (isFolderViewUrl(page.url())) {
      targetFolderUrl = page.url();
      await saveCachedFolderUrl(scratch, page.url());
      return;
    }
  }

  targetFolderUrl = await navigateToTargetFolder(page, scratch);
}

async function collectViaScopedSearch(
  page: import('playwright').Page,
  manifestLines: string[],
  scratch: string,
): Promise<ListingEntry[]> {
  const entries: ListingEntry[] = [];
  const seen = new Set<string>();

  for (const top of REQUIRED_TOP) {
    const query = `"${top}" "${TARGET_FOLDER}" type:folder`;
    await page.goto(
      `https://drive.google.com/drive/search?q=${encodeURIComponent(query)}`,
      { waitUntil: 'domcontentloaded', timeout: 90000 },
    );
    await page.waitForTimeout(2500);
    const hits = await listVisibleItemNames(page);
    if (hits.some((h) => h.toLowerCase() === top.toLowerCase())) {
      entries.push({ name: top, path: top, source: 'remote_scoped_search_folder' });
      seen.add(top);
    }
  }

  for (const line of manifestLines) {
    const fileName = line.split('/').pop()!;
    const bareName = fileName.replace(/_/g, '');
    const queries = [
      `"${fileName}" "${TARGET_FOLDER}"`,
      `"${fileName}" ${PARENT_PATH}`,
      `"${fileName}"`,
      `"${bareName}" "${TARGET_FOLDER}"`,
    ];
    if (fileName.startsWith('.')) {
      queries.unshift(`"${fileName.slice(1)}" "${TARGET_FOLDER}"`);
    }
    if (fileName.startsWith('__') && fileName.endsWith('.py')) {
      // Drive often strips leading underscores in search UI labels
      queries.unshift(`"${fileName.replace(/^_+/, '')}" "${TARGET_FOLDER}"`);
    }
    let matched: string | undefined;
    for (const query of queries) {
      await page.goto(
        `https://drive.google.com/drive/search?q=${encodeURIComponent(query)}`,
        { waitUntil: 'domcontentloaded', timeout: 90000 },
      );
      await page.waitForTimeout(2000);
      const hits = await listVisibleItemNames(page);
      matched = hits.find((h) => nameMatches(fileName, h));
      if (matched) break;
    }
    if (matched && !seen.has(line)) {
      entries.push({ name: matched, path: line, source: 'remote_scoped_search_file' });
      seen.add(line);
    }
  }

  await navigateToTargetFolder(page, scratch);
  return entries.sort((a, b) => a.path.localeCompare(b.path));
}

async function collectFolderTree(
  page: import('playwright').Page,
  _targetFolderUrl: string,
  scratch: string,
  manifestLines: string[],
): Promise<ListingEntry[]> {
  const entries: ListingEntry[] = [];

  await returnToTargetRoot(page, scratch);
  await page.waitForTimeout(3000);

  for (const top of REQUIRED_TOP) {
    await returnToTargetRoot(page, scratch);
    if (!(await openFolderByName(page, top))) {
      continue;
    }

    const level1 = await listVisibleItemNames(page);
    const nestedTargets = NESTED[top] ?? [];

    for (const item of level1) {
      const isNestedFolder = nestedTargets.some((n) => nameMatches(n, item));
      if (isNestedFolder) {
        if (await openFolderByName(page, item)) {
          const level2 = await listVisibleItemNames(page);
          for (const sub of level2) {
            entries.push({
              name: sub,
              path: `${top}/${item}/${sub}`.replace(/\\/g, '/'),
              source: 'remote_in_folder_nested',
            });
          }
          await returnToTargetRoot(page, scratch);
          if (!(await openFolderByName(page, top))) continue;
        }
      } else if (item.includes('.') || item === 'app' || item === 'drive' || item.startsWith('__')) {
        entries.push({
          name: item,
          path: `${top}/${item}`.replace(/\\/g, '/'),
          source: 'remote_in_folder',
        });
      } else if (!item.includes('.')) {
        // Unknown folder-like entry: record it so nested layout is visible.
        entries.push({
          name: item,
          path: `${top}/${item}`.replace(/\\/g, '/'),
          source: 'remote_in_folder_maybe_dir',
        });
      }
    }
  }

  await returnToTargetRoot(page, scratch);
  const rootItems = await listVisibleItemNames(page);
  for (const name of rootItems) {
    const base = name.replace(/\s*\(\d+\)$/, '');
    if (REQUIRED_TOP.includes(base) || name === 'DRIVE_STAGING_MANIFEST.txt') {
      entries.push({ name, path: base, source: 'remote_target_root' });
    }
  }

  const scoped = await collectViaScopedSearch(page, manifestLines, scratch);
  const merged = new Map<string, ListingEntry>();
  for (const e of [...entries, ...scoped]) merged.set(e.path, e);
  const combined = [...merged.values()].sort((a, b) => a.path.localeCompare(b.path));

  const parity = manifestSatisfied(manifestLines, combined);
  if (!parity.ok) {
    await page.screenshot({ path: path.join(scratch, 'drive-collect-debug.png'), fullPage: true });
  }

  return combined;
}

async function createFolder(page: import('playwright').Page, name: string): Promise<boolean> {
  await page.getByRole('button', { name: /^New$/i }).click({ timeout: 15000 });
  const folderItem = page.getByRole('menuitem', { name: /New folder/i });
  await folderItem.waitFor({ state: 'visible', timeout: 10000 });
  await folderItem.click();
  await page.waitForTimeout(1500);

  const nameInput = page.locator('input[aria-label*="Name"], input[aria-label*="name"], input[type="text"]').last();
  if (await nameInput.isVisible().catch(() => false)) {
    await nameInput.fill(name);
    await page.keyboard.press('Enter');
    await page.waitForTimeout(3000);
    return true;
  }

  await page.keyboard.type(name);
  await page.keyboard.press('Enter');
  await page.waitForTimeout(3000);
  return true;
}

async function ensureFolderPath(page: import('playwright').Page, scratch: string): Promise<string> {
  await page.goto('https://drive.google.com/drive/my-drive', {
    waitUntil: 'domcontentloaded',
    timeout: 90000,
  });
  await page.waitForTimeout(3000);

  for (const segment of PATH_SEGMENTS) {
    if (await openFolderSegment(page, segment)) {
      if (isFolderViewUrl(page.url())) {
        targetFolderUrl = page.url();
        await saveCachedFolderUrl(scratch, page.url());
      }
      continue;
    }

    await createFolder(page, segment);
    if (!(await openFolderSegment(page, segment))) {
      throw new Error(`Failed to create/open folder segment: ${segment}`);
    }
    if (isFolderViewUrl(page.url())) {
      targetFolderUrl = page.url();
      await saveCachedFolderUrl(scratch, page.url());
    }
  }

  if (!isFolderViewUrl(page.url())) {
    throw new Error('ensureFolderPath did not reach folder view');
  }
  return page.url();
}

async function uploadDirectory(page: import('playwright').Page, dirPath: string): Promise<void> {
  await page.getByRole('button', { name: /^New$/i }).click({ timeout: 15000 });
  const uploadItem = page.getByRole('menuitem', { name: /Folder upload/i });
  await uploadItem.waitFor({ state: 'visible', timeout: 10000 });
  const fileChooserPromise = page.waitForEvent('filechooser', { timeout: 15000 });
  await uploadItem.click();
  const fileChooser = await fileChooserPromise;
  await fileChooser.setFiles(dirPath);
  await page.waitForTimeout(12000);
}

async function uploadFile(page: import('playwright').Page, filePath: string): Promise<void> {
  await page.getByRole('button', { name: /^New$/i }).click({ timeout: 15000 });
  const uploadItem = page.getByRole('menuitem', { name: /File upload/i });
  await uploadItem.waitFor({ state: 'visible', timeout: 10000 });
  const fileChooserPromise = page.waitForEvent('filechooser', { timeout: 15000 });
  await uploadItem.click();
  const fileChooser = await fileChooserPromise;
  await fileChooser.setFiles(filePath);
  await page.waitForTimeout(5000);
}

function remotePathSet(entries: ListingEntry[]): Set<string> {
  const paths = new Set<string>();
  for (const e of entries) {
    const normPath = normalizeItemName(e.path);
    const normName = normalizeItemName(e.name);
    paths.add(normPath);
    paths.add(normName);
    paths.add(normPath.replace(/_/g, ''));
    paths.add(normName.replace(/_/g, ''));
    if (normPath.includes('/')) {
      paths.add(normPath.split('/').pop()!);
    }
  }
  return paths;
}

function manifestSatisfied(manifestLines: string[], remoteEntries: ListingEntry[]): {
  missing: string[];
  ok: boolean;
} {
  const remote = remotePathSet(remoteEntries);
  const missing: string[] = [];
  for (const line of manifestLines) {
    const normLine = normalizeItemName(line);
    const fileName = normLine.split('/').pop()!;
    const found =
      remote.has(normLine) ||
      remote.has(fileName) ||
      remote.has(normLine.replace(/_/g, '')) ||
      remote.has(fileName.replace(/_/g, '')) ||
      remoteEntries.some((e) => {
        const p = normalizeItemName(e.path);
        const n = normalizeItemName(e.name);
        return (
          nameMatches(normLine, p) ||
          nameMatches(fileName, n) ||
          p.endsWith(`/${fileName}`) ||
          p.toLowerCase().endsWith(`/${fileName.toLowerCase()}`)
        );
      });
    if (!found) missing.push(line);
  }
  return { missing, ok: missing.length === 0 };
}

async function repairMissingFiles(
  page: import('playwright').Page,
  scratch: string,
  staging: string,
  missingPaths: string[],
  uploadedFolders: string[],
): Promise<void> {
  for (const missingPath of missingPaths) {
    const localFile = path.join(staging, missingPath);
    try {
      await fs.access(localFile);
    } catch {
      continue;
    }
    const parts = missingPath.split('/');
    const fileName = parts[parts.length - 1]!;
    await navigateToTargetFolder(page, scratch);
    let parentOk = true;
    for (let i = 0; i < parts.length - 1; i++) {
      const segment = parts[i]!;
      if (!(await openFolderByName(page, segment))) {
        await createFolder(page, segment);
        if (!(await openFolderByName(page, segment))) {
          console.error(`repair: failed to open/create segment ${segment} for ${missingPath}`);
          parentOk = false;
          break;
        }
      }
    }
    if (!parentOk) {
      uploadedFolders.push(`repair-nav-failed:${missingPath}`);
      continue;
    }
    // Avoid duplicate uploads if already visible in parent
    const before = await listVisibleItemNames(page);
    if (before.some((n) => nameMatches(fileName, n))) {
      uploadedFolders.push(`repair-already-visible:${missingPath}`);
      continue;
    }
    await uploadFile(page, localFile);
    await page.waitForTimeout(4000);
    const after = await listVisibleItemNames(page);
    if (after.some((n) => nameMatches(fileName, n))) {
      uploadedFolders.push(`repair-ok:${missingPath}`);
    } else {
      // retry once
      await uploadFile(page, localFile);
      await page.waitForTimeout(6000);
      const after2 = await listVisibleItemNames(page);
      uploadedFolders.push(
        after2.some((n) => nameMatches(fileName, n))
          ? `repair-retry-ok:${missingPath}`
          : `repair-unconfirmed:${missingPath}`,
      );
    }
  }
}

async function main(): Promise<void> {
  const staging = path.resolve(
    values.staging ?? 'C:/Users/Keith/AppData/Local/Temp/grok-goal-96e31bb2e41a/implementer/x402-drive-staging',
  );
  const scratch = path.dirname(staging);
  const listingPath = values.listing
    ? path.resolve(values.listing as string)
    : path.join(scratch, 'drive_staging_listing.json');
  const remotePath = values.remote
    ? path.resolve(values.remote as string)
    : path.join(scratch, 'drive_remote_listing.json');
  const manifestPath = values.manifest
    ? path.resolve(values.manifest as string)
    : path.join(scratch, 'drive_staging_manifest.txt');

  const folderListing = await walkStaging(staging);
  await fs.writeFile(listingPath, JSON.stringify(folderListing, null, 2), 'utf-8');

  const manifestLines = await loadManifestLines(manifestPath);
  const proofMissing = REQUIRED_PROOF_PATHS.filter((p) => !folderListing.some((e) => e.path === p));
  if (proofMissing.length > 0) {
    throw new Error(`staging missing proof paths: ${proofMissing.join(', ')}`);
  }

  const result: Record<string, unknown> = {
    ok: false,
    staging,
    targetFolder: `${PARENT_PATH}/${TARGET_FOLDER}`,
    uploadedFolders: [] as string[],
    folderListing,
    proofPaths: REQUIRED_PROOF_PATHS.filter((p) => folderListing.some((e) => e.path === p)),
    fileCount: folderListing.length,
    error: null as string | null,
    remoteListing: null as unknown,
  };

  for (const dir of REQUIRED_TOP) {
    await fs.access(path.join(staging, dir));
  }

  const collectOnly = Boolean(values['collect-only']);

  await withDriveContext(async ({ page, storageStatePath }) => {
    await page.goto('https://drive.google.com/drive/my-drive', {
      waitUntil: 'domcontentloaded',
      timeout: 90000,
    });
    await requireAuthenticatedDrive(page, storageStatePath);
    const folderUrl = await navigateToTargetFolder(page, scratch);

    if (!collectOnly) {
    for (const dir of REQUIRED_TOP) {
      const dirPath = path.join(staging, dir);
      await navigateToTargetFolder(page, scratch);
      await uploadDirectory(page, dirPath);
      (result.uploadedFolders as string[]).push(
        `${dir}/ (${folderListing.filter((e) => e.path.startsWith(`${dir}/`)).length} files)`,
      );
    }

    const manifestUpload = path.join(staging, 'DRIVE_STAGING_MANIFEST.txt');
    const manifestSrc = manifestPath;
    try {
      await fs.copyFile(manifestSrc, manifestUpload);
    } catch {
      await fs.writeFile(manifestUpload, `x402-mcp staging: ${REQUIRED_TOP.join(', ')}\n`, 'utf-8');
    }
    await navigateToTargetFolder(page, scratch);
    await uploadFile(page, manifestUpload);
    (result.uploadedFolders as string[]).push('DRIVE_STAGING_MANIFEST.txt');

    await returnToTargetRoot(page, scratch);
    await page.waitForTimeout(8000);
    }

    if (collectOnly) {
      await navigateToTargetFolder(page, scratch);
      await page.waitForTimeout(3000);
      (result.uploadedFolders as string[]).push('collect-only (skipped upload)');
    }
    let remoteEntries = await collectFolderTree(page, folderUrl, scratch, manifestLines);
    let parity = manifestSatisfied(manifestLines, remoteEntries);

    // Up to two repair passes for small missing sets.
    for (let pass = 1; pass <= 2 && !parity.ok && parity.missing.length > 0 && parity.missing.length <= 20; pass++) {
      console.error(`repair pass ${pass}: missing ${parity.missing.length} -> ${parity.missing.join(', ')}`);
      await repairMissingFiles(
        page,
        scratch,
        staging,
        parity.missing,
        result.uploadedFolders as string[],
      );
      await page.waitForTimeout(6000);
      remoteEntries = await collectFolderTree(page, folderUrl, scratch, manifestLines);
      parity = manifestSatisfied(manifestLines, remoteEntries);
    }

    const remoteListing = {
      ok: parity.ok,
      method: 'in_folder_listing_same_session',
      targetFolder: `${PARENT_PATH}/${TARGET_FOLDER}`,
      listedAt: new Date().toISOString(),
      entryCount: remoteEntries.length,
      manifestLineCount: manifestLines.length,
      missingFromRemote: parity.missing,
      proofPathsPresent: REQUIRED_PROOF_PATHS.filter((p) =>
        remoteEntries.some((e) => e.path === p || e.path.endsWith(p.split('/').pop()!)),
      ),
      topFoldersPresent: REQUIRED_TOP.filter((t) =>
        remoteEntries.some((e) => e.path === t || e.path.startsWith(`${t}/`)),
      ),
      entries: remoteEntries,
    };

    await fs.writeFile(remotePath, JSON.stringify(remoteListing, null, 2), 'utf-8');
    await fs.writeFile(
      path.join(scratch, 'drive_remote_listing.log'),
      ['=== Remote Drive listing (same session) ===', JSON.stringify(remoteListing, null, 2)].join('\n'),
      'utf-8',
    );

    result.remoteListing = remoteListing;
    result.ok = parity.ok;
    result.requiredFolders = REQUIRED_TOP;
    result.stagingLayout = REQUIRED_TOP;

    if (!parity.ok) {
      result.error = `remote missing ${parity.missing.length} manifest paths: ${parity.missing.slice(0, 5).join(', ')}`;
    }
  });

  const outPath = path.resolve(values.output as string);
  await fs.writeFile(outPath, JSON.stringify(result, null, 2), 'utf-8');
  const logPath = path.join(scratch, 'drive_upload.log');
  await fs.writeFile(
    logPath,
    [
      '=== Drive folder structure upload + remote tree ===',
      JSON.stringify(result, null, 2),
      `required_top_level=${REQUIRED_TOP.join(',')}`,
      `drive_staging_listing=${listingPath}`,
      `drive_remote_listing=${remotePath}`,
      `manifest_lines=${manifestLines.length}`,
      `remote_ok=${(result.remoteListing as { ok: boolean })?.ok}`,
    ].join('\n'),
    'utf-8',
  );
  console.log(JSON.stringify({ ok: result.ok, remote: result.remoteListing }, null, 2));
  if (!result.ok) process.exit(1);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});