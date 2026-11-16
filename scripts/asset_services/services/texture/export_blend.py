# 作用：导入官方 GLB 并保存自包含的 Blender 查看文件。
# 输入输出：result.json、目标 blend 路径 -> 米制 Z-up、图片已内嵌的 blend。
import json
from pathlib import Path
import sys

import bpy
from mathutils import Vector


def main():
    """通过 Blender 的 glTF 导入器接入几何、UV 和材质，并设置查看视角。

    Returns:
        None: 保存包含官方产物的可查看文件，不执行重拓扑或重新烘焙。
    """
    result_path, output_path = map(Path, sys.argv[sys.argv.index('--') + 1:])
    result = json.loads(result_path.read_text(encoding='utf-8'))
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    bpy.ops.import_scene.gltf(filepath=result['artifacts']['glb'])
    objects = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH']
    if not objects:
        raise RuntimeError('GLB 中没有可查看网格')
    bpy.ops.file.pack_all()
    corners = [obj.matrix_world @ Vector(corner) for obj in objects for corner in obj.bound_box]
    minimum = Vector(tuple(min(p[i] for p in corners) for i in range(3)))
    maximum = Vector(tuple(max(p[i] for p in corners) for i in range(3)))
    center, radius = (minimum + maximum) / 2, (maximum - minimum).length
    bpy.context.scene.unit_settings.system = 'METRIC'
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                space = area.spaces.active
                space.shading.type = 'MATERIAL'
                space.shading.use_scene_world = False
                space.shading.use_scene_lights = False
                space.overlay.show_overlays = False
                space.region_3d.view_location = center
                space.region_3d.view_distance = radius * 1.7
                space.region_3d.view_rotation = Vector((1, -3, 1.5)).to_track_quat('Z', 'Y')
                space.clip_start = max(radius / 10000, 0.00001)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(output_path))


if __name__ == '__main__':
    main()
