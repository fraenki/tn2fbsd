"""Shared state passed to every generator."""


class Context:
    def __init__(self, db, pwenc_secret, out, root_authorized_keys=None):
        self.db = db
        self.pwenc_secret = pwenc_secret
        self.out = out
        # /root/.ssh/authorized_keys content, or None when not in the export.
        self.root_authorized_keys = root_authorized_keys
        # (category, text) manual steps collected by generators for MIGRATION.md.
        self.notes = []
        # (oid, value, change, freebsd) rows for the MIGRATION.md tunable table.
        self.tunable_changes = []

    def note(self, text, category="general"):
        self.notes.append((category, text))
