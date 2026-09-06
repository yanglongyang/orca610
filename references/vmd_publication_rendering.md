# VMD publication rendering

The generated Tcl files are self-contained and run with `vmd -dispdev text`.
They do not read or modify global `vmd.rc`. The default profiles are white
background, orthographic projection, AOShiny material, ambient occlusion,
shadows, and paired positive/negative isosurfaces.

`preview` is 1200 x 900; `publication` is 3000 x 2400. VMD/Tachyon produces a
TGA which is converted to lossless PNG only when ImageMagick is available.
The manifest records an absent renderer/converter as absent—it never claims a
PNG was made when it was not.

For comparisons, keep the isovalue, rendering profile, camera convention, and
front/side axis selectors constant. `--comparison-manifest` enforces that
convention against an existing AutoORCA visualization manifest. An exception
requires both `--allow-comparison-exception` and a human-supplied
`--comparison-exception-reason`, which is retained in the manifest.
