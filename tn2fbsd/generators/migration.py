"""Assemble freebsd/MIGRATION.md.

Must run last, after every other generator, so out.records and ctx.notes are
complete. Prose lives in data/messages.toml (see tn2fbsd.text).
"""
import json

from ..text import text
from . import advanced, users

# Manual steps are grouped by topic in this order.
_CATEGORY_ORDER = [
    "pools", "network", "tunables", "nfs", "smb", "ssh", "zettarepl", "scrub",
    "cron", "disks", "general",
]


def _pool_of(path):
    """Return the pool name from a /mnt/<pool>/... path, or None."""
    if path and path.startswith("/mnt/"):
        parts = path.strip("/").split("/")
        if len(parts) >= 2:
            return parts[1]
    return None


def _referenced_pools(db):
    """Pool names appearing in share/home paths."""
    pools = set()
    for row in db.all("sharing_nfs_share"):
        for path in json.loads(row["nfs_paths"] or "[]"):
            pools.add(_pool_of(path))
    for row in db.all("sharing_cifs_share"):
        pools.add(_pool_of(row["cifs_path"]))
    for row in db.all("account_bsdusers", where="bsdusr_builtin=0"):
        pools.add(_pool_of(row["bsdusr_home"]))
    pools.discard(None)
    return pools


def _table(headers, rows):
    """Render a GitHub-flavoured markdown table; cells are escaped for pipes."""
    def cell(value):
        return str(value).replace("|", "\\|")

    out = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    out += ["| " + " | ".join(cell(c) for c in row) + " |" for row in rows]
    return out


def _zfs_pools_section(db):
    volumes = db.all("storage_volume", order="vol_name")
    if not volumes:
        return []

    commands = ["zpool import"]
    for volume in volumes:
        name = volume["vol_name"]
        commands.append(f"zpool import -f -N -o cachefile=/etc/zfs/zpool.cache {name}")
        commands.append(f"zfs set mountpoint=/mnt/{name} {name}")
    commands.append("zfs mount -a")

    lines = ["## ZFS pools", "", text("zfs", "intro"), "", "```sh", *commands, "```",
             "", text("zfs", "verify")]
    encrypted = [v["vol_name"] for v in volumes if v["vol_encrypt"]]
    if encrypted:
        lines += ["", text("zfs", "encrypted", pools=", ".join(encrypted))]
    return lines


def _ownership_section(records):
    rows = [
        (f"`/{r['path']}`", r["owner"], r["group"], f"{r['mode']:04o}")
        for r in sorted(records, key=lambda r: r["path"])
    ]
    return (
        ["## File ownership", "", text("migration", "ownership_intro"), ""]
        + _table(["File", "Owner", "Group", "Mode"], rows)
    )


def _tunable_changes_section(changes):
    renamed = sorted((c for c in changes if c[2] == "renamed"), key=lambda c: c[0])
    removed = sorted((c for c in changes if c[2] == "removed"), key=lambda c: c[0])

    rows = []
    if renamed:
        rows += ["## Renamed tunables", "", text("tunables", "renamed_intro"), ""]
        rows += _table(
            ["TrueNAS OID", "New OID"],
            [(f"`{oid}`", f"`{fb}`") for oid, _v, _c, fb in renamed],
        )
    if removed:
        if rows:
            rows.append("")
        rows += ["## Removed tunables", "", text("tunables", "removed_intro"), ""]
        rows += _table(
            ["TrueNAS OID", "Value"],
            [(f"`{oid}`", f"`{value}`") for oid, value, _c, _fb in removed],
        )
    return rows


def _manual_steps(ctx):
    # (category, text); categories are ordered by _CATEGORY_ORDER, insertion order
    # is kept within a category (stable sort) so related notes stay together.
    notes = list(ctx.notes)
    for oid, value, change, _fb in ctx.tunable_changes:
        if change == "boot-only":
            notes.append(("tunables", text("tunables", "boot_only", oid=oid, value=value)))

    known_pools = {v["vol_name"] for v in ctx.db.all("storage_volume")}
    extra_pools = sorted(_referenced_pools(ctx.db) - known_pools)
    if extra_pools:
        notes.append(("pools", text("notes", "extra_pools", pools=", ".join(extra_pools))))

    notes += [("disks", note) for note in advanced.migration_notes(ctx.db)]

    smb_users = ctx.db.all("account_bsdusers", where="bsdusr_smb=1 AND bsdusr_builtin=0")
    if smb_users:
        names = ", ".join(u["bsdusr_username"] for u in smb_users)
        notes.append(("smb", text("notes", "smb_auth", names=names)))

    notes.append(("general", text("notes", "pkg_install")))

    rank = {category: index for index, category in enumerate(_CATEGORY_ORDER)}
    notes.sort(key=lambda note: rank.get(note[0], len(_CATEGORY_ORDER)))
    return [note_text for _category, note_text in notes]


def generate(ctx):
    group_cmds, user_cmds = users.build(ctx.db)

    lines = ["# Migration notes", "", text("migration", "intro"), ""]
    lines += _zfs_pools_section(ctx.db)
    lines += [""] + _ownership_section(ctx.out.records)

    if group_cmds:
        lines += ["", "## Groups", "", "```sh", *group_cmds, "```"]
    if user_cmds:
        lines += ["", "## Users", "", text("migration", "users_intro"), "",
                  "```sh", *user_cmds, "```"]

    changes_section = _tunable_changes_section(ctx.tunable_changes)
    if changes_section:
        lines += ["", *changes_section]

    lines += ["", "## Manual steps", ""]
    lines += [f"- {note}" for note in _manual_steps(ctx)]

    ctx.out.write("MIGRATION.md", "\n".join(lines))
