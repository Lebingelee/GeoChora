"""Provider-free behavioral counterexamples for the offline projection."""

import copy
from dataclasses import replace

import numpy as np
import pytest

from validation.sampling import MeasurementPolicy, conjunction, disjunction, evaluate_drawer_geometry, in_local_frame, ordered_witness, predicate, sphere_inside


POLICY = MeasurementPolicy()
RETRIEVE = {"kind": "store_and_retrieve", "drawer": "container", "same_ball": True,
            "order": ["pick_table", "place_drawer", "release", "regrasp_drawer", "place_table", "release"]}


def fixture():
    geometry = {"spheres": {"object_a": {"radius_m": .02}, "object_b": {"radius_m": .02}},
                "container": {"name": "container", "closed_origin_world_m": [0, .18, .4],
                              "opening_axis_world": [0, -1, 0],
                              "cavity_bounds_local_m": [[-.1, -.1, 0], [.1, .1, .1]]},
                "table_bounds_world_m": [[-1, -1, -.1], [1, 1, 0]],
                "gripper_enclosing_radii_m": {"finger": .06}}
    positions = {"container": [[0, 0, .4]] * 5, "finger": [[2, 2, 2]] * 5,
                 "object_a": [[.3, 0, .02], [.3, 0, .2], [0, 0, .42], [0, 0, .55], [.3, 0, .02]],
                 "object_b": [[.7, 0, .02]] * 5}
    return {"criterion": copy.deepcopy(RETRIEVE), "times_s": np.arange(5) * .03,
            "positions": positions, "orientations_wxyz": {"container": [[1, 0, 0, 0]] * 5},
            "geometry": geometry, "recording_complete": True, "policy": POLICY}


def value(data):
    return evaluate_drawer_geometry(**data)["geometric_goal"]["value"]


def test_success_requires_the_same_ball_at_every_stage():
    data = fixture()
    assert value(data) is True
    data["positions"]["object_a"][3:] = [[0, 0, .42]] * 2
    data["positions"]["object_b"][3] = [0, 0, .55]
    assert value(data) is False  # A was stored; moving B cannot discharge A's retrieval.


def test_lift_plan_without_object_lift_cannot_pass():
    data = fixture()
    data["positions"]["object_a"][3:] = [[0, 0, .42]] * 2
    data["positions"]["finger"][3] = [0, 0, 1.4]
    report = evaluate_drawer_geometry(**data)
    assert report["geometric_goal"]["value"] is False
    assert len(report["candidates"]["object_a"]["witness"]) == 2


def test_matching_final_frame_without_required_history_does_not_pass():
    data = fixture()
    data["positions"]["object_a"] = [[.3, 0, .02]] * 5
    assert value(data) is False


def test_store_close_cannot_close_empty_then_gain_contents_afterwards():
    data = fixture()
    data["criterion"] = {"kind": "drawer_store_close", "drawer": "container", "object_type": "ball",
                         "order": ["open", "pick", "place", "release", "close"], "contents_remain_inside": True}
    data["times_s"] = np.arange(6) * .03
    data["positions"] = {"container": [[0, 0, .4]] * 4 + [[0, .18, .4]] * 2,
                         "finger": [[2, 2, 2]] * 6,
                         "object_a": [[.3, 0, .02], [.3, 0, .2], [0, 0, .42], [.3, 0, .02], [.3, 0, .02], [0, .18, .42]],
                         "object_b": [[.7, 0, .02]] * 6}
    data["orientations_wxyz"]["container"] = [[1, 0, 0, 0]] * 6
    assert value(data) is False
    data["positions"]["object_a"][3:5] = [[0, 0, .42], [0, .18, .42]]
    assert value(data) is True


def test_store_close_can_recover_before_final_valid_release_and_close():
    data = fixture()
    data["criterion"] = {"kind": "drawer_store_close", "drawer": "container", "object_type": "ball",
                         "order": ["open", "pick", "place", "release", "close"], "contents_remain_inside": True}
    data["times_s"] = np.arange(8) * .03
    data["positions"] = {"container": [[0, 0, .4]] * 7 + [[0, .18, .4]], "finger": [[2, 2, 2]] * 8,
                         "object_a": [[.3, 0, .02], [.3, 0, .2], [0, 0, .42], [.3, 0, .02], [.3, 0, .2], [0, 0, .42], [0, 0, .42], [0, .18, .42]],
                         "object_b": [[.7, 0, .02]] * 8}
    data["orientations_wxyz"]["container"] = [[1, 0, 0, 0]] * 8
    report = evaluate_drawer_geometry(**data)
    assert report["geometric_goal"]["value"] is True
    assert report["candidates"]["object_a"]["witness"][2]["sample_index"] == 5


def test_missing_object_measurement_is_unknown_not_failure():
    data = fixture()
    del data["positions"]["object_a"]
    assert value(data) is None


def test_unknown_contact_never_becomes_full_task_success():
    report = evaluate_drawer_geometry(**fixture())
    assert report["geometric_goal"]["value"] is True
    assert report["task_success"] is None
    assert report["physical_execution"]["status"] == "unavailable"


def test_object_renaming_and_permutation_do_not_change_decision():
    data = fixture()
    data["positions"]["another_eligible_sphere"] = data["positions"].pop("object_a")
    data["geometry"]["spheres"] = {"object_b": {"radius_m": .02}, "another_eligible_sphere": {"radius_m": .02}}
    assert value(data) is True


def test_world_translation_does_not_change_decision():
    data = fixture()
    offset = np.array([5, -4, 2])
    data["positions"] = {name: np.asarray(points) + offset for name, points in data["positions"].items()}
    data["geometry"]["container"]["closed_origin_world_m"] = (np.asarray([0, .18, .4]) + offset).tolist()
    data["geometry"]["table_bounds_world_m"] = (np.asarray(data["geometry"]["table_bounds_world_m"]) + offset).tolist()
    assert value(data) is True


def test_center_inside_but_sphere_crossing_wall_is_not_containment():
    assert sphere_inside([[.095, 0, .05]], .02, [[-.1, -.1, 0], [.1, .1, .1]], .001) == [False]


def test_rigid_local_frame_handles_wxyz_rotation_and_translation():
    q = [[np.sqrt(.5), 0, 0, np.sqrt(.5)]]
    np.testing.assert_allclose(in_local_frame([[10, 21, 30]], [[10, 20, 30]], q), [[1, 0, 0]], atol=1e-12)
    assert np.isnan(in_local_frame([[1, 0, 0]], [[0, 0, 0]], [[0, 0, 0, 0]])).all()


def test_partial_or_gapped_record_is_never_a_negative():
    data = fixture()
    data["recording_complete"] = False
    assert value(data) is None
    data["recording_complete"] = True
    data["times_s"][-1] = 1.0
    assert value(data) is None


def test_sequence_order_repeated_release_and_recovery():
    times = np.arange(6) * .03
    rows = {"release": [False, True, False, False, True, False],
            "lift": [False, False, False, True, False, False]}
    result, indices = ordered_witness(times, rows, ["release", "lift", "release"], policy=POLICY, recording_complete=True)
    assert result.value is True and indices == (1, 3, 4)
    result, _ = ordered_witness(times, rows, ["lift", "release", "lift"], policy=POLICY, recording_complete=True)
    assert result.value is False


def test_sequence_does_not_reuse_one_sample_for_two_stages():
    result, _ = ordered_witness([0], {"a": [True], "b": [True]}, ["a", "b"], policy=POLICY, recording_complete=True)
    assert result.value is False


def test_missing_sequence_event_is_not_false_and_missing_irrelevant_event_can_be_bypassed():
    rows = {"a": [True, False, False], "b": [False, None, False]}
    result, _ = ordered_witness([0, .03, .06], rows, ["a", "b"], policy=POLICY, recording_complete=True)
    assert result.value is None
    rows["b"][-1] = True
    result, _ = ordered_witness([0, .03, .06], rows, ["a", "b"], policy=POLICY, recording_complete=True)
    assert result.value is True


@pytest.mark.parametrize("times", [[0, 0], [1, 0], [0, float("nan")]])
def test_invalid_clock_rejected(times):
    with pytest.raises(ValueError):
        ordered_witness(times, {"x": [True, True]}, ["x"], policy=POLICY, recording_complete=True)


def test_unsupported_requirements_are_not_silently_ignored():
    data = fixture()
    data["criterion"]["must_be_red"] = True
    assert value(data) is None
    data = fixture()
    data["criterion"]["same_ball"] = 1
    assert value(data) is None


def test_aggregation_preserves_missing_evidence():
    unknown = predicate(None)
    assert conjunction([predicate(True), unknown]).value is None
    assert conjunction([predicate(False), unknown]).value is False
    assert disjunction([predicate(False), unknown]).value is None
    assert disjunction([predicate(True), unknown]).value is True
    with pytest.raises(TypeError):
        predicate(0)


def test_measurement_policy_is_not_tuned_by_episode_identity():
    data = fixture()
    for tolerance in [.0005, .001, .002]:
        data["policy"] = replace(POLICY, distance_tolerance_m=tolerance)
        assert value(data) is True
    with pytest.raises(ValueError):
        MeasurementPolicy(float("nan"), .05)
