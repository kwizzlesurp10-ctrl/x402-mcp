const STORAGE_KEY = "x402-admin-api-base";
const DEFAULT_LOCAL = "http://127.0.0.1:8402";
const DEFAULT_PROXY = "/api";

export function defaultApiBase(): string {
  const env = import.meta.env.VITE_PUBLIC_API_BASE_URL;
  if (env && env.length > 0) return env.replace(/\/$/, "");
  if (import.meta.env.DEV) return DEFAULT_PROXY;
  return DEFAULT_LOCAL;
}

export function readStoredApiBase(): string {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) return stored.replace(/\/$/, "");
  } catch {
    /* ignore */
  }
  return defaultApiBase();
}

export function writeStoredApiBase(url: string): void {
  const normalized = url.replace(/\/$/, "");
  localStorage.setItem(STORAGE_KEY, normalized);
}

export function isValidApiBase(url: string): boolean {
  if (url === DEFAULT_PROXY) return true;
  try {
    const parsed = new URL(url);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}
