"""Pinned source binding and source-to-Core assembly owners."""


def build_assembly(task_input: dict, manifest: dict) -> dict:
    return {
        "native_problem": task_input["native_reference"]["problem_class"],
        "native_arena_xml": task_input["native_reference"]["active_scene_xml"],
        "source_manifest_id": manifest["manifest_id"],
        "asset_closure": manifest["asset_closure"],
        "source_consumption": "Not run in a Core importer; installation proves source bytes only.",
        "factory_owner": "task_env/registry.py::make_env and existing selected candidate registration",
        "task_source_owner": "task_env/environment/task_source.py and task_env/assembly/source.py::TaskSceneSource",
        "reference_owner": "task_env/assembly/references.py::resolve_task_references",
        "runtime_source_owner": "task_env/runtime/sessions/source.py::RuntimeSource and ExecutionSourceReceiptV1",
        "core_native_admission_ready": False,
    }
