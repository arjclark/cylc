#!/bin/bash
# THIS FILE IS PART OF THE CYLC SUITE ENGINE.
# Copyright (C) 2008-2018 NIWA
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#-------------------------------------------------------------------------------
# Test "cylc cat-log" with a custom remote tail command.
CYLC_TEST_IS_GENERIC=false
. $(dirname $0)/test_header
set_test_remote
#-------------------------------------------------------------------------------
set_test_number 4
install_suite $TEST_NAME_BASE $TEST_NAME_BASE
set -eu
SSH='ssh -oBatchMode=yes -oConnectTimeout=5'
SCP='scp -oBatchMode=yes -oConnectTimeout=5'
$SSH -n "${CYLC_TEST_OWNER}@${CYLC_TEST_HOST}" "mkdir -p cylc-run/.bin"
#-------------------------------------------------------------------------------
TEST_NAME=$TEST_NAME_BASE-validate
run_ok $TEST_NAME cylc validate $SUITE_NAME
#-------------------------------------------------------------------------------
REMOTE_HOME=$($SSH -n "${CYLC_TEST_OWNER}@${CYLC_TEST_HOST}" 'echo $PWD')
create_test_globalrc "" "
[hosts]
   [[$CYLC_TEST_HOST]]
        tail command template = $REMOTE_HOME/cylc-run/.bin/my-tailer.sh %(filename)s"
$SCP $PWD/bin/my-tailer.sh ${CYLC_TEST_OWNER}@${CYLC_TEST_HOST}:cylc-run/.bin/my-tailer.sh
#-------------------------------------------------------------------------------
# Run detached.
suite_run_ok "${TEST_NAME_BASE}-run" cylc run "${SUITE_NAME}"
#-------------------------------------------------------------------------------
while ! grep -q -F '[foo.1] -(current:submitted)> started' \
    "${SUITE_RUN_DIR}/log/suite/log"
do
    sleep 1
done
TEST_NAME=$TEST_NAME_BASE-cat-log
cylc cat-log $SUITE_NAME -f o -m t foo.1 > ${TEST_NAME}.out
grep_ok "HELLO from foo 1" ${TEST_NAME}.out
#-------------------------------------------------------------------------------
TEST_NAME=$TEST_NAME_BASE-stop
run_ok $TEST_NAME cylc stop --kill --max-polls=20 --interval=1 $SUITE_NAME
#-------------------------------------------------------------------------------
purge_suite_remote "${CYLC_TEST_OWNER}@${CYLC_TEST_HOST}" "${SUITE_NAME}"
$SSH -n "${CYLC_TEST_OWNER}@${CYLC_TEST_HOST}" "rm -rf cylc-run/.bin/"
purge_suite $SUITE_NAME
exit
