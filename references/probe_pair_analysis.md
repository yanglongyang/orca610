# Probe-pair analysis gate

Use this workflow for an intact probe, released fluorophore, reaction product, or reference dye. A project may contain more than two species; choose a pair explicitly for each comparison.

Before attributing a spectral shift to chemistry, compare matching stages between species: `s0_geometry`, `absorption`, `s1_geometry`, and `emission`. Within each matching stage, require identical functional, basis, dispersion, solvent model/solvent, solvent regime, `CPCMEQ`, response formalism, and numerical settings. Molecular structures are expected to differ; the four stages within one species need not share the same protocol.

Run:

```bash
python3 scripts/probe_pair_compare.py examples/probe_pair_results.example.json
```

Compare calculated absorption/emission energies, oscillator strengths, Stokes shifts, and only validated `E00` values. An E00 record must include `eV`, `energy_cycle_gate: "PASS"`, and a source path to the successful four-point cycle; otherwise the report labels it `NOT_VALIDATED` and omits ΔE00. Wavelength differences are display quantities; calculate Stokes shifts from energy or wavenumber.

Never interpret the HOMO-LUMO gap as the optical gap. Never subtract total electronic energies of chemically different probe/product structures as a reaction energy unless a balanced thermochemical cycle has been constructed.
