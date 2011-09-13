#!/bin/bash

set -e

cylc checkvars  TASK_EXE_SECONDS
cylc checkvars -d INPUT_DIR
cylc checkvars -c OUTPUT_DIR RUNNING_DIR

# CHECK INPUT FILES EXIST
ONE=$INPUT_DIR/obs-${CYCLE_TIME}.nc
TWO=$RUNNING_DIR/A-${CYCLE_TIME}.restart
for PRE in $ONE $TWO; do
    if [[ ! -f $PRE ]]; then
        echo "ERROR, file not found $PRE" >&2
        exit 1
    fi
done

echo "Hello from $TASK_NAME at $CYCLE_TIME in $CYLC_SUITE_REGNAME"
sleep $TASK_EXE_SECONDS

# generate a restart file for the next three cycles
touch $RUNNING_DIR/A-$(cylc cycletime --add=6 ).restart
touch $RUNNING_DIR/A-$(cylc cycletime --add=12).restart
touch $RUNNING_DIR/A-$(cylc cycletime --add=18).restart

# model outputs
touch $OUTPUT_DIR/surface-winds-${CYCLE_TIME}.nc
touch $OUTPUT_DIR/precipitation-${CYCLE_TIME}.nc

echo "Goodbye"
