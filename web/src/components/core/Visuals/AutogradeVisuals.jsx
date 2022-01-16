import React from 'react';

import Grid from '@material-ui/core/Grid';

import AssignmentSundialPaper from './AssignmentSundialPaper';

export default function AutogradeVisuals() {
  return (
    <Grid container spacing={1} justify={'center'} alignItems={'center'}>
      <Grid item>
        <AssignmentSundialPaper/>
      </Grid>
    </Grid>
  );
}