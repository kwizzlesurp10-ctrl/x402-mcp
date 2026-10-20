/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  /** Public paid storefront origin (Resource/Visit URLs). Never the SPA host. */
  readonly VITE_STOREFRONT_BASE_URL?: string;
  readonly VITE_DEMO_DEFAULT?: string;
  readonly VITE_DASHBOARD_ACTIONS?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
