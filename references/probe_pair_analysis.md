# Probe-pair analysis gate

Use this workflow for an intact probe, released fluorophore, reaction product, or reference dye. A project may contain more than two species; choose a pair explicitly for each comparison.

Before attributing a spectral shift to chemistry, require identical functional, basis, dispersion, solvent model/solvent, TDA or full-TD-DFT setting, state identity, and vertical/relaxed protocol. Molecular structures are expected to differ.

Run:

```bash
python3 scripts/probe_pair_compare.py examples/probe_pair_results.example.json
```

Compare calculated absorption/emission energies, oscillator strengths, Stokes shifts, and valid `E00` values. Wavelength differences are display quantities; calculate Stokes shifts from energy or wavenumber.

Never interpret the HOMO-LUMO gap as the optical gap. Never subtract total electronic energies of chemically different probe/product structures as a reaction energy unless a balanced thermochemical cycle has been constructed.
