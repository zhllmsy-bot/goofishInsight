import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';

const DEFAULT_FASTAPI_ORIGIN = 'http://127.0.0.1:8791';
const DEFAULT_BFF_ORIGIN = 'http://127.0.0.1:8787';

function normalizeOrigin(value?: string) {
  if (!value) {
    return null;
  }
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed.replace(/\/+$/, '') : null;
}

function resolveDashboardProxyTarget() {
  const explicitProxyTarget = normalizeOrigin(process.env.VITE_PROXY_TARGET);
  if (explicitProxyTarget) {
    return explicitProxyTarget;
  }

  const mode = (process.env.VITE_DASHBOARD_API_MODE ?? 'fastapi').trim().toLowerCase();

  if (mode === 'bff') {
    return normalizeOrigin(process.env.VITE_BFF_ORIGIN) ?? DEFAULT_BFF_ORIGIN;
  }

  return (
    normalizeOrigin(process.env.VITE_FASTAPI_ORIGIN) ?? DEFAULT_FASTAPI_ORIGIN
  );
}

const dashboardProxyTarget = resolveDashboardProxyTarget();

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: '127.0.0.1',
    port: 5174,
    proxy: {
      '/api/dashboard': {
        target: dashboardProxyTarget,
        changeOrigin: true,
      },
      '/api/progress': {
        target: dashboardProxyTarget,
        changeOrigin: true,
      },
      '/api/config': {
        target: dashboardProxyTarget,
        changeOrigin: true,
      },
      '/api/buy': {
        target: dashboardProxyTarget,
        changeOrigin: true,
      },
    },
  },
});
