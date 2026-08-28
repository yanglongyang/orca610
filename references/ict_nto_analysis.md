# NTO and ICT evidence

For each important absorption or emission state, first verify state identity across geometries, then inspect NTOs, transition/difference density, fragment populations, and only then canonical HOMO/LUMO orbitals as supporting images.

ORCA 6.1 supports `DoNTO`, `NTOStates`, and `NTOThresh` in `%tddft`; AutoORCA enables NTO generation in S1 optimization and emission inputs. Consult the [ORCA 6.1 TD-DFT manual](https://www.faccts.de/docs/orca/6.1/manual/contents/spectroscopyproperties/tddft.html) before changing related keywords.

Classify a state as `LOCAL`, `PARTIAL_CT`, `STRONG_CT`, `MIXED`, or `UNRESOLVED` only after state identity and donor/acceptor NTO descriptions are recorded. Qualitative NTO evidence and quantitative hole-electron evidence must be reported separately. Do not fabricate a CT distance from an orbital image.

Keep visual products under a project-local convention such as `analysis/nto/<species>_R0/` and `analysis/nto/<species>_R1/`. Generate cube files with locally verified `orca_plot` commands when practical; this repository intentionally does not guess an interactive plotting sequence.
