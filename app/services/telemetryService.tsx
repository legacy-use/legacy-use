import posthog from 'posthog-js';

// Forwarding the distinct_id to the backend
export const forwardDistinctId = (config: { headers?: Record<string, any> }) => {
  // making sure headers is defined
  if (!config.headers) {
    config.headers = {};
  }
  // add posthog distinct_id to request headers for backend
  config.headers['X-Distinct-ID'] = posthog.get_distinct_id();
  return config;
};
