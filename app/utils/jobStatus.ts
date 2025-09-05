import type { ChipProps } from '@mui/material/Chip';

export type JobStatusColor = ChipProps['color'];

// Centralized mapping for job status -> MUI Chip color
const JOB_STATUS_TO_CHIP_COLOR: Record<string, JobStatusColor> = {
  pending: 'warning',
  queued: 'warning',
  running: 'primary',
  recovery: 'warning',
  paused: 'secondary',
  success: 'success',
  failed: 'warning', // failed same color as warning recovery, for more differentiation from error
  error: 'error',
  canceled: 'default',
  interrupted: 'error',
};

export const getJobStatusChipColor = (status?: string): JobStatusColor => {
  const key = (status || '').toLowerCase();
  return JOB_STATUS_TO_CHIP_COLOR[key] || 'default';
};

export default getJobStatusChipColor;
