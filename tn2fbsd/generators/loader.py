"""Bootloader configuration.

/boot/loader.conf is shipped verbatim from the bundled asset for maximum
compatibility with the original TrueNAS Core system. LOADER-type tunables, the
serial-console settings and the NIC driver modules for the configured interfaces
are written to /boot/loader.conf.local (processed last, so it overrides
loader.conf).
"""
from .. import ASSETS_DIR
from ..text import text
from . import advanced, network, tunables


def generate(ctx):
    ctx.out.write("boot/loader.conf", (ASSETS_DIR / "loader.conf").read_text())

    kept, changes = tunables.prepare(tunables.enabled(ctx.db, "loader"), drop_boot_only=False)
    lines = [
        tunables.line(var, value, comment, quote=True) for var, value, comment in kept
    ]
    ctx.tunable_changes.extend(changes)
    lines += advanced.loader_lines(ctx.db)

    nic_lines, unknown_drivers = network.nic_modules(ctx.db)
    lines += nic_lines
    if unknown_drivers:
        ctx.note(text("notes", "loader_unknown_drivers", drivers=", ".join(unknown_drivers)), "network")

    if lines:
        ctx.out.write("boot/loader.conf.local", "\n".join(sorted(lines)))
