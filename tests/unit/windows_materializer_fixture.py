"""Host-file composition with fake Win32 metadata; never native qualification.

Only OS leaves are replaced. The caller supplies its own imported cache module,
so release, owner, info and ACL records retain their exact production identities.
This helper has no pytest dependency and can run in the isolated builder child.
"""

import os
import stat
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

USER = bytes.fromhex("010200000000000515000000e8030000")


def short_root(tmp_path):
    """Keep stage + bundle ID inside the production Windows path budget."""
    return Path(tempfile.mkdtemp(prefix="wm-", dir=tmp_path.parent))


def publish_inert_zip(source, destination):
    """Explicit unit double, not evidence for atomic hard-link publication."""
    with Path(source).open("rb") as incoming, Path(destination).open("xb") as outgoing:
        outgoing.write(incoming.read())


class FileMetadataAPI:
    """Real inert files, explicit synthetic NTFS/security/handle observations."""

    def __init__(self, cache_module):
        self.w = cache_module
        self.handles, self.allocations, self.events = {}, {}, []
        self.closed, self.freed = [], []
        self.next_value = 100
        self.owner = None
        self.security_path = ""
        self.info_change = lambda value: value
        self.security_change = lambda value: value
        self.hook = lambda event: None

    def hit(self, *event):
        self.events.append(event)
        self.hook(event)

    def new_value(self):
        self.next_value += 1
        return self.next_value

    def secure(self, directory=True):
        w = self.w
        return w._Security(
            USER,
            True,
            True,
            tuple(
                w._Ace(sid, w._FILE_ALL_ACCESS, 3 if directory else 0)
                for sid in (USER, w._SYSTEM, w._ADMINISTRATORS)
            ),
        )

    def open_token(self, output):
        output.value = self.new_value()
        self.handles[output.value] = None
        self.hit("token_open", output.value)

    def token_user(self, handle):
        assert self.handles[handle] is None
        return USER

    def close_handle(self, handle):
        assert handle not in self.closed, "uncertain close must never retry"
        self.closed.append(handle)
        self.hit("close", handle)
        del self.handles[handle]

    def allocate(self, value, output):
        output.value = self.new_value()
        self.allocations[output.value] = value
        return 0

    def convert_descriptor(self, sddl, output):
        assert sddl == (
            "O:S-1-5-21-1000D:P(A;OICI;FA;;;S-1-5-21-1000)(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)"
        )
        return self.allocate(self.secure(), output)

    def security_descriptor(self, handle, output):
        self.security_path = self.handles[handle]
        info = self.observe(self.security_path)
        return self.allocate(self.secure(info.directory), output)

    def parse_security(self, pointer):
        assert any(r.value == pointer for r in self.owner._resources)
        return self.security_change(self.allocations[pointer])

    def local_free(self, pointer):
        assert pointer not in self.freed, "uncertain free must never retry"
        self.freed.append(pointer)
        self.hit("free", pointer)
        del self.allocations[pointer]

    def create_directory(self, path, descriptor):
        assert descriptor in self.allocations
        self.hit("create", path)
        try:
            Path(path).mkdir()
        except FileExistsError:
            return False
        return True

    def observe(self, path):
        info = os.lstat(path)
        directory = stat.S_ISDIR(info.st_mode)
        return self.w._Info(
            (info.st_dev, info.st_ino),
            str(path),
            getattr(info, "st_file_attributes", 16 if directory else 0),
            True,
            directory,
            info.st_nlink,
        )

    def attributes(self, path):
        self.hit("attributes", str(path))
        return self.observe(path).attributes

    def open_entry(self, path, *, security):
        handle = self.new_value()
        self.handles[handle] = str(path)
        self.hit("open", str(path), security)
        return handle

    def info(self, handle):
        return self.info_change(self.observe(self.handles[handle]))

    def volume(self, handle, path):
        self.hit("volume", str(path))
        return self.w._Volume("NTFS", True, 255, True)


class ComposedStorage:
    def __init__(self, cache_module, package, known, release):
        self.w, self.package, self.known, self.release = cache_module, package, known, release
        self.cache = known / "MechanicalCAD" / "r"
        self.attempts = []
        self.configure = lambda owner, api: None
        self.cancelled = lambda: False

    def invoke(self, operation, **options):
        w = self.w

        def forbidden(*args, **kwargs):
            raise AssertionError("composed unit fixture must not bind native Windows APIs")

        def worker():
            api = FileMetadataAPI(w)
            owner = w.WindowsCacheOwner(
                w.WindowsCacheLocation(str(self.known), str(self.cache)),
                package_root=str(self.package),
                expected_platform="windows-x64",
                release=self.release,
                api=api,
            )
            api.owner = owner
            self.attempts.append((owner, api))
            self.configure(owner, api)
            try:
                owner.acquire(cancelled=self.cancelled)
                return operation(
                    str(self.package), str(self.cache), windows_storage=owner, **options
                )
            finally:
                if not owner.cleanup_uncertain:
                    owner.close()
                    assert not api.handles and not api.allocations
                    assert all(r.closed for r in owner._resources)

        with patch.object(w, "_WindowsAPI", forbidden):
            with patch.object(w.ctypes, "WinDLL", forbidden, create=True):
                with ThreadPoolExecutor(max_workers=1) as pool:
                    return pool.submit(worker).result(timeout=30)
