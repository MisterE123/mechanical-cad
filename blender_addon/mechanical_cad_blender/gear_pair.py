"""Native-free complete gear-pair candidates; only guarded replay can accept them.

The tooth convention is +X at zero, XY profile, +Z shaft. Backlash below is
TOTAL pair circular backlash and is divided equally between the two gears.
"""

import math

from .assembly_edit import canonical_digest, identity, origin_frame


def pair_dimensions(
    *,
    module,
    teeth_a,
    teeth_b,
    pressure_angle,
    thickness,
    bore_a,
    bore_b,
    pair_backlash,
    clearance,
    profile_tolerance,
):
    values = (
        module,
        pressure_angle,
        thickness,
        bore_a,
        bore_b,
        pair_backlash,
        clearance,
        profile_tolerance,
    )
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
        raise ValueError("Gear dimensions must be finite numbers.")
    if not 14.5 <= pressure_angle <= 30:
        raise ValueError("Pressure angle must be 14.5–30 degrees.")
    minimum = math.ceil(2 / math.sin(math.radians(pressure_angle)) ** 2 - 1e-12)
    for teeth in (teeth_a, teeth_b):
        if type(teeth) is not int or not minimum <= teeth <= 200:
            raise ValueError(f"Use {minimum}–200 teeth at this pressure angle (no undercut).")
    if not 0.1 <= module <= 100 or not 0.1 <= thickness <= 1000:
        raise ValueError("Module must be 0.1–100 mm; thickness 0.1–1000 mm.")
    if not 0.0001 <= profile_tolerance <= min(0.1, 0.05 * module):
        raise ValueError("Profile tolerance must be 0.0001–min(0.1, 0.05 × module) mm.")
    if clearance > 0.5 or pair_backlash > module:
        raise ValueError("Root clearance must be ≤0.5 module; pair backlash ≤1 module.")
    if min(bore_a, bore_b, pair_backlash, clearance) < 0:
        raise ValueError("Bores, backlash and root clearance cannot be negative.")
    if pair_backlash >= math.pi * module:
        raise ValueError("Backlash removes the whole pitch tooth thickness.")
    for teeth, bore in ((teeth_a, bore_a), (teeth_b, bore_b)):
        root_radius = module * (teeth / 2 - 1 - clearance)
        if root_radius <= 0 or bore / 2 > root_radius - module - profile_tolerance:
            raise ValueError(
                "Each bore must leave at least one module of material inside the root circle."
            )
    return {
        "center_distance": module * (teeth_a + teeth_b) / 2,
        "ratio": -teeth_a / teeth_b,
        "phase": math.pi + math.pi / teeth_b,
        "minimum_teeth": minimum,
    }


def _document(name, features, parameters):
    return {
        "schema_version": 1,
        "id": identity("source"),
        "name": name,
        "units": "mm",
        "parameters": parameters,
        "features": features,
        "active_feature": features[-1]["id"],
    }


def _feature(id_, kind, params, inputs=None):
    return {
        "id": id_,
        "kind": kind,
        "label": id_.replace("_", " ").title(),
        "params": params,
        "inputs": inputs or {},
    }


def build_pair(
    *,
    name="Printable spur gear pair",
    module=2.0,
    teeth_a=20,
    teeth_b=40,
    pressure_angle=20.0,
    thickness=8.0,
    bore_a=5.0,
    bore_b=5.0,
    pair_backlash=0.2,
    clearance=0.25,
    profile_tolerance=0.01,
):
    """Build three editable Parts and one complete rooted, geared assembly.

    The third Part is a small reference-only base below the gears, NOT a shaft,
    bearing, printable mounting design or an implicit part of either STL.
    No existing state is read or changed. Native replay is required before use.
    """
    dimensions = pair_dimensions(
        module=module,
        teeth_a=teeth_a,
        teeth_b=teeth_b,
        pressure_angle=pressure_angle,
        thickness=thickness,
        bore_a=bore_a,
        bore_b=bore_b,
        pair_backlash=pair_backlash,
        clearance=clearance,
        profile_tolerance=profile_tolerance,
    )
    if not isinstance(name, str) or not name.strip() or len(name) > 256:
        raise ValueError("Give the pair a nonempty name of at most 256 characters.")
    # Keep physical reference geometry far below tooth solids, independent of fit.
    support = _document(
        "Reference base — NOT FOR PRINT",
        [
            _feature(
                "reference_profile",
                "sketch_rectangle",
                {"width": 2.0, "height": 2.0, "x": -1.0, "y": -1.0, "z": -5.0},
            ),
            _feature(
                "reference_base", "extrude", {"length": 1.0}, {"profile": "reference_profile"}
            ),
        ],
        {},
    )
    documents = [support]
    for label, teeth, bore in (("A", teeth_a, bore_a), ("B", teeth_b, bore_b)):
        params = dict(
            module=float(module),
            tooth_count=teeth,
            thickness=float(thickness),
            pressure_angle=float(pressure_angle),
            bore_diameter=float(bore),
            backlash=float(pair_backlash / 2),
            clearance=float(clearance),
            profile_tolerance=float(profile_tolerance),
        )
        documents.append(
            _document(
                f"Gear {label} ({teeth} teeth)",
                [_feature("gear", "spur_gear", {key: key for key in params})],
                params,
            )
        )
    sources, parts, instances = [], [], []
    for index, document in enumerate(documents):
        digest = canonical_digest(document)
        sources.append(
            {"source_document_id": document["id"], "source_digest": digest, "document": document}
        )
        frames = [{"id": "origin", "name": "Shaft +Z / tooth zero +X", "placement": origin_frame()}]
        if index == 0:
            frames = [
                {"id": "axis_a", "name": "Gear A +Z shaft", "placement": origin_frame()},
                {
                    "id": "axis_b",
                    "name": "Gear B +Z shaft",
                    "placement": {
                        "xyz_mm": [dimensions["center_distance"], 0.0, 0.0],
                        "wxyz": [1.0, 0.0, 0.0, 0.0],
                    },
                },
            ]
        parts.append(
            {
                "id": f"part_{index}",
                "name": document["name"],
                "source_document_id": document["id"],
                "source_digest": digest,
                "output_feature_id": document["active_feature"],
                "mate_frames": frames,
            }
        )
        instances.append(
            {"id": f"instance_{index}", "name": document["name"], "part_id": f"part_{index}"}
        )
    joints = [
        {
            "id": f"shaft_{label}",
            "name": f"Gear {label.upper()} shaft (+Z)",
            "kind": "revolute",
            "parent": "instance_0",
            "child": f"instance_{index}",
            "parent_frame": f"axis_{label}",
            "child_frame": "origin",
            "coordinate": 0.0 if index == 1 else None,
            "limits": None,
        }
        for index, label in ((1, "a"), (2, "b"))
    ]
    return {
        "kind": "assembly",
        "assembly_schema_version": 1,
        "id": identity("gear_pair"),
        "name": name.strip(),
        "length_unit": "mm",
        "angle_unit": "rad",
        "part_sources": sources,
        "parts": parts,
        "instances": instances,
        "joints": joints,
        "grounded_instance": "instance_0",
        "ground": origin_frame(),
        "gear_relations": [
            {
                "id": "external_mesh",
                "name": "External spur mesh (kinematic)",
                "driver_joint": "shaft_a",
                "driven_joint": "shaft_b",
                "ratio": dimensions["ratio"],
                "offset_rad": dimensions["phase"],
            }
        ],
        "verification_presets": [],
        "active_verification_preset": None,
    }


EDIT_REFUSAL = (
    "Edit Gear Pair needs an unchanged generated external spur pair. "
    "This assembly is customized or not recognized. Edit its Parts/mates individually, "
    "or save it and use New Printable Gear Pair."
)


def _retain_names(template, accepted, defaults=None):
    """Only display names/labels are free; every structural field must still match."""
    if isinstance(template, dict) and isinstance(accepted, dict):
        for key, value in template.items():
            if key in ("name", "label") and key in accepted:
                if defaults is None or accepted[key] != defaults.get(key):
                    template[key] = accepted[key]
            elif key in accepted and key != "verification_presets":
                _retain_names(value, accepted[key], defaults.get(key) if defaults else None)
    elif isinstance(template, list) and isinstance(accepted, list):
        for index, (value, old) in enumerate(zip(template, accepted, strict=True)):
            _retain_names(value, old, defaults[index] if defaults else None)


def _bind_identity(candidate, accepted):
    candidate["id"] = accepted["id"]
    for source, old, part in zip(
        candidate["part_sources"], accepted["part_sources"], candidate["parts"], strict=True
    ):
        source["source_document_id"] = old["source_document_id"]
        source["document"]["id"] = old["document"]["id"]
        source["source_digest"] = canonical_digest(source["document"])
        part["source_document_id"] = source["source_document_id"]
        part["source_digest"] = source["source_digest"]
    candidate["joints"][0]["coordinate"] = accepted["joints"][0]["coordinate"]


def recognize_pair(accepted):
    """Recognize the full authored template, never geometry or names alone.

    Legacy generator IDs plus exact source/structure equivalence are deliberately
    required. These are recognition constraints, not an authenticity certificate.
    Renaming and moving the independent driver are supported; other edits fail
    closed. No schema extension or inferred pairing is needed.
    """
    import re

    try:
        if not re.fullmatch(r"gear_pair_[0-9a-f]{32}", accepted["id"]):
            raise ValueError(EDIT_REFUSAL)
        if len({s["source_document_id"] for s in accepted["part_sources"]}) != 3:
            raise ValueError(EDIT_REFUSAL)
        for source in accepted["part_sources"]:
            if not re.fullmatch(r"source_[0-9a-f]{32}", source["source_document_id"]):
                raise ValueError(EDIT_REFUSAL)
        a, b = [s["document"]["parameters"] for s in accepted["part_sources"]][1:]
        params = {
            "module": a["module"],
            "teeth_a": a["tooth_count"],
            "teeth_b": b["tooth_count"],
            "pressure_angle": a["pressure_angle"],
            "thickness": a["thickness"],
            "bore_a": a["bore_diameter"],
            "bore_b": b["bore_diameter"],
            "pair_backlash": 2 * a["backlash"],
            "clearance": a["clearance"],
            "profile_tolerance": a["profile_tolerance"],
        }
        angle = accepted["joints"][0]["coordinate"]
        if type(angle) not in (int, float) or not math.isfinite(angle) or abs(angle) > 1e4:
            raise ValueError(EDIT_REFUSAL)
        expected = build_pair(name=accepted["name"], **params)
        _retain_names(expected, accepted)
        _bind_identity(expected, accepted)
        # Presets are authored checking intent, not geometry. Keep them untouched;
        # normal replay invalidates their old measurement authority.
        expected["verification_presets"] = accepted["verification_presets"]
        expected["active_verification_preset"] = accepted["active_verification_preset"]
        if expected != accepted:
            raise ValueError(EDIT_REFUSAL)
        return params
    except (KeyError, TypeError, IndexError, ValueError) as exc:
        raise ValueError(EDIT_REFUSAL) from exc


def edit_pair(accepted, *, name=None, **changes):
    """Regenerate a recognized pair, retaining IDs, display names and driver pose."""
    import copy

    params = recognize_pair(accepted)
    defaults = build_pair(**params)
    params.update(changes)
    candidate = build_pair(name=accepted["name"], **params)
    _retain_names(candidate, accepted, defaults)
    _bind_identity(candidate, accepted)
    candidate["verification_presets"] = copy.deepcopy(accepted["verification_presets"])
    candidate["active_verification_preset"] = accepted["active_verification_preset"]
    if name is not None:
        if not isinstance(name, str) or not name.strip() or len(name) > 256:
            raise ValueError("Give the pair a nonempty name of at most 256 characters.")
        candidate["name"] = name.strip()
    return candidate
