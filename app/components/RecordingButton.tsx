import ArrowDropDownIcon from '@mui/icons-material/ArrowDropDown';
import UploadIcon from '@mui/icons-material/Upload';
import {
  Button,
  ButtonGroup,
  ClickAwayListener,
  Grow,
  MenuItem,
  MenuList,
  Paper,
  Popper,
} from '@mui/material';
import { useEffect, useRef, useState } from 'react';
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
  onVideoFileSelected?: (file: File) => void;
}

const recordingOptions: RecordingRequest = {
  framerate: 30,
  quality: 'fast',
  format: 'mp4',
};

export default function RecordingButton({
  sessionId,
  onRecordingStarted,
  onRecordingStopped,
  onVideoFileSelected,
}: RecordingButtonProps) {
  const [recordingStatus, setRecordingStatus] = useState<RecordingStatusResponse | null>(null);
  const [open, setOpen] = useState(false);
  const anchorRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

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

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      onVideoFileSelected?.(file);
    }
  };

  const handleVideoUpload = () => {
    setOpen(false);
    fileInputRef.current?.click();
  };

  const handleToggle = () => {
    setOpen(prevOpen => !prevOpen);
  };

  const handleClose = (event: Event) => {
    if (anchorRef.current?.contains(event.target as Node)) {
      return;
    }
    setOpen(false);
  };

  if (!recordingStatus) {
    return <div>Loading...</div>;
  }

  const isRecording =
    recordingStatus?.status === RecordingStatus.started ||
    recordingStatus?.status === RecordingStatus.recording;

  return (
    <div>
      <input
        ref={fileInputRef}
        type="file"
        accept="video/*"
        onChange={handleFileChange}
        style={{ display: 'none' }}
      />

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
        <>
          <ButtonGroup
            variant="contained"
            color="error"
            ref={anchorRef}
            aria-label="Recording actions"
          >
            <Button onClick={handleStartRecording} startIcon={<RecordIcon />}>
              Start Recording
            </Button>
            <Button size="small" onClick={handleToggle}>
              <ArrowDropDownIcon />
            </Button>
          </ButtonGroup>

          <Popper
            sx={{ zIndex: 1 }}
            open={open}
            anchorEl={anchorRef.current}
            transition
            disablePortal
          >
            {({ TransitionProps, placement }) => (
              <Grow
                {...TransitionProps}
                style={{
                  transformOrigin: placement === 'bottom' ? 'center top' : 'center bottom',
                }}
              >
                <Paper>
                  <ClickAwayListener onClickAway={handleClose}>
                    <MenuList id="split-button-menu" autoFocusItem>
                      <MenuItem onClick={handleVideoUpload}>
                        <UploadIcon sx={{ mr: 1 }} />
                        Upload Video
                      </MenuItem>
                    </MenuList>
                  </ClickAwayListener>
                </Paper>
              </Grow>
            )}
          </Popper>
        </>
      )}
    </div>
  );
}
