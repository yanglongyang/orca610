# AutoORCA v3.5.1 orbital rendering template. Values are substituted per image.
display projection Orthographic
display depthcue off
axes location Off
color Display Background white
display ambientocclusion on
display shadows on
mol new "{{XYZ}}" type xyz waitfor all
mol addfile "{{CUBE}}" type cube waitfor all
mol delrep 0 top
mol representation CPK 0.85 0.25 18.0 18.0
mol color Name
mol material AOShiny
mol addrep top
mol representation Isosurface {{ISOVALUE}} 0 0 0 1 1
mol color ColorID 0
mol material AOShiny
mol addrep top
mol representation Isosurface -{{ISOVALUE}} 0 0 0 1 1
mol color ColorID 1
mol material AOShiny
mol addrep top
molinfo top set rotate_matrix {{ROTATE_MATRIX}}
display resize {{WIDTH}} {{HEIGHT}}
render TachyonInternal "{{TGA}}"
quit
