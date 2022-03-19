import os
from pathlib import Path

DEFAULT_ROOT_PATH = Path(os.path.expanduser(os.getenv("PETROLEUM_ROOT", "~/.petroleum/mainnet"))).resolve()

DEFAULT_KEYS_ROOT_PATH = Path(os.path.expanduser(os.getenv("SIT_KEYS_ROOT", "~/.petroleum_keys"))).resolve()
