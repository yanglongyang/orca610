# Optional hole-electron analysis

ORCA-native NTO/state analysis is the baseline. Multiwfn is an optional external backend for documented hole-electron metrics such as centroid separation, overlap, or fragment contributions.

Set `MULTIWFN_BIN` to a verified executable when available. AutoORCA only detects that executable and records whether quantitative analysis was run; it does not invoke undocumented Multiwfn menu sequences. Verify commands and metric definitions against the installed Multiwfn version/manual before adding project automation.

If Multiwfn is absent, use `hole_electron_status = NOT_RUN` and continue the ORCA-only workflow.
