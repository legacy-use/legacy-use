export const formatDuration = (durationSeconds: number) => {
  if (durationSeconds === null || durationSeconds === undefined) return 'N/A';

  // Round to 0 decimal places for sub-minute durations
  if (durationSeconds < 60) {
    return `${durationSeconds.toFixed(0)}s`;
  }

  const hours = Math.floor(durationSeconds / 3600);
  const minutes = Math.floor((durationSeconds % 3600) / 60);
  const seconds = Math.floor(durationSeconds % 60);

  const parts = [];
  if (hours > 0) parts.push(`${hours}h`);
  if (minutes > 0) parts.push(`${minutes}m`);
  if (seconds > 0 || parts.length === 0) parts.push(`${seconds}s`);

  return parts.join(' ');
};
