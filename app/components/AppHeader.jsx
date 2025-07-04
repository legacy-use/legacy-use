import ApiIcon from '@mui/icons-material/Api';
import ComputerIcon from '@mui/icons-material/Computer';
import KeyIcon from '@mui/icons-material/Key';
import ListAltIcon from '@mui/icons-material/ListAlt';
import WorkIcon from '@mui/icons-material/Work';
import AppBar from '@mui/material/AppBar';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import IconButton from '@mui/material/IconButton';
import Menu from '@mui/material/Menu';
import MenuItem from '@mui/material/MenuItem';
import Toolbar from '@mui/material/Toolbar';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import { useState } from 'react';
import { Link as RouterLink, useLocation } from 'react-router-dom';
import { useApiKey } from '../contexts/ApiKeyContext';
import { useAIProvider } from '../contexts/AIProviderContext';
import AIProviderSetup from './AIProviderSetup';
import ApiKeyDialog from './ApiKeyDialog';
import ProviderStatusIndicator from './ProviderStatusIndicator';

const AppHeader = () => {
  const location = useLocation();
  const { apiKey, clearApiKey, isApiKeyValid } = useApiKey();
  const { isConfigured } = useAIProvider();
  const [anchorEl, setAnchorEl] = useState(null);
  const [apiKeyDialogOpen, setApiKeyDialogOpen] = useState(false);
  const [aiProviderSetupOpen, setAiProviderSetupOpen] = useState(false);

  const isActive = path => {
    return location.pathname === path;
  };

  const handleMenuClick = event => {
    setAnchorEl(event.currentTarget);
  };

  const handleMenuClose = () => {
    setAnchorEl(null);
  };

  const handleOpenApiKeyDialog = () => {
    handleMenuClose();
    setApiKeyDialogOpen(true);
  };

  const handleClearApiKey = () => {
    clearApiKey();
    handleMenuClose();
  };

  const handleOpenProviderSetup = () => {
    setAiProviderSetupOpen(true);
  };

  return (
    <>
      <AppBar position="static">
        <Toolbar>
          <ApiIcon sx={{ mr: 2 }} />
          <Typography
            variant="h6"
            component={RouterLink}
            to="/"
            sx={{
              flexGrow: 0,
              mr: 4,
              textDecoration: 'none',
              color: 'inherit',
              '&:hover': {
                color: 'secondary.main',
              },
            }}
          >
            legacy-use
          </Typography>

          <Button
            component={RouterLink}
            to="/jobs"
            color={isActive('/jobs') ? 'secondary' : 'inherit'}
            startIcon={<WorkIcon />}
            sx={{ mr: 2 }}
          >
            Jobs
          </Button>

          <Box sx={{ flexGrow: 1, display: 'flex' }}>
            <Button
              component={RouterLink}
              to="/sessions"
              color={isActive('/sessions') ? 'secondary' : 'inherit'}
              startIcon={<ListAltIcon />}
              sx={{ mr: 2 }}
            >
              Sessions
            </Button>

            <Button
              component={RouterLink}
              to="/targets"
              color={isActive('/targets') ? 'secondary' : 'inherit'}
              startIcon={<ComputerIcon />}
              sx={{ mr: 2 }}
            >
              Targets
            </Button>

            <Button
              component={RouterLink}
              to="/apis"
              color={isActive('/apis') ? 'secondary' : 'inherit'}
              startIcon={<ApiIcon />}
            >
              APIs
            </Button>
          </Box>

          {isConfigured && (
            <ProviderStatusIndicator onOpenSetup={handleOpenProviderSetup} />
          )}

          <Tooltip title="API Key Settings">
            <IconButton
              color={isApiKeyValid ? 'success' : 'error'}
              onClick={handleMenuClick}
              size="large"
            >
              <KeyIcon />
            </IconButton>
          </Tooltip>

          <Menu anchorEl={anchorEl} open={Boolean(anchorEl)} onClose={handleMenuClose}>
            <MenuItem onClick={handleOpenApiKeyDialog}>
              {apiKey ? 'Change API Key' : 'Set API Key'}
            </MenuItem>
            {apiKey && <MenuItem onClick={handleClearApiKey}>Clear API Key</MenuItem>}
          </Menu>
        </Toolbar>
      </AppBar>

      <ApiKeyDialog open={apiKeyDialogOpen} onClose={() => setApiKeyDialogOpen(false)} />
      <AIProviderSetup open={aiProviderSetupOpen} onClose={() => setAiProviderSetupOpen(false)} />
    </>
  );
};

export default AppHeader;
