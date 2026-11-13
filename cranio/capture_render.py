"""Fixed background-Blender renderer for reviewed neutral export bundles."""
from pathlib import Path
import sys

# Invoked as a script by a fixed add-on path, never by a path embedded in data.
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import bpy
import numpy as np
from mathutils import Matrix

from cranio import capture_plan as core
from cranio.record import canonical_bytes, _digest
from cranio.export import atomic_text


def render_bundle(report_path, bundle_dir, output_dir, *, resolution=1024, bar_mm=50., samples=16):
    vertices, triangles, recipe, pinned = core.load_inputs(report_path, bundle_dir,
        resolution=resolution, bar_mm=bar_mm, samples=samples)
    out = Path(output_dir)
    if out.exists() or out.is_symlink():
        raise ValueError('Capture output directory exists; choose a new destination')
    out.mkdir(parents=True, exist_ok=False)
    scene = bpy.data.scenes.new('GNM isolated capture')
    objects, data, materials = [], [], []
    world = None
    def obj(name, block):
        value = bpy.data.objects.new(name, block)
        scene.collection.objects.link(value)
        objects.append(value)
        data.append(block)
        return value
    def material(name, color, emission=False):
        value = bpy.data.materials.new(name)
        materials.append(value)
        value.use_nodes = True
        nodes = value.node_tree.nodes
        if emission:
            nodes.clear()
            shader = nodes.new('ShaderNodeEmission')
            shader.inputs['Color'].default_value = color
            output = nodes.new('ShaderNodeOutputMaterial')
            value.node_tree.links.new(shader.outputs[0], output.inputs['Surface'])
        else:
            shader = nodes.get('Principled BSDF')
            shader.inputs['Base Color'].default_value = color
            shader.inputs['Roughness'].default_value = .7
        return value
    try:
        scene.render.engine = 'CYCLES'
        scene.cycles.device = 'CPU'
        scene.cycles.samples = samples
        scene.cycles.use_denoising = False
        scene.cycles.seed = 0
        scene.render.resolution_x = scene.render.resolution_y = resolution
        scene.render.resolution_percentage = 100
        scene.render.pixel_aspect_x = scene.render.pixel_aspect_y = 1
        scene.render.image_settings.file_format = 'PNG'
        scene.render.image_settings.color_mode = 'RGB'
        scene.render.image_settings.color_depth = '8'
        scene.render.film_transparent = False
        scene.view_settings.view_transform = 'Standard'
        scene.view_settings.look = 'None'
        scene.view_settings.exposure = 0
        scene.view_settings.gamma = 1
        scene.unit_settings.system, scene.unit_settings.scale_length = 'METRIC', .001
        world = bpy.data.worlds.new('GNM capture white world')
        world.use_nodes = True
        world.node_tree.nodes['Background'].inputs['Color'].default_value = (1, 1, 1, 1)
        world.node_tree.nodes['Background'].inputs['Strength'].default_value = .8
        scene.world = world
        gray = material('GNM capture gray', (.5, .5, .5, 1))
        black = material('GNM capture annotation', (0, 0, 0, 1), emission=True)
        mesh = bpy.data.meshes.new('GNM saved neutral')
        mesh.from_pydata(vertices.tolist(), [], triangles.tolist())
        mesh.update()
        face = obj('GNM saved neutral', mesh)
        mesh.materials.append(gray)
        for polygon in mesh.polygons:
            polygon.use_smooth = True
        camera = obj('GNM orthographic capture', bpy.data.cameras.new('GNM capture camera'))
        camera.data.type = 'ORTHO'
        scene.camera = camera
        lights = []
        for name, strength in (('Key', 3.), ('Fill', 1.)):
            light = obj(name, bpy.data.lights.new(name, 'SUN'))
            light.data.energy = strength
            lights.append(light)
        bar_mesh = bpy.data.meshes.new('GNM scale bar')
        bar_mesh.from_pydata([(0, 0, 0)]*4, [], [(0, 1, 2, 3)])
        bar = obj('GNM metric scale', bar_mesh)
        bar_mesh.materials.append(black)
        texts = []
        for name in ('Mode', 'View', 'Scale'):
            font = bpy.data.curves.new('GNM '+name, 'FONT')
            font.align_x = 'LEFT'
            font.materials.append(black)
            texts.append(obj('GNM '+name, font))
        short_label = ('ILLUSTRATIVE / NOT VALIDATED' if recipe['export_mode'] == 'illustrative' else
                       'SCIENTIFIC / OVERRIDE RECORDED' if recipe['check_gate']['status'] == 'overridden'
                       else 'SCIENTIFIC / NOT VALIDATED')
        origin = np.asarray(recipe['frame']['geometry']['origin_mm'])
        outputs = {}
        for view in recipe['views']:
            core.assert_unchanged(pinned)
            basis = np.asarray(view['camera_to_world_rotation'])
            scale, z = view['ortho_scale_mm'], view['annotation_plane_offset_mm']
            camera.matrix_world = Matrix(np.block([[basis, np.asarray(view['camera_location_mm'])[:, None]],
                                                    [np.zeros((1, 3)), np.ones((1, 1))]]).tolist())
            camera.data.ortho_scale = scale
            camera.data.clip_start, camera.data.clip_end = view['clip_start_mm'], view['clip_end_mm']
            for light, direction in zip(lights, ((.6, 1., .6), (-.6, .6, .6))):
                location = origin+basis@np.asarray(direction)*recipe['bounding_radius_mm']*4
                light.location = location.tolist()
                light.rotation_mode = 'QUATERNION'
                light.rotation_quaternion = (Matrix.Translation(tuple(origin)).translation-light.location).to_track_quat('-Z', 'Y')
            x, y = -.4*scale, -.42*scale
            bar_points = np.array([[x, y, z], [x+bar_mm, y, z],
                                   [x+bar_mm, y+.008*scale, z], [x, y+.008*scale, z]])
            for vertex, point in zip(bar_mesh.vertices, origin+bar_points@basis.T):
                vertex.co = point.tolist()
            bar_mesh.update()
            for text, body, position in zip(texts,
                (short_label, view['name'].upper()+' | anatomical superior up', f'{bar_mm:g} mm'),
                ((-.4, .455), (-.4, .425), (-.4, -.465))):
                text.data.body, text.data.size = body, .018*scale
                text.rotation_mode = 'QUATERNION'
                text.rotation_quaternion = Matrix(basis.tolist()).to_quaternion()
                text.location = (origin+basis@np.array([position[0]*scale, position[1]*scale, z])).tolist()
            path = out/(view['name']+'.png')
            if path.exists() or path.is_symlink():
                raise ValueError('Capture image already exists')
            scene.render.filepath = str(path)
            bpy.ops.render.render(write_still=True, scene=scene.name)
            if not path.is_file():
                raise ValueError('Renderer did not write the expected PNG')
            outputs[path.name] = dict(sha256=_digest(path.read_bytes()))
        recipe.update(kind='standardized_saved_fit_captures', status='completed', files=outputs,
            renderer=dict(blender=bpy.app.version_string, engine='CYCLES', device='CPU', samples=samples,
                          seed=0, denoising=False, view_transform='Standard', smooth_shading=True,
                          textures=False, material='neutral_gray'),
            implementation_sha256=dict(plan=_digest(Path(core.__file__).read_bytes()), renderer=_digest(Path(__file__).read_bytes())))
        def validate(_):
            core.assert_unchanged(pinned)
            if (out/'capture_manifest.json').exists() or (out/'capture_manifest.json').is_symlink():
                raise ValueError('Capture completion file already exists')
            if any(_digest((out/name).read_bytes()) != row['sha256'] for name, row in outputs.items()):
                raise ValueError('Capture image changed before completion')
        with atomic_text(out/'capture_manifest.json', validate=validate) as stream:
            stream.write(canonical_bytes(recipe).decode('utf-8'))
        return out/'capture_manifest.json'
    finally:
        for value in objects:
            bpy.data.objects.remove(value, do_unlink=True)
        bpy.data.scenes.remove(scene)
        for block in data:
            if block.users == 0:
                # Each block was created here; remove it through its collection.
                collection = (bpy.data.meshes if isinstance(block, bpy.types.Mesh) else
                              bpy.data.cameras if isinstance(block, bpy.types.Camera) else
                              bpy.data.lights if isinstance(block, bpy.types.Light) else bpy.data.curves)
                collection.remove(block)
        for value in materials:
            if value.users == 0:
                bpy.data.materials.remove(value)
        if world is not None and world.users == 0:
            bpy.data.worlds.remove(world)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', required=True)
    parser.add_argument('--bundle', required=True)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--resolution', type=int, default=1024)
    parser.add_argument('--bar-mm', type=float, default=50.)
    parser.add_argument('--samples', type=int, default=16)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    render_bundle(args.report, args.bundle, args.output_dir,
                  resolution=args.resolution, bar_mm=args.bar_mm, samples=args.samples)
    print('GNM_CAPTURE_RENDER_COMPLETE')


if __name__ == '__main__':
    main()
