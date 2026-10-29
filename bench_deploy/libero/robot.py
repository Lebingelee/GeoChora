"""Native robot interface facts and Core mapping status."""


def build_robot(task_input: dict, manifest: dict) -> dict:
    native = task_input["native_reference"]["robot"]
    xmls = [
        row for row in manifest["selected_xml_sources"]
        if row["repository"] == "robosuite"
        and any(part in row["path"] for part in ("/robots/", "/grippers/", "/mounts/"))
    ]
    if len(xmls) != 3:
        raise ValueError("pilot robot recipe must bind Panda, PandaGripper, and RethinkMount XMLs")
    return {
        "native_reference": native,
        "source_xmls": xmls,
        "actuator_interface": native["actuators"],
        "deployment_status": "BLOCKED_CORE_ACTUATOR_MAPPING; preserve seven torque motors and two finger-position actuators",
    }
