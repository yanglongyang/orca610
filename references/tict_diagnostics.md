# TICT diagnostic workflow

TICT is a multi-evidence interpretation, not an angle threshold. User-supplied dihedral atoms define the diagnostic; AutoORCA never infers donor/bridge/acceptor fragments or dihedrals.

Compare S0/S1 dihedrals and, where justified, run a relaxed S1 dihedral scan with root following and NTO output. ORCA's `%geom Scan D` performs constrained relaxed scans; consult the [ORCA 6.1 surface-scan manual](https://www.faccts.de/docs/orca/6.1/manual/contents/structurereactivity/optimizations_scans.html) for syntax and cost.

The scan configuration uses `scan.start_deg`, `scan.end_deg`, and `scan.n_steps`; `n_steps` is ORCA's number of equally spaced scan steps, not a degrees-per-step increment. The builder reads the XYZ atom count and refuses an out-of-range dihedral index.

`TICT_SUPPORTED` requires substantial twisting plus a low-energy twisted region, changed CT character, and at least one further corroborating signal (oscillator-strength reduction, solvent stabilization, or a plausible Franck-Condon-to-twisted path). A twisted geometry alone is never sufficient.
