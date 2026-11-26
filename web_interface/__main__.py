"""``python -m web_interface`` starts the local app on 127.0.0.1."""

import sys

from web_interface.server import main

if __name__ == "__main__":
    sys.exit(main())
