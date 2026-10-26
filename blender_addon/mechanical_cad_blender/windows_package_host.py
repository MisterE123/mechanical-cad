"""Bounded read-only OS package binding of this process's launcher ancestry.

No executable-name heuristic, environment selection or discovered path alias.
Package identity comes from the retained process handle and current-user OS
registration is checked separately by the application-data provider. Original
handles have one retirement attempt; uncertainty retains the owning object.
"""

import ctypes as c
import sys

from .windows_package_cache import PackageCacheCleanupError


class WindowsPackageHost:
    def __init__(self):
        if sys.platform != "win32" or c.sizeof(c.c_void_p) != 8:
            raise OSError("Windows x64 package host capture required")
        self.k = c.WinDLL("kernel32", use_last_error=True, winmode=0x800)
        self._resources, self.cleanup_uncertain = [], False
        D, H, B, W = c.c_uint32, c.c_void_p, c.c_int32, c.c_wchar_p

        class Entry(c.Structure):
            _fields_ = [
                ("size", D),
                ("usage", D),
                ("pid", D),
                ("heap", c.c_size_t),
                ("module", D),
                ("threads", D),
                ("parent", D),
                ("priority", c.c_int32),
                ("flags", D),
                ("name", c.c_wchar * 260),
            ]

        class FT(c.Structure):
            _fields_ = [("low", D), ("high", D)]

        self.Entry, self.FT = Entry, FT
        for name, args, result in (
            ("CreateToolhelp32Snapshot", [D, D], H),
            ("Process32FirstW", [H, c.POINTER(Entry)], B),
            ("Process32NextW", [H, c.POINTER(Entry)], B),
            ("GetCurrentProcessId", [], D),
            ("OpenProcess", [D, B, D], H),
            ("GetProcessId", [H], D),
            ("WaitForSingleObject", [H, D], D),
            ("GetHandleInformation", [H, c.POINTER(D)], B),
            ("GetProcessTimes", [H, *([c.POINTER(FT)] * 4)], B),
            ("GetPackageFamilyName", [H, c.POINTER(D), W], c.c_int32),
            ("GetPackageFullName", [H, c.POINTER(D), W], c.c_int32),
            ("CloseHandle", [H], B),
        ):
            function = getattr(self.k, name)
            function.argtypes, function.restype = args, result

    def _check(self, value):
        if not value:
            raise c.WinError(c.get_last_error())
        return value

    def _own(self, handle):
        if handle in (None, 0, c.c_void_p(-1).value):
            raise c.WinError(c.get_last_error())
        self._resources.append([handle, False, False])
        flags = c.c_uint32()
        self._check(self.k.GetHandleInformation(handle, c.byref(flags)))
        if flags.value & 1:
            raise OSError("Inheritable package-host capture handle")
        return handle

    def _snapshot(self):
        handle = self._own(self.k.CreateToolhelp32Snapshot(2, 0))
        entry = self.Entry()
        entry.size = c.sizeof(entry)
        self._check(self.k.Process32FirstW(handle, c.byref(entry)))
        parents = {}
        while True:
            if entry.pid in parents or len(parents) >= 4096:
                raise OSError("Ambiguous or oversized process ancestry snapshot")
            parents[entry.pid] = entry.parent
            if not self.k.Process32NextW(handle, c.byref(entry)):
                if c.get_last_error() != 18:
                    raise c.WinError(c.get_last_error())
                return parents

    def _creation(self, handle, pid):
        if self.k.GetProcessId(handle) != pid or self.k.WaitForSingleObject(handle, 0) != 258:
            raise OSError("Package-host process identity unavailable")
        times = [self.FT() for _ in range(4)]
        self._check(self.k.GetProcessTimes(handle, *[c.byref(t) for t in times]))
        return times[0].high << 32 | times[0].low

    def _package_string(self, name, handle):
        query = getattr(self.k, name)
        length = c.c_uint32()
        status = query(handle, c.byref(length), None)
        if status == 15700:  # APPMODEL_ERROR_NO_PACKAGE, not an access denial.
            return None
        if status != 122 or not 1 < length.value <= 256:
            raise OSError(status, "Package-host identity query failed")
        buffer = c.create_unicode_buffer(length.value)
        capacity = length.value
        status = query(handle, c.byref(length), buffer)
        if status != 0 or not 1 < length.value <= capacity or not buffer.value:
            raise OSError(status, "Package-host identity changed")
        return buffer.value

    def capture(self):
        if self.cleanup_uncertain:
            error = PackageCacheCleanupError("Package-host cleanup remains uncertain")
            error.owner = self
            raise error
        if self._resources:
            raise OSError("Package-host capture is one-shot")
        try:
            parents, observed = self._snapshot(), []
            pid, child_creation, selected = self.k.GetCurrentProcessId(), None, None
            for _ in range(16):
                if pid not in parents or any(item[0] == pid for item in observed):
                    raise OSError("Package-host ancestry unavailable or cyclic")
                handle = self._own(self.k.OpenProcess(0x1000 | 0x100000, False, pid))
                creation = self._creation(handle, pid)
                if child_creation is not None and creation > child_creation:
                    raise OSError("Package-host ancestor PID was recycled")
                family = self._package_string("GetPackageFamilyName", handle)
                full_name = self._package_string("GetPackageFullName", handle)
                if (family is None) != (full_name is None):
                    raise OSError("Inconsistent OS package-host identity")
                observed.append((pid, parents[pid], handle, creation, family, full_name))
                if family is not None:
                    selected = (family, full_name)
                    break
                pid, child_creation = parents[pid], creation
                if pid in (0, 4):
                    break
            else:
                raise OSError("Package-host ancestry exceeds its fixed bound")
            current = self._snapshot()
            for pid, parent, handle, creation, family, full_name in observed:
                if (
                    current.get(pid) != parent
                    or self._creation(handle, pid) != creation
                    or self._package_string("GetPackageFamilyName", handle) != family
                    or self._package_string("GetPackageFullName", handle) != full_name
                ):
                    raise OSError("Package-host identity changed during capture")
            return selected
        finally:
            for resource in reversed(self._resources):
                resource[1] = True
                try:
                    self._check(self.k.CloseHandle(resource[0]))
                    resource[2] = True
                except BaseException:
                    self.cleanup_uncertain = True
            if self.cleanup_uncertain:
                error = PackageCacheCleanupError("Package-host handle cleanup unconfirmed")
                error.owner = self
                raise error
