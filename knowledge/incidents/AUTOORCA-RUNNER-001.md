# AUTOORCA-RUNNER-001 — `job_running` false self-lock

- Classification: deterministic AutoORCA runner defect, **not** a scientific-input experience rule.
- Status: fixed.
- Fixed by: `b9dd50db03f8d43d67d36e8b9f5130cf28c4dd01` (`fix: scope runner jobs and manifests to inputs`).

## Trigger

The former `job_running()` scanned the global process table using a broad
pattern equivalent to `orca.*${basename}`. If the runner command line included
an installation or script path containing `orca` and the input basename, it
could match itself and loop indefinitely at `Waiting for running job`.

The same basename in another project could also be mistaken for the current
job.

## Root cause

Global process-name matching is not a job identity. It cannot distinguish the
runner, an ORCA child, or a separate work directory from their text fragments.

## Remediation and regression coverage

Jobs are now represented by an adjacent PID lock containing the absolute input
path and process-start token. The runner validates that lock and PID rather
than grepping all processes; stale locks are removed. Direct standalone
review/approve/run commands now choose manifests relative to the input unless a
workflow manifest is explicitly supplied.

`tests/test_runner_locking.py` covers an `orca`-containing path and two projects
with the same input basename. This incident remains outside `knowledge/rules/`
and is never evaluated as ORCA input evidence.
