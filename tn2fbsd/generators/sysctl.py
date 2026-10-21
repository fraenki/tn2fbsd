"""SYSCTL tunables -> /etc/sysctl.conf."""
from . import tunables


def generate(ctx):
    rows = tunables.enabled(ctx.db, "sysctl")

    lines = []
    if rows:
        kept, changes = tunables.prepare(rows, drop_boot_only=True)
        lines = [
            tunables.line(var, value, comment, quote=False)
            for var, value, comment in kept
        ]
        ctx.tunable_changes.extend(changes)

    # Sysctls contributed by other generators run before this one (e.g. NFS).
    lines += ctx.extra_sysctls

    if lines:
        ctx.out.write("etc/sysctl.conf", "\n".join(lines))
