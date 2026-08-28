# TICT diagnostic workflow

TICT is a multi-evidence interpretation, not an angle threshold. User-supplied dihedral atoms define the diagnostic; AutoORCA never infers donor/bridge/acceptor fragments or dihedrals.

Compare S0/S1 dihedrals and, where justified, run a relaxed S1 dihedral scan with root following and NTO output. ORCA's `%geom Scan D` performs constrained relaxed scans; consult the [ORCA 6.1 surface-scan manual](https://www.faccts.de/docs/orca/6.1/manual/contents/structurereactivity/optimizations_scans.html) for syntax and cost.

`TICT_SUPPORTED` requires substantial twisting plus a low-energy twisted region, changed CT character, and at least one further corroborating signal (oscillator-strength reduction, solvent stabilization, or a plausible Franck-Condon-to-twisted path). A twisted geometry alone is never sufficient.
