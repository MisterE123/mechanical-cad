"""Readable construction labels; persistent identities remain separate values."""


def face_label(face):
    role = face.get("role", "Face")
    if role == "shell.opening_lip":
        return "Current opening lip"
    if role.startswith("shell.opening_lip."):
        source = face.get("provenance", {}).get("source_id", "")
        return "Opening lip from " + source.replace("/face/", " / ")
    if role.startswith("shell.inner."):
        label = "Inner wall"
        source = face.get("provenance", {}).get("source_id", "")
        if source and "/face/shell." not in source:
            return label + " from " + source.replace("/face/", " / ")
        return label
    if role.startswith("pattern.copy."):
        occurrence = int(role.split(".")[2]) + 1
        source = face.get("provenance", {}).get("source_id", "")
        return f"Hole copy {occurrence} from " + source.replace("/face/", " / ")
    if role.startswith("blend.surface."):
        pair = face.get("provenance", {}).get("source_faces", [])
        return (
            "Blend between " + " and ".join(pair) if pair else "Selected multi-edge blend surface"
        )
    if role == "blend.surface":
        return "Selected blend surface"
    return role
