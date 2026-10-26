"""Request-local Cut ancestry for logical workplanes, never stable face naming.

Mirrored in the native-free client. Every handle refers only to topology within
one fresh replay. Only an authored source-feature ID may enter saved intent.
"""

from __future__ import annotations


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _faces(row):
    topology = row.get("topology")
    _require(isinstance(topology, list) and len(topology) <= 200_000, "Missing Cut topology.")
    _require(
        all(
            isinstance(face, dict)
            and all(isinstance(face.get(key), str) for key in ("id", "feature_id", "role"))
            and isinstance(face.get("signature"), dict)
            and isinstance(face.get("provenance"), dict)
            for face in topology
        ),
        "Malformed current Cut topology.",
    )
    faces = {face["id"]: face for face in topology}
    _require(len(faces) == len(topology), "Aliased Cut topology IDs.")
    return faces


def validate_cut_ancestry(cut, base, tool):
    """Validate a complete native ledger against the exact current input rows."""
    ledger = cut.get("cut_ancestry")
    _require(
        cut.get("kind") == "cut"
        and cut.get("status") == base.get("status") == tool.get("status") == "ok"
        and cut.get("inputs") == {"base": base["id"], "tool": tool["id"]},
        "Cut ancestry is not bound to its current inputs.",
    )
    _require(
        isinstance(ledger, dict)
        and set(ledger) == {"version", "sources"}
        and type(ledger["version"]) is int
        and ledger["version"] == 1,
        "Missing or unsupported complete Cut ancestry.",
    )
    output = _faces(cut)
    available = {"base": _faces(base), "tool": _faces(tool)}
    records = ledger["sources"]
    _require(isinstance(records, list) and len(records) <= 400_000, "Unbounded Cut sources.")
    by_source, claims = {}, {identifier: [] for identifier in output}
    for record in records:
        _require(
            isinstance(record, dict)
            and set(record)
            == {"port", "source_id", "deleted", "modified", "generated", "unchanged"},
            "Malformed Cut source ledger.",
        )
        port, identifier = record["port"], record["source_id"]
        _require(
            isinstance(port, str)
            and port in available
            and isinstance(identifier, str)
            and identifier in available[port]
            and (port, identifier) not in by_source
            and type(record["deleted"]) is bool,
            "Cut ledger contains an unavailable or aliased source.",
        )
        by_source[port, identifier] = record
        for relation in ("modified", "generated", "unchanged"):
            images = record[relation]
            _require(
                isinstance(images, list)
                and len(images) <= len(output)
                and all(isinstance(image, str) and image in output for image in images)
                and len(set(images)) == len(images),
                "Cut ledger contains missing or repeated images.",
            )
            _require(
                not (relation == "unchanged" and images and record["deleted"]),
                "Deleted Cut source cannot be unchanged.",
            )
            for image in images:
                claims[image].append((port, identifier, relation))
    _require(
        set(by_source)
        == {(port, identifier) for port, faces in available.items() for identifier in faces},
        "Cut ledger omitted an input source.",
    )
    # Existing inherited descriptors must agree with the independently supplied
    # native ledger; the ledger cannot replace or silently upgrade face identity.
    for face in output.values():
        provenance = face["provenance"]
        relation = provenance.get("relation")
        if relation in {"modified", "generated", "unchanged", "tool_modified", "tool_unchanged"}:
            port = "tool" if relation.startswith("tool_") else "base"
            source_id = provenance.get("source_id")
            _require(
                isinstance(source_id, str) and (port, source_id) in by_source,
                "Cut descriptor cites a missing source.",
            )
            native_relation = relation.removeprefix("tool_")
            record = by_source[port, source_id]
            images = set(record["modified"] + record["generated"] + record["unchanged"])
            _require(
                face["id"] in record[native_relation]
                and provenance.get("image_count") == len(images),
                "Cut descriptor differs from its native ancestry ledger.",
            )
    return by_source, claims


def replay_rows(results):
    _require(
        isinstance(results, (list, tuple)) and len(results) <= 256, "Unbounded support ancestry."
    )
    _require(
        all(
            isinstance(row, dict)
            and isinstance(row.get("id"), str)
            and isinstance(row.get("inputs", {}), dict)
            for row in results
        ),
        "Malformed support replay rows.",
    )
    rows = {row["id"]: row for row in results}
    _require(len(rows) == len(results), "Duplicate support features.")
    return rows


def source_chain(source_id, support_id, rows):
    """An explicit source may reach support only through consecutive base Cuts."""
    chain, seen = [], set()
    current = rows.get(support_id)
    while current is not None and current["id"] != source_id:
        _require(
            current["id"] not in seen and current.get("kind") == "cut",
            "The saved source needs a continuous ordinary Cut base chain; choose another support.",
        )
        seen.add(current["id"])
        chain.append(current)
        current = rows.get(current.get("inputs", {}).get("base"))
    _require(current is not None, "The saved source feature is unavailable.")
    return current, list(reversed(chain))


def _tool_aliases(tool, face_id, rows):
    # Conservatively reject reuse of the same construction identity through a
    # different operand, including aliases hidden by an earlier split/deletion.
    pending, seen = [tool], set()
    while pending:
        row = pending.pop()
        if row["id"] in seen:
            continue
        seen.add(row["id"])
        if any(
            face["id"] == face_id or f"{face['feature_id']}/face/{face['role']}" == face_id
            for face in _faces(row).values()
        ):
            return True
        pending.extend(
            rows[identifier]
            for port, identifier in row.get("inputs", {}).items()
            if port in {"base", "tool"} and identifier in rows
        )
    return False


def resolve_replay_support(face_id, intent, support_id, results):
    from .support_intent import _transport_signature, resolve_support_signature, validate_intent

    rows = replay_rows(results)
    support = rows.get(support_id)
    _require(support is not None and support.get("status") == "ok", "Support is unavailable.")
    if intent is None or "source_feature" not in intent:
        # Old records keep their immediate-source frame convention byte-for-byte.
        base = rows.get(support.get("inputs", {}).get("base"), {})
        return resolve_support_signature(face_id, intent, support["topology"], base.get("topology"))
    validate_intent(intent)
    source, chain = source_chain(intent["source_feature"], support_id, rows)
    source_faces = _faces(source)
    original = source_faces.get(face_id)
    _require(
        source.get("status") == "ok"
        and original is not None
        and original["provenance"].get("semantic_status") == "stable"
        and original["signature"].get("surface") == "plane",
        "The bound original stable planar source is unavailable.",
    )
    if not chain:
        return resolve_support_signature(
            face_id,
            {key: value for key, value in intent.items() if key != "source_feature"},
            support["topology"],
        )
    current = {face_id: original}
    for cut in chain:
        base = rows[cut["inputs"]["base"]]
        tool = rows.get(cut["inputs"]["tool"])
        _require(
            tool is not None and not _tool_aliases(tool, face_id, rows),
            "Competing or aliased Cut source; choose another supporting plane.",
        )
        ledger, claims = validate_cut_ancestry(cut, base, tool)
        output = _faces(cut)
        descendants = {}
        for identifier, parent in current.items():
            record = ledger["base", identifier]
            _require(
                not record["generated"],
                "Generated-only or competing lineage cannot preserve a plane.",
            )
            images = set(record["modified"] + record["unchanged"])
            _require(bool(images) or record["deleted"], "Missing surviving fragment ancestry.")
            for image in images:
                owners = {(port, source) for port, source, _ in claims[image]}
                _require(
                    owners == {("base", identifier)}
                    and not any(relation == "generated" for _, _, relation in claims[image])
                    and image not in descendants,
                    "A Cut fragment has competing origins or generated ancestry.",
                )
                face = output[image]
                provenance = face["provenance"]
                expected = "split" if len(images) > 1 else parent["provenance"]["semantic_status"]
                _require(
                    expected in {"stable", "split"}
                    and provenance.get("semantic_status") == expected
                    and provenance.get("source_id") == identifier
                    and type(provenance.get("source_count")) is int
                    and provenance["source_count"] == 1
                    and type(provenance.get("image_count")) is int
                    and provenance["image_count"] == len(images)
                    and provenance.get("operation") == "cut"
                    and provenance.get("operation_id") == cut["id"]
                    and provenance.get("relation") in {"modified", "unchanged"}
                    and face["signature"].get("surface") == "plane",
                    "Incomplete or nonplanar Cut fragment ancestry.",
                )
                descendants[image] = face
        _require(
            descendants, "The original plane has no surviving fragments; choose another support."
        )
        # Check every step, not only a favorable coplanar final subset.
        _transport_signature(intent, original["signature"], list(descendants.values()))
        current = descendants
    signature = _transport_signature(intent, original["signature"], list(current.values()))
    stable = (
        len(current) == 1
        and face_id in current
        and current[face_id]["provenance"]["semantic_status"] == "stable"
    )
    return signature, {
        "status": "assumed",
        "policy": "preserve_plane",
        "source_face": face_id,
        "source_feature": source["id"],
        "descendant_count": len(current),
        "cut_count": len(chain),
        "identity_status": "stable" if stable else "split",
        **({"orientation_policy": "minimal_twist"} if "orientation" in intent else {}),
        "reason": f"Preserved the saved source workplane through {len(chain)} proven Cut(s), not fragment centroids. No fragment was chosen; the plane may span removed material. Choose Strict or another support to change this assumption."
        + (
            " Minimal twist follows the saved tangent, not material spin."
            if "orientation" in intent
            else ""
        ),
    }
