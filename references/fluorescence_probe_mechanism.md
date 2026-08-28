# Fluorescence-probe mechanism evidence

Evaluate hypotheses such as ICT restoration, PET-like quenching, conjugation interruption/restoration, donor/acceptor change, TICT access, planarization, state reordering, or oscillator-strength redistribution with an evidence table.

Each evidence item must declare an `evidence_family` such as `spectral`, `NTO`, `charge_transfer`, `geometry`, `TICT_PES`, `solvent`, `oscillator_strength`, `high_level_reference`, or `experimental`. Use `SUPPORTED` only when at least two supporting non-canonical-orbital observations come from two distinct evidence families and one is strong (for example state-matched NTO plus a quantitative hole-electron result). Use `PLAUSIBLE`, `INSUFFICIENT`, or `CONTRADICTED` otherwise.

Never infer quantum yield from oscillator strength alone, or a mechanism from only a HOMO-LUMO-gap change. Flexible probes require a conformer check when low-energy conformers or D-pi-A dihedrals can materially change the spectrum.
