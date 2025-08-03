import axios from 'axios';
import {
  listSessionsSessionsGet,
  type Session,
  getProvidersSettingsProvidersGet,
  updateProviderSettingsSettingsProvidersPost,
  getApiDefinitionsApiDefinitionsGet,
  exportApiDefinitionApiDefinitionsApiNameExportGet,
  importApiDefinitionApiDefinitionsImportPost,
  getApiDefinitionMetadataApiDefinitionsApiNameMetadataGet,
  getApiDefinitionVersionsApiDefinitionsApiNameVersionsGet,
  getApiDefinitionVersionApiDefinitionsApiNameVersionsVersionIdGet,
  updateApiDefinitionApiDefinitionsApiNamePut,
  archiveApiDefinitionApiDefinitionsApiNameDelete,
  unarchiveApiDefinitionApiDefinitionsApiNameUnarchivePost,
  getSessionSessionsSessionIdGet,
  createSessionSessionsPost,
  deleteSessionSessionsSessionIdDelete,
  hardDeleteSessionSessionsSessionIdHardDelete,
  listAllJobsJobsGet,
  getQueueStatusJobsQueueStatusGet,
  getJobTargetsTargetIdJobsJobIdGet,
  createJobTargetsTargetIdJobsPost,
  interruptJobTargetsTargetIdJobsJobIdInterruptPost,
  cancelJobTargetsTargetIdJobsJobIdCancelPost,
  getJobLogsTargetsTargetIdJobsJobIdLogsGet,
  getJobHttpExchangesTargetsTargetIdJobsJobIdHttpExchangesGet,
  listTargetsTargetsGet,
  createTargetTargetsPost,
  getTargetTargetsTargetIdGet,
  updateTargetTargetsTargetIdPut,
  deleteTargetTargetsTargetIdDelete,
  hardDeleteTargetTargetsTargetIdHardDelete,
  resolveJobTargetsTargetIdJobsJobIdResolvePost,
  resumeJobTargetsTargetIdJobsJobIdResumePost,
  listTargetJobsTargetsTargetIdJobsGet,
} from '../gen/endpoints';
import { forwardDistinctId } from './telemetryService';

// Always use the API_URL from environment variables
// This should be set to the full URL of your API server (e.g., http://localhost:8088)
export const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8088';

// Create an axios instance with default config
export const apiClient = axios.create({
  baseURL: API_URL,
});

// Log every request with telemetry
apiClient.interceptors.request.use(config => {
  forwardDistinctId(config);
  return config;
});

// Function to set the API key for all requests
export const setApiKeyHeader = (apiKey: string | null) => {
  if (apiKey) {
    apiClient.defaults.headers.common['X-API-Key'] = apiKey;
    // Also store in localStorage for the interceptor
    localStorage.setItem('apiKey', apiKey);
  } else {
    delete apiClient.defaults.headers.common['X-API-Key'];
    localStorage.removeItem('apiKey');
  }
};

// Add a request interceptor to ensure API key is set for every request
apiClient.interceptors.request.use(
  config => {
    // Check if API key is in localStorage but not in headers
    const apiKey = localStorage.getItem('apiKey');
    if (apiKey && !config.headers['X-API-Key']) {
      config.headers['X-API-Key'] = apiKey;
    }

    return config;
  },
  error => {
    return Promise.reject(error);
  },
);

// Function to test if an API key is valid
export const testApiKey = async (apiKey: string) => {
  // Create a temporary axios instance with the API key
  const tempClient = axios.create({
    baseURL: API_URL,
    headers: {
      'X-API-Key': apiKey,
    },
  });

  // Try to access an endpoint that requires authentication
  const response = await tempClient.get(`${API_URL}/api/definitions`);
  return response.data;
};

// Function to get provider configuration
export const getProviders = async () => {
  return getProvidersSettingsProvidersGet();
};

// Function to update provider settings
export const updateProviderSettings = async (provider, credentials) => {
  return updateProviderSettingsSettingsProvidersPost({
    provider,
    credentials,
  });
};

// Function to check if any API provider is configured (after ensuring API key is provided)
export const checkApiProviderConfiguration = async () => {
  // Get provider configuration
  const providersData = await getProviders();

  // Check if any provider is configured (has available = true)
  const configuredProviders = providersData.providers.filter(provider => provider.available);
  const hasConfiguredProvider = configuredProviders.length > 0;

  return {
    hasApiKey: true,
    hasConfiguredProvider,
    currentProvider: providersData.current_provider,
    configuredProviders,
    allProviders: providersData.providers,
    error: null,
  };
};

// API Definitions
export const getApiDefinitions = async (include_archived = false) => {
  return getApiDefinitionsApiDefinitionsGet({ include_archived });
};

export const exportApiDefinition = async apiName => {
  return exportApiDefinitionApiDefinitionsApiNameExportGet(apiName);
};

export const importApiDefinition = async apiDefinition => {
  return importApiDefinitionApiDefinitionsImportPost({
    api_definition: apiDefinition,
  });
};

export const getApiDefinitionDetails = async apiName => {
  // First, get the metadata to check if the API is archived
  const metadataResponse = await getApiDefinitionMetadataApiDefinitionsApiNameMetadataGet(apiName);
  const isArchived = metadataResponse.is_archived;

  // For both archived and non-archived APIs, use the export endpoint
  // The backend should handle returning the correct data
  const response = await exportApiDefinitionApiDefinitionsApiNameExportGet(apiName);
  const apiDefinition = response.api_definition;

  // Return the API definition with the archived status
  return {
    ...apiDefinition,
    is_archived: isArchived,
  };
};

export const getApiDefinitionVersions = async apiName => {
  const response = await getApiDefinitionVersionsApiDefinitionsApiNameVersionsGet(apiName);
  return response.versions;
};

export const getApiDefinitionVersion = async (apiName, versionId) => {
  const response = await getApiDefinitionVersionApiDefinitionsApiNameVersionsVersionIdGet(
    apiName,
    versionId,
  );
  return response.version;
};

export const updateApiDefinition = async (apiName, apiDefinition) => {
  return updateApiDefinitionApiDefinitionsApiNamePut(apiName, {
    api_definition: apiDefinition,
  });
};

export const archiveApiDefinition = async apiName => {
  return archiveApiDefinitionApiDefinitionsApiNameDelete(apiName);
};

export const unarchiveApiDefinition = async apiName => {
  return unarchiveApiDefinitionApiDefinitionsApiNameUnarchivePost(apiName);
};

// Sessions
export const getSessions = async (include_archived = false): Promise<Session[]> => {
  return listSessionsSessionsGet({ include_archived });
};

export const getSession = async sessionId => {
  return getSessionSessionsSessionIdGet(sessionId);
};

export const createSession = async sessionData => {
  return createSessionSessionsPost(sessionData);
};

export const deleteSession = async (sessionId, hardDelete = false) => {
  if (hardDelete) {
    return hardDeleteSessionSessionsSessionIdHardDelete(sessionId);
  } else {
    return deleteSessionSessionsSessionIdDelete(sessionId);
  }
};

// Jobs
export const getJobs = async targetId => {
  return listTargetJobsTargetsTargetIdJobsGet(targetId, {});
};

export const getJobQueueStatus = async () => {
  return getQueueStatusJobsQueueStatusGet();
};

export const getAllJobs = async (limit = 10, offset = 0, filters = {}) => {
  const params = {
    limit,
    offset,
    ...filters, // Include any additional filters: status, target_id, api_name
  };

  return listAllJobsJobsGet(params);
};

export const getJob = async (targetId, jobId) => {
  const response = await getJobTargetsTargetIdJobsJobIdGet(targetId, jobId);
  // add Z suffix to the date so JS can parse it as UTC
  response.created_at = response.created_at + 'Z';
  if (response.completed_at) {
    response.completed_at = response.completed_at + 'Z';
  }
  return response;
};

export const createJob = async (targetId, jobData) => {
  return createJobTargetsTargetIdJobsPost(targetId, jobData);
};

export const interruptJob = async (targetId, jobId) => {
  return interruptJobTargetsTargetIdJobsJobIdInterruptPost(targetId, jobId);
};

export const cancelJob = async (targetId, jobId) => {
  return cancelJobTargetsTargetIdJobsJobIdCancelPost(targetId, jobId);
};

export const getJobLogs = async (targetId, jobId) => {
  const response = await getJobLogsTargetsTargetIdJobsJobIdLogsGet(targetId, jobId);

  // The response is now a direct array of log objects
  const logs = response || [];

  // Convert log_type to type for compatibility with LogViewer
  return logs.map(log => ({
    ...log,
    type: log.log_type, // Add type property while preserving log_type
  }));
};

export const getJobHttpExchanges = async (targetId, jobId) => {
  const response = await getJobHttpExchangesTargetsTargetIdJobsJobIdHttpExchangesGet(
    targetId,
    jobId,
  );

  // Handle the new response format where the endpoint directly returns an array
  // instead of a nested structure with http_exchanges key
  const httpExchanges = Array.isArray(response) ? response : response.http_exchanges || [];

  return httpExchanges;
};

// Targets
export const getTargets = async (include_archived = false) => {
  return listTargetsTargetsGet({ include_archived });
};

export const createTarget = async targetData => {
  return createTargetTargetsPost(targetData);
};

export const getTarget = async targetId => {
  return getTargetTargetsTargetIdGet(targetId);
};

export const updateTarget = async (targetId, targetData) => {
  return updateTargetTargetsTargetIdPut(targetId, targetData);
};

export const deleteTarget = async (targetId, hardDelete = false) => {
  if (hardDelete) {
    return hardDeleteTargetTargetsTargetIdHardDelete(targetId);
  } else {
    return deleteTargetTargetsTargetIdDelete(targetId);
  }
};

// Resolve a job (set to success with custom result)
export const resolveJob = async (targetId, jobId, result) => {
  return resolveJobTargetsTargetIdJobsJobIdResolvePost(targetId, jobId, result);
};

// Health check
export const checkTargetHealth = async containerIp => {
  const response = await axios.get(`http://${containerIp}:8088/health`, { timeout: 2000 });
  return response.data;
};

// Resume Job Function (New)
export const resumeJob = async (targetId, jobId) => {
  return resumeJobTargetsTargetIdJobsJobIdResumePost(targetId, jobId);
};
