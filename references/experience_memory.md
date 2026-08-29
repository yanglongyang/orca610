# Experience-consistency gate

Before generating an ORCA input, AutoORCA must consult the structured rule set, relevant active templates, deprecated failures, project-local observations, and the applicable manual guidance. Archive files are evidence, not automatic execution authority.

Evidence levels are deliberately distinct:

- `MANUAL_CONFIRMED`: documented by the applicable ORCA manual.
- `VERIFIED_SUCCESS`: successfully executed under recorded conditions.
- `VERIFIED_FAILURE`: reproducible failure within a stated scope.
- `LOCAL_OBSERVATION`: a captured project/machine event; never generalize it without review.

`experience_gate.py check input.inp` is mandatory before review registration and `require` is repeated in `run_orca()`. A known invalid rule is a hard refusal. The gate records input and rule-database hashes in `experience_checks.json`; changing either requires a new check.

Failed runtime jobs are saved under `experience/cases/failure/` as `LOCAL_OBSERVATION`. They are not promoted automatically into universal restrictions. Curate a reusable rule only after reviewing scope, evidence, and authoritative syntax.
