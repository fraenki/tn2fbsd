"""Load the TrueNAS configuration export.

tn2fbsd expects the "Save Config" export produced with "Export Secret Seed"
enabled. That export is a tar archive containing:

  * freenas-v1.db          -- the SQLite configuration database (required)
  * pwenc_secret           -- the 32-byte secret to decrypt pwenc fields (required)
  * root_authorized_keys   -- /root/.ssh/authorized_keys, present only if the
                              "Export authorized_keys for root" option was enabled

The members are extracted to a temporary directory for the duration of the run.
"""
import os
import tarfile
import tempfile

from .db import DB

DB_MEMBER = "freenas-v1.db"
SECRET_MEMBER = "pwenc_secret"
ROOT_AUTHORIZED_KEYS_MEMBER = "root_authorized_keys"


class SourceError(RuntimeError):
    pass


class Source:
    def __init__(self, tar_path):
        # Reject a missing, non-regular, or unreadable path before opening it.
        if not os.path.exists(tar_path):
            raise SourceError(f"{tar_path}: no such file")
        if not os.path.isfile(tar_path):
            raise SourceError(f"{tar_path}: not a regular file")
        if not os.access(tar_path, os.R_OK):
            raise SourceError(f"{tar_path}: not readable (check permissions)")
        self._tmp = tempfile.TemporaryDirectory(prefix="tn2fbsd-")
        try:
            with tarfile.open(tar_path) as tar:
                members = {os.path.basename(m.name): m for m in tar.getmembers()}
                for required in (DB_MEMBER, SECRET_MEMBER):
                    if required not in members:
                        raise SourceError(
                            f"{tar_path}: missing '{required}'. The export must be created "
                            f"with 'Export Secret Seed' enabled."
                        )
                extract = [DB_MEMBER, SECRET_MEMBER]
                if ROOT_AUTHORIZED_KEYS_MEMBER in members:
                    extract.append(ROOT_AUTHORIZED_KEYS_MEMBER)
                for name in extract:
                    member = members[name]
                    member.name = name  # flatten any leading path components
                    tar.extract(member, self._tmp.name)
        except tarfile.ReadError as exc:
            raise SourceError(f"{tar_path}: not a readable tar archive") from exc

        self.db = DB(os.path.join(self._tmp.name, DB_MEMBER))
        with open(os.path.join(self._tmp.name, SECRET_MEMBER), "rb") as handle:
            self.pwenc_secret = handle.read()

        # authorized_keys is not stored in the config database; it is only present
        # here when the "Export authorized_keys for root" option was enabled.
        self.root_authorized_keys = None
        keys_path = os.path.join(self._tmp.name, ROOT_AUTHORIZED_KEYS_MEMBER)
        if os.path.exists(keys_path):
            with open(keys_path, encoding="utf8") as handle:
                self.root_authorized_keys = handle.read()

    def close(self):
        self.db.close()
        self._tmp.cleanup()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
