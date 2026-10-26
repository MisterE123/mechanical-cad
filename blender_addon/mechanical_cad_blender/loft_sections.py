"""Explicit ordered Loft inputs. Pure contract shared with the Blender client."""

MAX_LOFT_SECTIONS = 16


def section_ports(intent):
    if (
        type(intent) is not dict
        or set(intent) != {"version", "ports"}
        or type(intent["version"]) is not int
        or intent["version"] != 1
    ):
        raise ValueError("Unsupported Loft section intent; expected version 1 and ordered ports")
    ports = intent["ports"]
    if (
        type(ports) is not list
        or not 2 <= len(ports) <= MAX_LOFT_SECTIONS
        or ports != [f"section_{i + 1}" for i in range(len(ports))]
    ):
        raise ValueError("Loft requires 2–16 ordered section ports (section_1, section_2, …)")
    return tuple(ports)


def validate_sections(intent, inputs):
    ports = section_ports(intent)
    if set(inputs) != set(ports):
        raise ValueError("Loft section ports must match the explicit profile dependencies")
    values = [inputs[p] for p in ports]
    if any(type(v) is not str or not v or v == "NONE" for v in values):
        raise ValueError("Choose an existing closed profile for every Loft section")
    if len(set(values)) != len(values):
        raise ValueError("Loft sections must be distinct profiles; remove repeated sections")
    return ports


def set_sections(feature, profiles):
    if feature["kind"] != "loft":
        raise ValueError("Only Loft accepts ordered section intent")
    ports = [f"section_{i + 1}" for i in range(len(profiles))]
    intent = {"version": 1, "ports": ports}
    inputs = dict(zip(ports, profiles, strict=True))
    validate_sections(intent, inputs)
    feature["loft_sections"], feature["inputs"] = intent, inputs
