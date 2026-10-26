"""Editable current-source enclosure stress example; no manufacturing certification."""

import importlib
import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
p = types.ModuleType("example_addon")
p.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[p.__name__] = p
hole = importlib.import_module("example_addon.hole_recipe")
from mechanical_cad.engine import regenerate  # noqa: E402
from mechanical_cad.kernel_ocp import OCPKernel  # noqa: E402
from mechanical_cad.loft_sections import set_sections  # noqa: E402
from mechanical_cad.model import Document  # noqa: E402

OUT = Path(sys.argv[1])
OUT.mkdir(exist_ok=True, parents=True)
PARAMS = dict(
    width=100,
    depth=70,
    height=35,
    wall=2.4,
    cover=3.6,
    vent_count=7,
    vent_pitch=10,
    duct_middle=20,
    duct_wall=2,
)


def new(name):
    return dict(
        schema_version=1,
        id=name,
        name=name.replace("_", " ").title(),
        units="mm",
        parameters=PARAMS.copy(),
        features=[],
        active_feature=None,
    )


def add(d, id, kind, params=None, inputs=None, **extra):
    d["features"].append(
        dict(
            id=id,
            kind=kind,
            label=id.replace("_", " ").title(),
            params=params or {},
            inputs=inputs or {},
            **extra,
        )
    )
    d["active_feature"] = id
    return id


def extr(d, id, w, h, x, y, z, length):
    add(d, id + "_profile", "sketch_rectangle", dict(width=w, height=h, x=x, y=y, z=z))
    return add(d, id, "extrude", dict(length=length), dict(profile=id + "_profile"))


def replay(d):
    k = OCPKernel()
    r = regenerate(Document.from_dict(d), k, result_version=3)
    if not r.ok:
        print([(f["id"], f.get("error")) for f in r.result["features"] if f["status"] != "ok"])
        raise RuntimeError(d["id"])
    return k, r


body = new("ventilated_body")
extr(body, "blank", "width", "depth", 0, 0, 0, "height")
pairs = [
    ["blank/face/side." + x, "blank/face/side." + y]
    for x in ("x_min", "x_max")
    for y in ("y_min", "y_max")
]
add(body, "corner_rounds", "fillet", dict(radius=3), dict(base="blank"), edge_pairs=pairs)
add(
    body,
    "open_shell",
    "shell",
    dict(thickness="wall"),
    dict(base="corner_rounds"),
    opening_faces=["blank/face/cap.end"],
)
# Explicit bottom edge treatment, separate selected-edge intent.
add(
    body,
    "bottom_bevel",
    "chamfer",
    dict(distance=0.5),
    dict(base="open_shell"),
    edge_pairs=[
        ["blank/face/cap.start", "blank/face/side.x_min"],
        ["blank/face/cap.start", "blank/face/side.x_max"],
    ],
)
extr(body, "vent_tool", 4, 30, 18, 20, -1, "wall+2")
add(
    body,
    "bottom_vents",
    "linear_cut_pattern",
    dict(count="vent_count", dx="vent_pitch"),
    dict(base="bottom_bevel", tool="vent_tool"),
)
base = "bottom_vents"
for n, y in enumerate([13, "depth-16"]):
    extr(body, f"rib_{n}", "width-2*wall", 3, "wall", y, "wall-0.2", 5)
    base = add(body, f"join_rib_{n}", "union", {}, dict(base=base, tool=f"rib_{n}"))
for n, (x, y) in enumerate([(7, 7), ("width-7", 7), (7, "depth-7"), ("width-7", "depth-7")]):
    add(body, f"post_profile_{n}", "sketch_circle", dict(radius=4.5, x=x, y=y, z="wall-0.2"))
    add(
        body,
        f"post_{n}",
        "extrude",
        dict(length="height-wall+0.2"),
        dict(profile=f"post_profile_{n}"),
    )
    base = add(body, f"join_post_{n}", "union", {}, dict(base=base, tool=f"post_{n}"))
    # Datum tools avoid centroid drift in repeated cuts.
    add(body, f"pilot_profile_{n}", "sketch_circle", dict(radius=1.3, x=x, y=y, z="height-10"))
    add(body, f"pilot_tool_{n}", "extrude", dict(length=11), dict(profile=f"pilot_profile_{n}"))
    base = add(body, f"pilot_{n}", "cut", {}, dict(base=base, tool=f"pilot_tool_{n}"))
cover = new("removable_duct_cover")
extr(cover, "lid", "width", "depth", 0, 0, 0, "cover")
add(
    cover,
    "lid_rounds",
    "fillet",
    dict(radius=3),
    dict(base="lid"),
    edge_pairs=[[a.replace("blank/", "lid/"), b.replace("blank/", "lid/")] for a, b in pairs],
)
base = "lid_rounds"
for n, (x, y) in enumerate([(-43, -28), (43, -28), (-43, 28), (43, 28)]):
    # The Hole recipe uses current face centroid offsets, not edge distances.
    k, r = replay(cover)
    top = next(t for t in r.result["features"][-1]["topology"] if t["id"] == "lid/face/cap.end")
    cx, cy, _ = top["signature"]["centroid"]
    x, y = x + 50 - cx, y + 35 - cy
    root = "hole_" + f"{n + 1:032x}"
    cover = hole.hole_candidate(
        cover,
        root,
        base=base,
        face="lid/face/cap.end",
        diameter=3.2,
        depth=5,
        x=x,
        y=y,
        counterbore=True,
        counter_diameter=6.4,
        counter_depth=1.6,
        label=f"Cover screw {n + 1}",
    )
    base = root
# Ring/flange and four section transition integrated into removable lid.
for scope, _offset in [("outer", 0), ("inner", "duct_wall")]:
    for n, (radius, z) in enumerate([(24, -1), (24, 5), ("duct_middle", 24), (16, 43)]):
        r = radius if scope == "outer" else f"({radius})-duct_wall"
        add(cover, f"{scope}_{n}", "sketch_circle", dict(radius=r, x="width/2", y="depth/2", z=z))
    f = dict(
        id=scope + "_loft",
        kind="loft",
        label=scope.title() + " four-section duct",
        params=dict(ruled=0),
    )
    set_sections(f, [f"{scope}_{i}" for i in range(4)])
    cover["features"].append(f)
add(cover, "join_duct", "union", {}, dict(base=base, tool="outer_loft"))
add(cover, "open_airway", "cut", {}, dict(base="join_duct", tool="inner_loft"))
# Build the duct before drilling: optional native cleanup on an already
# perforated exact-aligned cover can become pathologically expensive.
fs = cover["features"]
holes = fs[3:27]
duct_features = fs[27:]
for f in duct_features:
    if f["id"] == "join_duct":
        f["inputs"]["base"] = "lid_rounds"
for f in holes[:6]:
    for port, source in f["inputs"].items():
        if source == "lid_rounds":
            f["inputs"][port] = "open_airway"
cover["features"] = fs[:3] + duct_features + holes
cover["active_feature"] = holes[-1]["id"]
# Recalculate literal centroid offsets against each actual finished support.
for n, (tx, ty) in enumerate([(7, 7), (93, 7), (7, 63), (93, 63)]):
    prefix = dict(cover)
    prefix["features"] = cover["features"][: 15 + 6 * n]
    prefix["active_feature"] = prefix["features"][-1]["id"]
    k, r = replay(prefix)
    top = next(t for t in r.result["features"][-1]["topology"] if t["id"] == "lid/face/cap.end")
    cx, cy, _ = top["signature"]["centroid"]
    for f in cover["features"][15 + 6 * n : 21 + 6 * n]:
        if f["kind"] == "sketch_face_circle":
            f["params"].update(x=tx - cx, y=ty - cy)
# Avoid an inner cap at upper endpoint: both lofts share the endpoint datum.
models = [body, cover]
for d in models:
    d = Document.from_dict(d).to_dict()
    (OUT / (d["id"] + ".mcad.json")).write_text(json.dumps(d, indent=2) + "\n")
    k, r = replay(d)
    shape = r.shapes[d["active_feature"]]
    stats = k.inspect(shape)
    check = k.manufacturing_check(shape)
    (OUT / (d["id"] + ".mcad.json")).write_text(json.dumps(d, indent=2) + "\n")
    (OUT / (d["id"] + "_check.json")).write_text(json.dumps(check, indent=2) + "\n")
    print(d["id"], len(d["features"]), stats, flush=True)
    k.export_step(shape, str(OUT / (d["id"] + ".step")))
    k.export_stl(shape, str(OUT / (d["id"] + ".stl")))
