import {
  Alert,
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  TextField,
} from '@mui/material';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getApiDefinitionDetails, importApiDefinition } from '../services/apiService';
import type { ImportApiDefinitionBody } from '../gen/endpoints';

const DuplicateApiDialog = ({ open, onClose, onApiDuplicated, apiName }: { open: boolean; onClose: () => void; onApiDuplicated: (name: string) => void; apiName: string }) => {
  const navigate = useNavigate();
  const [newApiName, setNewApiName] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleChange = e => {
    setNewApiName(e.target.value);
  };

  const handleDuplicate = async () => {
    if (!newApiName.trim()) {
      setError('New API name is required');
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const body = {
        name: newApiName,
        description: '',
        parameters: [],
        prompt: '',
        prompt_cleanup: '',
        response_example: {},
      } as ImportApiDefinitionBody;
      await importApiDefinition(body);
      onApiDuplicated(newApiName);
      onClose();
      navigate(`/apis/${newApiName.trim()}/edit`);
    } catch (err) {
      console.error('Error duplicating API:', err);
      setError(err.response?.data?.detail || 'Failed to duplicate API');
    } finally {
      setLoading(false);
    }
  };

  const handleCancel = () => {
    onClose();
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Duplicate API</DialogTitle>
      <DialogContent>
        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}

        <TextField
          name="newName"
          label="New API Name"
          value={newApiName}
          onChange={handleChange}
          fullWidth
          required
          margin="normal"
          helperText={`Enter a unique name for the duplicated API. This will create a copy of '${apiName}'.`}
          autoFocus
        />
      </DialogContent>
      <DialogActions>
        <Button onClick={handleCancel} disabled={loading}>
          Cancel
        </Button>
        <Button
          onClick={handleDuplicate}
          variant="contained"
          color="primary"
          disabled={loading}
          startIcon={loading ? <CircularProgress size={20} /> : null}
        >
          {loading ? 'Duplicating...' : 'Duplicate & Edit'}
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default DuplicateApiDialog;
