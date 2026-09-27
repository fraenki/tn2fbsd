"""System advanced settings (system_advanced) -> rc.conf / loader.conf.local.

These are the real, database-backed system settings. In rc.conf they are placed
after the static fallback block so they take precedence over it; loader.conf.local
is processed after loader.conf and overrides it likewise.

Mirrors the TrueNAS Core middleware (etc_files/rc.conf.py powerd_config,
etc_files/loader.py generate_serial_loader_config).
"""
from ..db import as_bool
from ..text import text


def rcconf_lines(db):
    advanced = db.one("system_advanced")
    if not advanced:
        return []
    return [f'powerd_enable="{"YES" if as_bool(advanced["adv_powerdaemon"]) else "NO"}"']


def migration_notes(db):
    """Advanced settings that have no config-file target and are documented instead."""
    advanced = db.one("system_advanced")
    notes = []
    if advanced and advanced["adv_overprovision"]:
        # Over-provisioning is applied by TrueNAS only when a LOG (SLOG) disk is
        # added to a pool (it shrinks the SSD's usable capacity via disk_resize), so
        # it has no config-file target and is documented for future SLOG additions.
        notes.append(text("notes", "overprovision", size=advanced["adv_overprovision"]))
    return notes


def loader_lines(db):
    advanced = db.one("system_advanced")
    if not advanced or not as_bool(advanced["adv_serialconsole"]):
        return []
    # The middleware picks the console string from the source machine's boot
    # method (UEFI vs BIOS) at runtime; that is not available offline, so use the
    # multi-console string that works on both BIOS and UEFI targets.
    return [
        'boot_multicons="YES"',
        'boot_serial="YES"',
        f'comconsole_port="{advanced["adv_serialport"]}"',
        f'comconsole_speed="{advanced["adv_serialspeed"]}"',
        'console="comconsole,vidconsole"',
    ]
