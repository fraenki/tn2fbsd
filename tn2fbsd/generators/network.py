"""Network configuration.

TrueNAS Core does not store the network configuration in rc.conf; it configures
interfaces live. These functions reconstruct the equivalent rc.conf(5) directives
following the field semantics of the middleware (plugins/interface/*.py and
plugins/network.py).
"""
from ..db import as_bool, json_list, words

# NIC interface-name prefix -> loader module for drivers that are loadable kernel
# modules on FreeBSD 15.1. The module name is not always derivable from the
# interface name (mlxen -> mlx4en, igb -> if_em), so the mapping is explicit and
# verified against the driver manpages. TrueNAS loads these drivers, but on stock
# FreeBSD they are not all in GENERIC and must be loaded via loader.conf.
NIC_MODULES = {
    "bge": "if_bge",
    "bnxt": "if_bnxt",
    "em": "if_em",
    "igb": "if_em",
    "ix": "if_ix",
    "ixl": "if_ixl",
    "lem": "if_em",
    "mce": "mlx5en",
    "mlxen": "mlx4en",
    "oce": "if_oce",
    "re": "if_re",
    "vtnet": "if_vtnet",
}


def fqdn(gc):
    host = gc["gc_hostname"]
    domain = gc["gc_domain"]
    return f"{host}.{domain}" if domain else host


def _addr_tokens(row):
    """ifconfig arguments describing a single interface's addressing."""
    tokens = []
    if as_bool(row["int_dhcp"]):
        tokens.append("DHCP")
    elif row["int_ipv4address"]:
        tokens.append(f"inet {row['int_ipv4address']}/{row['int_v4netmaskbit']}")
    if row["int_ipv6address"]:
        tokens.append(f"inet6 {row['int_ipv6address']}/{row['int_v6netmaskbit']}")
    if row["int_mtu"]:
        tokens.append(f"mtu {row['int_mtu']}")
    options = words(row["int_options"])
    tokens.extend(options)
    if "up" not in options and "down" not in options:
        tokens.append("up")
    return tokens


def _iface_lines(name, row, aliases, prefix_tokens=()):
    lines = []
    tokens = list(prefix_tokens) + _addr_tokens(row)
    lines.append(f'ifconfig_{name}="{" ".join(tokens)}"')
    if as_bool(row["int_ipv6auto"]):
        lines.append(f'ifconfig_{name}_ipv6="inet6 accept_rtadv"')
    index = 0
    for alias in aliases:
        if alias["alias_interface_id"] != row["id"]:
            continue
        if alias["alias_v4address"]:
            lines.append(
                f'ifconfig_{name}_alias{index}="inet {alias["alias_v4address"]}'
                f'/{alias["alias_v4netmaskbit"]}"'
            )
            index += 1
        if alias["alias_v6address"]:
            lines.append(
                f'ifconfig_{name}_alias{index}="inet6 {alias["alias_v6address"]}'
                f'/{alias["alias_v6netmaskbit"]}"'
            )
            index += 1
    return lines


def rcconf_lines(db):
    """Return the network-related rc.conf lines (interfaces, routes, gateway)."""
    gc = db.one("network_globalconfiguration")
    interfaces = {r["id"]: r for r in db.all("network_interfaces")}
    by_name = {r["int_interface"]: r for r in interfaces.values()}
    laggs = db.all("network_lagginterface")
    lagg_members = db.all("network_lagginterfacemembers", order="lagg_ordernum")
    vlans = db.all("network_vlan")
    bridges = db.all("network_bridge")
    aliases = db.all("network_alias")
    routes = db.all("network_staticroute")

    lagg_names = [interfaces[lg["lagg_interface_id"]]["int_interface"] for lg in laggs]
    vlan_names = [v["vlan_vint"] for v in vlans]
    bridge_names = [interfaces[b["interface_id"]]["int_interface"] for b in bridges]
    member_names = {m["lagg_physnic"] for m in lagg_members}
    handled = set(lagg_names) | set(vlan_names) | set(bridge_names) | member_names

    lines = []
    # All cloned pseudo-interfaces are created via cloned_interfaces.
    cloned = lagg_names + vlan_names + bridge_names
    if cloned:
        lines.append(f'cloned_interfaces="{" ".join(cloned)}"')

    for lg in laggs:
        ifrow = interfaces[lg["lagg_interface_id"]]
        name = ifrow["int_interface"]
        members = [
            m["lagg_physnic"]
            for m in lagg_members
            if m["lagg_interfacegroup_id"] == lg["id"]
        ]
        prefix = [f"laggproto {lg['lagg_protocol']}"]
        prefix += [f"laggport {member}" for member in members]
        lines += _iface_lines(name, ifrow, aliases, prefix)

    for member in sorted(member_names):
        lines.append(f'ifconfig_{member}="up"')

    # ifconfig(8) requires the vlan tag and vlandev parent to be set together, so
    # they are supplied as create_args (ifconfig <name> create ...); the
    # ifconfig_<name> line then carries only the address.
    for vlan in vlans:
        name = vlan["vlan_vint"]
        create_args = f"vlan {vlan['vlan_tag']} vlandev {vlan['vlan_pint']}"
        if vlan["vlan_pcp"] is not None:
            create_args += f" vlanpcp {vlan['vlan_pcp']}"
        lines.append(f'create_args_{name}="{create_args}"')
        ifrow = by_name.get(name)
        if ifrow:
            lines += _iface_lines(name, ifrow, aliases)
        else:
            lines.append(f'ifconfig_{name}="up"')

    for bridge in bridges:
        ifrow = interfaces[bridge["interface_id"]]
        prefix = [f"addm {member}" for member in json_list(bridge["members"])]
        lines += _iface_lines(ifrow["int_interface"], ifrow, aliases, prefix)

    for row in interfaces.values():
        name = row["int_interface"]
        if name in handled:
            continue
        configured = (
            as_bool(row["int_dhcp"])
            or row["int_ipv4address"]
            or row["int_ipv6address"]
            or as_bool(row["int_ipv6auto"])
            or words(row["int_options"])
        )
        if not configured:
            continue
        lines += _iface_lines(name, row, aliases)

    if gc["gc_ipv4gateway"]:
        lines.append(f'defaultrouter="{gc["gc_ipv4gateway"]}"')
    if gc["gc_ipv6gateway"]:
        lines.append(f'ipv6_defaultrouter="{gc["gc_ipv6gateway"]}"')

    v4_routes, v6_routes = [], []
    for route in routes:
        name = f"net{route['id']}"
        entry = f'-net {route["sr_destination"]} {route["sr_gateway"]}'
        if ":" in route["sr_destination"]:
            v6_routes.append(name)
            lines.append(f'ipv6_route_{name}="{entry}"')
        else:
            v4_routes.append(name)
            lines.append(f'route_{name}="{entry}"')
    if v4_routes:
        lines.append(f'static_routes="{" ".join(v4_routes)}"')
    if v6_routes:
        lines.append(f'ipv6_static_routes="{" ".join(v6_routes)}"')

    return lines


def nic_modules(db):
    """Return (loader lines, unknown prefixes) for the physical NIC drivers.

    Loads the kernel module of every configured physical interface (standalone
    NICs plus lagg/bridge members) so the interface exists at boot on FreeBSD.
    """
    interfaces = {r["id"]: r for r in db.all("network_interfaces")}
    laggs = db.all("network_lagginterface")
    bridges = db.all("network_bridge")
    virtual = {interfaces[lg["lagg_interface_id"]]["int_interface"] for lg in laggs}
    virtual |= {v["vlan_vint"] for v in db.all("network_vlan")}
    virtual |= {interfaces[b["interface_id"]]["int_interface"] for b in bridges}

    physical = {r["int_interface"] for r in interfaces.values()} - virtual
    physical |= {m["lagg_physnic"] for m in db.all("network_lagginterfacemembers")}
    for bridge in bridges:
        physical |= set(json_list(bridge["members"]))

    modules, unknown = set(), set()
    for name in physical:
        prefix = name.rstrip("0123456789")
        module = NIC_MODULES.get(prefix)
        if module:
            modules.add(f'{module}_load="YES"')
        else:
            unknown.add(prefix)
    return sorted(modules), sorted(unknown)


def generate(ctx):
    gc = ctx.db.one("network_globalconfiguration")

    resolv = []
    search = ([gc["gc_domain"]] if gc["gc_domain"] else []) + words(gc["gc_domains"])
    if search:
        resolv.append(f"search {' '.join(search)}")
    for key in ("gc_nameserver1", "gc_nameserver2", "gc_nameserver3"):
        if gc[key]:
            resolv.append(f"nameserver {gc[key]}")
    if resolv:
        ctx.out.write("etc/resolv.conf", "\n".join(resolv))

    name = gc["gc_hostname"]
    hosts = [
        "::1\t\t\tlocalhost",
        "127.0.0.1\t\tlocalhost",
        f"127.0.0.1\t\t{fqdn(gc)} {name}",
    ]
    if gc["gc_hosts"]:
        hosts.append(gc["gc_hosts"].rstrip("\n"))
    ctx.out.write("etc/hosts", "\n".join(hosts))
