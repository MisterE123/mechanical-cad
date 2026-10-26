"""Unselected, child-only bootstrap for exact platform-specific CPython 3.12 profiles.

Copy this trusted source to payload bootstrap.py. No production owner imports it.
The parent must verify the complete final tree under its retained lifetime pin;
this child checks setup consistency, never creates a CAD receipt or capability.
This is trusted installed code, not a sandbox against hostile same-user tampering.
Only main() consumes the separate inherited descriptor handle. Stdin is untouched
until the unchanged mechanical_cad.sidecar.main() owns its ordinary request.
"""

import sys

MAX_DESCRIPTOR_BYTES = 16 * 1024
MAX_BOOTSTRAP_BYTES = 64 * 1024
MAX_PATH_CHARS = 4096
_FIELDS = frozenset(
    {
        "schema_version",
        "bundle_id",
        "source_commit",
        "runtime_lock_sha256",
        "platform",
        "manifest_sha256",
        "payload_sha256",
        "root",
        "python_path",
        "bootstrap_path",
    }
)
_FORBIDDEN = frozenset(
    {
        "site",
        "sitecustomize",
        "usercustomize",
        "bpy",
        "mechanical_cad",
        "OCP",
        "slvs",
        "cadquery",
        "pip",
    }
)


class BootstrapError(RuntimeError):
    """Fixed bounded diagnostic; never includes descriptor/model/environment data."""


def _fail(code):
    raise BootstrapError(code)


def _flags(system):
    for name in (
        "isolated",
        "ignore_environment",
        "no_site",
        "no_user_site",
        "dont_write_bytecode",
        "safe_path",
        "utf8_mode",
    ):
        if getattr(system.flags, name, None) != 1:
            _fail("isolated_flags_required")
    if system.flags.optimize != 0 or not system.dont_write_bytecode:
        _fail("isolated_flags_required")
    if system._xoptions != {"utf8": True}:
        _fail("isolated_flags_required")
    if (
        len(system.orig_argv) != 9
        or system.orig_argv[1:7] != ["-I", "-S", "-B", "-X", "utf8", "-c"]
        or system.argv != ["-c", system.orig_argv[8]]
    ):
        _fail("fixed_launch_required")


def _layout(system, operating_system):
    _flags(system)
    if (
        system.implementation.name != "cpython"
        or system.implementation.cache_tag != "cpython-312"
        or tuple(system.version_info)
        != (3, 12, 10 if system.platform == "win32" else 15, "final", 0)
        or system.maxsize != 2**63 - 1
        or getattr(system, "abiflags", "") != ""
    ):
        _fail("runtime_profile_mismatch")
    root = operating_system.getcwd()
    join = operating_system.path.join
    prefix = join(root, "python")
    if system.platform == "linux" and operating_system.name == "posix":
        platform = "linux-x64"
        executable = join(prefix, "bin", "python3.12")
        stdlib = join(prefix, "lib", "python3.12")
        native = join(stdlib, "lib-dynload")
        placeholder = join(prefix, "lib", "python312.zip")
        startup = [placeholder, stdlib, native]
        suffix = ".cpython-312-x86_64-linux-gnu.so"
    elif system.platform == "win32" and operating_system.name == "nt":
        platform = "windows-x64"
        executable = join(prefix, "python.exe")
        stdlib, native = join(prefix, "Lib"), join(prefix, "DLLs")
        placeholder = join(prefix, "python312.zip")
        startup = [placeholder, native, stdlib, prefix]
        suffix = ".cp312-win_amd64.pyd"
    else:
        _fail("unsupported_platform")
    if (
        system.executable != executable
        or system.prefix != prefix
        or system.base_prefix != prefix
        or system.exec_prefix != prefix
        or system.base_exec_prefix != prefix
        or getattr(system, "_base_executable", executable) != executable
        or getattr(system, "_stdlib_dir", stdlib) != stdlib
    ):
        _fail("interpreter_origin_mismatch")
    if system.path != startup:
        _fail("startup_import_path_mismatch")
    if operating_system.path.lexists(placeholder):
        _fail("unexpected_stdlib_archive")
    return {
        "root": root,
        "prefix": prefix,
        "executable": executable,
        "stdlib": stdlib,
        "native": native,
        "platform": platform,
        "suffix": suffix,
        "bootstrap": join(root, "bootstrap.py"),
        "src": join(root, "src"),
        "packages": join(root, "packages"),
    }


def _loaded_modules(system, layout, operating_system):
    """Before any dependency imports, accept only bundled stdlib or frozen/builtin."""
    path = operating_system.path
    for name, module in tuple(system.modules.items()):
        top = name.partition(".")[0]
        if top in _FORBIDDEN:
            _fail("forbidden_preloaded_module")
        if module is None:
            _fail("invalid_preloaded_module")
        spec = getattr(module, "__spec__", None)
        origin = getattr(spec, "origin", None)
        if name == "__main__":
            if getattr(module, "__file__", layout["bootstrap"]) != layout["bootstrap"]:
                _fail("external_preloaded_module")
            continue
        if origin == "built-in" and name in system.builtin_module_names:
            continue
        if origin == "frozen" and top in system.stdlib_module_names:
            continue
        filename = getattr(module, "__file__", None)
        if top not in system.stdlib_module_names or type(filename) is not str:
            _fail("external_preloaded_module")
        if (
            origin != filename
            or not any(
                filename.startswith(directory + path.sep)
                for directory in (layout["stdlib"], layout["native"])
            )
            or path.realpath(filename) != filename
        ):
            _fail("external_preloaded_module")
        package_paths = getattr(module, "__path__", ())
        if any(not item.startswith(layout["stdlib"] + path.sep) for item in package_paths):
            _fail("external_preloaded_package")


def _pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            _fail("duplicate_descriptor_field")
        value[key] = item
    return value


def _constant(_value):
    _fail("invalid_descriptor_json")


def parse_descriptor(data):
    """Pure flat bounded descriptor syntax; no paths are evaluated here."""
    if type(data) is not bytes or not 0 < len(data) <= MAX_DESCRIPTOR_BYTES:
        _fail("descriptor_size")
    import json

    try:
        value = json.loads(
            data.decode("utf-8", "strict"), object_pairs_hook=_pairs, parse_constant=_constant
        )
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise BootstrapError("invalid_descriptor_json") from exc
    if type(value) is not dict or value.keys() != _FIELDS:
        _fail("descriptor_fields")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        _fail("descriptor_schema")
    for key, item in value.items():
        if key == "schema_version":
            continue
        if type(item) is not str or not item or len(item) > MAX_PATH_CHARS or "\0" in item:
            _fail("descriptor_value")
        try:
            item.encode("utf-8", "strict")
        except UnicodeError as exc:
            raise BootstrapError("descriptor_value") from exc
    for key in (
        "bundle_id",
        "runtime_lock_sha256",
        "manifest_sha256",
        "payload_sha256",
        "source_commit",
    ):
        item = value[key]
        if len(item) != (40 if key == "source_commit" else 64) or any(
            char not in "0123456789abcdef" for char in item
        ):
            _fail("descriptor_digest")
    if value["platform"] not in {"linux-x64", "windows-x64"}:
        _fail("descriptor_platform")
    import hashlib

    identity = [value["source_commit"], value["runtime_lock_sha256"], value["platform"]]
    expected = hashlib.sha256(json.dumps(identity, separators=(",", ":")).encode("ascii"))
    if expected.hexdigest() != value["bundle_id"]:
        _fail("descriptor_identity")
    return value


def _checked_path(value, kind, operating_system):
    import stat

    path = operating_system.path
    if (
        type(value) is not str
        or not 0 < len(value) <= MAX_PATH_CHARS
        or not path.isabs(value)
        or path.normpath(value) != value
        or path.realpath(value) != value
    ):
        _fail("noncanonical_runtime_path")
    current = value
    while True:
        info = operating_system.lstat(current)
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            _fail("linked_runtime_path")
        parent = path.dirname(current)
        if current == parent:
            break
        current = parent
    info = operating_system.lstat(value)
    if kind == "file":
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            _fail("nonregular_runtime_file")
    elif not stat.S_ISDIR(info.st_mode):
        _fail("runtime_directory_required")
    return value


def _read_raw(descriptor, limit, operating_system):
    """Bounded bytes only. This helper neither wraps nor closes the raw owner."""
    chunks, size = [], 0
    while size <= limit:
        chunk = operating_system.read(descriptor, limit + 1 - size)
        if not chunk:
            break
        chunks.append(chunk)
        size += len(chunk)
    return b"".join(chunks)


def _bounded_file(path, limit, operating_system):
    import stat

    _checked_path(path, "file", operating_system)
    flags = operating_system.O_RDONLY | getattr(operating_system, "O_BINARY", 0)
    flags |= getattr(operating_system, "O_NOFOLLOW", 0)
    flags |= getattr(operating_system, "O_NONBLOCK", 0)
    descriptor = operating_system.open(path, flags)
    try:
        info = operating_system.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or getattr(info, "st_file_attributes", 0) & 0x400
        ):
            _fail("nonregular_setup_file")
        if not 0 <= info.st_size <= limit:
            _fail("setup_file_size")
        data = _read_raw(descriptor, limit, operating_system)
        if len(data) != info.st_size or len(data) > limit:
            _fail("setup_file_size")
        return data
    finally:
        # No stream constructor receives ownership. Never retry this close.
        operating_system.close(descriptor)


def _validate_files(descriptor, layout, operating_system, finder):
    import importlib.machinery
    import json

    path = operating_system.path
    join = path.join
    if (
        descriptor["platform"] != layout["platform"]
        or descriptor["root"] != layout["root"]
        or descriptor["python_path"] != layout["executable"]
        or descriptor["bootstrap_path"] != layout["bootstrap"]
        or path.basename(layout["root"]) != descriptor["bundle_id"]
    ):
        _fail("descriptor_origin_mismatch")
    for key in ("root", "prefix", "stdlib", "native", "src", "packages"):
        _checked_path(layout[key], "directory", operating_system)
    for key in ("executable", "bootstrap"):
        _checked_path(layout[key], "file", operating_system)
    for relative in ("python._pth", "python312._pth", "pyvenv.cfg"):
        if path.lexists(join(layout["prefix"], relative)):
            _fail("unexpected_python_configuration")
    if path.lexists(join(layout["root"], "pyvenv.cfg")):
        _fail("unexpected_python_configuration")
    expected_marker = json.dumps(
        {key: descriptor[key] for key in ("bundle_id", "manifest_sha256", "payload_sha256")},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    if (
        _bounded_file(join(layout["root"], ".bundle-ready.json"), 512, operating_system)
        != expected_marker
    ):
        _fail("publication_marker_mismatch")
    for package, parent in (
        ("mechanical_cad", layout["src"]),
        ("OCP", layout["packages"]),
        ("slvs", layout["packages"]),
    ):
        directory = _checked_path(join(parent, package), "directory", operating_system)
        origin = _checked_path(join(directory, "__init__.py"), "file", operating_system)
        spec = finder.find_spec(package, [parent])
        if (
            spec is None
            or spec.origin != origin
            or type(spec.loader) is not importlib.machinery.SourceFileLoader
            or list(spec.submodule_search_locations or ()) != [directory]
        ):
            _fail("package_origin_mismatch")
    core = join(layout["src"], "mechanical_cad")
    checks = [
        ("mechanical_cad.sidecar", core, "sidecar.py"),
        ("OCP.OCP", join(layout["packages"], "OCP"), "OCP" + layout["suffix"]),
        (
            "slvs.solvespace",
            join(layout["packages"], "slvs"),
            "solvespace.pyd" if layout["platform"] == "windows-x64" else "solvespace.so",
        ),
    ]
    for name, directory, filename in checks:
        origin = _checked_path(join(directory, filename), "file", operating_system)
        spec = finder.find_spec(name, [directory])
        loader_type = (
            importlib.machinery.SourceFileLoader
            if name == "mechanical_cad.sidecar"
            else importlib.machinery.ExtensionFileLoader
        )
        if (
            spec is None
            or spec.origin != origin
            or type(spec.loader) is not loader_type
            or spec.submodule_search_locations is not None
        ):
            _fail("module_origin_mismatch")
    return core


def _restrict_windows_dll_search():
    """Child-only policy for later loads; initial Python PE loads need host evidence."""
    try:
        import ctypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        configure = kernel.SetDefaultDllDirectories
        configure.argtypes = [ctypes.c_uint32]
        configure.restype = ctypes.c_int
        # Application directory, System32 and explicitly registered user directories.
        if not configure(0x00000200 | 0x00000800 | 0x00000400):
            _fail("dll_search_policy_failed")
    except Exception:
        _fail("dll_search_policy_failed")


def _checked_windows_image(value, operating_system=None):
    """Resolve loader casing only after proof with both original file handles.

    GetModuleFileNameW preserves a DLL's imported spelling (VCRUNTIME140.dll).
    Case folding alone never establishes identity on case-sensitive NTFS. Other
    aliases, links, multiple hardlinks and uncertain original closes fail closed.
    """
    if operating_system is None:
        import os as operating_system
    import ntpath
    import stat

    path = operating_system.path
    canonical = path.realpath(value)
    _checked_path(canonical, "file", operating_system)
    if canonical == value:
        return canonical
    if (
        ntpath.normcase(value) != ntpath.normcase(canonical)
        or path.normpath(value) != value
        or not path.isabs(value)
    ):
        _fail("mapped_dll_origin_rejected")
    current = value
    while True:
        info = operating_system.lstat(current)
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            _fail("linked_runtime_path")
        parent = path.dirname(current)
        if parent == current:
            break
        current = parent
    descriptors, observations = [], []
    try:
        for name in (value, canonical):
            descriptor = operating_system.open(
                name, operating_system.O_RDONLY | getattr(operating_system, "O_BINARY", 0)
            )
            descriptors.append(descriptor)  # Own before any observation can fail.
            info = operating_system.fstat(descriptor)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_nlink != 1
                or getattr(info, "st_file_attributes", 0) & 0x400
                or type(info.st_dev) is not int
                or type(info.st_ino) is not int
                or info.st_ino <= 0
            ):
                _fail("mapped_dll_origin_rejected")
            observations.append((info.st_dev, info.st_ino, info.st_size))
        if observations[0] != observations[1]:
            _fail("mapped_dll_origin_rejected")
        return canonical
    finally:
        uncertain = False
        for descriptor in reversed(descriptors):
            try:
                operating_system.close(descriptor)
            except BaseException:
                uncertain = True
        if uncertain:
            _fail("mapped_dll_cleanup_failed")


def _verify_windows_images(layout):
    """Check actual mapped PE origins after the fixed private imports.

    Parent-held, hashed native files must map from those exact private paths;
    other images must come directly from the OS System32 directory. Neither
    PATH/CWD providers nor unrelated injection directories gain admission.
    """
    import ctypes as c
    import json
    import ntpath

    kernel = c.WinDLL("kernel32", use_last_error=True)
    H, D, W = c.c_void_p, c.c_uint32, c.c_wchar_p
    signatures = (
        ("GetCurrentProcess", [], H),
        ("K32EnumProcessModulesEx", [H, c.POINTER(H), D, c.POINTER(D), D], c.c_int),
        ("GetModuleFileNameW", [H, W, D], D),
        ("GetSystemDirectoryW", [W, D], D),
    )
    for name, args, result in signatures:
        function = getattr(kernel, name)
        function.argtypes, function.restype = args, result
    system = c.create_unicode_buffer(260)
    count = kernel.GetSystemDirectoryW(system, 260)
    if not 0 < count < 260:
        _fail("system_dll_origin_unavailable")
    modules, needed = (H * 512)(), D()
    if (
        not kernel.K32EnumProcessModulesEx(
            kernel.GetCurrentProcess(), modules, c.sizeof(modules), c.byref(needed), 3
        )
        or not 0 < needed.value <= c.sizeof(modules)
        or needed.value % c.sizeof(H)
    ):
        _fail("mapped_dll_inventory_unavailable")
    private = tuple(
        ntpath.normcase(path) + "\\"
        for path in (
            layout["prefix"],
            layout["native"],
            ntpath.join(layout["packages"], "OCP"),
            ntpath.join(layout["packages"], "slvs"),
            ntpath.join(layout["packages"], "cadquery_ocp_novtk.libs"),
        )
    )
    required = {
        ntpath.normcase(path)
        for path in (
            layout["executable"],
            ntpath.join(layout["prefix"], "python312.dll"),
            ntpath.join(layout["packages"], "OCP", "OCP" + layout["suffix"]),
            ntpath.join(layout["packages"], "slvs", "solvespace.pyd"),
        )
    }
    images, seen_handles, seen_paths = [], set(), set()
    for handle in modules[: needed.value // c.sizeof(H)]:
        if not handle or handle in seen_handles:
            _fail("mapped_dll_inventory_unavailable")
        seen_handles.add(handle)
        path = c.create_unicode_buffer(260)
        count = kernel.GetModuleFileNameW(handle, path, 260)
        if not 0 < count < 260:
            _fail("mapped_dll_origin_unavailable")
        normalized = ntpath.normcase(path.value)
        if normalized in seen_paths:
            _fail("mapped_dll_inventory_unavailable")
        seen_paths.add(normalized)
        if any(normalized.startswith(directory) for directory in private):
            _checked_windows_image(path.value)
        elif ntpath.normcase(ntpath.dirname(path.value)) != ntpath.normcase(system.value):
            _fail("mapped_dll_origin_rejected")
        images.append(path.value)
    if not required <= seen_paths:
        _fail("mapped_dll_inventory_incomplete")
    # Bounded diagnostic supports native qualification, never CAD authority.
    summary = {
        "windows_mapped_images_checked": len(images),
        "private_images": sum(
            any(ntpath.normcase(p).startswith(d) for d in private) for p in images
        ),
        "platform": layout["platform"],
    }
    print(json.dumps(summary, separators=(",", ":")), file=sys.stderr, flush=True)


def _dispatch(layout, core, system, operating_system, importer):
    handles, close_error = [], False
    try:
        if layout["platform"] == "windows-x64":
            _restrict_windows_dll_search()
            for directory in (
                layout["prefix"],
                layout["native"],
                operating_system.path.join(layout["packages"], "OCP"),
                operating_system.path.join(layout["packages"], "slvs"),
                operating_system.path.join(layout["packages"], "cadquery_ocp_novtk.libs"),
            ):
                _checked_path(directory, "directory", operating_system)
                handle = operating_system.add_dll_directory(directory)
                if not callable(getattr(handle, "close", None)):
                    _fail("dll_directory_cookie_invalid")
                handles.append(handle)
        system.path[:] = [layout["stdlib"], layout["native"], layout["src"], layout["packages"]]
        system.path_importer_cache.clear()
        if layout["platform"] == "windows-x64":
            # The origin gate runs before a request or export is dispatched.
            import importlib.machinery

            for name, relative in (
                ("OCP.OCP", ("OCP", "OCP" + layout["suffix"])),
                ("slvs.solvespace", ("slvs", "solvespace.pyd")),
            ):
                module = importer(name)
                expected = operating_system.path.join(layout["packages"], *relative)
                spec = getattr(module, "__spec__", None)
                if (
                    getattr(module, "__file__", None) != expected
                    or getattr(spec, "origin", None) != expected
                    or type(getattr(spec, "loader", None))
                    is not importlib.machinery.ExtensionFileLoader
                ):
                    _fail("imported_native_origin_mismatch")
            _verify_windows_images(layout)
        package = importer("mechanical_cad")
        if (
            package.__file__ != operating_system.path.join(core, "__init__.py")
            or package.__spec__.origin != package.__file__
            or list(package.__path__) != [core]
            or package.__version__ != "1.30.0"
        ):
            _fail("imported_core_origin_mismatch")
        sidecar = importer("mechanical_cad.sidecar")
        if (
            sidecar.__file__ != operating_system.path.join(core, "sidecar.py")
            or sidecar.__spec__.origin != sidecar.__file__
        ):
            _fail("imported_sidecar_origin_mismatch")
        return sidecar.main()
    finally:
        for handle in reversed(handles):
            try:
                handle.close()
            except Exception:
                close_error = True
        if close_error:
            _fail("dll_directory_cleanup_failed")


def bootstrap(data, *, system=sys, operating_system=None, finder=None, importer=None):
    """Child-only setup and fixed dispatch. Injectable leaves support pure tests."""
    _flags(system)
    if operating_system is None:
        import os as operating_system
    layout = _layout(system, operating_system)
    _loaded_modules(system, layout, operating_system)
    import _imp
    import importlib
    import importlib.machinery

    if _imp.extension_suffixes()[0] != layout["suffix"]:
        _fail("runtime_architecture_mismatch")
    machinery = importlib.machinery
    if system.meta_path != [
        machinery.BuiltinImporter,
        machinery.FrozenImporter,
        machinery.PathFinder,
    ]:
        _fail("unexpected_import_finder")
    descriptor = parse_descriptor(data)
    core = _validate_files(descriptor, layout, operating_system, finder or machinery.PathFinder)
    _loaded_modules(system, layout, operating_system)
    return _dispatch(layout, core, system, operating_system, importer or importlib.import_module)


def read_descriptor(token, *, system=sys, operating_system=None, windows_crt=None):
    """Consume/close only the inherited setup handle, never a standard stream.

    Windows read-only handle rights are guaranteed by the parent transport;
    open_osfhandle transfers that exact handle into a read-only CRT descriptor.
    This does not independently prove its original Win32 access mask.
    """
    if (
        type(token) is not str
        or not token.isascii()
        or not token.isdecimal()
        or len(token) > 20
        or token.startswith("0")
        or not 0 < int(token) < 2**64 - 1
    ):
        _fail("invalid_descriptor_handle")
    if operating_system is None:
        import os as operating_system
    import stat

    handle = int(token)
    if system.platform == "win32":
        if windows_crt is None:
            import msvcrt as windows_crt
        if handle in {windows_crt.get_osfhandle(index) for index in (0, 1, 2)}:
            _fail("standard_descriptor_handle")
        operating_system.set_handle_inheritable(handle, False)
        descriptor = windows_crt.open_osfhandle(
            handle, operating_system.O_RDONLY | operating_system.O_BINARY
        )
    else:
        if handle <= 2:
            _fail("standard_descriptor_handle")
        descriptor = handle
    # Keep raw ownership through reads; no stream constructor can consume it.
    try:
        operating_system.set_inheritable(descriptor, False)
        if system.platform != "win32":
            import fcntl

            if fcntl.fcntl(descriptor, fcntl.F_GETFL) & operating_system.O_ACCMODE:
                _fail("readonly_descriptor_required")
        info = operating_system.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_DESCRIPTOR_BYTES:
            _fail("descriptor_file_required")
        if operating_system.lseek(descriptor, 0, operating_system.SEEK_CUR) != 0:
            _fail("descriptor_offset")
        data = _read_raw(descriptor, MAX_DESCRIPTOR_BYTES, operating_system)
        if len(data) != info.st_size or len(data) > MAX_DESCRIPTOR_BYTES:
            _fail("descriptor_size")
        return data
    finally:
        operating_system.close(descriptor)


# The launcher substitutes only an inventory-derived trusted digest. No request
# or descriptor content appears in this source. It fits LaunchSpec's 4096 chars.
_ENTRY_TEMPLATE = """import sys, os
try:
 f=sys.flags
 if any(getattr(f,n,None)!=1 for n in ("isolated","ignore_environment","no_site","no_user_site","dont_write_bytecode","safe_path","utf8_mode")) or f.optimize or not sys.dont_write_bytecode: raise ValueError()
 if sys._xoptions!={"utf8":True} or len(sys.argv)!=2 or sys.argv[0]!="-c": raise ValueError()
 if os.__spec__.origin!="frozen": raise ValueError()
 r=os.getcwd(); p=os.path.join(r,"python")
 if sys.platform=="linux" and os.name=="posix":
  s=os.path.join(p,"lib","python3.12"); n=os.path.join(s,"lib-dynload"); z=os.path.join(p,"lib","python312.zip"); e=os.path.join(p,"bin","python3.12"); paths=[z,s,n]
 elif sys.platform=="win32" and os.name=="nt":
  s=os.path.join(p,"Lib"); n=os.path.join(p,"DLLs"); z=os.path.join(p,"python312.zip"); e=os.path.join(p,"python.exe"); paths=[z,n,s,p]
 else: raise ValueError()
 if sys.path!=paths or sys.executable!=e or sys.prefix!=p or sys.base_prefix!=p or os.path.lexists(z): raise ValueError()
 if any(len(v)>4096 or os.path.realpath(v)!=v for v in (r,p,e,s,n)): raise ValueError()
 for k,m in tuple(sys.modules.items()):
  if k=="__main__": continue
  o=getattr(getattr(m,"__spec__",None),"origin",None); t=k.split(".")[0]
  if t in ("site","sitecustomize","usercustomize","mechanical_cad","OCP","slvs","bpy"): raise ValueError()
  if o=="built-in" and k in sys.builtin_module_names: continue
  if o=="frozen" and t in sys.stdlib_module_names: continue
  v=getattr(m,"__file__",None)
  if t not in sys.stdlib_module_names or not isinstance(v,str) or o!=v or not any(v.startswith(d+os.sep) for d in (s,n)) or os.path.realpath(v)!=v: raise ValueError()
 import hashlib, stat
 b=os.path.join(r,"bootstrap.py"); i=os.lstat(b)
 if not stat.S_ISREG(i.st_mode) or i.st_nlink!=1 or getattr(i,"st_file_attributes",0)&1024 or not 0<i.st_size<=65536: raise ValueError()
 fd=os.open(b,os.O_RDONLY|getattr(os,"O_BINARY",0)|getattr(os,"O_NOFOLLOW",0)|getattr(os,"O_NONBLOCK",0))
 try:
  i=os.fstat(fd)
  if not stat.S_ISREG(i.st_mode) or i.st_nlink!=1 or getattr(i,"st_file_attributes",0)&1024 or not 0<i.st_size<=65536: raise ValueError()
  chunks=[]; size=0
  while size<=65536:
   chunk=os.read(fd,65537-size)
   if not chunk: break
   chunks.append(chunk); size+=len(chunk)
  data=b"".join(chunks)
 finally:
  os.close(fd)
 if len(data)!=i.st_size or hashlib.sha256(data).hexdigest()!="@DIGEST@": raise ValueError()
except Exception:
 sys.stderr.write("standalone_bootstrap: entry_rejected\\n"); raise SystemExit(78)
exec(compile(data,b,"exec"),{"__name__":"__main__","__file__":b})
"""


def entry_loader(bootstrap_sha256):
    """Build fixed trusted launcher text from the release inventory, not JSON."""
    if (
        type(bootstrap_sha256) is not str
        or len(bootstrap_sha256) != 64
        or any(char not in "0123456789abcdef" for char in bootstrap_sha256)
    ):
        _fail("trusted_bootstrap_digest_required")
    return _ENTRY_TEMPLATE.replace("@DIGEST@", bootstrap_sha256)


def main():
    try:
        _flags(sys)
        import os

        layout = _layout(sys, os)
        _loaded_modules(sys, layout, os)
        return bootstrap(read_descriptor(sys.argv[1]))
    except Exception as exc:
        code = str(exc) if isinstance(exc, BootstrapError) else "setup_failed"
        sys.stderr.write("standalone_bootstrap: " + code[:80] + "\n")
        return 78


if __name__ == "__main__":
    raise SystemExit(main())
