# Experience-consistency gate

Before generating an ORCA input, AutoORCA must consult the structured rule set, relevant active templates, deprecated failures, project-local observations, and the applicable manual guidance. Archive files are evidence, not automatic execution authority.

Evidence levels are deliberately distinct:

- `MANUAL_CONFIRMED`: documented by the applicable ORCA manual.
- `VERIFIED_SUCCESS`: successfully executed under recorded conditions.
- `VERIFIED_FAILURE`: reproducible failure within a stated scope.
- `LOCAL_OBSERVATION`: a captured project/machine event; never generalize it without review.

`experience_gate.py lookup --calculation-type TYPE` is mandatory before generation, `check input.inp` repeats the lookup against the rendered input before review registration, and `require` is repeated in `run_orca()`. A known invalid rule is a hard refusal. Exact repetition means identical input hash, dependency fingerprints, and ORCA version; sufficiently similar prior failures are warnings requiring inspection. The gate records input and complete consulted-evidence-index hashes in `experience_checks.json`. When that index changes, `require` re-evaluates unchanged input automatically, refuses any new hard evidence, requires a human acknowledgement command with `--human-acknowledged` for new similar failures, and refreshes only unrelated changes without changing independent human approval. The acknowledgement output lists every new similar failure before all are recorded as acknowledged. This acknowledgement records `acknowledged_by: human` and an acknowledgement timestamp; it is not a replacement for input approval. `run_orca()` additionally refuses to launch when current ORCA version differs from the input declaration; completed-output provenance is bound to both input path and input SHA256.

Failed runtime jobs are saved under `experience/cases/failure/` as `LOCAL_OBSERVATION`, including full input text, metadata, dependent-file hashes, ORCA version, selected environment data, and output tail. They are not promoted automatically into universal restrictions. Curate a reusable rule only after reviewing scope, evidence, and authoritative syntax.
