"""Go2 MJCF composition and stable scene references."""

from __future__ import annotations

from pathlib import Path
import hashlib
import xml.etree.ElementTree as ET

from ...environment import AssetManifest, ReferenceSpec
from ...registry import register_scene
from ...robots.go2 import (
    GO2_ACTUATOR_NAMES,
    GO2_ASSET_ROOT,
    GO2_BODY_NAMES,
    GO2_FOOT_GEOM_NAMES,
    GO2_JOINT_NAMES,
    GO2_MJCF_PATH,
    GO2_SITE_NAMES,
)
from ..worlds.base import BaseSceneBuilder


GO2_SCENE_UID = "go2-walk-v1"
GO2_GROUND_GEOM_NAME = "go2_ground"
GO2_EMPTY_FOOT_BODY_NAMES = frozenset(
    {"FL_foot", "FR_foot", "RL_foot", "RR_foot"}
)


def canonical_xml_digest() -> str:
    """Digest the unmodified canonical menagerie XML used by composition."""

    return hashlib.sha256(GO2_MJCF_PATH.read_bytes()).hexdigest()


def _disable_go2_self_collisions(root: ET.Element) -> None:
    """Encode Unitree's ``self_collisions=1`` asset policy in MJCF.

    Isaac Gym's Go2 asset disables robot self-collision.  MuJoCo does not
    infer that Isaac asset flag, and GeoPhys otherwise sees overlapping
    leg/base geoms as ordinary body contacts.  Keep the policy at the private
    asset boundary by excluding every pair of canonical robot bodies while
    leaving the separately-added ground/support geom collidable.
    """

    contact = root.find("contact")
    if contact is None:
        contact = ET.SubElement(root, "contact")
    existing = {
        (str(elem.get("body1", "")), str(elem.get("body2", "")))
        for elem in contact.findall("exclude")
    }
    for index, body_a in enumerate(GO2_BODY_NAMES):
        for body_b in GO2_BODY_NAMES[index + 1 :]:
            pair = (body_a, body_b)
            if pair in existing or (body_b, body_a) in existing:
                continue
            ET.SubElement(contact, "exclude", {"body1": body_a, "body2": body_b})


def _remove_empty_foot_bodies(root: ET.Element) -> None:
    """Remove visual-only empty foot bodies from the TaskEnv MJCF copy.

    The current menagerie XML adds four named bodies below the calf links,
    but each is an empty transform with no joint, geom, site, or inertial.
    TaskEnv's fixed-topology articulated response requires every non-root body
    route to own exactly one hinge/slide joint.  The foot collision geoms are
    still attached to the calf bodies, so removing these empty wrappers does
    not change the TaskEnv physical model.  The standalone MuJoCo evaluator
    does not call this helper and retains the canonical XML unchanged.
    """

    for parent in root.iter():
        for child in list(parent):
            if child.tag != "body" or child.get("name") not in GO2_EMPTY_FOOT_BODY_NAMES:
                continue
            if list(child):
                raise ValueError(
                    f"Go2 foot body {child.get('name')!r} is no longer empty; "
                    "update the TaskEnv asset adaptation before removing it"
                )
            parent.remove(child)


def _go2_xml_with_support(*, platform_box: bool = False) -> str:
    root = ET.parse(GO2_MJCF_PATH).getroot()
    compiler = root.find("compiler")
    if compiler is None:
        compiler = ET.SubElement(root, "compiler")
    compiler.set("meshdir", str((GO2_ASSET_ROOT / "assets").resolve()).replace("\\", "/"))
    option = root.find("option")
    if option is None:
        option = ET.SubElement(root, "option")
    option.set("timestep", "0.005")
    option.set("gravity", "0 0 -9.81")
    option.set("integrator", "implicitfast")
    # The canonical menagerie asset may contain MuJoCo sensor declarations
    # (joint position/velocity, actuator force and IMU sensors).  TaskEnv's
    # static-template runtime reads the compiled state arrays directly and
    # does not expose MuJoCo sensor buffers; keeping these declarations would
    # make an otherwise compatible Go2 scene fail the capability guard.  The
    # standalone MuJoCo evaluator still loads the canonical XML unchanged.
    sensor = root.find("sensor")
    if sensor is not None:
        root.remove(sensor)
    _remove_empty_foot_bodies(root)
    _disable_go2_self_collisions(root)
    worldbody = root.find("worldbody")
    if worldbody is None:
        raise KeyError("Go2 MJCF does not contain worldbody")
    if worldbody.find(f"geom[@name='{GO2_GROUND_GEOM_NAME}']") is None:
        support = {
            "name": GO2_GROUND_GEOM_NAME,
            "type": "box" if platform_box else "plane",
            "size": "20 20 0.005" if platform_box else "25 25 0.1",
            "friction": "1.0 0.02 0.01",
            "condim": "3",
            "contype": "1",
            "conaffinity": "1",
            "rgba": "0.35 0.38 0.42 1",
        }
        if platform_box:
            # Keep the diagnostic box as a real static body.  GeoPhys treats
            # the worldbody's direct plane/hfield geom as the analytic ground
            # configuration, but does not lower an arbitrary top-level box
            # into the rigid-body geom table.  A no-joint body preserves the
            # intended body-body collision route while remaining immovable.
            # A literal zero-height geom is invalid/ill-conditioned in both
            # MuJoCo and the GeoPhys convex compiler.
            support["pos"] = "0 0 0"
            platform = ET.SubElement(
                worldbody,
                "body",
                {"name": "go2_support_platform", "pos": "0 0 -0.005"},
            )
            ET.SubElement(platform, "geom", support)
        else:
            ET.SubElement(worldbody, "geom", support)
    return ET.tostring(root, encoding="unicode")


def _go2_xml_with_ground() -> str:
    return _go2_xml_with_support(platform_box=False)


def _go2_xml_with_platform_box() -> str:
    """Return a private diagnostic scene with a thin static box support."""

    return _go2_xml_with_support(platform_box=True)


class Go2WalkSceneComposer:
    def build_scene_source(self, composition, agents):
        if tuple(agent.uid for agent in agents) != ("go2-v1",):
            raise ValueError("Go2 walk scene requires exactly one go2-v1 agent")
        from scene import SceneSource

        return (
            SceneSource.mjcf_string(
                _go2_xml_with_ground(),
                base_dir=GO2_ASSET_ROOT,
                label="task-env-go2-menagerie-v1",
            ),
            "task_env_go2_walk_menagerie_v1",
        )


class Go2PlatformBoxSceneComposer(Go2WalkSceneComposer):
    """Private diagnostic composer; it is not a public runtime capability."""

    def build_scene_source(self, composition, agents):
        if tuple(agent.uid for agent in agents) != ("go2-v1",):
            raise ValueError("Go2 platform scene requires exactly one go2-v1 agent")
        from scene import SceneSource

        return (
            SceneSource.mjcf_string(
                _go2_xml_with_platform_box(),
                base_dir=GO2_ASSET_ROOT,
                label="task-env-go2-menagerie-platform-box-diagnostic-v1",
            ),
            "task_env_go2_walk_platform_box_diagnostic_v1",
        )


@register_scene(GO2_SCENE_UID)
class Go2WalkSceneBuilder(BaseSceneBuilder):
    uid = GO2_SCENE_UID

    def asset_manifest(self) -> AssetManifest:
        return AssetManifest(
            owner_uid=self.uid,
            asset_kind="agent_scene_with_ground",
            mjcf_sources=(GO2_MJCF_PATH,),
            asset_roots=(GO2_ASSET_ROOT,),
            asset_version="mujoco-menagerie-unitree-go2-ground-self-collision-off-v2",
        )

    def reference_spec(self) -> ReferenceSpec:
        return ReferenceSpec(
            body_names=GO2_BODY_NAMES,
            joint_names=GO2_JOINT_NAMES,
            site_names=GO2_SITE_NAMES,
            geom_names=(*GO2_FOOT_GEOM_NAMES, GO2_GROUND_GEOM_NAME),
            actuator_names=GO2_ACTUATOR_NAMES,
        )


__all__ = [
    "GO2_GROUND_GEOM_NAME",
    "GO2_SCENE_UID",
    "canonical_xml_digest",
    "Go2WalkSceneBuilder",
    "Go2WalkSceneComposer",
    "Go2PlatformBoxSceneComposer",
]
