"""Reproduce the historical R06b order-only diagnostic source pair."""

import hashlib
import xml.etree.ElementTree as ET

from task_env.assembly.panda_source_profiles import (
    _BASE_SOURCE_SHA256, _apply_r06b_order_recipe, _recipe_xml_root,
    validate_r06b_order_sources,
)


def derive_r06b_order_sources(arm_xml: str, hand_xml: str) -> tuple[str, str]:
    """Return the one pinned order-only derivative of the Menagerie XML pair."""
    arm_raw, hand_raw = arm_xml.encode("utf-8"), hand_xml.encode("utf-8")
    actual = {
        "panda-arm": hashlib.sha256(arm_raw).hexdigest(),
        "panda-hand": hashlib.sha256(hand_raw).hexdigest(),
    }
    if actual != _BASE_SOURCE_SHA256:
        raise ValueError("R06b recipe input is not the exact pinned Menagerie source pair")
    arm, hand = _recipe_xml_root(arm_xml), _recipe_xml_root(hand_xml)
    _apply_r06b_order_recipe(arm, hand)
    arm_derived = ET.tostring(arm, encoding="utf-8", xml_declaration=True).decode("utf-8")
    hand_derived = ET.tostring(hand, encoding="utf-8", xml_declaration=True).decode("utf-8")
    validate_r06b_order_sources(arm_derived, hand_derived)
    return arm_derived, hand_derived
