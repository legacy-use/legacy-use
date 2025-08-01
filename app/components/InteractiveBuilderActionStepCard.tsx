import { Edit } from '@mui/icons-material';
import { Box, Button, Card, CardContent, TextField, Typography } from '@mui/material';
import { useState } from 'react';
import type { ActionStep } from '../gen/endpoints';

interface ActionStepCardProps {
  action: ActionStep;
  onUpdate: (updatedAction: ActionStep) => void;
}

export default function ActionStepCard({ action, onUpdate }: ActionStepCardProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editedAction, setEditedAction] = useState(action);

  const handleSave = () => {
    onUpdate(editedAction);
    setIsEditing(false);
  };

  const handleCancel = () => {
    setEditedAction(action);
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
              label="Title"
              value={editedAction.title}
              onChange={e => setEditedAction({ ...editedAction, title: e.target.value })}
              onKeyDown={handleKeyPress}
              fullWidth
              size="small"
            />
            <TextField
              label="Instruction"
              value={editedAction.instruction}
              onChange={e => setEditedAction({ ...editedAction, instruction: e.target.value })}
              onKeyDown={handleKeyPress}
              fullWidth
              multiline
              rows={3}
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
              <Typography variant="subtitle1">{action.title}</Typography>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <Typography fontSize={12} fontFamily="monospace" color="text.secondary">
                  {action.tool}
                </Typography>
              </Box>
            </Box>
            <Typography variant="body2" color="text.secondary">
              {action.instruction}
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
