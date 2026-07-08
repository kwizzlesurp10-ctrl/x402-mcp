/**
 * Reusable Google Drive Playwright context helpers.
 * Drive UI version: 2026-07
 */

import { Browser, BrowserContext, Page } from 'playwright';
import fs from 'fs/promises';
import {
  DEFAULT_STORAGE_STATE_PATH,
  launchGoogleFriendlyBrowser,
  newStealthContext,
} from './browser-config.js';

export const STORAGE_STATE_PATH =
  process.env.DRIVE_AUTH_PATH || DEFAULT_STORAGE_STATE_PATH;

export interface DriveContextOptions {
  headed?: boolean;
  storageStatePath?: string;
}

export interface DriveContext {
  browser: Browser;
  context: BrowserContext;
  page: Page;
  storageStatePath: string;
}

export async function sessionExists(
  storageStatePath = STORAGE_STATE_PATH,
): Promise<boolean> {
  return fs.access(storageStatePath).then(() => true).catch(() => false);
}

export async function isLoggedIn(page: Page): Promise<boolean> {
  const url = page.url();
  if (url.includes('accounts.google.com') || url.includes('signin')) {
    return false;
  }

  const loggedInIndicators = [
    '[data-is-root="true"]',
    'div[aria-label*="My Drive"]',
    'button[aria-label*="New"]',
    'div[role="main"]',
    '.a-u-xb',
  ];

  for (const selector of loggedInIndicators) {
    try {
      const element = await page.$(selector);
      if (element) return true;
    } catch {
      // selector may be invalid or page still loading
    }
  }

  return false;
}

export async function deleteStaleSession(
  storageStatePath = STORAGE_STATE_PATH,
): Promise<void> {
  await fs.unlink(storageStatePath).catch(() => {});
}

export async function createDriveContext(
  options: DriveContextOptions = {},
): Promise<DriveContext> {
  const storageStatePath = options.storageStatePath ?? STORAGE_STATE_PATH;
  const headed = options.headed ?? process.env.HEADED === 'true';

  const { browser } = await launchGoogleFriendlyBrowser(!headed);

  const hasSession = await sessionExists(storageStatePath);
  const context = await newStealthContext(browser, {
    ...(hasSession ? { storageState: storageStatePath } : {}),
  });

  const page = await context.newPage();

  return { browser, context, page, storageStatePath };
}

export async function withDriveContext<T>(
  fn: (ctx: DriveContext) => Promise<T>,
  options: DriveContextOptions = {},
): Promise<T> {
  const ctx = await createDriveContext(options);
  try {
    return await fn(ctx);
  } finally {
    await ctx.context.close();
    await ctx.browser.close();
  }
}

export async function gotoMyDrive(
  page: Page,
  options: { timeout?: number } = {},
): Promise<void> {
  await page.goto('https://drive.google.com/drive/my-drive', {
    waitUntil: 'domcontentloaded',
    timeout: options.timeout ?? 60_000,
  });
  await page.waitForTimeout(3000);
}

export async function requireAuthenticatedDrive(
  page: Page,
  storageStatePath = STORAGE_STATE_PATH,
): Promise<void> {
  const loggedIn = await isLoggedIn(page);
  if (loggedIn) return;

  await deleteStaleSession(storageStatePath);
  throw new Error(
    'Authentication required. Session was invalid. Re-run: npx tsx scripts/re-auth.ts',
  );
}