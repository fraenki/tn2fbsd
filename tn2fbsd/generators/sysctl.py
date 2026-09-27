"""SYSCTL tunables -> /etc/sysctl.conf."""
from . import tunables


def generate(ctx):
    rows = tunables.enabled(ctx.db, "sysctl")
    if not rows:
        return

    kept, changes = tunables.prepare(rows, drop_boot_only=True)
    lines = [
        tunables.line(var, value, comment, quote=False)
        for var, value, comment in kept
    ]
    if lines:
        ctx.out.write("etc/sysctl.conf", "\n".join(lines))
    ctx.tunable_changes.extend(changes)
