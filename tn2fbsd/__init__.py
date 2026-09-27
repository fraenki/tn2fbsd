"""tn2fbsd: migrate a TrueNAS Core 13.x configuration to FreeBSD 15.1 config files."""
import sys

# Keep the project tree free of __pycache__/.pyc artifacts.
sys.dont_write_bytecode = True

from pathlib import Path

__version__ = "0.1.0"

# Static assets live next to the package, in the project root's "assets" directory.
ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
