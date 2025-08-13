import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import CircularProgress from '@mui/material/CircularProgress';
import Paper from '@mui/material/Paper';
import Tab from '@mui/material/Tab';
import Tabs from '@mui/material/Tabs';
import Typography from '@mui/material/Typography';
import HttpExchangeViewer from './HttpExchangeViewer';
import LogViewer from './LogViewer';

interface JobTabsProps {
  activeTab: number;
  handleTabChange: (_: any, newValue: any) => void;
  job: any;
  regularLogs: any;
  httpExchanges: any;
  httpExchangesLoading: any;
  hasHttpExchanges: any;
}

const JobTabs = ({
  activeTab,
  handleTabChange,
  job,
  regularLogs,
  httpExchanges,
  httpExchangesLoading,
  hasHttpExchanges,
}: JobTabsProps) => {
  return (
    <Paper sx={{ p: 2, display: 'flex', flexDirection: 'column', height: '100%' }}>
      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 2 }}>
        <Tabs value={activeTab} onChange={handleTabChange}>
          <Tab label="Logs" />
          {job.error && <Tab label="Error" />}
          {hasHttpExchanges && <Tab label="HTTP Exchanges" />}
        </Tabs>
      </Box>

      {activeTab === 0 && (
        <Box
          sx={{
            position: 'relative',
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            minHeight: 0,
          }}
        >
          <Box sx={{ flex: 1, minHeight: 0, overflowY: 'auto' }}>
            <LogViewer logs={regularLogs} />
          </Box>
        </Box>
      )}

      {activeTab === 1 && job.error && (
        <Box>
          <Typography variant="subtitle1" gutterBottom color="error">
            Error Details
          </Typography>
          <Alert severity="error" sx={{ mb: 2 }}>
            {job.error}
          </Alert>
          {job.error_details && (
            <Box
              sx={{
                backgroundColor: '#2d2d2d',
                p: 2,
                fontFamily: 'monospace',
                fontSize: '0.9rem',
              }}
            >
              <pre style={{ margin: 0, color: '#ff6b6b' }}>{job.error_details}</pre>
            </Box>
          )}
        </Box>
      )}

      {((job.error && activeTab === 2) || (!job.error && activeTab === 1)) && (
        <Box>
          {httpExchangesLoading ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', my: 2 }}>
              <CircularProgress size={24} />
            </Box>
          ) : httpExchanges.length > 0 ? (
            <HttpExchangeViewer exchanges={httpExchanges} />
          ) : (
            <Typography variant="body2" color="textSecondary">
              No HTTP exchanges found for this job.
            </Typography>
          )}
        </Box>
      )}
    </Paper>
  );
};

export default JobTabs;
