"""Periodic snapshot + replication tasks -> /usr/local/etc/zettarepl.yaml.

Mirrors the definition assembled by the middleware
(plugins/zettarepl.py ``get_definition``).
"""
import yaml

from .. import ASSETS_DIR, pwenc
from ..db import as_bool, json_list
from ..text import text

UNIT_SECONDS = {
    "DAY": 86400,
    "HOUR": 3600,
    "MONTH": 30 * 86400,
    "WEEK": 604800,
    "YEAR": 365 * 86400,
}


def _lifetime(value, unit):
    return f"PT{int(value) * UNIT_SECONDS[unit]}S"


def _schedule(minute, hour, daymonth, month, dayweek, begin=None, end=None):
    schedule = {
        "minute": minute,
        "hour": hour,
        "day-of-month": daymonth,
        "month": month,
        "day-of-week": dayweek,
    }
    if begin:
        schedule["begin"] = begin[:5]
    if end:
        schedule["end"] = end[:5]
    return schedule


def _periodic_snapshot_tasks(db):
    tasks = {}
    for task in db.all("storage_task", where="task_enabled=1", order="id"):
        tasks[f"task_{task['id']}"] = {
            "dataset": task["task_dataset"],
            "recursive": as_bool(task["task_recursive"]),
            "exclude": json_list(task["task_exclude"]),
            "lifetime": _lifetime(task["task_lifetime_value"], task["task_lifetime_unit"]),
            "naming-schema": task["task_naming_schema"],
            "schedule": _schedule(
                task["task_minute"], task["task_hour"], task["task_daymonth"],
                task["task_month"], task["task_dayweek"],
                task["task_begin"], task["task_end"],
            ),
            "allow-empty": as_bool(task["task_allow_empty"]),
        }
    return tasks


def _transport(ctx, repl):
    kind = repl["repl_transport"]
    if kind == "LOCAL":
        return {"type": "local"}, False

    credentials = ctx.db.one(
        "system_keychaincredential",
        where=f"id={repl['repl_ssh_credentials_id']}",
    )
    attrs = pwenc.decrypt_json(ctx.pwenc_secret, credentials["attributes"])
    key_pair = ctx.db.one(
        "system_keychaincredential", where=f"id={attrs['private_key']}"
    )
    key_attrs = pwenc.decrypt_json(ctx.pwenc_secret, key_pair["attributes"])

    transport = {
        "type": "ssh",
        "hostname": attrs["host"],
        "port": attrs.get("port", 22),
        "username": attrs.get("username", "root"),
        "private-key": key_attrs["private_key"],
        "host-key": attrs["remote_host_key"],
        "connect-timeout": attrs.get("connect_timeout", 10),
    }
    if kind == "SSH+NETCAT":
        transport["type"] = "ssh+netcat"
        transport["active-side"] = repl["repl_netcat_active_side"].lower()
        for src, dst in (
            ("repl_netcat_active_side_listen_address", "active-side-listen-address"),
            ("repl_netcat_active_side_port_min", "active-side-min-port"),
            ("repl_netcat_active_side_port_max", "active-side-max-port"),
            ("repl_netcat_passive_side_connect_address", "passive-side-connect-address"),
        ):
            if repl[src]:
                transport[dst] = repl[src]
    return transport, True


def _replication_tasks(ctx):
    tasks = {}
    uses_secret = False
    for repl in ctx.db.all("storage_replication", where="repl_enabled=1", order="id"):
        transport, secret = _transport(ctx, repl)
        uses_secret = uses_secret or secret
        definition = {
            "direction": repl["repl_direction"].lower(),
            "transport": transport,
            "source-dataset": json_list(repl["repl_source_datasets"]),
            "target-dataset": repl["repl_target_dataset"],
            "recursive": as_bool(repl["repl_recursive"]),
            "auto": as_bool(repl["repl_auto"]),
            "retention-policy": repl["repl_retention_policy"].lower(),
        }
        if json_list(repl["repl_exclude"]):
            definition["exclude"] = json_list(repl["repl_exclude"])
        naming_schema = json_list(repl["repl_naming_schema"])
        if naming_schema:
            definition["naming-schema"] = naming_schema
        bound = [
            f"task_{row['task_id']}"
            for row in ctx.db.all(
                "storage_replication_repl_periodic_snapshot_tasks",
                where=f"replication_id={repl['id']}",
            )
        ]
        if bound:
            definition["periodic-snapshot-tasks"] = bound
        if repl["repl_schedule_minute"]:
            definition["schedule"] = _schedule(
                repl["repl_schedule_minute"], repl["repl_schedule_hour"],
                repl["repl_schedule_daymonth"], repl["repl_schedule_month"],
                repl["repl_schedule_dayweek"], repl["repl_schedule_begin"],
                repl["repl_schedule_end"],
            )
        if repl["repl_retention_policy"] == "CUSTOM" and repl["repl_lifetime_value"]:
            definition["lifetime"] = _lifetime(
                repl["repl_lifetime_value"], repl["repl_lifetime_unit"]
            )
        tasks[f"task_{repl['id']}"] = definition
    return tasks, uses_secret


def generate(ctx):
    snapshot_tasks = _periodic_snapshot_tasks(ctx.db)
    replication_tasks, uses_secret = _replication_tasks(ctx)
    if not snapshot_tasks and not replication_tasks:
        return

    definition = {}
    config = ctx.db.one("storage_replication_config")
    if config and config["max_parallel_replication_tasks"] is not None:
        definition["max-parallel-replication-tasks"] = config["max_parallel_replication_tasks"]
    settings = ctx.db.one("system_settings")
    if settings and settings["stg_timezone"]:
        definition["timezone"] = settings["stg_timezone"]
    if snapshot_tasks:
        definition["periodic-snapshot-tasks"] = snapshot_tasks
    if replication_tasks:
        definition["replication-tasks"] = replication_tasks

    yaml_text = yaml.safe_dump(definition, default_flow_style=False, sort_keys=False)
    mode = 0o600 if uses_secret else 0o644
    ctx.out.write("usr/local/etc/zettarepl.yaml", yaml_text, mode=mode)
    ctx.note(text("notes", "zettarepl"), "zettarepl")
    if uses_secret:
        ctx.note(text("notes", "zettarepl_secret"), "zettarepl")
