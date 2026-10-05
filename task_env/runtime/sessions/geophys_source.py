"""The only conversion of a neutral MJCF description to GeoPhys SceneSource."""
from ...assembly.source import TaskSceneSource


def native_scene_source(source: TaskSceneSource):
    from scene import SceneSource
    return SceneSource.mjcf_string(source.xml, base_dir=source.base_dir, label=source.source_id)


class GeoPhysSourceComposer:
    adapter_name = 'task_env_neutral_mjcf_bridge_v0'

    def __init__(self, source):
        self._source = source

    def build_scene_source(self, composition, agents):
        return native_scene_source(self._source), self.adapter_name

    def build_scene_model(self, imported_scene, composition):
        return imported_scene.build_rigid_scene_model(use_imported_meshes=False)
