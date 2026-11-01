"""LIBERO task predicate and public contact-summary contracts."""

import pytest

from bench_deploy.libero.tasks.predicates import (
    ON_THRESHOLD_M, PILOT_TASK_UID, OnBowlPlateEvidenceV1,
    evaluate_on_bowl_plate_v1,
)
from task_env.environment import ContactSummary


_MANIFEST_SHA = "4ad168e4710f3153d0f1f470389a506df27588e4d5ce1eaec450289807d30a75"


def _on_evidence(*, x=0.0, bowl_z=0.20, plate_z=0.10, contact=True, frame="world"):
    return OnBowlPlateEvidenceV1(
        task_uid=PILOT_TASK_UID,
        source_manifest_sha256=_MANIFEST_SHA,
        frame_id=frame,
        bowl_center_m=(x, 0.0, bowl_z),
        plate_center_m=(0.0, 0.0, plate_z),
        geom_group_contact=contact,
    )


def _on(evidence):
    return evaluate_on_bowl_plate_v1(
        evidence, expected_source_manifest_sha256=_MANIFEST_SHA
    )


def test_on_predicate_requires_contact_vertical_order_and_strict_xy_threshold():
    assert _on(_on_evidence()).value is True
    assert _on(_on_evidence(contact=False)).value is False
    assert _on(_on_evidence(bowl_z=0.09)).value is False
    assert _on(_on_evidence(x=ON_THRESHOLD_M)).value is False
    assert _on(_on_evidence(x=ON_THRESHOLD_M - 1.0e-6)).value is True


def test_missing_or_mismatched_public_on_evidence_is_unavailable_not_false():
    assert _on(None).status == "unavailable"
    assert _on(_on_evidence(contact=None)).status == "unavailable"
    assert _on(_on_evidence(frame="robot0")).status == "unavailable"
    mismatch = evaluate_on_bowl_plate_v1(
        _on_evidence(), expected_source_manifest_sha256="c" * 64
    )
    assert mismatch.status == "unavailable"


def test_unavailable_contact_summary_cannot_hide_counts_or_invalid_schema():
    with pytest.raises(ValueError, match="cannot carry contact counts"):
        ContactSummary(
            pair_counts={"bowl/plate": 1},
            status="unavailable",
            reason="provider_contact_pair_query_not_implemented",
        )
    with pytest.raises(ValueError, match="unsupported ContactSummary schema"):
        ContactSummary(schema_version="task-contact-summary-v0")
