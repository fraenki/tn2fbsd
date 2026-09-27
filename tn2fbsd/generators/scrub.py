"""ZFS scrub tasks -> /etc/periodic.conf.

TrueNAS runs each scrub on its own cron schedule with a "threshold" (minimum
days between scrubs). FreeBSD's periodic(8) scrub runs daily and honours the
same threshold, so the per-task cron schedule collapses to the daily model.
"""
from ..text import text


def generate(ctx):
    scrubs = ctx.db.all("storage_scrub", where="scrub_enabled=1", order="id")
    if not scrubs:
        return
    volumes = {v["id"]: v["vol_name"] for v in ctx.db.all("storage_volume")}

    pools = []
    thresholds = []
    for scrub in scrubs:
        name = volumes.get(scrub["scrub_volume_id"])
        if not name:
            continue
        pools.append(name)
        thresholds.append(
            f'daily_scrub_zfs_{name}_threshold="{scrub["scrub_threshold"]}"'
        )

    lines = ['daily_scrub_zfs_enable="YES"', f'daily_scrub_zfs_pools="{" ".join(pools)}"']
    lines += thresholds
    ctx.out.write("etc/periodic.conf", "\n".join(lines))
    ctx.note(text("notes", "scrub"), "scrub")
