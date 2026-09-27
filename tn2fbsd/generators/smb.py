"""SMB shares + service -> /usr/local/etc/smb4.conf.

A standards-compliant smb.conf is produced for the FreeBSD samba package: a
[global] section derived from services_cifs and one inline section per enabled
share derived from sharing_cifs_share, using the VFS objects available in the
stock FreeBSD samba build. MIGRATION.md documents the registry.tdb fallback for
exact TrueNAS fidelity.
"""
from ..db import as_bool
from ..text import text

LOG_LEVELS = {"DEBUG": "10", "FULL": "3", "MINIMUM": "1", "NONE": "0", "NORMAL": "2"}


def _parse_aux(text):
    """Yield (key, value) pairs from an auxiliary smb.conf block."""
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        yield key.strip(), value.strip()


def _global_section(config):
    lines = ["[global]"]

    def put(key, value):
        lines.append(f"    {key} = {value}")

    put("workgroup", config["cifs_srv_workgroup"].upper())
    put("server string", config["cifs_srv_description"])
    put("netbios name", config["cifs_srv_netbiosname"])
    if config["cifs_srv_netbiosalias"]:
        put("netbios aliases", config["cifs_srv_netbiosalias"])
    put("server role", "standalone")
    put("unix charset", config["cifs_srv_unixcharset"])
    put("log level", LOG_LEVELS.get(str(config["cifs_srv_loglevel"]).upper(),
                                    str(config["cifs_srv_loglevel"])))
    put("logging", "syslog" if as_bool(config["cifs_srv_syslog"]) else "file")

    if as_bool(config["cifs_srv_enable_smb1"]):
        put("server min protocol", "NT1")
    else:
        put("server min protocol", "SMB2_02")
        put("unix extensions", "no")

    put("create mask", config["cifs_srv_filemask"])
    put("directory mask", config["cifs_srv_dirmask"])
    if config["cifs_srv_guest"] and config["cifs_srv_guest"] != "nobody":
        put("guest account", config["cifs_srv_guest"])
    if as_bool(config["cifs_srv_ntlmv1_auth"]):
        put("ntlm auth", "yes")
    if config["cifs_srv_bindip"]:
        put("interfaces", f"127.0.0.1 {config['cifs_srv_bindip']}")
        put("bind interfaces only", "yes")
    if as_bool(config["cifs_srv_aapl_extensions"]):
        put("fruit:aapl", "yes")

    for key, value in _parse_aux(config["cifs_srv_smb_options"]):
        put(key, value)
    return lines


def _share_section(share, aapl_extensions):
    name = "homes" if as_bool(share["cifs_home"]) else share["cifs_name"]
    params = {}

    path = share["cifs_path"] or ""
    if as_bool(share["cifs_home"]):
        path = f"{path}/%U" if path else "%U"
    params["path"] = path
    if share["cifs_comment"]:
        params["comment"] = share["cifs_comment"]
    params["read only"] = "yes" if as_bool(share["cifs_ro"]) else "no"
    params["browseable"] = "yes" if as_bool(share["cifs_browsable"]) else "no"
    if as_bool(share["cifs_guestok"]):
        params["guest ok"] = "yes"
    if share["cifs_hostsallow"]:
        params["hosts allow"] = share["cifs_hostsallow"]
    if share["cifs_hostsdeny"]:
        params["hosts deny"] = share["cifs_hostsdeny"]
    if as_bool(share["cifs_abe"]):
        params["access based share enum"] = "yes"

    vfs = []
    if as_bool(share["cifs_recyclebin"]):
        vfs.append("recycle")
    if as_bool(share["cifs_aapl_name_mangling"]):
        vfs.append("catia")
    if aapl_extensions or as_bool(share["cifs_timemachine"]):
        vfs.append("fruit")
    if as_bool(share["cifs_streams"]) or "fruit" in vfs:
        vfs.append("streams_xattr")
    if as_bool(share["cifs_shadowcopy"]) or as_bool(share["cifs_fsrvp"]):
        vfs.append("shadow_copy2")
    if vfs:
        params["vfs objects"] = " ".join(vfs)
    if as_bool(share["cifs_timemachine"]):
        params["fruit:time machine"] = "yes"
    if as_bool(share["cifs_recyclebin"]):
        params["recycle:repository"] = ".recycle/%U"
        params["recycle:keeptree"] = "yes"

    for key, value in _parse_aux(share["cifs_auxsmbconf"]):
        if key == "vfs objects" and not value:
            params.pop("vfs objects", None)
            continue
        params[key] = value

    lines = [f"[{name}]"]
    lines += [f"    {key} = {value}" for key, value in params.items()]
    return lines


def generate(ctx):
    config = ctx.db.one("services_cifs")
    if not config:
        return
    aapl = as_bool(config["cifs_srv_aapl_extensions"])

    blocks = ["\n".join(_global_section(config))]
    shares = ctx.db.all("sharing_cifs_share", where="cifs_enabled=1", order="id")
    for share in shares:
        blocks.append("\n".join(_share_section(share, aapl)))

    ctx.out.write("usr/local/etc/smb4.conf", "\n\n".join(blocks))
    ctx.note(text("notes", "smb_install"), "smb")
    if shares:
        ctx.note(text("notes", "smb"), "smb")
