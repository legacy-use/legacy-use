import Box from '@mui/material/Box';
import FormControl from '@mui/material/FormControl';
import InputLabel from '@mui/material/InputLabel';
import MenuItem from '@mui/material/MenuItem';
import Select from '@mui/material/Select';
import Typography from '@mui/material/Typography';

const SessionSelector = ({ targetSessions, selectedSession, handleSessionChange }) => (
  <Box sx={{ mb: 3 }}>
    <Typography variant="h5" gutterBottom>
      Sessions
    </Typography>
    <FormControl fullWidth variant="outlined" sx={{ mb: 2 }}>
      <InputLabel id="session-select-label">Select Session</InputLabel>
      <Select
        labelId="session-select-label"
        value={selectedSession ? selectedSession.id : ''}
        onChange={handleSessionChange}
        label="Select Session"
      >
        {targetSessions.length > 0 ? (
          targetSessions.map(session => (
            <MenuItem key={session.id} value={session.id}>
              Session {session.id.substring(0, 8)}
              {session.is_archived && ' (Archived)'}
            </MenuItem>
          ))
        ) : (
          <MenuItem value="" disabled>
            No sessions available
          </MenuItem>
        )}
      </Select>
    </FormControl>
  </Box>
);

export default SessionSelector;
