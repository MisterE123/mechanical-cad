"""Read-only registered-package cache provider using the Windows SDK ABI.

No shell, environment selection, alias discovery, permissions or package install.
The caller must select a trusted registered package family. Every original COM,
HSTRING and apartment resource is retired once, including on partial failure.
"""

import ctypes as c
import sys
import uuid


class PackageCacheCleanupError(RuntimeError):
    """Original native provider resources could not all be retired once."""


class PackageCacheAPI:
    def __init__(self):
        if sys.platform != "win32":
            raise OSError("Windows registered-package provider is unavailable")
        self.kernel = c.WinDLL("kernel32", use_last_error=True, winmode=0x800)
        self.runtime = c.WinDLL("combase", use_last_error=True, winmode=0x800)
        h, u, p = c.c_void_p, c.c_uint32, c.c_wchar_p
        bindings = (
            (
                self.kernel,
                "GetPackagesByPackageFamily",
                [p, c.POINTER(u), c.POINTER(p), c.POINTER(u), p],
                c.c_long,
            ),
            (self.runtime, "RoInitialize", [u], c.c_int32),
            (self.runtime, "RoUninitialize", [], None),
            (self.runtime, "WindowsCreateString", [p, u, c.POINTER(h)], c.c_int32),
            (self.runtime, "WindowsDeleteString", [h], c.c_int32),
            (self.runtime, "WindowsGetStringRawBuffer", [h, c.POINTER(u)], h),
            (self.runtime, "RoGetActivationFactory", [h, h, c.POINTER(h)], c.c_int32),
        )
        for library, name, args, result in bindings:
            function = getattr(library, name)
            function.argtypes, function.restype = args, result

    @staticmethod
    def _check(result):
        if result < 0:
            raise OSError(f"Windows package-data HRESULT 0x{result & 0xFFFFFFFF:08x}")

    @staticmethod
    def _iid(value):
        return (c.c_ubyte * 16).from_buffer_copy(uuid.UUID(value).bytes_le)

    @staticmethod
    def _call(pointer, slot, args, *values, result=c.c_int32):
        table = c.cast(pointer, c.POINTER(c.POINTER(c.c_void_p))).contents
        function = c.WINFUNCTYPE(result, c.c_void_p, *args)(table[slot])
        return function(pointer, *values)

    def registered_full_name(self, family):
        count, length = c.c_uint32(), c.c_uint32()
        query = self.kernel.GetPackagesByPackageFamily
        status = query(family, c.byref(count), None, c.byref(length), None)
        if status != 122 or count.value != 1 or not 1 < length.value <= 32768:
            raise OSError(status, "A unique current-user package registration is required")
        names, buffer = (c.c_wchar_p * count.value)(), c.create_unicode_buffer(length.value)
        capacity = length.value
        status = query(family, c.byref(count), names, c.byref(length), buffer)
        if status != 0 or count.value != 1 or not 1 < length.value <= capacity:
            raise OSError(status, "Package registration changed during capture")
        name = names[0]
        if not name or len(name) > 255:
            raise OSError("Invalid registered package name")
        return name

    def query(self, family):
        if getattr(self, "_cleanup_uncertain", False):
            raise PackageCacheCleanupError("Windows package-data cleanup unconfirmed")
        if getattr(self, "_query_active", False):
            raise OSError("Windows package-data query already active")
        before = self.registered_full_name(family)
        resources, initialized = [], False
        self._resources, self._query_active = resources, True

        def output(kind, function):
            pointer = c.c_void_p()
            try:
                self._check(function(c.byref(pointer)))
            finally:
                # Retain non-null failure outputs too. Never hand ownership away.
                if pointer.value:
                    resources.append([kind, pointer.value, False, False])
            if not pointer.value:
                raise OSError("Null Windows package-data output")
            return pointer.value

        def string(value):
            return output(
                "string", lambda dest: self.runtime.WindowsCreateString(value, len(value), dest)
            )

        def interface(pointer, iid):
            identity = self._iid(iid)
            return output(
                "interface",
                lambda dest: self._call(
                    pointer, 0, [c.c_void_p, c.POINTER(c.c_void_p)], c.byref(identity), dest
                ),
            )

        try:
            self._check(self.runtime.RoInitialize(1))  # RO_INIT_MULTITHREADED
            initialized = True
            factory_id = self._iid("1e1862e3-698e-49a1-9752-dee94925b9b3")
            class_name = string("Windows.Management.Core.ApplicationDataManager")
            factory = output(
                "interface",
                lambda dest: self.runtime.RoGetActivationFactory(
                    class_name, c.byref(factory_id), dest
                ),
            )
            package = string(family)
            data = output(
                "interface",
                lambda dest: self._call(
                    factory, 6, [c.c_void_p, c.POINTER(c.c_void_p)], package, dest
                ),
            )
            data2 = interface(data, "9e65cd69-0ba3-4e32-be29-b02de6607638")
            folder = output(
                "interface", lambda dest: self._call(data2, 6, [c.POINTER(c.c_void_p)], dest)
            )
            item = interface(folder, "4207a996-ca2f-42f7-bde8-8b10457a7f30")
            path = output(
                "string", lambda dest: self._call(item, 12, [c.POINTER(c.c_void_p)], dest)
            )
            length = c.c_uint32()
            raw = self.runtime.WindowsGetStringRawBuffer(path, c.byref(length))
            if not raw or not 0 < length.value < 248:
                raise OSError("Invalid package cache path")
            root = c.wstring_at(raw, length.value)
            if before != self.registered_full_name(family):
                raise OSError("Package registration changed during capture")
            return before, root
        finally:
            uncertain = False
            for resource in reversed(resources):
                kind, pointer, _, _ = resource
                resource[2] = True
                try:
                    if kind == "string":
                        self._check(self.runtime.WindowsDeleteString(pointer))
                    else:
                        self._call(pointer, 2, [], result=c.c_uint32)
                    resource[3] = True
                except BaseException:
                    uncertain = True
            if initialized:
                try:
                    self.runtime.RoUninitialize()
                except BaseException:
                    uncertain = True
            self._query_active = False
            self._cleanup_uncertain = uncertain
            if uncertain:
                raise PackageCacheCleanupError("Windows package-data cleanup unconfirmed")
