export type RefreshSlice<T> =
  | { ok: true; value: T }
  | { ok: false; error: string };

export function settledSlice<T>(result: PromiseSettledResult<T>): RefreshSlice<T> {
  if (result.status === "fulfilled") {
    return { ok: true, value: result.value };
  }
  const reason = result.reason;
  return {
    ok: false,
    error: reason instanceof Error ? reason.message : String(reason),
  };
}

export function refreshErrors(slices: Array<RefreshSlice<unknown>>): string | null {
  const msgs = slices.filter((slice) => !slice.ok).map((slice) => slice.error);
  return msgs.length > 0 ? msgs.join("; ") : null;
}
