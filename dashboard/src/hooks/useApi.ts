/** API hooks for fetching stats, ledger, doctor, wallet data. */

import { useCallback, useEffect, useState } from "react";
import type {
  DoctorResponse,
  LedgerRow,
  ProbeResponse,
  StatsResponse,
  WalletResponse,
} from "../types/api";
import {
  DEMO_DOCTOR,
  DEMO_REVENUE,
  DEMO_SPEND,
  DEMO_STATS,
  DEMO_WALLET,
} from "../lib/demo-data";

const BASE = "";

export function useStats(demo: boolean) {
  const [data, setData] = useState<StatsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (demo) {
      setData(DEMO_STATS);
      return;
    }
    try {
      const resp = await fetch(`${BASE}/stats`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      setData(await resp.json());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
    }
  }, [demo]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { data, error, refresh };
}

export function useLedger(name: "spend" | "revenue", demo: boolean) {
  const [rows, setRows] = useState<LedgerRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (demo) {
      setRows(name === "spend" ? DEMO_SPEND : DEMO_REVENUE);
      return;
    }
    try {
      const resp = await fetch(`${BASE}/ledger/${name}`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      setRows(await resp.json());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
    }
  }, [name, demo]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { rows, error, refresh };
}

export function useDoctor(demo: boolean) {
  const [data, setData] = useState<DoctorResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (demo) {
      setData({ ok: true, checks: DEMO_DOCTOR });
      return;
    }
    try {
      const resp = await fetch(`${BASE}/doctor`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      setData(await resp.json());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
    }
  }, [demo]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { data, error, refresh };
}

export function useWallet(demo: boolean) {
  const [data, setData] = useState<WalletResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (demo) {
      setData(DEMO_WALLET);
      return;
    }
    try {
      const resp = await fetch(`${BASE}/wallet`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      setData(await resp.json());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
    }
  }, [demo]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { data, error, refresh };
}

export async function probeUrl(
  url: string,
  method = "GET",
): Promise<ProbeResponse> {
  const params = new URLSearchParams({ url, method });
  const resp = await fetch(`${BASE}/probe?${params}`);
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${resp.status}`);
  }
  return resp.json();
}
