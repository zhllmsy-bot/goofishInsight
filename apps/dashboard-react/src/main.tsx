import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import { AppErrorBoundary } from './shared/components/AppErrorBoundary'
import { AppProviders } from './app/providers/AppProviders'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AppErrorBoundary
      onError={(error, errorInfo) => {
        console.error('Dashboard app boundary caught an error', error, errorInfo)
      }}
    >
      <AppProviders>
        <App />
      </AppProviders>
    </AppErrorBoundary>
  </StrictMode>,
)
