"""Allow running the package with ``python3 -m cascade_windows``."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
