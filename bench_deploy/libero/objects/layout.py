"""LIBERO movable-object and fixture layout facts shared by reset and MJCF."""

PILOT_TABLE_TOP_Z_M = 0.90
PILOT_MOVABLE_Z_OFFSET_M = 0.01
PILOT_TABLE_FULL_THICKNESS_M = 0.05
PILOT_FIXTURE_Z_OFFSET_M = PILOT_MOVABLE_Z_OFFSET_M - PILOT_TABLE_FULL_THICKNESS_M

PILOT_MOVABLES = (
    ("akita_black_bowl_1", "between_plate_ramekin_region", "upstream/libero/libero/libero/assets/stable_scanned_objects/akita_black_bowl/akita_black_bowl.xml"),
    ("akita_black_bowl_2", "next_to_ramekin_region", "upstream/libero/libero/libero/assets/stable_scanned_objects/akita_black_bowl/akita_black_bowl.xml"),
    ("plate_1", "plate_region", "upstream/libero/libero/libero/assets/stable_scanned_objects/plate/plate.xml"),
    ("cookies_1", "box_region", "upstream/libero/libero/libero/assets/stable_hope_objects/cookies/cookies.xml"),
    ("glazed_rim_porcelain_ramekin_1", "ramekin_region", "upstream/libero/libero/libero/assets/stable_scanned_objects/glazed_rim_porcelain_ramekin/glazed_rim_porcelain_ramekin.xml"),
)
PILOT_MOVABLE_OBJECT_CLASSES = {
    "akita_black_bowl_1": "libero.libero.envs.objects.google_scanned_objects.AkitaBlackBowl",
    "akita_black_bowl_2": "libero.libero.envs.objects.google_scanned_objects.AkitaBlackBowl",
    "plate_1": "libero.libero.envs.objects.google_scanned_objects.Plate",
    "cookies_1": "libero.libero.envs.objects.hope_objects.Cookies",
    "glazed_rim_porcelain_ramekin_1": (
        "libero.libero.envs.objects.google_scanned_objects.GlazedRimPorcelainRamekin"
    ),
}
PILOT_FIXTURES = (
    ("wooden_cabinet_1", "cabinet_region", "upstream/libero/libero/libero/assets/articulated_objects/wooden_cabinet.xml"),
    ("flat_stove_1", "stove_region", "upstream/libero/libero/libero/assets/articulated_objects/flat_stove.xml"),
)

FIXTURE_WORLD_POSES = {
    "wooden_cabinet_1_main": {
        "pos": (0.032160686061349086, -0.26769535926827864, 0.905),
        "quat": (0.21813924162729167, 0.0, 0.0, 0.9759176559844944),
    },
    "flat_stove_1_main": {
        "pos": (-0.4146303298573933, -0.13499687702793547, 0.905),
        "quat": (1.0, 0.0, 0.0, 0.0),
    },
}
TABLE_REGION_SITES = {
    "main_table_between_plate_ramekin_region": ((-0.05, 0.20, 0.02), (0.01, 0.01, 0.007)),
    "main_table_box_region": ((0.07, 0.03, 0.02), (0.01, 0.01, 0.007)),
    "main_table_cabinet_region": ((0.03, -0.27, 0.02), (0.01, 0.01, 0.007)),
    "main_table_next_to_box_region": ((0.13, -0.07, 0.02), (0.01, 0.01, 0.007)),
    "main_table_next_to_plate_region": ((0.01, 0.31, 0.02), (0.01, 0.01, 0.007)),
    "main_table_next_to_ramekin_region": ((-0.18, 0.32, 0.02), (0.01, 0.01, 0.007)),
    "main_table_plate_region": ((0.06, 0.20, 0.02), (0.01, 0.01, 0.007)),
    "main_table_ramekin_region": ((-0.20, 0.20, 0.02), (0.01, 0.01, 0.007)),
    "main_table_stove_region": ((-0.41, -0.14, 0.02), (0.01, 0.01, 0.007)),
    "main_table_table_center": ((-0.075, 0.0, 0.02), (0.025, 0.01, 0.007)),
    "main_table_table_front": ((0.20, 0.0, 0.02), (0.01, 0.01, 0.007)),
}
