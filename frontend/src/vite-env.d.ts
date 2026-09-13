/// <reference types="vite/client" />

// Public build-time configuration (documented in frontend/.env.example). Never put secrets here:
// every VITE_* value is visible in the shipped JavaScript.
interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_USE_MOCK_DATA?: string;
  readonly VITE_API_TIMEOUT_MS?: string;
  readonly VITE_PREDICTION_STRATEGY?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
