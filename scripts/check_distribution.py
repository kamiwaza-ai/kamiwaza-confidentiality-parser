"""Verify the actual sdist and the wheel built from it, using only stdlib."""

import argparse
import tarfile
import zipfile
from email.parser import BytesParser
from pathlib import Path


def check_distribution(sdist: Path, wheel: Path) -> None:
    with tarfile.open(sdist, "r:gz") as archive:
        names = {name.partition("/")[2] for name in archive.getnames()}
        required = {
            "CONTRACT.md",
            "LICENSE",
            "README.md",
            "pyproject.toml",
            "src/kamiwaza_confidentiality/__init__.py",
            "src/kamiwaza_confidentiality/profiles/commercial.yaml",
            "src/kamiwaza_confidentiality/py.typed",
        }
        if missing := required - names:
            raise ValueError(f"Missing sdist contents: {sorted(missing)}")
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        required = {
            "kamiwaza_confidentiality/__init__.py",
            "kamiwaza_confidentiality/profiles/commercial.yaml",
            "kamiwaza_confidentiality/py.typed",
        }
        if missing := required - names:
            raise ValueError(f"Missing wheel contents: {sorted(missing)}")
        metadata_paths = [
            name for name in names if name.endswith(".dist-info/METADATA")
        ]
        if len(metadata_paths) != 1:
            raise ValueError("Wheel must contain exactly one distribution METADATA")
        metadata_path = metadata_paths[0]
        metadata = BytesParser().parsebytes(archive.read(metadata_path))
        expected = {
            "Name": "kamiwaza-confidentiality-parser",
            "Version": "0.1.0",
            "Requires-Python": ">=3.10",
            "License-Expression": "Apache-2.0",
        }
        for field, value in expected.items():
            if metadata.get_all(field) != [value]:
                raise ValueError(
                    f"Unexpected packaged {field}: {metadata.get_all(field)}"
                )
        if metadata.get_all("License-File") != ["LICENSE"]:
            raise ValueError("Packaged METADATA must declare License-File: LICENSE")
        license_path = metadata_path.rsplit("/", 1)[0] + "/licenses/LICENSE"
        if license_path not in names or not archive.read(license_path).strip():
            raise ValueError("Wheel is missing the declared license file")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sdist", type=Path)
    parser.add_argument("wheel", type=Path)
    args = parser.parse_args()
    check_distribution(args.sdist, args.wheel)
    print("Packaged sdist contents and wheel METADATA checks passed")


if __name__ == "__main__":
    main()
