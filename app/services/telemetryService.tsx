import posthog from 'posthog-js';
const IP_ADDRESS_REGEX = /^(\d{1,3}\.){3}\d{1,3}$/;

const extractTenantFromHostname = (hostname: string): string | null => {
  const normalizedHost = hostname?.toLowerCase()?.trim();
  if (!normalizedHost) {
    return null;
  }

  if (IP_ADDRESS_REGEX.test(normalizedHost)) {
    return null;
  }

  const segments = normalizedHost.split('.').filter(Boolean);
  if (segments.length < 2) {
    return null;
  }

  const [subdomain] = segments;

  // Require at least one subdomain (e.g. tenant.example.com)
  if (segments.length === 2) {
    return null;
  }

  return subdomain;
};

export const getCurrentTenant = (): string | null => {
  if (typeof window === 'undefined') {
    return null;
  }

  const tenant = extractTenantFromHostname(window.location.hostname);
  return tenant;
};

export const applyTenantToPosthog = (client: typeof posthog = posthog) => {
  const tenant = getCurrentTenant();
  if (!tenant) {
    return;
  }

  // using super properties to set the tenant, across all future events
  client.register({ tenant });
};
// Forwarding the distinct_id to the backend
export const forwardDistinctId = config => {
  // making sure headers is defined
  if (!config.headers) {
    config.headers = {};
  }
  // add posthog distinct_id to request headers for backend
  config.headers['X-Distinct-ID'] = posthog.get_distinct_id();
};
