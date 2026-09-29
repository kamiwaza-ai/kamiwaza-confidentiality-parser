"""Install only local wheels into a clean environment and exercise the API."""

import argparse
import os
import subprocess
import tempfile
import venv
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("wheelhouse", type=Path)
args = parser.parse_args()
wheelhouse = args.wheelhouse.resolve(strict=True)
with tempfile.TemporaryDirectory(prefix="markings-offline-") as directory:
    root = Path(directory)
    venv.create(root / "venv", with_pip=True)
    python = root / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    env = dict(os.environ, PIP_NO_INDEX="1", PIP_DISABLE_PIP_VERSION_CHECK="1")
    env.pop("PYTHONPATH", None)
    subprocess.run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--no-index",
            "--find-links",
            str(wheelhouse),
            "kamiwaza-confidentiality-parser==0.1.0",
        ],
        env=env,
        cwd=root,
        check=True,
    )
    subprocess.run(
        [
            str(python),
            "-I",
            "-c",
            """
from kamiwaza_confidentiality import create_provider, load_from_env
assert load_from_env({}) is None
provider = load_from_env({"KAMIWAZA_MARKINGS_ENABLED": "true"})
assert provider.parse("private").level_id == "private"
assert provider.present(provider.parse("private")).text == "Company Private"
assert create_provider().profile.revision == "1"
print("Offline installed-wheel API smoke passed")
""",
        ],
        env=env,
        cwd=root,
        check=True,
    )
