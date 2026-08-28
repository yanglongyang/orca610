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

Never equate automation with authority: the final ORCA input is an inspectable scientific object whose method, geometry, state definition, solvation, and resource settings must be understood before execution.
