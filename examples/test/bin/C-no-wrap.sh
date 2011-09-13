#!/bin/bash

set -e; trap 'cylc failed "error trapped"' ERR

cylc task started

cylc util checkvars  TASK_EXE_SECONDS
cylc util checkvars -d INPUT_DIR
cylc util checkvars -c OUTPUT_DIR RUNNING_DIR

# CHECK INPUT FILES EXIST
ONE=$INPUT_DIR/precipitation-${CYCLE_TIME}.nc
TWO=$RUNNING_DIR/C-${CYCLE_TIME}.restart
for PRE in $ONE $TWO; do
    if [[ ! -f $PRE ]]; then
        cylc task failed "ERROR, file not found $PRE"
        exit 1
    fi
done

echo "Hello from $TASK_NAME at $CYCLE_TIME in $CYLC_SUITE_REGNAME"

sleep $TASK_EXE_SECONDS

# generate a restart file for the next three cycles
touch $RUNNING_DIR/C-$(cylc util cycletime --add=6 ).restart
touch $RUNNING_DIR/C-$(cylc util cycletime --add=12).restart
touch $RUNNING_DIR/C-$(cylc util cycletime --add=18).restart

# model outputs
touch $OUTPUT_DIR/river-flow-${CYCLE_TIME}.nc

cylc task message "river flow outputs done for $CYCLE_TIME"

sleep $TASK_EXE_SECONDS

echo "Goodbye"

cylc task succeeded
