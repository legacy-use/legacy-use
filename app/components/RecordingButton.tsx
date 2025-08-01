import { Button } from '@mui/material';
import { useEffect, useState } from 'react';
import {
  type RecordingRequest,
  type RecordingResultResponse,
  RecordingStatus,
  type RecordingStatusResponse,
} from '../gen/endpoints';
import { getRecordingStatus, startRecording, stopRecording } from '../services/apiService';
import { formatDuration } from '../utils/formatDuration';
import RecordIcon from './RecordIcon';

interface RecordingButtonProps {
  sessionId: string;
  onRecordingStarted?: (recordingStatus: RecordingStatusResponse) => void;
  onRecordingStopped?: (recordingResult: RecordingResultResponse) => void;
}

const recordingOptions: RecordingRequest = {
  framerate: 30,
  quality: 'fast',
  format: 'mp4',
  capture_vnc_input: true,
};

export default function RecordingButton({
  sessionId,
  onRecordingStarted,
  onRecordingStopped,
}: RecordingButtonProps) {
  const [recordingStatus, setRecordingStatus] = useState<RecordingStatusResponse | null>(null);

  useEffect(() => {
    const interval = setInterval(async () => {
      const result = await getRecordingStatus(sessionId);
      setRecordingStatus(result);
    }, 1000);

    return () => clearInterval(interval);
  }, [sessionId]);

  const handleStartRecording = async () => {
    const result = await startRecording(sessionId, recordingOptions);
    setRecordingStatus(result);
    onRecordingStarted?.(result);
  };

  const handleStopRecording = async () => {
    const result = await stopRecording(sessionId);
    onRecordingStopped?.(result);
  };

  if (!recordingStatus) {
    return <div>Loading...</div>;
  }

  const isRecording =
    recordingStatus?.status === RecordingStatus.started ||
    recordingStatus?.status === RecordingStatus.recording;

  return (
    <div>
      {isRecording ? (
        <Button
          variant="outlined"
          color="error"
          onClick={handleStopRecording}
          startIcon={<RecordIcon />}
        >
          Stop Recording ({formatDuration(recordingStatus?.duration_seconds ?? 0)})
        </Button>
      ) : (
        <Button variant="contained" color="error" onClick={handleStartRecording}>
          Start Recording
        </Button>
      )}
    </div>
  );
}
