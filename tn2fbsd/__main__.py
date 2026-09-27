"""Command-line entry point."""
import argparse
import sys

from .context import Context
from .generators import (
    cron,
    loader,
    migration,
    network,
    nfs,
    rcconf,
    scrub,
    smb,
    ssh,
    sysctl,
    zettarepl,
)
from .output import OutputTree
from .source import Source, SourceError

# migration must run last so it can report every written file and note.
GENERATORS = [network, rcconf, loader, sysctl, nfs, smb, ssh, scrub, cron, zettarepl, migration]


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="tn2fbsd",
        description="Generate FreeBSD 15.1 configuration from a TrueNAS Core 13.x "
        "configuration export.",
    )
    parser.add_argument(
        "export",
        help="TrueNAS 'Save Config' tar archive created with 'Export Secret Seed'.",
    )
    parser.add_argument(
        "-o", "--output", default="freebsd",
        help="Output directory (default: freebsd).",
    )
    args = parser.parse_args(argv)

    try:
        with Source(args.export) as source:
            out = OutputTree(args.output)
            ctx = Context(source.db, source.pwenc_secret, out, source.root_authorized_keys)
            for generator in GENERATORS:
                generator.generate(ctx)
    except SourceError as exc:
        print(f"tn2fbsd: {exc}", file=sys.stderr)
        return 1

    print(f"tn2fbsd: wrote {len(out.records)} files to {args.output}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
