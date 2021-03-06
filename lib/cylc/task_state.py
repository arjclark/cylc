#!/usr/bin/env python

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

"""Task state related logic."""


import cylc.flags as flags
from cylc.prerequisite import Prerequisite
from cylc.suite_logging import LOG
from cylc.task_id import TaskID
from cylc.task_outputs import (
    TaskOutputs,
    TASK_OUTPUT_EXPIRED, TASK_OUTPUT_SUBMITTED, TASK_OUTPUT_SUBMIT_FAILED,
    TASK_OUTPUT_STARTED, TASK_OUTPUT_SUCCEEDED, TASK_OUTPUT_FAILED)
from cylc.wallclock import get_current_time_string


# Task status names and meanings.
# Held back from dependency matching, in the runahead pool:
TASK_STATUS_RUNAHEAD = "runahead"
# Held back from job submission due to un-met prerequisites:
TASK_STATUS_WAITING = "waiting"
# Held back from job submission even if prerequisites are met:
TASK_STATUS_HELD = "held"
# Prerequisites met, but held back in a limited internal queue:
TASK_STATUS_QUEUED = "queued"
# Ready (prerequisites met) to be passed to job submission system:
TASK_STATUS_READY = "ready"
# Prerequisites unmet for too long - will never be submitted now:
TASK_STATUS_EXPIRED = "expired"
# Job submitted to run:
TASK_STATUS_SUBMITTED = "submitted"
# Job submission failed:
TASK_STATUS_SUBMIT_FAILED = "submit-failed"
# Job submission failed but will try again soon:
TASK_STATUS_SUBMIT_RETRYING = "submit-retrying"
# Job execution started, but not completed yet:
TASK_STATUS_RUNNING = "running"
# Job execution completed successfully:
TASK_STATUS_SUCCEEDED = "succeeded"
# Job execution failed:
TASK_STATUS_FAILED = "failed"
# Job execution failed, but will try again soon:
TASK_STATUS_RETRYING = "retrying"

# Tasks statuses ordered according to task runtime progression.
TASK_STATUSES_ORDERED = [
    TASK_STATUS_RUNAHEAD,
    TASK_STATUS_WAITING,
    TASK_STATUS_HELD,
    TASK_STATUS_QUEUED,
    TASK_STATUS_EXPIRED,
    TASK_STATUS_READY,
    TASK_STATUS_SUBMIT_FAILED,
    TASK_STATUS_SUBMIT_RETRYING,
    TASK_STATUS_SUBMITTED,
    TASK_STATUS_RETRYING,
    TASK_STATUS_RUNNING,
    TASK_STATUS_FAILED,
    TASK_STATUS_SUCCEEDED
]

TASK_STATUSES_ALL = set(TASK_STATUSES_ORDERED)

# Tasks statuses to show in restricted monitoring mode.
TASK_STATUSES_RESTRICTED = set([
    TASK_STATUS_EXPIRED,
    TASK_STATUS_SUBMITTED,
    TASK_STATUS_SUBMIT_FAILED,
    TASK_STATUS_SUBMIT_RETRYING,
    TASK_STATUS_RUNNING,
    TASK_STATUS_FAILED,
    TASK_STATUS_RETRYING
])

# Tasks statuses to show in restricted monitoring mode.
TASK_STATUSES_NO_JOB_FILE = set([
    TASK_STATUS_RUNAHEAD,
    TASK_STATUS_WAITING,
    TASK_STATUS_HELD,
    TASK_STATUS_READY,
    TASK_STATUS_EXPIRED,
    TASK_STATUS_QUEUED
])

# Task statuses we can manually reset a task TO.
TASK_STATUSES_CAN_RESET_TO = set([
    TASK_STATUS_SUBMITTED,
    TASK_STATUS_SUBMIT_FAILED,
    TASK_STATUS_RUNNING,
    TASK_STATUS_WAITING,
    TASK_STATUS_EXPIRED,
    TASK_STATUS_SUCCEEDED,
    TASK_STATUS_FAILED
])

# Task statuses that are final.
TASK_STATUSES_FINAL = set([
    TASK_STATUS_EXPIRED,
    TASK_STATUS_SUCCEEDED,
    TASK_STATUS_FAILED,
    TASK_STATUS_SUBMIT_FAILED,
])

# Task statuses that are never active.
# For tasks that have never been submitted, but excluding:
# - expired: which is effectively the "succeeded" final state.
# - held: which is placeholder state, not a real state.
TASK_STATUSES_NEVER_ACTIVE = set([
    TASK_STATUS_RUNAHEAD,
    TASK_STATUS_WAITING,
    TASK_STATUS_QUEUED,
    TASK_STATUS_READY,
])

# Task statuses that are to be externally active
TASK_STATUSES_TO_BE_ACTIVE = set([
    TASK_STATUS_QUEUED,
    TASK_STATUS_READY,
    TASK_STATUS_SUBMIT_RETRYING,
    TASK_STATUS_RETRYING,
])

# Task statuses that are externally active
TASK_STATUSES_ACTIVE = set([
    TASK_STATUS_SUBMITTED,
    TASK_STATUS_RUNNING,
])

# Task statuses in which tasks cannot be considered stalled
TASK_STATUSES_NOT_STALLED = TASK_STATUSES_ACTIVE | TASK_STATUSES_TO_BE_ACTIVE

# Task statuses that can be manually triggered.
TASK_STATUSES_TRIGGERABLE = set([
    TASK_STATUS_WAITING,
    TASK_STATUS_HELD,
    TASK_STATUS_QUEUED,
    TASK_STATUS_EXPIRED,
    TASK_STATUS_SUBMIT_FAILED,
    TASK_STATUS_SUBMIT_RETRYING,
    TASK_STATUS_SUCCEEDED,
    TASK_STATUS_FAILED,
    TASK_STATUS_RETRYING
])

# Tasks statuses to auto-exand in the gcylc tree view.
TASK_STATUSES_AUTO_EXPAND = set([
    TASK_STATUS_QUEUED,
    TASK_STATUS_READY,
    TASK_STATUS_EXPIRED,
    TASK_STATUS_SUBMITTED,
    TASK_STATUS_RUNNING,
    TASK_STATUS_FAILED,
])


def status_leq(status_a, status_b):
    """"Return True if status_a <= status_b"""
    return (TASK_STATUSES_ORDERED.index(status_a) <=
            TASK_STATUSES_ORDERED.index(status_b))


def status_geq(status_a, status_b):
    """"Return True if status_a >= status_b"""
    return (TASK_STATUSES_ORDERED.index(status_a) >=
            TASK_STATUSES_ORDERED.index(status_b))


class TaskState(object):
    """Task status and utilities."""

    # Memory optimization - constrain possible attributes to this list.
    __slots__ = ["identity", "status", "hold_swap",
                 "_is_satisfied", "_suicide_is_satisfied", "prerequisites",
                 "suicide_prerequisites", "external_triggers", "outputs",
                 "kill_failed", "time_updated", "confirming_with_poll"]

    def __init__(self, tdef, point, status, hold_swap):
        self.identity = TaskID.get(tdef.name, str(point))
        self.status = status
        self.hold_swap = hold_swap
        self.time_updated = None

        self._is_satisfied = None
        self._suicide_is_satisfied = None

        # Prerequisites.
        self.prerequisites = []
        self.suicide_prerequisites = []
        self._add_prerequisites(point, tdef)

        # External Triggers.
        self.external_triggers = {}
        for ext in tdef.external_triggers:
            # Allow cycle-point-specific external triggers - GitHub #1893.
            if '$CYLC_TASK_CYCLE_POINT' in ext:
                ext = ext.replace('$CYLC_TASK_CYCLE_POINT', str(point))
            # set unsatisfied
            self.external_triggers[ext] = False

        self.outputs = TaskOutputs(tdef)
        self.kill_failed = False
        self.confirming_with_poll = False

    def satisfy_me(self, all_task_outputs):
        """Attempt to get my prerequisites satisfied."""
        for prereqs in [self.prerequisites, self.suicide_prerequisites]:
            for prereq in prereqs:
                if prereq.satisfy_me(all_task_outputs):
                    self._is_satisfied = None
                    self._suicide_is_satisfied = None

    def prerequisites_are_all_satisfied(self):
        """Return True if (non-suicide) prerequisites are fully satisfied."""
        if self._is_satisfied is None:
            self._is_satisfied = all(
                preq.is_satisfied() for preq in self.prerequisites)
        return self._is_satisfied

    def prerequisites_are_not_all_satisfied(self):
        """Return True if (any) prerequisites are not fully satisfied."""
        return (not self.prerequisites_are_all_satisfied() or
                not self.suicide_prerequisites_are_all_satisfied())

    def suicide_prerequisites_satisfied(self):
        """Return True if any suicide prerequisites are satisfied."""
        if self._suicide_is_satisfied is True:
            return True
        return any(preq.is_satisfied() for preq in self.suicide_prerequisites)

    def suicide_prerequisites_are_all_satisfied(self):
        """Return True if all suicide prerequisites are satisfied."""
        if self._suicide_is_satisfied is None:
            self._suicide_is_satisfied = all(
                preq.is_satisfied() for preq in self.suicide_prerequisites)
        return self._suicide_is_satisfied

    def prerequisites_get_target_points(self):
        """Return a list of cycle points targeted by each prerequisite."""
        return set(point for prerequisite in self.prerequisites for
                   point in prerequisite.get_target_points())

    def prerequisites_eval_all(self):
        """Set all prerequisites to satisfied."""
        # (Validation: will abort on illegal trigger expressions.)
        for preqs in [self.prerequisites, self.suicide_prerequisites]:
            for preq in preqs:
                preq.is_satisfied()

    def set_prerequisites_all_satisfied(self):
        """Set prerequisites to all satisfied."""
        for prereq in self.prerequisites:
            prereq.set_satisfied()
        self._is_satisfied = None

    def set_prerequisites_not_satisfied(self):
        """Reset prerequisites."""
        for prereq in self.prerequisites:
            prereq.set_not_satisfied()
        self._is_satisfied = None

    def prerequisites_dump(self, list_prereqs=False):
        """Dump prerequisites."""
        if list_prereqs:
            return [Prerequisite.MESSAGE_TEMPLATE % msg for prereq in
                    self.prerequisites for msg in sorted(prereq.satisfied)]
        else:
            return [x for prereq in self.prerequisites for x in prereq.dump()]

    def get_resolved_dependencies(self):
        """Return a list of dependencies which have been met for this task.

        E.G: ['foo.1', 'bar.2']

        The returned list is sorted to allow comparison with reference run
        task with lots of near-simultaneous triggers.

        """
        return list(sorted(dep for prereq in self.prerequisites for dep in
                           prereq.get_resolved_dependencies()))

    def set_held(self):
        """Set state to TASK_STATUS_HELD, if possible.

        If state can be held, set hold_swap to current state.
        If state is active, set hold_swap to TASK_STATUS_HELD.
        If state cannot be held, do nothing.
        """
        if self.status in TASK_STATUSES_ACTIVE:
            self.hold_swap = TASK_STATUS_HELD
            return
        elif self.status in [
                TASK_STATUS_WAITING, TASK_STATUS_QUEUED,
                TASK_STATUS_SUBMIT_RETRYING, TASK_STATUS_RETRYING]:
            return self._set_state(TASK_STATUS_HELD)

    def unset_held(self):
        """Reset to my pre-held state, if not beyond the stop point."""
        if self.status != TASK_STATUS_HELD:
            return
        elif self.hold_swap is None:
            self.reset_state(TASK_STATUS_WAITING)
        elif self.hold_swap == TASK_STATUS_HELD:
            self.hold_swap = None
        else:
            self.reset_state(self.hold_swap)

    def reset_state(self, status):
        """Change status, and manipulate outputs and prerequisites accordingly.

        Outputs are manipulated on manual state reset to reflect the new task
        status, except for custom outputs on reset to succeeded or later -
        these can be completed if need be using "cylc reset --output".

        Prerequisites, which reflect the state of *other tasks*, are not
        manipulated, except to unset them on reset to waiting or earlier.
        (TODO - we should not do this - see GitHub #2329).

        Note this method could take an additional argument to distinguish
        internal and manually forced state changes, if needed.

        The held state is handled in set/unset_held() for swap-state handling.

        """
        self.kill_failed = False

        # Set standard outputs in accordance with task state.
        if status_leq(status, TASK_STATUS_SUBMITTED):
            self.outputs.set_all_incomplete()
        self.outputs.set_completion(
            TASK_OUTPUT_EXPIRED, status == TASK_STATUS_EXPIRED)
        self.outputs.set_completion(
            TASK_OUTPUT_SUBMITTED, status_geq(status, TASK_STATUS_SUBMITTED))
        self.outputs.set_completion(
            TASK_OUTPUT_STARTED, status_geq(status, TASK_STATUS_RUNNING))
        self.outputs.set_completion(
            TASK_OUTPUT_SUBMIT_FAILED, status == TASK_STATUS_SUBMIT_FAILED)
        self.outputs.set_completion(
            TASK_OUTPUT_SUCCEEDED, status == TASK_STATUS_SUCCEEDED)
        self.outputs.set_completion(
            TASK_OUTPUT_FAILED, status == TASK_STATUS_FAILED)

        # Unset prerequisites on reset to waiting (see docstring).
        if status == TASK_STATUS_WAITING:
            self.set_prerequisites_not_satisfied()

        return self._set_state(status)

    def _set_state(self, status):
        """Set, log and record task status (normal change, not forced - don't
        update task_events table)."""
        if self.status == self.hold_swap:
            self.hold_swap = None
        if status == self.status and self.hold_swap is None:
            return
        o_status, o_hold_swap = self.status, self.hold_swap
        if status == TASK_STATUS_HELD:
            self.hold_swap = self.status
        elif status in TASK_STATUSES_ACTIVE:
            if self.status == TASK_STATUS_HELD:
                self.hold_swap = TASK_STATUS_HELD
        elif (self.hold_swap == TASK_STATUS_HELD and
                status not in TASK_STATUSES_FINAL):
            self.hold_swap = status
            status = TASK_STATUS_HELD
        elif self.hold_swap:
            self.hold_swap = None
        self.status = status
        self.time_updated = get_current_time_string()
        flags.iflag = True
        # Log
        message = str(o_status)
        if o_hold_swap:
            message += " (%s)" % o_hold_swap
        message += " => %s" % self.status
        if self.hold_swap:
            message += " (%s)" % self.hold_swap
        LOG.debug(message, itask=self.identity)

    def is_gt(self, status):
        """"Return True if self.status > status."""
        return (TASK_STATUSES_ORDERED.index(self.status) >
                TASK_STATUSES_ORDERED.index(status))

    def _add_prerequisites(self, point, tdef):
        """Add task prerequisites."""
        # Triggers for sequence_i only used if my cycle point is a
        # valid member of sequence_i's sequence of cycle points.
        self._is_satisfied = None
        self._suicide_is_satisfied = None

        for sequence, dependencies in tdef.dependencies.items():
            if not sequence.is_valid(point):
                continue
            for dependency in dependencies:
                cpre = dependency.get_prerequisite(point, tdef)
                if dependency.suicide:
                    self.suicide_prerequisites.append(cpre)
                else:
                    self.prerequisites.append(cpre)

        if tdef.sequential:
            # Add a previous-instance succeeded prerequisite.
            p_prev = None
            adjusted = []
            for seq in tdef.sequences:
                prv = seq.get_nearest_prev_point(point)
                if prv:
                    # None if out of sequence bounds.
                    adjusted.append(prv)
            if adjusted:
                p_prev = max(adjusted)
                cpre = Prerequisite(point, tdef.start_point)
                cpre.add(tdef.name, p_prev, TASK_STATUS_SUCCEEDED,
                         p_prev < tdef.start_point)
                cpre.set_condition(tdef.name)
                self.prerequisites.append(cpre)
