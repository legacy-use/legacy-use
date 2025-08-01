import { Edit } from '@mui/icons-material';
import { Box, Button, Card, CardContent, TextField, Typography } from '@mui/material';
import { useState } from 'react';
import type { Parameter } from '../gen/endpoints';

interface ParameterCardProps {
  parameter: Parameter;
  onUpdate: (updatedParameter: Parameter) => void;
}

export default function ParameterCard({ parameter, onUpdate }: ParameterCardProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editedParameter, setEditedParameter] = useState(parameter);

  const handleSave = () => {
    onUpdate(editedParameter);
    setIsEditing(false);
  };

  const handleCancel = () => {
    setEditedParameter(parameter);
    setIsEditing(false);
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && e.ctrlKey) {
      handleSave();
    } else if (e.key === 'Escape') {
      handleCancel();
    }
  };

  return (
    <Card sx={{ mb: 3, position: 'relative' }}>
      <CardContent>
        {isEditing ? (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <TextField
              label="Name"
              value={editedParameter.name}
              onChange={e => setEditedParameter({ ...editedParameter, name: e.target.value })}
              onKeyDown={handleKeyPress}
              fullWidth
              size="small"
            />
            <TextField
              label="Type"
              value={editedParameter.type}
              onChange={e => setEditedParameter({ ...editedParameter, type: e.target.value })}
              onKeyDown={handleKeyPress}
              fullWidth
              size="small"
            />
            <TextField
              label="Description"
              value={editedParameter.description}
              onChange={e =>
                setEditedParameter({ ...editedParameter, description: e.target.value })
              }
              onKeyDown={handleKeyPress}
              fullWidth
              multiline
              rows={2}
              size="small"
            />
            <TextField
              label="Default Value"
              value={JSON.stringify(editedParameter.default)}
              onChange={e => {
                try {
                  const parsedValue = JSON.parse(e.target.value);
                  setEditedParameter({ ...editedParameter, default: parsedValue });
                } catch {
                  // Keep the raw string if it's not valid JSON yet
                  setEditedParameter({ ...editedParameter, default: e.target.value });
                }
              }}
              onKeyDown={handleKeyPress}
              fullWidth
              size="small"
            />
            <Box sx={{ display: 'flex', gap: 1 }}>
              <Button size="small" variant="contained" onClick={handleSave}>
                Save
              </Button>
              <Button size="small" variant="outlined" onClick={handleCancel}>
                Cancel
              </Button>
            </Box>
          </Box>
        ) : (
          <>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <Typography variant="subtitle1">{parameter.name}</Typography>
                <Typography variant="body2" color="text.secondary">
                  {JSON.stringify(parameter.default)}
                </Typography>
              </Box>
              <Typography fontSize={12} fontFamily="monospace" color="text.secondary">
                {parameter.type}
              </Typography>
            </Box>
            <Typography variant="body2" color="text.secondary">
              {parameter.description}
            </Typography>
          </>
        )}
      </CardContent>
      {!isEditing && (
        <Box
          onClick={() => setIsEditing(true)}
          sx={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            backgroundColor: 'transparent',
            cursor: 'pointer',
            transition: 'background-color 0.2s',
            '&:hover': {
              backgroundColor: 'rgba(0, 0, 0, 0.4)',
              '& .edit-icon': {
                opacity: 1,
              },
            },
          }}
        >
          <Edit
            className="edit-icon"
            sx={{
              color: 'white',
              fontSize: 32,
              opacity: 0,
              transition: 'opacity 0.2s',
            }}
          />
        </Box>
      )}
    </Card>
  );
}
