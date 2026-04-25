/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_LEGACY_ORIGIN?: string;
  readonly VITE_DASHBOARD_API_MODE?: string;
  readonly VITE_FASTAPI_ORIGIN?: string;
  readonly VITE_BFF_ORIGIN?: string;
  readonly VITE_DASHBOARD_API_TIMEOUT_MS?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
