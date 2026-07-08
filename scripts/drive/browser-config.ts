/**
 * Browser launch settings that reduce Google "browser not secure" blocks.
 * Drive UI version: 2026-07
 */

import fs from 'fs';
import fsPromises from 'fs/promises';
import path from 'path';
import { fileURLToPath } from 'url';
import {
  chromium,
  type Browser,
  type BrowserContext,
  type LaunchOptions,
} from 'playwright';

/** Directory containing this vendored script pair (`scripts/drive`). */
export const VENDOR_DIR = path.dirname(fileURLToPath(import.meta.url));

/** Prefer skill session; fall back to local vendor path. */
const SKILL_AUTH = path.join(
  process.env.USERPROFILE ?? process.env.HOME ?? '',
  '.grok',
  'skills',
  'google-drive-playwright',
  'drive-auth.json',
);

export const SKILL_ROOT = path.resolve(VENDOR_DIR, '..', '..');

export const DEFAULT_STORAGE_STATE_PATH = process.env.DRIVE_AUTH_PATH
  ? process.env.DRIVE_AUTH_PATH
  : fs.existsSync(SKILL_AUTH)
    ? SKILL_AUTH
    : path.join(VENDOR_DIR, 'drive-auth.json');

export const USER_DATA_DIR =
  process.env.DRIVE_USER_DATA_DIR ||
  path.join(SKILL_ROOT, 'drive-browser-profile');

const STEALTH_ARGS = ['--disable-blink-features=AutomationControlled'];
const STEALTH_IGNORE_ARGS = ['--enable-automation'];

const WINDOWS_BROWSER_PATHS = {
  chrome: [
    path.join(process.env.ProgramFiles ?? '', 'Google', 'Chrome', 'Application', 'chrome.exe'),
    path.join(process.env['ProgramFiles(x86)'] ?? '', 'Google', 'Chrome', 'Application', 'chrome.exe'),
  ],
  msedge: [
    path.join(process.env.ProgramFiles ?? '', 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
    path.join(process.env['ProgramFiles(x86)'] ?? '', 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
  ],
} as const;

type BrowserChannel = keyof typeof WINDOWS_BROWSER_PATHS;

function findInstalledBrowser(channel: BrowserChannel): string | null {
  for (const candidate of WINDOWS_BROWSER_PATHS[channel]) {
    if (candidate && fs.existsSync(candidate)) {
      return candidate;
    }
  }
  return null;
}

function baseLaunchOptions(headless: boolean): LaunchOptions {
  return {
    headless,
    args: STEALTH_ARGS,
    ignoreDefaultArgs: STEALTH_IGNORE_ARGS,
  };
}

async function tryLaunchWithChannel(
  channel: BrowserChannel,
  headless: boolean,
): Promise<Browser | null> {
  const executablePath = findInstalledBrowser(channel);
  if (!executablePath) return null;

  try {
    return await chromium.launch({
      ...baseLaunchOptions(headless),
      channel,
      executablePath,
    });
  } catch {
    try {
      return await chromium.launch({
        ...baseLaunchOptions(headless),
        executablePath,
      });
    } catch {
      return null;
    }
  }
}

async function tryPersistentWithChannel(
  channel: BrowserChannel,
  userDataDir: string,
): Promise<BrowserContext | null> {
  const executablePath = findInstalledBrowser(channel);
  if (!executablePath) return null;

  try {
    return await chromium.launchPersistentContext(userDataDir, {
      ...baseLaunchOptions(false),
      channel,
      executablePath,
      viewport: null,
    });
  } catch {
    try {
      return await chromium.launchPersistentContext(userDataDir, {
        ...baseLaunchOptions(false),
        executablePath,
        viewport: null,
      });
    } catch {
      return null;
    }
  }
}

export async function unlockBrowserProfile(
  userDataDir = USER_DATA_DIR,
): Promise<void> {
  const lockFiles = ['SingletonLock', 'SingletonCookie', 'lockfile'];
  for (const file of lockFiles) {
    await fsPromises.unlink(path.join(userDataDir, file)).catch(() => {});
  }
}

export async function launchGoogleFriendlyBrowser(
  headless = false,
): Promise<{ browser: Browser; channel: string }> {
  for (const channel of ['chrome', 'msedge'] as const) {
    const browser = await tryLaunchWithChannel(channel, headless);
    if (browser) {
      return { browser, channel };
    }
  }

  console.warn(
    'Chrome/Edge not found. Using bundled Chromium — Google sign-in is often blocked.\n' +
      'Install Google Chrome, then re-run re-auth.',
  );
  const browser = await chromium.launch(baseLaunchOptions(headless));
  return { browser, channel: 'chromium' };
}

export async function launchGoogleLoginContext(
  userDataDir = USER_DATA_DIR,
): Promise<{ context: BrowserContext; channel: string }> {
  await unlockBrowserProfile(userDataDir);

  for (const channel of ['chrome', 'msedge'] as const) {
    const context = await tryPersistentWithChannel(channel, userDataDir);
    if (context) {
      await applyStealthScripts(context);
      return { context, channel };
    }
  }

  console.warn(
    'Chrome/Edge not found. Using bundled Chromium — Google sign-in is often blocked.\n' +
      'Install Google Chrome, then re-run re-auth.',
  );
  const context = await chromium.launchPersistentContext(userDataDir, {
    ...baseLaunchOptions(false),
    viewport: null,
  });
  await applyStealthScripts(context);
  return { context, channel: 'chromium' };
}

export async function applyStealthScripts(context: BrowserContext): Promise<void> {
  await context.addInitScript(() => {
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
  });
}

export async function newStealthContext(
  browser: Browser,
  options: { storageState?: string } = {},
): Promise<BrowserContext> {
  const context = await browser.newContext({
    ...options,
    viewport: null,
  });
  await applyStealthScripts(context);
  return context;
}