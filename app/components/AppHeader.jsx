import ApiIcon from '@mui/icons-material/Api';
import ComputerIcon from '@mui/icons-material/Computer';
import KeyIcon from '@mui/icons-material/Key';
import ListAltIcon from '@mui/icons-material/ListAlt';
import PsychologyIcon from '@mui/icons-material/Psychology';
import RestartAltIcon from '@mui/icons-material/RestartAlt';
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
import { useAiProvider } from '../contexts/AiProviderContext';
import { useApiKey } from '../contexts/ApiKeyContext';
import ApiKeyDialog from './ApiKeyDialog';
import OnboardingWizard from './OnboardingWizard';

const AppHeader = () => {
  const location = useLocation();
  const { apiKey, clearApiKey, isApiKeyValid } = useApiKey();
  const { hasConfiguredProvider, isProviderValid } = useAiProvider();
  const [anchorEl, setAnchorEl] = useState(null);
  const [aiProviderAnchorEl, setAiProviderAnchorEl] = useState(null);
  const [apiKeyDialogOpen, setApiKeyDialogOpen] = useState(false);
  const [onboardingOpen, setOnboardingOpen] = useState(false);

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

  const handleAiProviderMenuClick = event => {
    setAiProviderAnchorEl(event.currentTarget);
  };

  const handleAiProviderMenuClose = () => {
    setAiProviderAnchorEl(null);
  };

  const handleRestartOnboarding = () => {
    handleAiProviderMenuClose();
    // Remove the local storage flag
    localStorage.removeItem('onboardingCompleted');
    // Open the onboarding wizard
    setOnboardingOpen(true);
  };

  const handleOnboardingComplete = () => {
    localStorage.setItem('onboardingCompleted', 'true');
    setOnboardingOpen(false);
  };

  const aiProviderStatus = hasConfiguredProvider
    ? isProviderValid
      ? 'success'
      : 'warning'
    : 'error';
  const aiProviderStatusText = hasConfiguredProvider
    ? isProviderValid
      ? 'Ready'
      : 'Inactive'
    : 'Not Configured';

  return (
    <>
      <AppBar position="static">
        <Toolbar>
          <img src="/logo-white.svg" alt="legacy-use" style={{ height: '24px' }} />
          <Typography
            variant="h6"
            component={RouterLink}
            to="/"
            sx={{
              flexGrow: 0,
              ml: 2,
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

          <Box sx={{ flexGrow: 1, display: 'flex', gap: 2 }}>
            <Button
              component={RouterLink}
              to="/jobs"
              color={isActive('/jobs') ? 'secondary' : 'inherit'}
              startIcon={<WorkIcon />}
            >
              Jobs
            </Button>
            <Button
              component={RouterLink}
              to="/sessions"
              color={isActive('/sessions') ? 'secondary' : 'inherit'}
              startIcon={<ListAltIcon />}
            >
              Sessions
            </Button>
            <Button
              component={RouterLink}
              to="/targets"
              color={isActive('/targets') ? 'secondary' : 'inherit'}
              startIcon={<ComputerIcon />}
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

          <Tooltip title={`AI Provider: ${aiProviderStatusText}`}>
            <IconButton
              color={aiProviderStatus}
              size="large"
              sx={{ mr: 1 }}
              onClick={handleAiProviderMenuClick}
            >
              <PsychologyIcon />
            </IconButton>
          </Tooltip>

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

          <Menu
            anchorEl={aiProviderAnchorEl}
            open={Boolean(aiProviderAnchorEl)}
            onClose={handleAiProviderMenuClose}
          >
            <MenuItem onClick={handleRestartOnboarding}>
              <RestartAltIcon sx={{ mr: 1 }} />
              Restart Onboarding
            </MenuItem>
          </Menu>
        </Toolbar>
      </AppBar>

      <ApiKeyDialog open={apiKeyDialogOpen} onClose={() => setApiKeyDialogOpen(false)} />
      <OnboardingWizard
        open={onboardingOpen}
        onClose={() => setOnboardingOpen(false)}
        onComplete={handleOnboardingComplete}
      />
    </>
  );
};

export default AppHeader;
