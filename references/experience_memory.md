# Experience-consistency gate

Before generating an ORCA input, AutoORCA must consult the structured rule set, relevant active templates, deprecated failures, project-local observations, and the applicable manual guidance. Archive files are evidence, not automatic execution authority.

Evidence levels are deliberately distinct:

- `MANUAL_CONFIRMED`: documented by the applicable ORCA manual.
- `VERIFIED_SUCCESS`: successfully executed under recorded conditions.
- `VERIFIED_FAILURE`: reproducible failure within a stated scope.
- `LOCAL_OBSERVATION`: a captured project/machine event; never generalize it without review.

`experience_gate.py lookup --calculation-type TYPE` is mandatory before generation, `check input.inp` repeats the lookup against the rendered input before review registration, and `require` is repeated in `run_orca()`. A known invalid rule is a hard refusal. Exact repetition of a captured failure under the same ORCA version is also refused; sufficiently similar prior failures are warnings requiring inspection. The gate records input and complete consulted-evidence-index hashes in `experience_checks.json`; changing rules, templates, or local cases requires a new check.

Failed runtime jobs are saved under `experience/cases/failure/` as `LOCAL_OBSERVATION`, including full input text, metadata, dependent-file hashes, ORCA version, selected environment data, and output tail. They are not promoted automatically into universal restrictions. Curate a reusable rule only after reviewing scope, evidence, and authoritative syntax.
