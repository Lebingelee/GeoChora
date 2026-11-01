"""Source-bound declarations for the three required v2.1.0 LIBERO tasks.

These declarations bind task identity and state-row layout only.  They do not
grant source eligibility, materialization, provider admission, or task success.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType


TASK_1 = (
    "libero_spatial/pick_up_the_black_bowl_between_the_plate_and_the_ramekin_"
    "and_place_it_on_the_plate"
)
TASK_2 = "libero_goal/open_the_middle_drawer_of_the_cabinet"
TASK_3 = "libero_goal/push_the_plate_to_the_front_of_the_stove"

LIBERO_REVISION = "8f1084e3132a39270c3a13ebe37270a43ece2a01"
ROBOSUITE_REVISION = "fbee5844ff5632f5b5698e204ec5357ca50be0df"


@dataclass(frozen=True)
class LiberoTaskSourceContractV1:
    task_uid: str
    suite: str
    bddl_path: str
    bddl_sha256: str
    init_path: str
    init_sha256: str
    init_shape: tuple[int, int]
    movable_instances: tuple[str, ...]
    fixture_joint_names: tuple[str, ...]
    goal_operator: str
    goal_arguments: tuple[str, ...]


_TASKS = {
    TASK_1: LiberoTaskSourceContractV1(
        task_uid=TASK_1,
        suite="libero_spatial",
        bddl_path=(
            "libero/libero/bddl_files/libero_spatial/"
            "pick_up_the_black_bowl_between_the_plate_and_the_ramekin_and_place_it_on_the_plate.bddl"
        ),
        bddl_sha256="9b59eb1287802868ad9bc78d58e6d36d4ba31134e679cfdbdf4b0feb660c959b",
        init_path=(
            "libero/libero/init_files/libero_spatial/"
            "pick_up_the_black_bowl_between_the_plate_and_the_ramekin_and_place_it_on_the_plate.pruned_init"
        ),
        init_sha256="cbbc73792ce546c9bec181fd328a411d3183074840b282671dee481511381d0a",
        init_shape=(50, 92),
        movable_instances=(
            "akita_black_bowl_1", "akita_black_bowl_2", "cookies_1",
            "glazed_rim_porcelain_ramekin_1", "plate_1",
        ),
        fixture_joint_names=(
            "wooden_cabinet_1.top_level", "wooden_cabinet_1.middle_level",
            "wooden_cabinet_1.bottom_level", "flat_stove_1.button",
        ),
        goal_operator="On",
        goal_arguments=("akita_black_bowl_1", "plate_1"),
    ),
    TASK_2: LiberoTaskSourceContractV1(
        task_uid=TASK_2,
        suite="libero_goal",
        bddl_path="libero/libero/bddl_files/libero_goal/open_the_middle_drawer_of_the_cabinet.bddl",
        bddl_sha256="832ab48ec476807c767e8985666e295700f92d1f8daeae1c34eee1e75293769b",
        init_path="libero/libero/init_files/libero_goal/open_the_middle_drawer_of_the_cabinet.pruned_init",
        init_sha256="977efe1216bee72bb4e9fa9ec4be1bcfe37fb00ece815eac117feba019b34b9f",
        init_shape=(50, 79),
        movable_instances=("akita_black_bowl_1", "cream_cheese_1", "wine_bottle_1", "plate_1"),
        fixture_joint_names=(
            "wooden_cabinet_1.top_level", "wooden_cabinet_1.middle_level",
            "wooden_cabinet_1.bottom_level", "flat_stove_1.button",
        ),
        goal_operator="Open",
        goal_arguments=("wooden_cabinet_1_middle_region",),
    ),
    TASK_3: LiberoTaskSourceContractV1(
        task_uid=TASK_3,
        suite="libero_goal",
        bddl_path="libero/libero/bddl_files/libero_goal/push_the_plate_to_the_front_of_the_stove.bddl",
        bddl_sha256="26f22f8ad39a4b2b344b049115c45661a877fa0b4821fb78246725e7e87d8c0b",
        init_path="libero/libero/init_files/libero_goal/push_the_plate_to_the_front_of_the_stove.pruned_init",
        init_sha256="794beed679b18bbd7d9fb851c81877a974915ad63addff2d5ac5af0607fafac9",
        init_shape=(50, 79),
        movable_instances=("akita_black_bowl_1", "cream_cheese_1", "wine_bottle_1", "plate_1"),
        fixture_joint_names=(
            "wooden_cabinet_1.top_level", "wooden_cabinet_1.middle_level",
            "wooden_cabinet_1.bottom_level", "flat_stove_1.button",
        ),
        goal_operator="On",
        goal_arguments=("plate_1", "main_table_stove_front_region"),
    ),
}

REQUIRED_TASKS_V1 = MappingProxyType(_TASKS)


def task_source_contract_v1(task_uid: str) -> LiberoTaskSourceContractV1:
    """Return one exact pinned source declaration; unknown IDs fail closed."""
    if type(task_uid) is not str:
        raise TypeError("LIBERO task identity must be a string")
    try:
        return REQUIRED_TASKS_V1[task_uid]
    except KeyError as exc:
        raise ValueError(f"LIBERO task is outside required task set: {task_uid!r}") from exc


__all__ = [
    "LIBERO_REVISION", "ROBOSUITE_REVISION", "TASK_1", "TASK_2", "TASK_3",
    "LiberoTaskSourceContractV1", "REQUIRED_TASKS_V1", "task_source_contract_v1",
]
