"""Advanced native-pairing camera capture, additive to existing UI renderers."""
from .api import CameraRenderSession, create_camera_session, render_manifest, admit_render
from .source import CameraCaptureIdentityV1, CameraRenderSource, TriangleMesh

__all__ = [
    'CameraCaptureIdentityV1', 'CameraRenderSession', 'CameraRenderSource',
    'TriangleMesh', 'create_camera_session', 'render_manifest', 'admit_render',
]
