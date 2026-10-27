"""Test-child source selection and a separate proof before accepting wire output."""

import hashlib
import importlib.abc
import importlib.machinery
import importlib.util
import json
import sys
from pathlib import Path


class SourceBindingError(AssertionError):
    def __init__(self, process, report, report_path):
        super().__init__(f"Child source binding failed: {report.get('error', 'missing proof')}")
        self.process, self.report, self.report_path = process, report, report_path


def require_source_binding(process, report_path):
    try:
        report = json.loads(Path(report_path).read_bytes())
    except (OSError, ValueError):
        report = {}
    if report.get("status") != "verified":
        raise SourceBindingError(process, report, report_path)
    return report


def source_bound_script(root, entry, report_path, *, historical_pins):
    root = Path(root).resolve()
    package = root / "src/mechanical_cad"
    sources = {
        str(path.resolve()): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(package.rglob("*.py"))
    }
    assert str(package / "__init__.py") in sources
    helper = Path(__file__).resolve()
    helper_sha = hashlib.sha256(helper.read_bytes()).hexdigest()
    config = dict(
        root=str(root),
        sources=sources,
        historical_pins=historical_pins,
        report_path=str(report_path),
        helper_sha256=helper_sha,
    )
    return (
        "import hashlib, pathlib\n"
        f"_binding_bytes = pathlib.Path({str(helper)!r}).read_bytes()\n"
        f"assert hashlib.sha256(_binding_bytes).hexdigest() == {helper_sha!r}\n"
        f"_binding_namespace = {{'__name__': '_process_source_binding', '__file__': {str(helper)!r}}}\n"
        f"exec(compile(_binding_bytes, {str(helper)!r}, 'exec'), _binding_namespace)\n"
        f"_binding_namespace['execute_bound']({config!r}, {entry!r})\n"
    )


def execute_bound(config, entry):
    """Use exact live bytes, with only explicitly pinned historical overrides."""
    root, expected = Path(config["root"]), config["sources"]
    report = dict(status="starting", root=str(root), loads=[], historical=[], modules={})
    approved_historical = {}
    compiled_historical = set()

    def check(condition, message):
        if not condition:
            report.update(status="failed", error="AssertionError: " + message)
            raise AssertionError(message)

    def file_hash(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    def verify_module(name, module):
        if approved_historical.get(name) is module:
            return dict(historical=True)
        filename = getattr(module, "__file__", None)
        spec = getattr(module, "__spec__", None)
        origin = getattr(spec, "origin", None)
        check(filename in expected and origin == filename, f"module origin mismatch: {name}")
        digest = file_hash(filename)
        check(digest == expected[filename], f"module bytes mismatch: {name}")
        return dict(path=filename, origin=origin, sha256=digest)

    class SourceLoader(importlib.machinery.SourceFileLoader):
        def get_code(self, fullname):
            raw = Path(self.path).read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            check(digest == expected[self.path], f"source bytes mismatch: {fullname}")
            report["loads"].append(dict(module=fullname, path=self.path, sha256=digest))
            return compile(raw, self.path, "exec", dont_inherit=True)

        def exec_module(self, module):
            super().exec_module(module)
            verify_module(module.__name__, module)

    class SourceFinder(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname != "mechanical_cad" and not fullname.startswith("mechanical_cad."):
                return None
            base = root / "src" / "/".join(fullname.split("."))
            if str(base / "__init__.py") in expected:
                filename, locations = base / "__init__.py", [str(base)]
            elif str(base.with_suffix(".py")) in expected:
                filename, locations = base.with_suffix(".py"), None
            else:
                raise ModuleNotFoundError("No intended checkout source for " + fullname)
            return importlib.util.spec_from_file_location(
                fullname,
                filename,
                loader=SourceLoader(fullname, str(filename)),
                submodule_search_locations=locations,
            )

    def audit(event, args):
        if event == "compile":
            source, filename = args
            pin = config["historical_pins"].get(filename)
            if filename not in expected and pin is None:
                return
            if isinstance(source, str):
                source = source.encode("utf-8")
            if isinstance(source, bytes):
                digest = hashlib.sha256(source).hexdigest()
                wanted = expected[filename] if pin is None else pin["sha256"]
                check(digest == wanted, f"compiled source mismatch: {filename}")
                if pin is not None:
                    compiled_historical.add(filename)
        elif event == "exec":
            filename = args[0].co_filename
            pin = config["historical_pins"].get(filename)
            if pin is not None:
                check(filename in compiled_historical, "historical code lacks source proof")
                report["historical"].append(dict(filename=filename, sha256=pin["sha256"]))
                name = pin.get("module")
                if name is not None:
                    module = sys.modules.get(name)
                    check(module is not None, f"missing historical module: {name}")
                    approved_historical[name] = module

    def finish():
        if report["status"] == "failed":
            return
        report["modules"] = {
            name: verify_module(name, module)
            for name, module in list(sys.modules.items())
            if name == "mechanical_cad" or name.startswith("mechanical_cad.")
        }
        report["status"] = "verified"
        Path(config["report_path"]).write_text(json.dumps(report), encoding="utf-8")

    try:
        for name in sys.modules:
            check(
                name != "mechanical_cad" and not name.startswith("mechanical_cad."),
                "preloaded project module: " + name,
            )
        sys.path.insert(0, str(root / "src"))
        sys.meta_path.insert(0, SourceFinder())
        sys.addaudithook(audit)
        namespace = {"__name__": "__main__", "__package__": None}
        try:
            exec(compile(entry, "<bound-process-test-entry>", "exec"), namespace)
        finally:
            finish()
    except BaseException as exc:
        if report["status"] != "verified":
            report.update(status="failed", error=type(exc).__name__ + ": " + str(exc))
            Path(config["report_path"]).write_text(json.dumps(report), encoding="utf-8")
        raise
