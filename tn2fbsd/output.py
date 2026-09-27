"""Output tree writer.

Files are written under the output directory at their real FreeBSD target path
(e.g. ``etc/rc.conf``). The target mode is recorded, together with owner/group, so
MIGRATION.md can list the ``chown``/``chmod`` for the FreeBSD system.
"""
import os


class OutputTree:
    def __init__(self, root):
        self.root = root
        self.records = []

    def write(self, relpath, content, owner="root", group="wheel", mode=0o644):
        target = os.path.join(self.root, relpath)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        if not content.endswith("\n"):
            content += "\n"
        # Drop any existing file first.
        if os.path.lexists(target):
            os.unlink(target)
        with open(target, "w", encoding="utf8") as handle:
            handle.write(content)
        # Apply the recorded target mode but always keep it writable by the owner.
        os.chmod(target, mode | 0o200)
        self.records.append(
            {"path": relpath, "owner": owner, "group": group, "mode": mode}
        )
