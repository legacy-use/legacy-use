import type { PostHogConfig } from 'posthog-js';
import { PostHogProvider } from 'posthog-js/react';

const posthogOptions: Partial<PostHogConfig> = {
  api_host: 'https://eu.i.posthog.com',
  opt_out_capturing_by_default: import.meta.env.VITE_PUBLIC_DISABLE_TRACKING === 'true',
  debug: false,
  disable_session_recording: true,
  person_profiles: 'identified_only',
  mask_all_text: true,
};

const posthogApiKey = 'phc_i1lWRELFSWLrbwV8M8sddiFD83rVhWzyZhP27T3s6V8';

export const PostHog = ({ children }: { children: React.ReactNode }) => {
  return (
    <PostHogProvider apiKey={posthogApiKey} options={posthogOptions}>
      {children}
    </PostHogProvider>
  );
};
