import {
  Box,
  Button,
  Chip,
  IconButton,
  Menu,
  MenuItem,
  Tooltip,
  Typography,
} from '@mui/material';
import {
  Cloud as CloudIcon,
  Refresh as RefreshIcon,
  Security as SecurityIcon,
  Settings as SettingsIcon,
} from '@mui/icons-material';
import { useState } from 'react';
import { AIProviderType, useAIProvider } from '../contexts/AIProviderContext';

const ProviderStatusIndicator = ({ onOpenSetup }) => {
  const { provider, isConfigured, hasSignedUp, clearProviderConfig } = useAIProvider();
  const [anchorEl, setAnchorEl] = useState(null);

  const handleClick = (event) => {
    setAnchorEl(event.currentTarget);
  };

  const handleClose = () => {
    setAnchorEl(null);
  };

  const handleReconfigure = () => {
    clearProviderConfig();
    handleClose();
    onOpenSetup();
  };

  const getProviderIcon = (providerType) => {
    switch (providerType) {
      case AIProviderType.ANTHROPIC:
        return <CloudIcon fontSize="small" />;
      case AIProviderType.BEDROCK:
        return <SecurityIcon fontSize="small" />;
      case AIProviderType.VERTEX:
        return <CloudIcon fontSize="small" />;
      default:
        return <SettingsIcon fontSize="small" />;
    }
  };

  const getProviderLabel = (providerType) => {
    switch (providerType) {
      case AIProviderType.ANTHROPIC:
        return 'Anthropic';
      case AIProviderType.BEDROCK:
        return 'AWS Bedrock';
      case AIProviderType.VERTEX:
        return 'Google Vertex';
      default:
        return 'Unknown';
    }
  };

  const getStatusColor = () => {
    if (hasSignedUp) return 'success';
    if (isConfigured) return 'primary';
    return 'default';
  };

  const getStatusText = () => {
    if (hasSignedUp) return 'Free Credits';
    if (isConfigured) return getProviderLabel(provider);
    return 'Not Configured';
  };

  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
      <Tooltip title={hasSignedUp ? 'Using free credits' : isConfigured ? `Using ${getProviderLabel(provider)}` : 'AI provider not configured'}>
        <Chip
          icon={hasSignedUp ? <RefreshIcon /> : getProviderIcon(provider)}
          label={getStatusText()}
          color={getStatusColor()}
          variant="outlined"
          size="small"
          onClick={handleClick}
          sx={{ cursor: 'pointer' }}
        />
      </Tooltip>

      <Menu
        anchorEl={anchorEl}
        open={Boolean(anchorEl)}
        onClose={handleClose}
        anchorOrigin={{
          vertical: 'bottom',
          horizontal: 'right',
        }}
        transformOrigin={{
          vertical: 'top',
          horizontal: 'right',
        }}
      >
        <MenuItem onClick={handleReconfigure}>
          <SettingsIcon sx={{ mr: 1 }} fontSize="small" />
          Reconfigure Provider
        </MenuItem>
        {isConfigured && (
          <MenuItem disabled>
            <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start' }}>
              <Typography variant="body2" color="text.secondary">
                Current Provider:
              </Typography>
              <Typography variant="body2" sx={{ fontWeight: 'bold' }}>
                {hasSignedUp ? 'Free Credits' : getProviderLabel(provider)}
              </Typography>
            </Box>
          </MenuItem>
        )}
      </Menu>
    </Box>
  );
};

export default ProviderStatusIndicator;