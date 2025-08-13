import {
  Alert,
  Box,
  Button,
  CircularProgress,
  FormControl,
  Grid,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  TextField,
  Typography,
} from '@mui/material';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { createTarget } from '../services/apiService';
import ResolutionRecommendation from './ResolutionRecommendation';
import VPNConfigInputField from './VPNConfigInputField';
import type { TargetCreate } from '../gen/endpoints';

// Default ports for different target types
const DEFAULT_PORTS: Record<string, number> = {
  vnc: 5900,
  'vnc+tailscale': 5900,
  rdp: 3389,
  rdp_wireguard: 3389,
  teamviewer: 5938,
  generic: 8080,
  'rdp+openvpn': 3389,
};

const CreateTarget = () => {
  const navigate = useNavigate();
  const [targetData, setTargetData] = useState<TargetCreate>({
    name: '',
    type: 'vnc' as any,
    host: '',
    username: '',
    password: '',
    port: DEFAULT_PORTS.vnc,
    vpn_config: '',
    vpn_username: '',
    vpn_password: '',
    width: 1024,
    height: 768,
    rdp_params: '',
  });
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<boolean>(false);
  const [validationErrors, setValidationErrors] = useState<Record<string, string>>({});

  // Check if OpenVPN is allowed based on environment variable
  const isOpenVPNAllowed = import.meta.env.VITE_ALLOW_OPENVPN === 'true';

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setTargetData(prev => ({
      ...prev,
      [name]: value,
    }));
  };

  const handlePortChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    if (value === '') {
      setTargetData(prev => ({
        ...prev,
        port: null as any,
      }));
    } else {
      const portValue = parseInt(value, 10);
      if (!Number.isNaN(portValue)) {
        setTargetData(prev => ({
          ...prev,
          port: portValue as any,
        }));
      }
    }
  };

  const handleResolutionChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    const numValue = parseInt(value, 10);
    if (!Number.isNaN(numValue)) {
      setTargetData(prev => ({
        ...prev,
        [name]: numValue as any,
      }));
    }
  };

  const handleTypeChange = (e: React.ChangeEvent<{ value: unknown }>) => {
    const newType = e.target.value as string;
    setTargetData(prev => ({
      ...prev,
      type: newType as any,
      port: (DEFAULT_PORTS[newType] as any) ?? null,
    }));
  };

  const handleRecommendedResolutionClick = ({ width, height }: { width: number; height: number }) => {
    setTargetData(prev => ({ ...prev, width: width as any, height: height as any }));
  };

  const validateForm = () => {
    const errors: Record<string, string> = {};

    if (!String(targetData.name).trim()) {
      errors.name = 'Name is required';
    }

    if (!targetData.type) {
      errors.type = 'Type is required';
    }

    if (!String(targetData.host).trim()) {
      errors.host = 'Host is required';
    }

    if (!String(targetData.password).trim()) {
      errors.password = 'Password is required';
    }

    const portVal = targetData.port as any;
    if (portVal !== null && (Number.isNaN(portVal) || portVal < 1 || portVal > 65535)) {
      errors.port = 'Port must be a valid number between 1 and 65535';
    }

    const widthVal = targetData.width as any;
    if (!widthVal || Number.isNaN(widthVal) || widthVal < 1) {
      errors.width = 'Width must be a positive number';
    }

    const heightVal = targetData.height as any;
    if (!heightVal || Number.isNaN(heightVal) || heightVal < 1) {
      errors.height = 'Height must be a positive number';
    }

    // Validate OpenVPN fields when target type is rdp+openvpn
    if ((targetData.type as any) === 'rdp+openvpn') {
      if (!String(targetData.vpn_username || '').trim()) {
        errors.vpn_username = 'OpenVPN username is required';
      }
      if (!String(targetData.vpn_password || '').trim()) {
        errors.vpn_password = 'OpenVPN password is required';
      }
      if (!String(targetData.vpn_config || '').trim()) {
        errors.vpn_config = 'OpenVPN config is required';
      }
    }

    setValidationErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!validateForm()) {
      return;
    }

    try {
      setLoading(true);
      setError(null);

      // Prepare data for submission
      const submissionData = { ...targetData } as TargetCreate;

      await createTarget(submissionData);

      setSuccess(true);
      setLoading(false);

      setTimeout(() => {
        navigate('/targets');
      }, 1500);
    } catch (err: any) {
      console.error('Error creating target:', err);
      setError(err?.response?.data?.detail || 'Failed to create target. Please try again.');
      setLoading(false);
    }
  };

  return (
    <Box>
      <Typography variant="h5" gutterBottom>
        Create New Target
      </Typography>
      {success && (
        <Alert severity="success" sx={{ mb: 3 }}>
          Target created successfully!
        </Alert>
      )}
      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
        </Alert>
      )}
      <Paper sx={{ p: 3 }}>
        <form onSubmit={handleSubmit}>
          <Grid container spacing={3}>
            <Grid
              size={{
                xs: 12,
                md: 6,
              }}
            >
              <TextField
                fullWidth
                label="Target Name"
                name="name"
                value={targetData.name}
                onChange={handleChange}
                error={!!validationErrors.name}
                helperText={validationErrors.name}
                disabled={loading}
                required
              />
            </Grid>

            <Grid
              size={{
                xs: 12,
                md: 4,
              }}
            >
              <FormControl fullWidth>
                <InputLabel>Type</InputLabel>
                <Select
                  name="type"
                  value={targetData.type}
                  onChange={handleTypeChange}
                  label="Type"
                  disabled={loading}
                  required
                >
                  <MenuItem value="vnc">VNC</MenuItem>
                  <MenuItem value="vnc+tailscale">VNC + Tailscale</MenuItem>
                  <MenuItem value="vnc+wireguard">VNC + WireGuard</MenuItem>
                  <MenuItem value="rdp">RDP</MenuItem>
                  <MenuItem value="rdp_wireguard">RDP + WireGuard</MenuItem>
                  <MenuItem value="rdp+tailscale">RDP + Tailscale</MenuItem>
                  <MenuItem value="rdp+openvpn" disabled={!isOpenVPNAllowed}>
                    RDP + OpenVPN {!isOpenVPNAllowed && '(Disabled - See Tutorial)'}
                  </MenuItem>
                  <MenuItem value="teamviewer">TeamViewer</MenuItem>
                  <MenuItem value="generic">Generic</MenuItem>
                </Select>
              </FormControl>
            </Grid>

            <Grid
              size={{
                xs: 12,
                md: 8,
              }}
            >
              <TextField
                fullWidth
                label="Host"
                name="host"
                value={targetData.host}
                onChange={handleChange}
                error={!!validationErrors.host}
                helperText={validationErrors.host}
                disabled={loading}
                required
                placeholder="hostname or IP address"
              />
            </Grid>

            <Grid
              size={{
                xs: 12,
                md: 4,
              }}
            >
              <TextField
                fullWidth
                label="Port"
                name="port"
                type="number"
                value={targetData.port === null ? '' : targetData.port}
                onChange={handlePortChange}
                error={!!validationErrors.port}
                helperText={validationErrors.port}
                disabled={loading}
                placeholder="Optional"
              />
            </Grid>

            <Grid size={12}>
              {/* Show OpenVPN security warning when OpenVPN is selected */}
              {targetData.type === 'rdp+openvpn' && (
                <Alert severity="warning" sx={{ mb: 2 }}>
                  <Typography variant="body2" sx={{ fontWeight: 'bold', mb: 1 }}>
                    OpenVPN Security Notice
                  </Typography>
                  <Typography variant="body2">
                    Using OpenVPN requires elevated privileges (NET_ADMIN capabilities) which may
                    pose security risks. OpenVPN connections will run with additional system
                    permissions that could be exploited if the target environment is compromised.
                    Consider using alternative VPN solutions like WireGuard or Tailscale for
                    enhanced security.
                  </Typography>
                </Alert>
              )}

              <VPNConfigInputField
                targetData={targetData}
                validationErrors={validationErrors}
                loading={loading}
                handleChange={handleChange}
              />
            </Grid>

            <Grid
              size={{
                xs: 12,
                sm: 6,
              }}
            >
              <TextField
                fullWidth
                variant="outlined"
                label="VNC/RDP Username (optional)"
                name="username"
                value={targetData.username}
                onChange={handleChange}
                error={!!validationErrors.username}
                helperText={validationErrors.username}
              />
            </Grid>

            <Grid
              size={{
                xs: 12,
                md: 6,
              }}
            >
              <TextField
                fullWidth
                label="VNC/RDP Password"
                name="password"
                type="password"
                value={targetData.password}
                onChange={handleChange}
                error={!!validationErrors.password}
                helperText={validationErrors.password}
                disabled={loading}
                required
              />
            </Grid>

            <Grid
              size={{
                xs: 12,
                md: 6,
              }}
            >
              <TextField
                fullWidth
                label="Width (px)"
                name="width"
                type="number"
                value={targetData.width}
                onChange={handleResolutionChange}
                error={!!validationErrors.width}
                helperText={validationErrors.width}
                disabled={loading}
                required
                InputProps={{ inputProps: { min: 1 } }}
              />
            </Grid>

            <Grid
              size={{
                xs: 12,
                md: 6,
              }}
            >
              <TextField
                fullWidth
                label="Height (px)"
                name="height"
                type="number"
                value={targetData.height}
                onChange={handleResolutionChange}
                error={!!validationErrors.height}
                helperText={validationErrors.height}
                disabled={loading}
                required
                InputProps={{ inputProps: { min: 1 } }}
              />
            </Grid>

            {/* RDP customization options */}
            {(targetData.type.startsWith('rdp') || targetData.type.includes('rdp')) && (
              <Grid size={12}>
                <TextField
                  fullWidth
                  multiline
                  minRows={2}
                  label="FreeRDP parameters"
                  name="rdp_params"
                  value={targetData.rdp_params}
                  onChange={handleChange}
                  disabled={loading}
                  placeholder="Defaults: /f +auto-reconnect +clipboard /cert:ignore. You can add or override here. Username (/u), Password (/p) and Host (/v) are always included."
                />
              </Grid>
            )}

            {/* Resolution recommendation warning */}
            <Grid size={12}>
              <ResolutionRecommendation
                width={targetData.width}
                height={targetData.height}
                onRecommendedResolutionClick={handleRecommendedResolutionClick}
                disabled={loading}
              />
            </Grid>

            <Grid sx={{ display: 'flex', justifyContent: 'flex-end', gap: 2 }} size={12}>
              <Button variant="outlined" onClick={() => navigate('/targets')} disabled={loading}>
                Cancel
              </Button>
              <Button
                type="submit"
                variant="contained"
                color="primary"
                disabled={loading}
                startIcon={loading ? <CircularProgress size={20} /> : null}
              >
                {loading ? 'Creating...' : 'Create Target'}
              </Button>
            </Grid>
          </Grid>
        </form>
      </Paper>
    </Box>
  );
};

export default CreateTarget;
