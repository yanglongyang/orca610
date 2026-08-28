# Solvent-series analysis

Two protocols answer different questions:

- `fixed_geometry`: reuse one geometry in every solvent. This estimates the electronic continuum-solvent response.
- `solvent_relaxed`: optimize or otherwise relax geometry in each solvent. This contains electronic response plus geometry/conformation changes.

Do not label solvent-relaxed shifts as pure solvent effects. For every entry retain solvent, geometry identifier, functional/basis/dispersion, state identity, TDA/full-TD-DFT setting, and LR-CPCM equilibrium/non-equilibrium behavior.

```bash
python3 scripts/solvent_series_report.py examples/solvent_series.example.json
```

Every series entry records `transition_kind` (`absorption` or `emission`) and `geometry_surface` (`R0` or `R1`); these must be matched across a controlled series. The script rejects a mixed-geometry series mislabeled `fixed_geometry`. Under `solvent_relaxed`, `geometry_solvent` must equal the entry solvent unless an explicit `allow_geometry_solvent_mismatch` composite-protocol override is documented.
