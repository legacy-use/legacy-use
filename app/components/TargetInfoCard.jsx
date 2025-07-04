import { Box, Card, CardContent, Chip, Grid, Typography } from '@mui/material';

import ResolutionRecommendation from './ResolutionRecommendation';

const TargetInfoCard = ({ target, formatDate }) => {
  if (!target) return null;
  return (
    <Card sx={{ mb: 3 }}>
      <CardContent>
        <Typography variant="subtitle1" gutterBottom>
          Target Details
        </Typography>
        <Grid container spacing={2}>
          <Grid item xs={12} sm={6}>
            <Typography variant="body2" color="textSecondary">
              ID: {target.id}
            </Typography>
          </Grid>
          <Grid item xs={12} sm={6}>
            <Typography variant="body2" color="textSecondary">
              Created: {formatDate(target.created_at)}
            </Typography>
          </Grid>
          <Grid item xs={12} sm={6}>
            <Typography variant="body2" color="textSecondary">
              Type: {target.type || 'Not specified'}
            </Typography>
          </Grid>
          {target.url && (
            <Grid item xs={12} sm={6}>
              <Typography variant="body2" color="textSecondary">
                URL: {target.url}
              </Typography>
            </Grid>
          )}
          {target.queue_status && (
            <Grid item xs={12} sm={6}>
              <Box display="flex" alignItems="center">
                <Typography variant="body2" color="textSecondary">
                  Queue Status:
                </Typography>
                <Chip
                  label={target.queue_status}
                  size="small"
                  color={target.queue_status === 'paused' ? 'error' : 'success'}
                  sx={{ ml: 1, textTransform: 'capitalize' }}
                />
              </Box>
            </Grid>
          )}
          {target.has_blocking_jobs && (
            <Grid item xs={12} sm={6}>
              <Box display="flex" alignItems="center">
                <Typography variant="body2" color="textSecondary">
                  Blocking Jobs:
                </Typography>
                <Chip
                  label={target.blocking_jobs_count}
                  size="small"
                  color="error"
                  sx={{ ml: 1 }}
                />
              </Box>
            </Grid>
          )}
          {target.width && target.height && (
            <Grid item xs={12} sm={6}>
              <Typography variant="body2" color="textSecondary">
                Screen Resolution: {target.width}×{target.height}
              </Typography>
            </Grid>
          )}
          {target.width && target.height && (
            <Grid item xs={12}>
              <ResolutionRecommendation
                width={target.width}
                height={target.height}
                showApplyButton={false}
                compact={true}
              />
            </Grid>
          )}
          {target.username && (
            <Grid item xs={12} sm={6}>
              <Typography variant="body2" color="textSecondary">
                Username: {target.username}
              </Typography>
            </Grid>
          )}
          {target.description && (
            <Grid item xs={12}>
              <Typography variant="body2" color="textSecondary">
                Description: {target.description}
              </Typography>
            </Grid>
          )}
        </Grid>
      </CardContent>
    </Card>
  );
};

export default TargetInfoCard;
