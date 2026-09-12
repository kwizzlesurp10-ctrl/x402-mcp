/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_PUBLIC_API_BASE_URL?: string;
  readonly VITE_API_PROXY_TARGET?: string;
  readonly VITE_DASHBOARD_ACTIONS?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

interface Window {
  x402Desktop?: {
    platform: string;
    isElectron: boolean;
  };
}
