"""
The plant V-ATPase in the tonoplast, with ATG12-ATG5-ATG16 complexes moving in the
cytosol beside its V1 head. A short seamless loop: the camera sways around the pump
and returns to where it started.

Structures (see structures/ and tools/):
  vatpase_up.cif     citrus V-ATPase (PDB 7UWA), oriented so the V0 c-ring sits at
                     the origin and V1 points to +z
  atg16_complex.cif  human ATG12-ATG5-ATG16N (PDB 4GDK, chains A-C), centred

Usage:
  blender --background --python scenes/vatpase_atg16.py -- --render-still 1
  blender --background --python scenes/vatpase_atg16.py -- --render
  blender --background --python scenes/vatpase_atg16.py -- --render-frames 1 72
  blender --background --python scenes/vatpase_atg16.py -- --encode
"""

import sys
import os
import math
import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as c

TOTAL_FRAMES = c.FPS * 6
MEMBRANE_THICKNESS = 0.4   # Molecular Nodes scale: 0.01 Blender units per angstrom


def load_molecule(mn, filename, name, material):
    mol = mn.Molecule.load(os.path.join(c.STRUCTURES_DIR, filename), name=name)
    mol.add_style("spheres", material=material, color="common")
    return mol.object


def create_membrane():
    """A nearly flat tonoplast (the pump spans it) covered with a lipid bilayer."""
    bpy.ops.mesh.primitive_grid_add(size=9, x_subdivisions=90, y_subdivisions=90, location=(0, 0, 0))
    membrane = bpy.context.active_object
    membrane.name = "Tonoplast"

    ripple = membrane.modifiers.new("Ripple", "DISPLACE")
    tex = bpy.data.textures.new("TonoplastNoise", type="CLOUDS")
    tex.noise_scale = 0.6
    ripple.texture = tex
    ripple.strength = 0.05

    thickness = membrane.modifiers.new("Thickness", "SOLIDIFY")
    thickness.thickness = MEMBRANE_THICKNESS
    thickness.offset = 0.0

    membrane.data.materials.append(
        c.make_material("Mat_Tonoplast", (0.32, 0.13, 0.58), roughness=0.22, transmission=0.25, subsurface=0.3)
    )
    bpy.ops.object.shade_smooth()
    c.add_lipid_bilayer(membrane, count=5200, seed=4)
    return membrane


def create_vatpase(mn):
    mat = c.make_material("Mat_VATPase", (0.95, 0.72, 0.28), roughness=0.32, subsurface=0.3, use_cpk=True)
    obj = load_molecule(mn, "vatpase_up.cif", "VATPase", mat)
    obj.location = (0, 0, 0)
    obj.rotation_mode = "XYZ"
    for f, deg in ((1, -3), (TOTAL_FRAMES // 2, 3), (TOTAL_FRAMES, -3)):
        obj.rotation_euler = (0, 0, math.radians(deg))
        obj.keyframe_insert(data_path="rotation_euler", frame=f)
    return obj


def create_atg16_complexes(mn):
    """Two copies moving through the cytosol next to the V1 base. Each path returns
    to its start so the video loops."""
    mat = c.make_material("Mat_ATG16", (0.1, 0.65, 0.7), roughness=0.28, subsurface=0.35, use_cpk=True)
    base = load_molecule(mn, "atg16_complex.cif", "ATG16_1", mat)
    objs = [base, c.duplicate_object(base, "ATG16_2")]
    paths = [
        [(1.05, -0.55, 0.75), (0.85, -0.75, 0.6), (1.15, -0.4, 0.95)],
        [(-1.15, -0.35, 0.95), (-0.95, -0.6, 0.7), (-1.25, -0.2, 1.1)],
    ]
    for i, (obj, pts) in enumerate(zip(objs, paths)):
        keys = [1, TOTAL_FRAMES // 3, 2 * TOTAL_FRAMES // 3, TOTAL_FRAMES]
        for f, p in zip(keys, pts + [pts[0]]):
            obj.location = p
            obj.keyframe_insert(data_path="location", frame=f)
        obj.rotation_euler = (math.radians(20 + 40 * i), math.radians(-15), math.radians(60 * i))
        c.add_brownian_jitter(obj, TOTAL_FRAMES, seed=60 + i, amplitude_deg=10, cycles=2)
    return objs


def create_camera_and_lights():
    """A gentle back-and-forth orbit around the pump's axis."""
    target = (0, 0, 0.75)
    bpy.ops.object.empty_add(location=(0, 0, 0))
    pivot = bpy.context.active_object
    pivot.name = "CameraPivot"

    bpy.ops.object.camera_add(location=(0, -6.4, 1.7))
    camera = bpy.context.active_object
    camera.name = "Camera"
    camera.parent = pivot
    camera.data.lens = 40
    direction = c.Vector(target) - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    camera.data.dof.use_dof = True
    camera.data.dof.aperture_fstop = 3.2
    camera.data.dof.focus_distance = 6.3
    bpy.context.scene.camera = camera

    for f, deg in ((1, -14), (TOTAL_FRAMES // 2, 14), (TOTAL_FRAMES, -14)):
        pivot.rotation_euler = (0, 0, math.radians(deg))
        pivot.keyframe_insert(data_path="rotation_euler", frame=f)

    c.add_wehi_lighting(key_loc=(2.6, -3.2, 3.6), target=target, key_energy=380, key_size=2.5)

    bpy.ops.object.light_add(type="AREA", location=(0, 0.5, -3.0))
    below = bpy.context.active_object
    below.name = "VacuoleGlow"
    below.data.energy = 60
    below.data.size = 7
    below.data.color = (0.6, 0.35, 0.9)
    below.rotation_euler = (math.radians(180), 0, 0)
    return camera


def build_scene():
    c.clear_scene()
    c.setup_world_dark()
    mn = c.enable_molecular_nodes()

    create_membrane()
    create_vatpase(mn)
    create_atg16_complexes(mn)
    c.create_crowding_proteins(
        bounds=((-3.2, 3.2), (-1.5, 2.5), (0.5, 2.6)),
        count=16,
        seed=400,
        total_frames=TOTAL_FRAMES,
    )

    create_camera_and_lights()
    c.setup_render_settings(TOTAL_FRAMES, "vatpase_atg16")
    scene = bpy.context.scene
    scene.eevee.taa_render_samples = 48
    scene.frame_set(1)


if __name__ == "__main__":
    build_scene()

    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if "--render-still" in args:
        frame = int(args[-1]) if args[-1].isdigit() else 1
        c.render_still(frame, "vatpase_atg16_preview.png")
    elif "--render-frames" in args:
        i = args.index("--render-frames")
        c.render_frame_range(int(args[i + 1]), int(args[i + 2]), "vatpase_atg16")
    elif "--encode" in args:
        c.encode_png_sequence("vatpase_atg16", 1, TOTAL_FRAMES, c.FPS, "vatpase_atg16.mp4")
    elif "--render" in args:
        c.render_animation("vatpase_atg16.mp4")
