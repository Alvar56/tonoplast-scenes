# ChimeraX script that writes the two structures the Blender scene loads.
#
#   chimerax --nogui --script tools/prepare_structures.py
#
# vatpase_up.cif     citrus V-ATPase (PDB 7UWA), turned so the axis from the V0 c-ring to
#                    the V1 A/B hexamer points along +z, with the c-ring centred at the origin
# atg16_complex.cif  ATG12-ATG5-ATG16N (PDB 4GDK, chains A-C), centred at the origin
import os
import numpy as np
from chimerax.core.commands import run

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'structures')
os.makedirs(OUT, exist_ok=True)


def rotation_to_z(axis):
    axis = axis / np.linalg.norm(axis)
    z = np.array([0.0, 0.0, 1.0])
    v = np.cross(axis, z)
    s, c = np.linalg.norm(v), float(axis @ z)
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + vx + vx @ vx * ((1 - c) / (s * s))


# V-ATPase
m = run(session, 'open 7uwa')[0]
run(session, 'delete solvent')
run(session, 'delete ligand')
desc = {ch.chain_id: (ch.description or '').lower() for ch in m.chains}
xyz = m.atoms.scene_coords
chain = np.array(m.atoms.residues.chain_ids)
is_c_ring = np.array([desc[c].endswith('subunit c') or 'subunit c"' in desc[c] for c in chain])
is_v1 = np.array(['catalytic subunit a' in desc[c] or 'subunit b' in desc[c] for c in chain])
v0, v1 = xyz[is_c_ring].mean(0), xyz[is_v1].mean(0)
m.atoms.scene_coords = (xyz - v0) @ rotation_to_z(v1 - v0).T
run(session, f'save "{os.path.join(OUT, "vatpase_up.cif")}" #1')
run(session, 'close')

# ATG12-ATG5-ATG16N
m = run(session, 'open 4gdk')[0]
run(session, 'delete solvent')
run(session, 'delete ligand')
run(session, 'delete /D-F')
xyz = m.atoms.scene_coords
m.atoms.scene_coords = xyz - xyz.mean(0)
run(session, f'save "{os.path.join(OUT, "atg16_complex.cif")}" #1')
run(session, 'exit')
