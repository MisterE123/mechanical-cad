"""Finite module-local cache metadata; no filesystem, native handles or DLLs."""

import ntpath
import threading
from dataclasses import replace

USER = bytes.fromhex("010200000000000515000000e8030000")
OTHER = bytes.fromhex("010100000000000100000000")


class MemoryCacheAPI:
    def __init__(self, cache, location):
        self.cache, self.location = cache, location
        self.paths, self.handles, self.allocations = {}, {}, {}
        self.events, self.close_calls, self.free_calls = [], [], []
        self.next_value = 100
        self.owner = None
        self.info_change = lambda value: value
        self.fail_owner_close = False
        drive, tail = ntpath.splitdrive(location.known_folder)
        path = drive + "\\"
        self.add(path)
        for part in tail[1:].split("\\"):
            if part:
                path = ntpath.join(path, part)
                self.add(path)

    def secure(self, *, directory=True):
        c = self.cache
        return c._Security(
            USER,
            True,
            True,
            tuple(
                c._Ace(sid, c._FILE_ALL_ACCESS, 3 if directory else 0)
                for sid in (USER, c._SYSTEM, c._ADMINISTRATORS)
            ),
        )

    def add(self, path, *, directory=True, security=None, **changes):
        info = self.cache._Info(
            (77, len(self.paths) + 1), path, 16 if directory else 0, True, directory, 1
        )
        self.paths[path] = (replace(info, **changes), security or self.secure(directory=directory))

    def hit(self, *event):
        assert self.owner._thread is threading.current_thread(), "metadata API left owner worker"
        self.events.append(event)

    def next(self):
        self.next_value += 1
        return self.next_value

    def open_token(self, output):
        self.hit("token_open")
        output.value = self.next()
        self.handles[output.value] = None

    def token_user(self, handle):
        self.hit("token_user", handle)
        assert self.handles[handle] is None
        return USER

    def close_handle(self, handle):
        self.hit("close", handle)
        assert handle not in self.close_calls, "uncertain close must not retry"
        self.close_calls.append(handle)
        entry = self.handles[handle]
        if (
            self.fail_owner_close
            and self.owner._state == "closing"
            and entry is not None
            and entry[0].path == self.location.cache_root
        ):
            raise OSError("injected uncertain owner close")
        del self.handles[handle]

    def allocate(self, value, output):
        output.value = self.next()
        self.allocations[output.value] = value
        return 0

    def convert_descriptor(self, sddl, output):
        self.hit("convert")
        assert (
            sddl == "O:S-1-5-21-1000D:P(A;OICI;FA;;;S-1-5-21-1000)(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)"
        )
        return self.allocate(self.secure(), output)

    def security_descriptor(self, handle, output):
        self.hit("security", self.handles[handle][0].path)
        return self.allocate(self.paths[self.handles[handle][0].path][1], output)

    def parse_security(self, pointer):
        self.hit("parse", pointer)
        assert any(resource.value == pointer for resource in self.owner._resources)
        return self.allocations[pointer]

    def local_free(self, pointer):
        self.hit("free", pointer)
        assert pointer not in self.free_calls, "uncertain free must not retry"
        self.free_calls.append(pointer)
        del self.allocations[pointer]

    def create_directory(self, path, descriptor):
        self.hit("create", path)
        assert descriptor in self.allocations
        if path in self.paths:
            return False
        self.add(path)
        return True

    def attributes(self, path):
        self.hit("attributes", path)
        return self.paths[path][0].attributes

    def open_entry(self, path, *, security):
        self.hit("open", path, security)
        handle = self.next()
        self.handles[handle] = self.paths[path]
        return handle

    def info(self, handle):
        self.hit("info", handle)
        return self.info_change(self.handles[handle][0])

    def volume(self, handle, path):
        self.hit("volume", path)
        return self.cache._Volume("NTFS", True, 255, True)
