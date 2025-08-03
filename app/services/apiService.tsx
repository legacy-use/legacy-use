import axios from 'axios';
import { 
  listSessionsSessionsGet, 
  type Session,
  getApiDefinitionsApiDefinitionsGet,
  exportApiDefinitionApiDefinitionsApiNameExportGet,
  importApiDefinitionApiDefinitionsImportPost,
  getApiDefinitionMetadataApiDefinitionsApiNameMetadataGet,
  getApiDefinitionVersionsApiDefinitionsApiNameVersionsGet,
  getApiDefinitionVersionApiDefinitionsApiNameVersionsVersionIdGet,
  updateApiDefinitionApiDefinitionsApiNamePut,
  archiveApiDefinitionApiDefinitionsApiNameDelete,
  unarchiveApiDefinitionApiDefinitionsApiNameUnarchivePost,
  type ImportApiDefinitionRequest,
  getSessionSessionsSessionIdGet,
  createSessionSessionsPost,
  deleteSessionSessionsSessionIdDelete,
  hardDeleteSessionSessionsSessionIdHardDelete,
  type SessionCreate,
  listAllJobsJobsGet,
  listTargetJobsTargetsTargetIdJobsGet,
  createJobTargetsTargetIdJobsPost,
  getJobTargetsTargetIdJobsJobIdGet,
  getQueueStatusJobsQueueStatusGet,
  interruptJobTargetsTargetIdJobsJobIdInterruptPost,
  cancelJobTargetsTargetIdJobsJobIdCancelPost,
  getJobLogsTargetsTargetIdJobsJobIdLogsGet,
  getJobHttpExchangesTargetsTargetIdJobsJobIdHttpExchangesGet,
  resolveJobTargetsTargetIdJobsJobIdResolvePost,
  resumeJobTargetsTargetIdJobsJobIdResumePost,
  type JobCreate,
  type JobLogEntry,
  listTargetsTargetsGet,
  createTargetTargetsPost,
  getTargetTargetsTargetIdGet,
  updateTargetTargetsTargetIdPut,
  deleteTargetTargetsTargetIdDelete,
  hardDeleteTargetTargetsTargetIdHardDelete,
  type TargetCreate,
  type TargetUpdate,
  getProvidersSettingsProvidersGet,
  updateProviderSettingsSettingsProvidersPost,
  type UpdateProviderRequest
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
  try {
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
  } catch (error) {
    console.error('Error testing API key:', error);
    throw error;
  }
};

// Function to get provider configuration
export const getProviders = async () => {
  return await getProvidersSettingsProvidersGet();
};

// Function to update provider settings
export const updateProviderSettings = async (provider: string, credentials: { [key: string]: string }) => {
  const request: UpdateProviderRequest = {
    provider,
    credentials,
  };
  return await updateProviderSettingsSettingsProvidersPost(request);
};

// Function to check if any API provider is configured (after ensuring API key is provided)
export const checkApiProviderConfiguration = async () => {
  try {
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
  } catch (error) {
    console.error('Error checking API provider configuration:', error);
    return {
      hasApiKey: !!localStorage.getItem('apiKey'),
      hasConfiguredProvider: false,
      error: `Failed to check provider configuration: ${error.message}`,
      providers: [],
    };
  }
};

// API Definitions
export const getApiDefinitions = async (include_archived = false) => {
  return await getApiDefinitionsApiDefinitionsGet({ include_archived });
};

export const exportApiDefinition = async (apiName: string) => {
  return await exportApiDefinitionApiDefinitionsApiNameExportGet(apiName);
};

export const importApiDefinition = async (apiDefinition: any) => {
  const request: ImportApiDefinitionRequest = {
    api_definition: apiDefinition,
  };
  return await importApiDefinitionApiDefinitionsImportPost(request);
};

export const getApiDefinitionDetails = async (apiName: string) => {
  try {
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
  } catch (error) {
    console.error(`Error fetching API definition details for ${apiName}:`, error);

    // If we get a 404 error, it might be because the API is archived
    // In this case, we'll return a basic API definition with just the name and archived status
    if (error.response && error.response.status === 404) {
      return {
        name: apiName,
        description: 'This API is archived and its definition is not available.',
        parameters: [],
        prompt: '',
        prompt_cleanup: '',
        response_example: {},
        is_archived: true,
      };
    }

    throw error;
  }
};

export const getApiDefinitionVersions = async (apiName: string) => {
  const response = await getApiDefinitionVersionsApiDefinitionsApiNameVersionsGet(apiName);
  return response.versions;
};

export const getApiDefinitionVersion = async (apiName: string, versionId: string) => {
  const response = await getApiDefinitionVersionApiDefinitionsApiNameVersionsVersionIdGet(apiName, versionId);
  return response.version;
};

export const updateApiDefinition = async (apiName: string, apiDefinition: any) => {
  const request: ImportApiDefinitionRequest = {
    api_definition: apiDefinition,
  };
  return await updateApiDefinitionApiDefinitionsApiNamePut(apiName, request);
};

export const archiveApiDefinition = async (apiName: string) => {
  return await archiveApiDefinitionApiDefinitionsApiNameDelete(apiName);
};

export const unarchiveApiDefinition = async (apiName: string) => {
  return await unarchiveApiDefinitionApiDefinitionsApiNameUnarchivePost(apiName);
};

// Sessions
export const getSessions = async (include_archived = false): Promise<Session[]> => {
  return listSessionsSessionsGet({ include_archived });
};

export const getSession = async (sessionId: string) => {
  return await getSessionSessionsSessionIdGet(sessionId);
};

export const createSession = async (sessionData: SessionCreate) => {
  return await createSessionSessionsPost(sessionData);
};

export const deleteSession = async (sessionId: string, hardDelete = false) => {
  if (hardDelete) {
    return await hardDeleteSessionSessionsSessionIdHardDelete(sessionId);
  } else {
    return await deleteSessionSessionsSessionIdDelete(sessionId);
  }
};

// Jobs
export const getJobs = async (targetId: string) => {
  return await listTargetJobsTargetsTargetIdJobsGet(targetId);
};

export const getJobQueueStatus = async () => {
  return await getQueueStatusJobsQueueStatusGet();
};

export const getAllJobs = async (limit = 10, offset = 0, filters = {}) => {
  try {
    const params = {
      limit,
      offset,
      ...filters, // Include any additional filters: status, target_id, api_name
    };

    return await listAllJobsJobsGet(params);
  } catch (error) {
    console.error('Error fetching all jobs:', error);
    // Return an empty response with default values to avoid null errors
    return { jobs: [], total_count: 0 };
  }
};

export const getJob = async (targetId: string, jobId: string) => {
  return await getJobTargetsTargetIdJobsJobIdGet(targetId, jobId);
};

export const createJob = async (targetId: string, jobData: JobCreate) => {
  return await createJobTargetsTargetIdJobsPost(targetId, jobData);
};

export const interruptJob = async (targetId: string, jobId: string) => {
  return await interruptJobTargetsTargetIdJobsJobIdInterruptPost(targetId, jobId);
};

export const cancelJob = async (targetId: string, jobId: string) => {
  return await cancelJobTargetsTargetIdJobsJobIdCancelPost(targetId, jobId);
};

export const getJobLogs = async (targetId: string, jobId: string) => {
  try {
    const logs = await getJobLogsTargetsTargetIdJobsJobIdLogsGet(targetId, jobId);

    // Convert log_type to type for compatibility with LogViewer
    return logs.map((log: JobLogEntry) => ({
      ...log,
      type: log.log_type, // Add type property while preserving log_type
    }));
  } catch (error) {
    console.error('Error fetching job logs:', error);
    throw error;
  }
};

export const getJobHttpExchanges = async (targetId: string, jobId: string) => {
  return await getJobHttpExchangesTargetsTargetIdJobsJobIdHttpExchangesGet(targetId, jobId);
};

// Targets
export const getTargets = async (include_archived = false) => {
  return await listTargetsTargetsGet({ include_archived });
};

export const createTarget = async (targetData: TargetCreate) => {
  return await createTargetTargetsPost(targetData);
};

export const getTarget = async (targetId: string) => {
  return await getTargetTargetsTargetIdGet(targetId);
};

export const updateTarget = async (targetId: string, targetData: TargetUpdate) => {
  return await updateTargetTargetsTargetIdPut(targetId, targetData);
};

export const deleteTarget = async (targetId: string, hardDelete = false) => {
  if (hardDelete) {
    return await hardDeleteTargetTargetsTargetIdHardDelete(targetId);
  } else {
    return await deleteTargetTargetsTargetIdDelete(targetId);
  }
};

// Resolve a job (set to success with custom result)
export const resolveJob = async (targetId: string, jobId: string, result: any) => {
  return await resolveJobTargetsTargetIdJobsJobIdResolvePost(targetId, jobId, result);
};

// Health check
export const checkTargetHealth = async (containerIp: string) => {
  try {
    const response = await axios.get(`http://${containerIp}:8088/health`, { timeout: 2000 });
    return response.data;
  } catch (error) {
    console.error('Error checking target health:', error);
    throw error;
  }
};

// Resume Job Function (New)
export const resumeJob = async (targetId: string, jobId: string) => {
  return await resumeJobTargetsTargetIdJobsJobIdResumePost(targetId, jobId);
};
