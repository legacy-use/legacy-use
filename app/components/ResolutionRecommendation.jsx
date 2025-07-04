import { Alert, Box, Button, IconButton, Tooltip, Typography } from '@mui/material';
import { Info, CheckCircle, Warning } from '@mui/icons-material';
import { useState } from 'react';
import { getResolutionRecommendation, getRecommendedResolution } from '../utils/resolutionHelper';

const ResolutionRecommendation = ({ 
  width, 
  height, 
  onApplyRecommended, 
  showApplyButton = true,
  compact = false 
}) => {
  const [dismissed, setDismissed] = useState(false);
  
  if (!width || !height) return null;
  
  const recommendation = getResolutionRecommendation(width, height);
  
  // Don't show anything if optimal resolution and compact mode
  if (compact && recommendation.severity === 'success') {
    return null;
  }
  
  // Don't show if dismissed
  if (dismissed) {
    return null;
  }
  
  const handleApplyRecommended = () => {
    if (onApplyRecommended) {
      const recommended = getRecommendedResolution();
      onApplyRecommended(recommended);
    }
  };
  
  const getIcon = () => {
    switch (recommendation.severity) {
      case 'success':
        return <CheckCircle />;
      case 'warning':
        return <Warning />;
      default:
        return <Info />;
    }
  };
  
  if (compact) {
    return (
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <Tooltip title={recommendation.message}>
          <Box sx={{ display: 'flex', alignItems: 'center' }}>
            {getIcon()}
            <Typography variant="body2" color="textSecondary" sx={{ ml: 0.5 }}>
              {recommendation.severity === 'success' ? 'Optimal' : 'Suboptimal'}
            </Typography>
          </Box>
        </Tooltip>
        {showApplyButton && recommendation.severity === 'warning' && (
          <Button
            size="small"
            variant="text"
            onClick={handleApplyRecommended}
            sx={{ minWidth: 'auto', p: 0.5 }}
          >
            Use 1024×768
          </Button>
        )}
      </Box>
    );
  }
  
  return (
    <Alert
      severity={recommendation.severity}
      sx={{ mb: 2 }}
      action={
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          {showApplyButton && recommendation.severity === 'warning' && (
            <Button
              size="small"
              variant="outlined"
              onClick={handleApplyRecommended}
              sx={{ whiteSpace: 'nowrap' }}
            >
              Use 1024×768
            </Button>
          )}
          <IconButton
            size="small"
            onClick={() => setDismissed(true)}
            sx={{ ml: 1 }}
          >
            ×
          </IconButton>
        </Box>
      }
    >
      <Typography variant="body2">
        {recommendation.message}
      </Typography>
    </Alert>
  );
};

export default ResolutionRecommendation;