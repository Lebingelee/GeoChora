"""Versioned Panda fixed-source identities and strict historical admission."""

import hashlib
import xml.etree.ElementTree as ET

SOURCE_REVISION = "b846dd12bc459d776cccb3dee0b1d02acbf7a9c7"
SOURCE_LICENSE_ID = "Apache-2.0"

R06B_ORDER_RECIPE_ID = "r06b-order-v1"
R06B_ORDER_ASSET_VERSION = "menagerie-b846dd12-r06b-order-v1"
R06B_ORDER_SOURCE_REFERENCES = {
    "panda-arm": "derived:menagerie:b846dd12bc459d776cccb3dee0b1d02acbf7a9c7/franka_emika_panda/panda_nohand.xml#r06b-order-v1",
    "panda-hand": "derived:menagerie:b846dd12bc459d776cccb3dee0b1d02acbf7a9c7/franka_emika_panda/hand.xml#r06b-order-v1",
}
_BASE_SOURCE_SHA256 = {
    "panda-arm": "e7090a5e2384b18a223ef532d98bf914f7f9a6b74dc8bc9f74c8291201074071",
    "panda-hand": "d2a6539d0fd7c55c75c14f11c78f04505ee33f31d93e6112e3ad7120e5ee786a",
}
_BASE_CANONICAL_SHA256 = {
    "panda-arm": "0288eb09c30232117abe6e0d2a80771953ed5bde38e31830572a83f4eca1dfa4",
    "panda-hand": "031c7c49b42230b19dfb3a12eacf022ba3e6a9f552af167c1cb1906c61e7a41b",
}
R06B_ORDER_SOURCE_SHA256 = {
    "panda-arm": "e556ae24843a6ef080c604b544e9f08ff531d036f414b7544dc1c6d7e44b3270",
    "panda-hand": "443f6d9ffbb7fc6ab27fbc8c493ab2b83a8dd2a03a431dac93eae9101eda9c29",
}
_SOURCE_JOINT_TRAVERSAL = {
    "r03b-exact": {
        "panda-arm": tuple(f"joint{index}" for index in range(1, 8)),
        "panda-hand": ("finger_joint1", "finger_joint2"),
    },
    R06B_ORDER_RECIPE_ID: {
        "panda-arm": tuple(f"joint{index}" for index in range(1, 8)),
        "panda-hand": ("finger_joint2", "finger_joint1"),
    },
}


def _recipe_xml_root(xml: str) -> ET.Element:
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    return ET.fromstring(xml, parser=parser)


def _reverse_recipe_children(parent: ET.Element, predicate) -> None:
    original = list(parent)
    indexes = [
        index for index, child in enumerate(original)
        if isinstance(child.tag, str) and predicate(child)
    ]
    selected = [original[index] for index in indexes]
    tails = [child.tail for child in selected]
    for index, child, tail in zip(indexes, reversed(selected), tails, strict=True):
        # Element tails are source formatting at a sibling position, not part of
        # the moved MJCF element. Keep them in their original positions.
        child.tail = tail
        parent[index] = child


def _apply_r06b_order_recipe(arm: ET.Element, hand: ET.Element) -> None:
    actuators = arm.find("actuator")
    if actuators is None:
        raise ValueError("R06b order recipe requires the Arm actuator section")
    _reverse_recipe_children(
        actuators, lambda node: (node.get("name") or "").startswith("actuator"),
    )
    hand_root = hand.find("./worldbody/body[@name='hand']")
    if hand_root is None:
        raise ValueError("R06b order recipe requires the Hand root body")
    wanted = {"left_finger", "right_finger"}
    found = [
        child for child in list(hand_root)
        if child.tag == "body" and child.get("name") in wanted
    ]
    if len(found) != 2 or {child.get("name") for child in found} != wanted:
        raise ValueError("R06b order recipe requires each named Hand finger subtree exactly once")
    _reverse_recipe_children(
        hand_root, lambda node: node.tag == "body" and node.get("name") in wanted,
    )


def _canonical_xml_sha256(root: ET.Element) -> str:
    serialized = ET.tostring(root, encoding="unicode")
    canonical = ET.canonicalize(serialized, with_comments=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_r06b_order_sources(arm_xml: str, hand_xml: str) -> None:
    """Verify pinned derivative bytes and that inverse order restores base MJCF semantics."""
    roots = {"panda-arm": _recipe_xml_root(arm_xml), "panda-hand": _recipe_xml_root(hand_xml)}
    actual_sha = {
        entity: hashlib.sha256(xml.encode("utf-8")).hexdigest()
        for entity, xml in (("panda-arm", arm_xml), ("panda-hand", hand_xml))
    }
    if actual_sha != R06B_ORDER_SOURCE_SHA256:
        raise ValueError("R06b derived XML differs from the one allowlisted order recipe")
    arm, hand = roots["panda-arm"], roots["panda-hand"]
    actuators = [node.get("name") for node in arm.findall("./actuator/*")]
    fingers = [node.get("name") for node in hand.findall("./worldbody/body/body")]
    if actuators != [f"actuator{index}" for index in range(7, 0, -1)]:
        raise ValueError("R06b Arm actuator declaration order differs from the frozen recipe")
    if fingers != ["right_finger", "left_finger"]:
        raise ValueError("R06b Hand finger body order differs from the frozen recipe")
    _apply_r06b_order_recipe(arm, hand)
    if {
        "panda-arm": _canonical_xml_sha256(arm),
        "panda-hand": _canonical_xml_sha256(hand),
    } != _BASE_CANONICAL_SHA256:
        raise ValueError("R06b inverse order operation changed non-order MJCF semantics")


def fixed_attachment_source_recipe(arm_xml: str, hand_xml: str) -> str:
    """Classify the exact legacy pair or validate the one admitted derivative."""
    actual = {
        "panda-arm": hashlib.sha256(arm_xml.encode("utf-8")).hexdigest(),
        "panda-hand": hashlib.sha256(hand_xml.encode("utf-8")).hexdigest(),
    }
    if actual == _BASE_SOURCE_SHA256:
        return "r03b-exact"
    validate_r06b_order_sources(arm_xml, hand_xml)
    return R06B_ORDER_RECIPE_ID


def admitted_fixed_source_profile(arm_xml: str, hand_xml: str):
    """Return verified traversal and provenance for the exact source pair."""
    recipe = fixed_attachment_source_recipe(arm_xml, hand_xml)
    if recipe == R06B_ORDER_RECIPE_ID:
        version = R06B_ORDER_ASSET_VERSION
        references = R06B_ORDER_SOURCE_REFERENCES
    else:
        version = "menagerie-b846dd12"
        references = {
            "panda-arm": "menagerie:franka_emika_panda/panda_nohand.xml",
            "panda-hand": "menagerie:franka_emika_panda/hand.xml",
        }
    return _SOURCE_JOINT_TRAVERSAL[recipe], version, references


def validate_attachment_plan(plan):
    """Keep the Panda hand's exact tendon ownership at the asset boundary."""
    if plan.native_tendon_names != {
        f"{plan.child_entity_id}/split": f"{plan.namespace_prefix}split",
    }:
        raise ValueError("fixed Attachment slice requires the exact Hand split tendon mapping")


def validate_panda_fixed_attachment_scene(plan, assembly, scene):
    """Validate shared attachment structure and the admitted Panda transmission."""
    from .fixed_attachment import validate_fixed_attachment_scene

    result = validate_fixed_attachment_scene(plan, assembly, scene)
    validate_attachment_plan(plan)
    return result


def validate_child_source(child_root, plan):
    """Validate the admitted Panda hand tendon, equality and actuator mapping."""
    hand_tendon = child_root.find("./tendon/fixed[@name='split']")
    if hand_tendon is None:
        raise ValueError("fixed Attachment Hand source is missing its split tendon")
    if plan.native_tendon_names[f"{plan.child_entity_id}/split"] != f"{plan.namespace_prefix}split":
        raise ValueError("fixed Attachment Hand tendon native mapping differs from its namespace")
    wraps = [(item.get("joint"), item.get("coef")) for item in hand_tendon.findall("joint")]
    if wraps != [("finger_joint1", "0.5"), ("finger_joint2", "0.5")]:
        raise ValueError("fixed Attachment Hand split tendon order/coefficients differ from source")
    equalities = child_root.findall("./equality/joint")
    if len(equalities) != 1 or (
        equalities[0].get("joint1"), equalities[0].get("joint2")
    ) != ("finger_joint1", "finger_joint2"):
        raise ValueError("fixed Attachment Hand source must preserve its one finger equality")
    child_actuators = [node for node in child_root.findall("./actuator/*") if node.get("name")]
    if (len(child_actuators) != 1 or child_actuators[0].get("name") != "actuator8"
            or child_actuators[0].get("tendon") != "split"):
        raise ValueError("fixed Attachment Hand actuator must remain attached to its split tendon")
