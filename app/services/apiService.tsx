import axios from 'axios';
import {
  type APIDefinition,
  analyzeVideoTeachingModeAnalyzeVideoPost,
  archiveApiDefinitionApiDefinitionsApiNameDelete,
  cancelJobTargetsTargetIdJobsJobIdCancelPost,
  createJobTargetsTargetIdJobsPost,
  createSessionSessionsPost,
  createTargetTargetsPost,
  deleteSessionSessionsSessionIdDelete,
  deleteTargetTargetsTargetIdDelete,
  exportApiDefinitionApiDefinitionsApiNameExportGet,
  getApiDefinitionMetadataApiDefinitionsApiNameMetadataGet,
  getApiDefinitionsApiDefinitionsGet,
  getApiDefinitionVersionApiDefinitionsApiNameVersionsVersionIdGet,
  getApiDefinitionVersionsApiDefinitionsApiNameVersionsGet,
  getJobHttpExchangesTargetsTargetIdJobsJobIdHttpExchangesGet,
  getJobLogsTargetsTargetIdJobsJobIdLogsGet,
  getJobTargetsTargetIdJobsJobIdGet,
  getProvidersSettingsProvidersGet,
  getQueueStatusJobsQueueStatusGet,
  getSessionRecordingStatusSessionsSessionIdRecordingStatusGet,
  getSessionSessionsSessionIdGet,
  getTargetTargetsTargetIdGet,
  type HttpExchangeLog,
  hardDeleteSessionSessionsSessionIdHardDelete,
  hardDeleteTargetTargetsTargetIdHardDelete,
  type ImportApiDefinitionBody,
  importApiDefinitionApiDefinitionsImportPost,
  interruptJobTargetsTargetIdJobsJobIdInterruptPost,
  type Job,
  type JobCreate,
  type JobLogEntry,
  listAllJobsJobsGet,
  listSessionsSessionsGet,
  listTargetJobsTargetsTargetIdJobsGet,
  listTargetsTargetsGet,
  type PaginatedJobsResponse,
  type ProvidersResponse,
  type RecordingRequest,
  type ResolveJobTargetsTargetIdJobsJobIdResolvePostBody,
  resolveJobTargetsTargetIdJobsJobIdResolvePost,
  resumeJobTargetsTargetIdJobsJobIdResumePost,
  type Session,
  type SessionCreate,
  startSessionRecordingSessionsSessionIdRecordingStartPost,
  stopSessionRecordingSessionsSessionIdRecordingStopPost,
  type Target,
  type TargetCreate,
  type TargetUpdate,
  type UpdateProviderRequest,
  unarchiveApiDefinitionApiDefinitionsApiNameUnarchivePost,
  unarchiveTargetTargetsTargetIdUnarchivePost,
  updateApiDefinitionApiDefinitionsApiNamePut,
  updateProviderSettingsSettingsProvidersPost,
  updateTargetTargetsTargetIdPut,
  getSessionContainerLogsSessionsSessionIdContainerLogsGet,
} from '../gen/endpoints';
import { forwardDistinctId } from './telemetryService';
import { API_BASE_URL } from '../utils/apiConstants';

// Create an axios instance with default config
export const apiClient = axios.create({
  baseURL: API_BASE_URL,
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
export const testApiKey = async (apiKey: string): Promise<APIDefinition[]> => {
  // Create a temporary axios instance with the API key
  const tempClient = axios.create({
    baseURL: API_BASE_URL,
    headers: {
      'X-API-Key': apiKey,
    },
  });

  // Try to access an endpoint that requires authentication
  const response = await tempClient.get(`${API_BASE_URL}/definitions`);
  return response.data;
};

// Function to get provider configuration
export const getProviders = async (): Promise<ProvidersResponse> => {
  return getProvidersSettingsProvidersGet();
};

// Function to update provider settings
export const updateProviderSettings = async (
  provider: string,
  credentials: Record<string, string>,
) => {
  const updateRequest: UpdateProviderRequest = {
    provider,
    credentials,
  };
  return updateProviderSettingsSettingsProvidersPost(updateRequest);
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
export const getApiDefinitions = async (include_archived = false): Promise<APIDefinition[]> => {
  return getApiDefinitionsApiDefinitionsGet({ include_archived });
};

export const exportApiDefinition = async (apiName: string) => {
  return exportApiDefinitionApiDefinitionsApiNameExportGet(apiName);
};

export const importApiDefinition = async (apiDefinition: ImportApiDefinitionBody) => {
  return importApiDefinitionApiDefinitionsImportPost({ api_definition: apiDefinition });
};

export const getApiDefinitionDetails = async (apiName: string) => {
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

export const getApiDefinitionVersions = async (apiName: string) => {
  const response = await getApiDefinitionVersionsApiDefinitionsApiNameVersionsGet(apiName);
  return response.versions;
};

export const getApiDefinitionVersion = async (apiName: string, versionId: string) => {
  const response = await getApiDefinitionVersionApiDefinitionsApiNameVersionsVersionIdGet(
    apiName,
    versionId,
  );
  return response.version;
};

export const updateApiDefinition = async (
  apiName: string,
  apiDefinition: ImportApiDefinitionBody,
) => {
  return updateApiDefinitionApiDefinitionsApiNamePut(apiName, { api_definition: apiDefinition });
};

export const archiveApiDefinition = async (apiName: string) => {
  return archiveApiDefinitionApiDefinitionsApiNameDelete(apiName);
};

export const unarchiveApiDefinition = async (apiName: string) => {
  return unarchiveApiDefinitionApiDefinitionsApiNameUnarchivePost(apiName);
};

// Sessions
export const getSessions = async (include_archived = false): Promise<Session[]> => {
  return listSessionsSessionsGet({ include_archived });
};

export const getSession = async (sessionId: string) => {
  return getSessionSessionsSessionIdGet(sessionId);
};

export const createSession = async (sessionData: SessionCreate): Promise<Session> => {
  return createSessionSessionsPost(sessionData);
};

export const deleteSession = async (sessionId: string, hardDelete = false) => {
  if (hardDelete) {
    return hardDeleteSessionSessionsSessionIdHardDelete(sessionId);
  } else {
    return deleteSessionSessionsSessionIdDelete(sessionId);
  }
};

// Jobs
export const getJobs = async (targetId: string): Promise<Job[]> => {
  return listTargetJobsTargetsTargetIdJobsGet(targetId);
};

export const getJobQueueStatus = async () => {
  return getQueueStatusJobsQueueStatusGet();
};

export const getAllJobs = async (
  limit = 10,
  offset = 0,
  filters = {},
): Promise<PaginatedJobsResponse> => {
  const params = {
    limit,
    offset,
    ...filters, // Include any additional filters: status, target_id, api_name
  };

  return listAllJobsJobsGet(params);
};

export const getJob = async (targetId: string, jobId: string): Promise<Job> => {
  const job = await getJobTargetsTargetIdJobsJobIdGet(targetId, jobId);
  // add Z suffix to the date so JS can parse it as UTC
  if (!job.created_at?.includes('Z')) {
    job.created_at = `${job.created_at}Z`;
  }
  if (job.completed_at && !job.completed_at?.includes('Z')) {
    job.completed_at = `${job.completed_at}Z`;
  }
  return job;
};

export const createJob = async (targetId: string, jobData: JobCreate) => {
  return createJobTargetsTargetIdJobsPost(targetId, jobData);
};

export const interruptJob = async (targetId: string, jobId: string) => {
  return interruptJobTargetsTargetIdJobsJobIdInterruptPost(targetId, jobId);
};

export const cancelJob = async (targetId: string, jobId: string) => {
  return cancelJobTargetsTargetIdJobsJobIdCancelPost(targetId, jobId);
};

export const getJobLogs = async (
  targetId: string,
  jobId: string,
): Promise<(JobLogEntry & { type: string })[]> => {
  const logs = await getJobLogsTargetsTargetIdJobsJobIdLogsGet(targetId, jobId);

  // Convert log_type to type for compatibility with LogViewer
  return logs.map(log => ({
    ...log,
    type: log.log_type, // Add type property while preserving log_type
  }));
};

export const getJobHttpExchanges = async (
  targetId: string,
  jobId: string,
): Promise<HttpExchangeLog[]> => {
  return getJobHttpExchangesTargetsTargetIdJobsJobIdHttpExchangesGet(targetId, jobId);
};

// Targets
export const getTargets = async (include_archived = false): Promise<Target[]> => {
  return listTargetsTargetsGet({ include_archived });
};

export const createTarget = async (targetData: TargetCreate): Promise<Target> => {
  return createTargetTargetsPost(targetData);
};

export const getTarget = async (targetId: string): Promise<Target> => {
  return getTargetTargetsTargetIdGet(targetId);
};

export const updateTarget = async (targetId: string, targetData: TargetUpdate): Promise<Target> => {
  return updateTargetTargetsTargetIdPut(targetId, targetData);
};

export const deleteTarget = async (targetId: string, hardDelete = false) => {
  if (hardDelete) {
    return hardDeleteTargetTargetsTargetIdHardDelete(targetId);
  } else {
    return deleteTargetTargetsTargetIdDelete(targetId);
  }
};

export const unarchiveTarget = async (targetId: string) => {
  return unarchiveTargetTargetsTargetIdUnarchivePost(targetId);
};

// Resolve a job (set to success with custom result)
export const resolveJob = async (
  targetId: string,
  jobId: string,
  result: ResolveJobTargetsTargetIdJobsJobIdResolvePostBody,
) => {
  return resolveJobTargetsTargetIdJobsJobIdResolvePost(targetId, jobId, result);
};

// Health check
export const checkTargetHealth = async (containerIp: string) => {
  const response = await axios.get(`http://${containerIp}:8088/health`, { timeout: 2000 });
  return response.data;
};

// Resume Job Function (New)
export const resumeJob = async (targetId: string, jobId: string): Promise<Job> => {
  return resumeJobTargetsTargetIdJobsJobIdResumePost(targetId, jobId);
};

// Recording functions
export const startRecording = async (sessionId: string, options: RecordingRequest) => {
  return startSessionRecordingSessionsSessionIdRecordingStartPost(sessionId, options);
};

export const stopRecording = async (sessionId: string) => {
  return stopSessionRecordingSessionsSessionIdRecordingStopPost(sessionId);
};

// AI Analysis
export const analyzeVideo = async (videoFile: Blob) => {
  return analyzeVideoTeachingModeAnalyzeVideoPost({ video: videoFile });
};

export const getRecordingStatus = async (sessionId: string) => {
  return getSessionRecordingStatusSessionsSessionIdRecordingStatusGet(sessionId);
};

// Container logs
export const getSessionContainerLogs = async (sessionId: string, lines = 1000) => {
  return getSessionContainerLogsSessionsSessionIdContainerLogsGet(sessionId, { lines });
};
