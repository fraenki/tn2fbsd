"""Build pw(8) commands to recreate non-builtin groups and users.

There is no configuration file for accounts; the commands are emitted into
MIGRATION.md instead. Builtin groups/users already exist on FreeBSD and are
skipped. Password hashes are applied verbatim via `pw ... -H 0`.
"""
from ..db import as_bool


def _shell_quote(value):
    return "'" + str(value).replace("'", "'\\''") + "'"


def build(db):
    groups = db.all("account_bsdgroups")
    gid_name = {g["id"]: g["bsdgrp_group"] for g in groups}

    group_cmds = [
        f"pw groupadd -n {g['bsdgrp_group']} -g {g['bsdgrp_gid']}"
        for g in sorted(groups, key=lambda g: g["bsdgrp_gid"])
        if not as_bool(g["bsdgrp_builtin"])
    ]

    memberships = {}
    for row in db.all("account_bsdgroupmembership"):
        memberships.setdefault(row["bsdgrpmember_user_id"], set()).add(
            row["bsdgrpmember_group_id"]
        )

    user_cmds = []
    users = db.all("account_bsdusers")
    for user in sorted(users, key=lambda u: u["bsdusr_uid"]):
        if as_bool(user["bsdusr_builtin"]):
            continue
        primary_id = user["bsdusr_group_id"]
        flags = [
            f"-n {user['bsdusr_username']}",
            f"-u {user['bsdusr_uid']}",
            f"-g {gid_name[primary_id]}",
        ]
        supplementary = sorted(
            gid_name[i]
            for i in memberships.get(user["id"], set())
            if i in gid_name and i != primary_id
        )
        if supplementary:
            flags.append(f"-G {','.join(supplementary)}")
        flags += [
            f"-d {user['bsdusr_home']}",
            f"-s {user['bsdusr_shell']}",
            f"-c {_shell_quote(user['bsdusr_full_name'])}",
            "-H 0",
        ]

        hash_value = user["bsdusr_unixhash"]
        if (
            as_bool(user["bsdusr_password_disabled"])
            or as_bool(user["bsdusr_locked"])
            or not hash_value
        ):
            hash_value = "*"
        user_cmds.append(f"echo {_shell_quote(hash_value)} | pw useradd {' '.join(flags)}")

    return group_cmds, user_cmds
