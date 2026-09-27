# tn2fbsd

TrueNAS Core is no longer under active development, so it is time to migrate
to FreeBSD.

This tool generates FreeBSD 15 configuration files from a TrueNAS Core 13.x
configuration export.

tn2fbsd reads a TrueNAS Core configuration database and writes a `freebsd/`
directory containing configuration files at their real target paths, plus a
`MIGRATION.md` describing the remaining manual steps.

## Migration

Migrating from TrueNAS Core to FreeBSD is straightforward. Anyone with solid
UNIX/Linux experience should be able to complete it.

The migration involves several manual steps. Below is an overview of the
required migration tasks:

- Install FreeBSD 15.x on a new SSD/HDD (use a separate server with the same architecture)
- Run tn2fbsd to generate FreeBSD configuration files and a migration guide
- Copy the generated configuration files to the new FreeBSD installation
- Remove the SSD/HDD containing the TrueNAS operating system from the server
- Install the new FreeBSD SSD/HDD in the TrueNAS Core server
- Boot the server into single-user mode
- Perform the remaining manual migration steps
- Reboot into a fully functional FreeBSD server

## Requirements

- Python 3.11+
- PyYAML (`pip install -r requirements.txt`)
- `openssl` in `PATH` (used to decrypt encrypted database fields such as SSH host
  keys and replication credentials)

## Input

The input is the TrueNAS "Save Config" export created with **"Export Secret
Seed"** enabled (System -> General -> Save Config). That export is a tar archive
containing:

- `freenas-v1.db` — the configuration database
- `pwenc_secret` — the secret used to decrypt encrypted fields

## Usage

```sh
./tn2fbsd.py [-o OUTPUT] EXPORT.tar
```

- `EXPORT.tar` — the export archive described above
- `-o`, `--output` — output directory (default: `freebsd`)

Example:

```sh
./tn2fbsd.py -o freebsd truenas.tar
```

Then read `freebsd/MIGRATION.md` and follow it: copy each generated file to the
listed path on the FreeBSD system, apply the listed ownership, create the users
and groups, and install the required packages.

## Output

| Path | Contents |
| --- | --- |
| `etc/rc.conf` | Base defaults, hostname, network, service enablement, RC tunables, system_advanced settings (e.g. powerd) |
| `etc/resolv.conf`, `etc/hosts` | DNS and hosts |
| `etc/exports` | NFS exports |
| `etc/ssh/sshd_config` | Base-system sshd configuration |
| `etc/ssh/ssh_host_*` | Migrated SSH host keys (private and public) |
| `root/.ssh/authorized_keys` | root's authorized_keys (only if included in the export) |
| `etc/sysctl.conf` | SYSCTL tunables (renamed/removed OIDs translated to FreeBSD 15.1) |
| `etc/periodic.conf` | ZFS scrub tasks |
| `etc/cron.d/tn2fbsd` | Migrated cron jobs |
| `boot/loader.conf`, `boot/loader.conf.local` | Bootloader config, LOADER tunables, serial console |
| `usr/local/etc/smb4.conf` | Samba global settings and shares |
| `usr/local/etc/zettarepl.yaml` | Periodic snapshot and replication tasks |
| `usr/local/etc/rc.d/zettarepl` | rc.d service script for zettarepl |
| `MIGRATION.md` | ZFS pool import, file ownership, account creation commands, manual steps |

## Scope

Not all TrueNAS Core services will be migrated. Only the following migrations
are currently available: network, users and groups, NFS, SMB, SSH (base-system
sshd with its configuration and host keys), zettarepl (periodic snapshots and
replication), ZFS scrub tasks, cron jobs, and tunables.

Migration is not available for AFP, WebDAV, iSCSI/block shares, plugins, virtual machines,
jails, and the SNMP/SMART/NTP/FTP/rsync/DynDNS daemons.

## Web GUI

The migration does not involve setting up a GUI. However, [WebZFS](https://github.com/webzfs/webzfs)
is freely available. It is a modern web-based management interface for ZFS pools, datasets,
snapshots, and SMART disk monitoring. This should make the transition from TrueNAS Core to
FreeBSD more seamless.

## Managing disks

TrueNAS partitions every data disk with a GPT scheme, an optional swap partition
and a `freebsd-zfs` partition, then adds that partition to the pool by its GPT
partition UUID (`gptid/<uuid>`) instead of the device name (`da0p2`). The gptid
does not change when devices are renumbered, so pool membership stays stable. To
keep managing disks in the same style on FreeBSD, reproduce these steps.

### Preparing a disk

Replace `da0` with the target device. TrueNAS reserves a 2 GiB swap partition per
data disk (`swapondrive`); drop the swap line to use the whole disk for ZFS.

```sh
gpart create -s gpt da0
gpart add -a 4k -b 128 -t freebsd-swap -s 2G da0
gpart add -a 4k -t freebsd-zfs da0
```

Without a swap partition the ZFS partition takes the first slot:

```sh
gpart create -s gpt da0
gpart add -a 4k -b 128 -t freebsd-zfs da0
```

Look up the gptid of the `freebsd-zfs` partition (its `rawuuid`):

```sh
gpart list da0
```

### Creating a new pool

Partition every disk first, then create the pool from the `freebsd-zfs` gptids.
The options and dataset properties match the TrueNAS defaults (`ashift=12`,
`altroot=/mnt`, `lz4` compression, `atime=off`, passthrough ACLs):

```sh
zpool create -o ashift=12 -o autoexpand=on -o failmode=continue -o altroot=/mnt \
    -O atime=off -O compression=lz4 -O aclmode=passthrough -O aclinherit=passthrough \
    tank mirror /dev/gptid/<uuid-disk1> /dev/gptid/<uuid-disk2>
```

Use `raidz1`/`raidz2`/`raidz3` or no keyword (stripe) in place of `mirror` as
needed.

### Adding disks to an existing pool

Partition the new disks as above, then add them by gptid. A new vdev extends the
pool's capacity (match the existing vdev layout):

```sh
zpool add tank mirror /dev/gptid/<uuid-disk3> /dev/gptid/<uuid-disk4>
```

To grow an existing mirror instead, attach the new disk to a disk already in it:

```sh
zpool attach tank /dev/gptid/<uuid-existing> /dev/gptid/<uuid-new>
```

## Trademark Notice

TrueNAS® is a registered trademark of iXsystems, Inc. This software is an independent
project and is not affiliated with, sponsored by, or endorsed by iXsystems, Inc.
