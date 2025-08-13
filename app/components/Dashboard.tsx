import AddIcon from '@mui/icons-material/Add';
import ApiIcon from '@mui/icons-material/Api';
import ScheduleIcon from '@mui/icons-material/Schedule';
import {
  Box,
  Button,
  Chip,
  Divider,
  List,
  ListItem,
  ListItemText,
  ListItemButton,
  Stack,
  Typography,
} from '@mui/material';
import React, { useEffect, useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import { getAllJobs, getApiDefinitions, getSessions, getTargets } from '../services/apiService';
import type { APIDefinition, Job, Session, Target } from '../gen/endpoints';

const Dashboard = () => {
  const [apis, setApis] = useState<APIDefinition[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [targets, setTargets] = useState<Target[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const [apisData, sessionsData, jobsResponse, targetsData] = await Promise.all([
          getApiDefinitions(),
          getSessions(),
          getAllJobs(),
          getTargets(),
        ]);

        setApis(apisData as APIDefinition[]);
        setSessions(sessionsData as Session[]);
        setTargets(targetsData as Target[]);

        // Properly handle the paginated response from the API
        const jobsData = (jobsResponse as any)?.jobs ? (jobsResponse as any).jobs : [];

        // Sort jobs by created_at in descending order and take the most recent 5
        const sortedJobs = [...jobsData]
          .sort((a, b) => new Date(b.created_at as any).getTime() - new Date(a.created_at as any).getTime())
          .slice(0, 5);

        setJobs(sortedJobs as Job[]);
        setLoading(false);
      } catch (err) {
        console.error('Error fetching dashboard data:', err);
        setError('Failed to load dashboard data');
        setLoading(false);
      }
    };

    fetchData();

    // Refresh data every 10 seconds
    const intervalId = setInterval(fetchData, 10000);

    return () => clearInterval(intervalId);
  }, []);

  const getStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case 'success':
        return 'success';
      case 'error':
        return 'error';
      case 'running':
        return 'primary';
      case 'pending':
        return 'warning';
      default:
        return 'default';
    }
  };

  const formatDate = (dateString?: string) => {
    if (!dateString) return '-';
    const date = new Date(dateString);
    return date.toLocaleString();
  };

  if (loading) {
    return <Typography>Loading dashboard...</Typography>;
  }

  if (error) {
    return <Typography color="error">{error}</Typography>;
  }

  return (
    <Stack spacing={2}>
      {/* Recent Jobs Section */}
      <Box>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
          <Typography variant="h6">Recent Jobs</Typography>
          <Button component={RouterLink} to="/jobs" size="small" startIcon={<ScheduleIcon />}>
            View All
          </Button>
        </Box>
        <List dense sx={{ bgcolor: 'background.paper' }}>
          {jobs.length > 0 ? (
            jobs.map(job => (
              <React.Fragment key={job.id}>
                <ListItem disablePadding>
                  <ListItemButton
                    component={RouterLink}
                    to={`/jobs/${job.target_id}/${job.id}`}
                    sx={{ color: 'white' }}
                  >
                    <ListItemText
                      primary={
                        <Box
                          sx={{
                            color: 'white',
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center',
                          }}
                        >
                          <Typography variant="body2" noWrap sx={{ maxWidth: '60%' }}>
                            {job.api_name}
                          </Typography>
                          <Chip
                            label={job.status}
                            size="small"
                            color={getStatusColor(job.status as string)}
                            sx={{ height: 20, fontSize: '0.7rem' }}
                          />
                        </Box>
                      }
                      secondary={formatDate(job.created_at as string)}
                    />
                  </ListItemButton>
                </ListItem>
                <Divider component="li" />
              </React.Fragment>
            ))
          ) : (
            <ListItem>
              <ListItemText primary="No jobs found" />
            </ListItem>
          )}
        </List>
      </Box>

      {/* Sessions Section */}
      <Box>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
          <Typography variant="h6">Sessions</Typography>
          <Button component={RouterLink} to="/sessions/new" size="small" startIcon={<AddIcon />}>
            New
          </Button>
        </Box>
        <List dense sx={{ bgcolor: 'background.paper' }}>
          {sessions.length > 0 ? (
            sessions.slice(0, 3).map(session => (
              <React.Fragment key={session.id}>
                <ListItem disablePadding>
                  <ListItemButton component={RouterLink} to={`/sessions`} sx={{ color: 'white' }}>
                    <ListItemText
                      primary={session.name || `Session ${session.id.substring(0, 8)}`}
                      secondary={`Target: ${session.target_id.substring(0, 8)}`}
                    />
                  </ListItemButton>
                </ListItem>
                <Divider component="li" />
              </React.Fragment>
            ))
          ) : (
            <ListItem>
              <ListItemText primary="No sessions found" />
            </ListItem>
          )}
          {sessions.length > 3 && (
            <ListItem disablePadding>
              <ListItemButton component={RouterLink} to="/sessions" sx={{ color: 'white' }}>
                <ListItemText primary={`View all ${sessions.length} sessions`} />
              </ListItemButton>
            </ListItem>
          )}
        </List>
      </Box>

      {/* Targets Section */}
      <Box>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
          <Typography variant="h6">Targets</Typography>
          <Button component={RouterLink} to="/targets/new" size="small" startIcon={<AddIcon />}>
            New
          </Button>
        </Box>
        <List dense sx={{ bgcolor: 'background.paper' }}>
          {targets.length > 0 ? (
            targets.slice(0, 3).map(target => (
              <React.Fragment key={target.id}>
                <ListItem disablePadding>
                  <ListItemButton component={RouterLink} to="/targets" sx={{ color: 'white' }}>
                    <ListItemText
                      primary={
                        <Box
                          sx={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center',
                          }}
                        >
                          <Typography variant="body2" noWrap>
                            {target.name || `Target ${String(target.id).substring(0, 8)}`}
                          </Typography>
                          <Chip
                            label={target.type}
                            size="small"
                            color="primary"
                            sx={{ height: 20, fontSize: '0.7rem', textTransform: 'capitalize' }}
                          />
                        </Box>
                      }
                      secondary={`Host: ${target.host}${target.port ? `:${target.port}` : ''}`}
                    />
                  </ListItemButton>
                </ListItem>
                <Divider component="li" />
              </React.Fragment>
            ))
          ) : (
            <ListItem>
              <ListItemText primary="No targets found" />
            </ListItem>
          )}
          {targets.length > 3 && (
            <ListItem disablePadding>
              <ListItemButton component={RouterLink} to="/targets" sx={{ color: 'white' }}>
                <ListItemText primary={`View all ${targets.length} targets`} />
              </ListItemButton>
            </ListItem>
          )}
        </List>
      </Box>

      {/* APIs Section */}
      <Box>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
          <Typography variant="h6">Available APIs</Typography>
          <Button component={RouterLink} to="/apis" size="small" startIcon={<ApiIcon />}>
            View All
          </Button>
        </Box>
        <List dense sx={{ bgcolor: 'background.paper' }}>
          {apis.length > 0 ? (
            apis.slice(0, 3).map(api => (
              <React.Fragment key={api.name}>
                <ListItem disablePadding>
                  <ListItemButton component={RouterLink} to="/apis" sx={{ color: 'white' }}>
                    <ListItemText
                      primary={api.name}
                      secondary={
                        api.description.substring(0, 60) + (api.description.length > 60 ? '...' : '')
                      }
                    />
                  </ListItemButton>
                </ListItem>
                <Divider component="li" />
              </React.Fragment>
            ))
          ) : (
            <ListItem>
              <ListItemText primary="No APIs found" />
            </ListItem>
          )}
          {apis.length > 3 && (
            <ListItem disablePadding>
              <ListItemButton component={RouterLink} to="/apis" sx={{ color: 'white' }}>
                <ListItemText primary={`View all ${apis.length} APIs`} />
              </ListItemButton>
            </ListItem>
          )}
        </List>
      </Box>
    </Stack>
  );
};

export default Dashboard;
