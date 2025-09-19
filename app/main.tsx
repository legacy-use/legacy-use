import * as Sentry from '@sentry/react';
import { browserTracingIntegration, replayIntegration } from '@sentry/react';
import type { PostHogConfig } from 'posthog-js';
import { PostHogProvider } from 'posthog-js/react';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import CloudApp from './cloud';
import { applyTenantToPosthog } from './services/telemetryService';

const isCloudDomain = window.location.host.startsWith('cloud');
const Main = isCloudDomain ? CloudApp : App;

const options: Partial<PostHogConfig> = {
  api_host: import.meta.env.VITE_PUBLIC_POSTHOG_HOST || 'https://eu.i.posthog.com',
  opt_out_capturing_by_default: import.meta.env.VITE_PUBLIC_DISABLE_TRACKING === 'true',
  debug: false,
  disable_session_recording: true,
  person_profiles: 'identified_only',
  mask_all_text: true,
  loaded: client => {
    applyTenantToPosthog(client);
  },
};

const apiKey =
  import.meta.env.VITE_PUBLIC_POSTHOG_KEY || 'phc_i1lWRELFSWLrbwV8M8sddiFD83rVhWzyZhP27T3s6V8';

// Initialize Sentry
Sentry.init({
  dsn: import.meta.env.VITE_SENTRY_DSN_UI,
  integrations: [browserTracingIntegration(), replayIntegration()],
  // Performance Monitoring
  tracesSampleRate: 1.0, // Capture 100% of transactions, reduce in production
  // Session Replay
  replaysSessionSampleRate: 0.1, // Sample rate for session replays (10%)
  replaysOnErrorSampleRate: 1.0, // Sample rate for replays on error (100%)
  environment: import.meta.env.MODE,
  debug: false, // Enable debug mode to see more logs
});

// biome-ignore lint/style/noNonNullAssertion: root is always present
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <PostHogProvider apiKey={apiKey} options={options}>
      <Main />
    </PostHogProvider>
  </StrictMode>,
);
