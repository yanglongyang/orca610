# ORCA orbital visualization

Use this layer only for completed ORCA calculations. It consumes `.out`,
`.gbw`, and geometry files and never changes an `.inp` or launches an
electronic-structure calculation.

`scripts/orbital_visualize.py` reads the completed output, resolves requested
frontier orbitals, writes a provenance manifest, and—only with `--execute`—
asks `orca_plot` to generate cubes. ORCA MO indices start at zero. For RHF/RKS
the operator is `0`; for UHF/UKS, alpha/beta use `0`/`1`. See the official
[ORCA 6.1 plotting documentation](https://www.faccts.de/docs/orca/6.1/manual/contents/utilitiesvisualization/plots.html).

The ORCA 6.1 interactive sequence implemented by `orbital_cube_orca.py` is:
MO plot type, orbital index, operator, grid, Gaussian Cube output, then
generate. Keep that version-specific sequence isolated in the backend; do not
copy a Gaussian or Multiwfn menu workflow into ORCA commands.

For an open-shell result, specify `--spin alpha`, `--spin beta`, or
`--all-spins`. A bare HOMO/LUMO request must never select a spin channel by
guesswork. Multiwfn is an optional future fallback for non-MO products such as
ESP, ELF, LOL, or specialized density analyses; it is not required here.
