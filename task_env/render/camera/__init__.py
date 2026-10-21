"""Advanced native-pairing camera capture, additive to existing UI renderers."""
from .api import (
    CameraRenderSession, create_camera_session, render_manifest, admit_render,
    D03_DYNAMIC_PROFILE, D03_PHYSICS_PROFILE, admit_dynamic_camera,
    D04_DYNAMIC_PROFILE, D04_ENTITY_SEGMENTATION_PROFILE,
    create_dynamic_camera_session, dynamic_render_manifest,
    dynamic_rgbd_render_manifest, dynamic_entity_instance_segmentation_manifest,
)
from .source import (
    CameraCaptureIdentityV1, CameraRenderSource, TriangleMesh,
    DynamicCameraRenderSourceV1, DynamicRenderFrameBindingV1,
    DynamicRenderJointBindingV1, RenderStateProjectionV1,
    RenderStateSyncReceiptV1, RenderVisualInstanceBindingV1,
    project_render_state_v1,
)

__all__ = [
    'CameraCaptureIdentityV1', 'CameraRenderSession', 'CameraRenderSource',
    'DynamicCameraRenderSourceV1', 'DynamicRenderFrameBindingV1',
    'DynamicRenderJointBindingV1', 'RenderStateProjectionV1',
    'RenderStateSyncReceiptV1', 'RenderVisualInstanceBindingV1',
    'TriangleMesh', 'create_camera_session', 'render_manifest', 'admit_render',
    'D03_DYNAMIC_PROFILE', 'D03_PHYSICS_PROFILE', 'D04_DYNAMIC_PROFILE',
    'D04_ENTITY_SEGMENTATION_PROFILE',
    'admit_dynamic_camera', 'create_dynamic_camera_session',
    'dynamic_render_manifest', 'dynamic_rgbd_render_manifest',
    'dynamic_entity_instance_segmentation_manifest',
    'project_render_state_v1',
]
