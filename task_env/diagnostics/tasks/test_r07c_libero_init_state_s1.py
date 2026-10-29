"""Provider-free tests for the pinned LIBERO init-state tokenizer."""
from __future__ import annotations

from pathlib import Path
from io import BytesIO
import zipfile

import pytest

from bench_deploy.libero import init_state


_INIT = Path(
    "/home/lly/Program_Files/Geochora/workspace/maintenance/phase_ii_01_sol_luna_handoff_20261023_001/"
    "r07b_pilot_001_install/final_001/upstream/libero/libero/libero/init_files/libero_spatial/"
    "pick_up_the_black_bowl_between_the_plate_and_the_ramekin_and_place_it_on_the_plate.pruned_init"
)


def test_pinned_init_array_is_read_without_unpickling_and_named_layout_is_explicit():
    decoded = init_state.read_pruned_init(_INIT)
    assert decoded.source_sha256 == init_state.INIT_SHA256
    assert len(decoded.values) == 50 * 92
    assert decoded.row_sha256[:3] == (
        "4e3eaf7a315bc3bafb6db4837c8eef0e5f8aea717782a2a3ea33139392d966ed",
        "6c2936dc25a97728b811f9db579687d011cbd231d5472e985775a67ca9892cf8",
        "a5d4b6d871eb48c276a3fc8499e1429ec1c59df278466aa82de44a93260087a0",
    )
    assert decoded.row(0)[0] == 0.0
    layout = init_state.init_layout_v1()
    assert layout["qpos_slice"] == [1, 49]
    assert layout["qvel_slice"] == [49, 92]
    assert (layout["expected_nq"], layout["expected_nv"], layout["expected_na"]) == (48, 43, 0)
    assert layout["fixture_body_pose_fields_in_flattened_state"] is False
    assert layout["status"] == "SOURCE_DERIVED_LAYOUT; FIXTURE_POSES_MISSING_FROM_INIT_ROWS"


def test_init_parser_rejects_changed_hash_and_unknown_pickle_tokens():
    data = _INIT.read_bytes()
    with pytest.raises(ValueError, match="pinned input SHA256"):
        init_state.decode_pruned_init_bytes(data + b"x")

    with zipfile.ZipFile(_INIT) as archive:
        payload = archive.read("archive/data.pkl")
    forged = payload[:-1] + b"N."
    with pytest.raises(ValueError, match="opcode stream"):
        init_state._tokenize_fixed_array(forged)


def test_init_parser_rejects_extra_zip_members_and_archive_versions():
    with zipfile.ZipFile(_INIT) as archive:
        data_pkl = archive.read("archive/data.pkl")
    extra = BytesIO()
    with zipfile.ZipFile(extra, "w") as archive:
        archive.writestr("archive/data.pkl", data_pkl)
        archive.writestr("archive/version", b"3\n")
        archive.writestr("unexpected", b"x")
    with pytest.raises(ValueError, match="only the two pinned members"):
        init_state._read_archive_payload(extra.getvalue())

    wrong_version = BytesIO()
    with zipfile.ZipFile(wrong_version, "w") as archive:
        archive.writestr("archive/data.pkl", data_pkl)
        archive.writestr("archive/version", b"4\n")
    with pytest.raises(ValueError, match="archive version"):
        init_state._read_archive_payload(wrong_version.getvalue())
