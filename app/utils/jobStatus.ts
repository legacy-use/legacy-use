import type { ChipProps } from '@mui/material/Chip';

export type JobStatusColor = ChipProps['color'];

// Centralized mapping for job status -> MUI Chip color
const JOB_STATUS_TO_CHIP_COLOR: Record<string, JobStatusColor> = {
  pending: 'warning',
  queued: 'warning',
  running: 'primary',
  paused: 'secondary',
  success: 'success',
  error: 'error',
  canceled: 'default',
  interrupted: 'error',
};

export const getJobStatusChipColor = (status?: string): JobStatusColor => {
  const key = (status || '').toLowerCase();
  return JOB_STATUS_TO_CHIP_COLOR[key] || 'default';
};

export default getJobStatusChipColor;


