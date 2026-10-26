"""Shared Blender helpers for the tonoplast scenes: scene reset, Molecular Nodes,
materials, a phospholipid bilayer, crowding, WEHI-style lighting, compositing and
rendering."""

import os
import math
import random
import bpy
from mathutils import Vector, Quaternion

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
OUTPUT_DIR = os.path.join(PROJECT_DIR, "output")
STRUCTURES_DIR = os.path.join(PROJECT_DIR, "structures")

FPS = 24


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for block_collection in (bpy.data.meshes, bpy.data.materials, bpy.data.cameras, bpy.data.lights, bpy.data.worlds):
        for block in list(block_collection):
            if block.users == 0:
                block_collection.remove(block)


def enable_molecular_nodes():
    bpy.ops.preferences.addon_enable(module="bl_ext.blender_org.molecularnodes")
    import bl_ext.blender_org.molecularnodes as mn
    return mn


def make_material(name, base_color, roughness=0.4, transmission=0.0, emission_strength=0.0, subsurface=0.0, use_cpk=False):
    """A Principled BSDF material. With use_cpk=True it multiplies base_color by the
    per-element "Color" attribute that Molecular Nodes writes, so a protein keeps its
    identifying tint but shows atom-level variation instead of one flat colour."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Roughness"].default_value = roughness

    if use_cpk:
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        attr = nodes.new("ShaderNodeAttribute")
        attr.attribute_name = "Color"
        attr.attribute_type = "GEOMETRY"
        mix = nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.blend_type = "MULTIPLY"
        mix.inputs[0].default_value = 1.0
        mix_a = next(s for s in mix.inputs if s.name == "A" and s.type == "RGBA")
        mix_b = next(s for s in mix.inputs if s.name == "B" and s.type == "RGBA")
        mix_result = next(o for o in mix.outputs if o.name == "Result" and o.type == "RGBA")
        mix_b.default_value = (*base_color, 1.0)
        links.new(attr.outputs["Color"], mix_a)
        links.new(mix_result, bsdf.inputs["Base Color"])
    else:
        bsdf.inputs["Base Color"].default_value = (*base_color, 1.0)
    if "Transmission Weight" in bsdf.inputs:
        bsdf.inputs["Transmission Weight"].default_value = transmission
    elif "Transmission" in bsdf.inputs:
        bsdf.inputs["Transmission"].default_value = transmission
    if subsurface > 0:
        if "Subsurface Weight" in bsdf.inputs:
            bsdf.inputs["Subsurface Weight"].default_value = subsurface
            bsdf.inputs["Subsurface Radius"].default_value = (0.5, 0.25, 0.15)
        elif "Subsurface" in bsdf.inputs:
            bsdf.inputs["Subsurface"].default_value = subsurface
    if emission_strength > 0:
        bsdf.inputs["Emission Color"].default_value = (*base_color, 1.0)
        bsdf.inputs["Emission Strength"].default_value = emission_strength
    return mat


def duplicate_object(source_obj, new_name):
    bpy.ops.object.select_all(action="DESELECT")
    source_obj.select_set(True)
    bpy.context.view_layer.objects.active = source_obj
    bpy.ops.object.duplicate(linked=True)
    dup = bpy.context.active_object
    dup.name = new_name
    return dup


def add_brownian_jitter(obj, total_frames, seed, amplitude_deg=12, cycles=2):
    """Slow random rotation so molecules never look frozen between moves."""
    rnd = random.Random(seed)
    axis_order = rnd.choice(["XYZ", "XZY", "YXZ", "ZXY"])
    obj.rotation_mode = axis_order
    base = obj.rotation_euler.copy()
    steps = max(cycles * 4, 4)
    for step in range(steps + 1):
        frame = int(1 + (total_frames - 1) * step / steps)
        wob = math.radians(amplitude_deg) * math.sin(step * math.pi / 2 + seed)
        obj.rotation_euler = (
            base[0] + wob * rnd.uniform(0.5, 1.0),
            base[1] + wob * rnd.uniform(0.5, 1.0),
            base[2] + wob * rnd.uniform(0.5, 1.0),
        )
        obj.keyframe_insert(data_path="rotation_euler", frame=frame)


def create_crowding_proteins(bounds, count, seed, total_frames, base_color=(0.32, 0.36, 0.46), name_prefix="Crowd"):
    """Molecular crowding: dozens of generic blobs drifting in the cytosol, in muted
    colours, so the space reads as dense and alive without competing with the real
    structures. They are procedural shapes, not structures, to keep render time low."""
    rnd = random.Random(seed)
    blobs = []
    for i in range(count):
        pos = (
            rnd.uniform(*bounds[0]),
            rnd.uniform(*bounds[1]),
            rnd.uniform(*bounds[2]),
        )
        radius = rnd.uniform(0.1, 0.3)
        bpy.ops.mesh.primitive_ico_sphere_add(radius=radius, location=pos, subdivisions=2)
        blob = bpy.context.active_object
        blob.name = f"{name_prefix}_{i+1}"
        blob.scale = (rnd.uniform(0.7, 1.4), rnd.uniform(0.7, 1.4), rnd.uniform(0.7, 1.4))

        displace = blob.modifiers.new("Bump", "DISPLACE")
        tex = bpy.data.textures.new(f"{name_prefix}Noise{i}", type="CLOUDS")
        tex.noise_scale = rnd.uniform(0.4, 0.8)
        displace.texture = tex
        displace.strength = 0.14

        color = tuple(max(0.05, min(0.95, ch + rnd.uniform(-0.05, 0.05))) for ch in base_color)
        mat = make_material(f"Mat_{name_prefix}_{i+1}", color, roughness=0.55, subsurface=0.2)
        blob.data.materials.append(mat)
        bpy.ops.object.shade_smooth()

        add_brownian_jitter(blob, total_frames, seed=seed * 137 + i, amplitude_deg=18, cycles=rnd.randint(1, 3))

        drift = (rnd.uniform(-0.4, 0.4), rnd.uniform(-0.4, 0.4), rnd.uniform(-0.25, 0.25))
        blob.keyframe_insert(data_path="location", frame=1)
        blob.location = (pos[0] + drift[0], pos[1] + drift[1], pos[2] + drift[2])
        blob.keyframe_insert(data_path="location", frame=total_frames)

        blobs.append(blob)
    return blobs


def add_lipid_bilayer(membrane_obj, count=900, seed=7, head_color=(0.35, 0.55, 0.85), tail_color=(0.3, 0.45, 0.8)):
    """Covers both faces of a solidified membrane with individual phospholipids aligned
    to the surface normal: thin, dense tails so the layer reads as one continuous sheet."""
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.045, location=(0, 0, 0.02), segments=7, ring_count=5)
    head = bpy.context.active_object
    head.data.materials.append(make_material("Mat_LipidHead", head_color, roughness=0.25, subsurface=0.35))

    tails = []
    for dx in (-0.012, 0.012):
        bpy.ops.mesh.primitive_cylinder_add(radius=0.006, depth=0.13, location=(dx, 0, -0.045), vertices=5)
        tail = bpy.context.active_object
        tail.data.materials.append(make_material("Mat_LipidTail", tail_color, roughness=0.4))
        tails.append(tail)

    bpy.ops.object.select_all(action="DESELECT")
    head.select_set(True)
    for t in tails:
        t.select_set(True)
    bpy.context.view_layer.objects.active = head
    bpy.ops.object.join()
    lipid = bpy.context.active_object
    lipid.name = f"{membrane_obj.name}_Phospholipid"
    lipid.hide_render = True
    lipid.hide_viewport = True

    depsgraph = bpy.context.evaluated_depsgraph_get()
    membrane_eval = membrane_obj.evaluated_get(depsgraph)
    mesh_eval = membrane_eval.to_mesh()
    mesh_eval.calc_loop_triangles()

    flat_faces = [p for p in mesh_eval.polygons if abs(p.normal.z) > 0.5]
    rnd = random.Random(seed)
    rnd.shuffle(flat_faces)
    n = min(count, len(flat_faces))

    coll = bpy.data.collections.new(f"{membrane_obj.name}_Bilayer")
    bpy.context.scene.collection.children.link(coll)

    lipids = []
    for i, poly in enumerate(flat_faces[:n]):
        center = membrane_obj.matrix_world @ poly.center
        normal = (membrane_obj.matrix_world.to_3x3() @ poly.normal).normalized()

        dup = bpy.data.objects.new(f"{membrane_obj.name}_Lipid_{i}", lipid.data)
        coll.objects.link(dup)
        jitter = Vector((rnd.uniform(-0.03, 0.03), rnd.uniform(-0.03, 0.03), rnd.uniform(-0.015, 0.015)))
        dup.location = center + jitter

        up = Vector((0, 0, 1))
        quat = up.rotation_difference(normal)
        spin = Quaternion(normal, rnd.uniform(0, 2 * math.pi))
        tilt_axis = Vector((rnd.uniform(-1, 1), rnd.uniform(-1, 1), 0)).normalized()
        tilt = Quaternion(tilt_axis, math.radians(rnd.uniform(0, 22)))
        quat = tilt @ quat
        dup.rotation_mode = "QUATERNION"
        dup.rotation_quaternion = spin @ quat

        s = rnd.uniform(0.65, 1.35)
        dup.scale = (s, s, s)
        lipids.append(dup)

    membrane_eval.to_mesh_clear()
    return lipids


def setup_world_dark():
    """Dark studio background so the lit molecules stand out (WEHI/HHMI style)."""
    world = bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    nodes = world.node_tree.nodes
    links = world.node_tree.links
    bg = nodes["Background"]

    gradient = nodes.new("ShaderNodeTexGradient")
    gradient.gradient_type = "SPHERICAL"
    color_ramp = nodes.new("ShaderNodeValToRGB")
    color_ramp.color_ramp.elements[0].color = (0.004, 0.006, 0.014, 1.0)
    color_ramp.color_ramp.elements[1].color = (0.03, 0.035, 0.055, 1.0)

    coord = nodes.new("ShaderNodeTexCoord")
    links.new(coord.outputs["Generated"], gradient.inputs["Vector"])
    links.new(gradient.outputs["Color"], color_ramp.inputs["Fac"])
    links.new(color_ramp.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 1.0
    return world


def setup_render_settings(total_frames, filename_prefix, engine="EEVEE", cycles_samples=128):
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = total_frames
    scene.render.fps = FPS
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100

    if engine == "CYCLES":
        scene.render.engine = "CYCLES"
        scene.cycles.samples = cycles_samples
        scene.cycles.use_denoising = True
        scene.cycles.device = "CPU"
    else:
        scene.render.engine = "BLENDER_EEVEE"
        scene.eevee.use_raytracing = True
        scene.eevee.taa_render_samples = 96
        scene.eevee.use_shadows = True

    scene.render.use_motion_blur = True
    scene.render.motion_blur_shutter = 0.4

    scene.render.filepath = os.path.join(OUTPUT_DIR, filename_prefix + "_")
    scene.render.image_settings.file_format = "PNG"

    setup_compositor()


def setup_compositor():
    """Post-processing in Blender's compositor: soft glow, colour balance, contrast and
    a vignette."""
    scene = bpy.context.scene
    scene.use_nodes = True
    tree = scene.compositing_node_group
    if tree is None:
        tree = bpy.data.node_groups.new("Compositing Nodetree", "CompositorNodeTree")
        scene.compositing_node_group = tree
    tree.nodes.clear()

    render_layers = tree.nodes.new("CompositorNodeRLayers")

    glare = tree.nodes.new("CompositorNodeGlare")
    glare.inputs["Type"].default_value = "Fog Glow"
    glare.inputs["Quality"].default_value = "Medium"
    glare.inputs["Threshold"].default_value = 0.75
    glare.inputs["Size"].default_value = 7
    glare.inputs["Strength"].default_value = 0.6

    color_balance = tree.nodes.new("CompositorNodeColorBalance")
    color_balance.inputs["Type"].default_value = "Lift/Gamma/Gain"
    # inputs come in VALUE + RGBA pairs with the same name; the RGBA is the second
    color_balance.inputs[4].default_value = (0.99, 0.99, 1.01, 1.0)  # Lift RGBA
    color_balance.inputs[6].default_value = (1.02, 1.0, 1.0, 1.0)    # Gamma RGBA
    color_balance.inputs[8].default_value = (1.05, 1.03, 1.0, 1.0)   # Gain RGBA

    contrast = tree.nodes.new("CompositorNodeBrightContrast")
    contrast.inputs["Brightness"].default_value = 2
    contrast.inputs["Contrast"].default_value = 14

    vignette_ramp = tree.nodes.new("CompositorNodeEllipseMask")
    vignette_ramp.inputs["Position"].default_value = (0.5, 0.5)
    vignette_ramp.inputs["Size"].default_value = (1.15, 1.15)
    vignette_blur = tree.nodes.new("CompositorNodeBlur")
    vignette_blur.inputs["Size"].default_value = (200, 200)
    vignette_mix = tree.nodes.new("ShaderNodeMix")
    vignette_mix.data_type = "RGBA"
    vignette_mix.blend_type = "MULTIPLY"
    vignette_mix.inputs[0].default_value = 0.35  # factor (VALUE)
    mix_a = next(s for s in vignette_mix.inputs if s.name == "A" and s.type == "RGBA")
    mix_b = next(s for s in vignette_mix.inputs if s.name == "B" and s.type == "RGBA")
    mix_result = next(o for o in vignette_mix.outputs if o.name == "Result" and o.type == "RGBA")

    if not any(i.name == "Image" and i.in_out == "OUTPUT" for i in tree.interface.items_tree):
        tree.interface.new_socket(name="Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    composite = tree.nodes.new("NodeGroupOutput")

    links = tree.links
    links.new(render_layers.outputs["Image"], glare.inputs["Image"])
    links.new(glare.outputs["Image"], color_balance.inputs["Image"])
    links.new(color_balance.outputs["Image"], contrast.inputs["Image"])
    links.new(vignette_ramp.outputs["Mask"], vignette_blur.inputs["Image"])
    links.new(contrast.outputs["Image"], mix_a)
    links.new(vignette_blur.outputs["Image"], mix_b)
    links.new(mix_result, composite.inputs["Image"])


def render_still(frame, filename):
    scene = bpy.context.scene
    scene.frame_set(frame)
    scene.render.filepath = os.path.join(OUTPUT_DIR, filename)
    bpy.ops.render.render(write_still=True)


def render_frame_range(start, end, prefix):
    """Render a range of frames to numbered PNGs, so a long render can be split
    across several Blender runs and encoded afterwards with encode_png_sequence()."""
    scene = bpy.context.scene
    scene.frame_start = start
    scene.frame_end = end
    scene.render.image_settings.media_type = "IMAGE"
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = os.path.join(OUTPUT_DIR, f"{prefix}_frame_")
    bpy.ops.render.render(animation=True)


def encode_png_sequence(prefix, frame_start, frame_end, fps, output_filename):
    """Join rendered PNG frames into an MP4 with Blender's sequencer (encoding only,
    no re-render)."""
    scene = bpy.data.scenes.new("EncodeScene")
    bpy.context.window.scene = scene
    scene.frame_start = frame_start
    scene.frame_end = frame_end
    scene.render.fps = fps

    scene.sequence_editor_create()
    seq = scene.sequence_editor
    first_frame_path = os.path.join(OUTPUT_DIR, f"{prefix}_frame_{frame_start:04d}.png")
    strip = seq.strips.new_image(
        name="frames", filepath=first_frame_path, channel=1, frame_start=frame_start
    )
    for f in range(frame_start + 1, frame_end + 1):
        strip.elements.append(f"{prefix}_frame_{f:04d}.png")

    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.image_settings.media_type = "VIDEO"
    scene.render.image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    scene.render.filepath = os.path.join(OUTPUT_DIR, output_filename)
    bpy.ops.render.render(animation=True, scene=scene.name)


def render_animation(filename):
    scene = bpy.context.scene
    scene.render.image_settings.media_type = "VIDEO"
    scene.render.image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    scene.render.filepath = os.path.join(OUTPUT_DIR, filename)
    bpy.ops.render.render(animation=True)


def add_wehi_lighting(key_loc, target, key_energy=400, key_size=2.5):
    """WEHI / Drew Berry style lighting: one strong warm key light for clear volume,
    a weak cool fill (8 % of the key) and a subtle cool rim to separate the subject
    from the dark background. The ratios matter more than the absolute values."""
    key_dir = Vector(target) - Vector(key_loc)

    bpy.ops.object.light_add(type="AREA", location=key_loc)
    key = bpy.context.active_object
    key.name = "KeyLight"
    key.data.energy = key_energy
    key.data.size = key_size
    key.data.color = (1.0, 0.93, 0.8)
    key.rotation_euler = key_dir.to_track_quat("-Z", "Y").to_euler()

    fill_loc = (-key_loc[0] * 0.5, key_loc[1] * 0.3, key_loc[2] * 0.15)
    bpy.ops.object.light_add(type="AREA", location=fill_loc)
    fill = bpy.context.active_object
    fill.name = "FillLight"
    fill.data.energy = key_energy * 0.08
    fill.data.size = key_size * 2
    fill.data.color = (0.55, 0.68, 1.0)
    fill.rotation_euler = (Vector(target) - Vector(fill_loc)).to_track_quat("-Z", "Y").to_euler()

    rim_loc = (target[0] * 0.3, target[1] - (key_loc[1] - target[1]), target[2] + 2.5)
    bpy.ops.object.light_add(type="AREA", location=rim_loc)
    rim = bpy.context.active_object
    rim.name = "RimLight"
    rim.data.energy = key_energy * 0.18
    rim.data.size = key_size
    rim.data.color = (0.6, 0.8, 1.0)
    rim.rotation_euler = (Vector(target) - Vector(rim_loc)).to_track_quat("-Z", "Y").to_euler()

    return key, fill, rim
