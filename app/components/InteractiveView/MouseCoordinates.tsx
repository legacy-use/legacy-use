import { Card, CardContent, Grid, TextField, Typography } from '@mui/material';
import type { CoordinateInput } from './types';

interface MouseCoordinatesProps {
  coordinate: CoordinateInput;
  setCoordinate: (coordinate: CoordinateInput) => void;
}

export default function MouseCoordinates({ coordinate, setCoordinate }: MouseCoordinatesProps) {
  return (
    <Card sx={{ mb: 3 }}>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          Mouse Coordinates
        </Typography>
        <Grid container spacing={2} alignItems="center">
          <Grid size={{ xs: 6 }}>
            <TextField
              label="X Coordinate"
              type="number"
              value={coordinate.x}
              onChange={e => setCoordinate({ ...coordinate, x: parseInt(e.target.value, 10) || 0 })}
              fullWidth
              size="small"
            />
          </Grid>
          <Grid size={{ xs: 6 }}>
            <TextField
              label="Y Coordinate"
              type="number"
              value={coordinate.y}
              onChange={e => setCoordinate({ ...coordinate, y: parseInt(e.target.value, 10) || 0 })}
              fullWidth
              size="small"
            />
          </Grid>
        </Grid>
      </CardContent>
    </Card>
  );
}
