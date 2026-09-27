"""NFS shares -> /etc/exports, and NFS service flags -> /etc/rc.conf.

Mirrors the middleware exports builder (etc_files/nfsd.py, plugins/nfs.py).
"""
from ..db import as_bool, json_list, words


def _share_lines(share, v4_enabled):
    paths = [p.rstrip("/") for p in json_list(share["nfs_paths"])]
    if not paths:
        return []

    options = []
    if as_bool(share["nfs_alldirs"]):
        options.append("-alldirs")
    if as_bool(share["nfs_ro"]):
        options.append("-ro")
    if as_bool(share["nfs_quiet"]):
        options.append("-quiet")

    # mapall takes precedence over maproot; they are mutually exclusive.
    if share["nfs_mapall_user"]:
        mapping = f'-mapall="{share["nfs_mapall_user"]}"'
        if share["nfs_mapall_group"]:
            mapping += f':"{share["nfs_mapall_group"]}"'
        options.append(mapping)
    elif share["nfs_maproot_user"]:
        mapping = f'-maproot="{share["nfs_maproot_user"]}"'
        if share["nfs_maproot_group"]:
            mapping += f':"{share["nfs_maproot_group"]}"'
        options.append(mapping)

    security = [s.lower() for s in words(share["nfs_security"].replace(",", " "))]
    if v4_enabled and security:
        options.append("-sec=" + ":".join(security))

    networks = words(share["nfs_network"])
    hosts = words(share["nfs_hosts"])
    head = paths + options

    lines = []
    for network in networks:
        lines.append(" ".join(head + ["-network", network]))
    if hosts:
        lines.append(" ".join(head + hosts))
    if not networks and not hosts:
        lines.append(" ".join(head))
    return lines


def generate(ctx):
    config = ctx.db.one("services_nfs")
    shares = ctx.db.all("sharing_nfs_share", where="nfs_enabled=1", order="id")
    if not shares:
        return

    v4_enabled = bool(config and as_bool(config["nfs_srv_v4"]))
    lines = []
    if v4_enabled:
        lines.append("V4: / -sec=sys")
    for share in shares:
        lines += _share_lines(share, v4_enabled)
    ctx.out.write("etc/exports", "\n".join(lines))


def rcconf_lines(db):
    """NFS service flags for rc.conf (enablement is handled by rcconf.py)."""
    config = db.one("services_nfs")
    if not config:
        return []

    mountd = ["-rS"]
    if as_bool(config["nfs_srv_mountd_log"]):
        mountd.append("-l")
    if config["nfs_srv_mountd_port"]:
        mountd += ["-p", str(config["nfs_srv_mountd_port"])]

    server = ["-t", "-n", str(config["nfs_srv_servers"])]
    if as_bool(config["nfs_srv_udp"]):
        server.append("-u")

    statd = []
    bindip = config["nfs_srv_bindip"]
    lines = []
    if bindip:
        mountd += ["-h", bindip]
        server += ["-h", bindip]
        statd += ["-h", bindip]
        lines.append(f'rpcbind_flags="-h {bindip}"')

    lines.append(f'mountd_flags="{" ".join(mountd)}"')
    lines.append(f'nfs_server_flags="{" ".join(server)}"')
    if statd:
        lines.append(f'rpc_statd_flags="{" ".join(statd)}"')
    if as_bool(config["nfs_srv_v4"]):
        lines.append('nfsv4_server_enable="YES"')
    return lines
