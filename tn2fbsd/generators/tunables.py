"""Shared helpers for TrueNAS "Tunables" (system_tunable).

Type mapping (tun_type is stored lowercase in the database):
  * sysctl -> /etc/sysctl.conf
  * loader -> /boot/loader.conf.local
  * rc     -> /etc/rc.conf

TrueNAS Core 13.x is based on FreeBSD 13; some sysctls were renamed or removed
by FreeBSD 15.1. A tunable is translated against reference data:

  * RENAMES  legacy OID -> FreeBSD 15.1 OID (data/freebsd15_sysctl_renames.tsv),
  * VALID    the configurable FreeBSD 15.1 sysctl OIDs in the covered tuning
             namespaces (data/freebsd15_sysctl_oids.txt).

A tunable whose OID is in RENAMES is rewritten. A tunable in a covered namespace
(see _COVERED) is kept when its OID is in VALID and dropped when it is not. Every
other tunable is kept unchanged, so anything uncertain is carried over to FreeBSD
for the user to review.
"""
import re
from pathlib import Path

_DATA = Path(__file__).resolve().parent.parent / "data"

VALID = frozenset((_DATA / "freebsd15_sysctl_oids.txt").read_text().split())

RENAMES = {}
for _row in (_DATA / "freebsd15_sysctl_renames.tsv").read_text().splitlines():
    if "\t" in _row:
        _old, _new = _row.split("\t", 1)
        RENAMES[_old] = _new

# Namespaces whose configurable sysctls VALID lists in full; a covered OID absent
# from VALID was removed on 15.1. Matches the filter that builds VALID.
_COVERED = ("vfs.", "net.", "kern.", "vm.", "security.")
_PER_INSTANCE = re.compile(r"\.\d+(\.|$)")

# Exist on FreeBSD 15.1 but are boot-time tunables that cannot be lowered from
# sysctl.conf at runtime ("Invalid argument"). Dropped from sysctl.conf only.
BOOT_ONLY = {"kern.ipc.nmbclusters"}


def _covered(var):
    """Whether VALID lists this OID's namespace in full, so absence means removed."""
    if not var.startswith(_COVERED):
        return False
    if var.startswith(("vm.uma.", "vm.stats.")):
        return False
    return not _PER_INSTANCE.search(var)


def _translate(var):
    """Return (new_var, action) with action in {"keep", "rename", "drop"}."""
    if var in RENAMES:
        return RENAMES[var], "rename"
    if _covered(var) and var not in VALID:
        return var, "drop"
    return var, "keep"


def enabled(db, tun_type):
    return db.all(
        "system_tunable",
        where=f"tun_enabled=1 AND tun_type='{tun_type}'",
        order="id",
    )


def prepare(rows, drop_boot_only):
    """Apply FreeBSD 15.1 renames and drop removed tunables.

    Returns (kept, changes): kept is a list of (var, value, comment) tuples with
    renames applied, sorted by the final variable name; changes is a list of
    (oid, value, change, freebsd) tuples describing each renamed, removed or
    boot-only tunable for the MIGRATION.md table.
    """
    kept, changes = [], []
    for row in rows:
        var = row["tun_var"]
        value = row["tun_value"]
        if drop_boot_only and var in BOOT_ONLY:
            changes.append((var, value, "boot-only", "set in /boot/loader.conf"))
            continue
        new_var, action = _translate(var)
        if action == "drop":
            changes.append((var, value, "removed", "—"))
            continue
        if action == "rename":
            changes.append((var, value, "renamed", new_var))
        kept.append((new_var, value, row["tun_comment"]))
    kept.sort(key=lambda entry: entry[0])
    return kept, changes


def line(var, value, comment, quote):
    rendered = f'"{value}"' if quote else value
    result = f"{var}={rendered}"
    if comment:
        result += f"  # {comment}"
    return result
