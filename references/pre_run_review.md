# Mandatory pre-run human review gate

Generation is not execution authority. Every AutoORCA-generated or modified `.inp` must pass:

```text
GENERATED -> REVIEW_REQUIRED -> APPROVED -> RUNNING -> COMPLETED

`REJECTED` records a human decision not to run the reviewed version. A changed
approved input is retained as `INVALIDATED` in the review history before the
new version returns to `REVIEW_REQUIRED`.
```

Use `python3 scripts/input_review.py review input.inp` to record the input SHA256, hash known external dependencies (`xyzfile`, `moinp`, `GSHessian`, `ESHessian`), print a semantic summary, warnings, and the complete raw input. Inspect the raw input; the summary is not a replacement.

Only after a human explicitly approves that displayed exact input may the executor invoke `python3 scripts/input_approve.py input.inp`. There is no `--yes`, global approval, or auto-approval mode. Approval binds input content plus dependency hashes, not a filename or a previously verified template.

`run_orca()` independently invokes the final `require` check. If an input or dependency changes, approval is recorded as invalidated, the manifest returns to `REVIEW_REQUIRED`, and execution is refused. Autopilot intentionally stops at this boundary and must be restarted after approval.

The approval check also runs before AutoORCA trusts an existing job or completed `.out`. A historical completed calculation without a v3.2 record is labelled `IMPORTED_UNREVIEWED`: it may be reviewed and approved for use now, but that approval never claims the calculation was approved before it ran.

Standalone generators must use the same review manifest as the workflow. `tict_scan_builder.py` accepts `--manifest "$INPUT_REVIEW_FILE"` and otherwise honors an exported `INPUT_REVIEW_FILE`.

Never equate automation with authority: the final ORCA input is an inspectable scientific object whose method, geometry, state definition, solvation, and resource settings must be understood before execution.
