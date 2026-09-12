from __future__ import annotations

import argparse
import hashlib
import json
import tarfile
import zipfile
from pathlib import Path


def sha256_for_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_archive(binary: Path, archive: Path) -> None:
    archive.parent.mkdir(parents=True, exist_ok=True)
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.write(binary, arcname=binary.name)
        return
    if archive.name.endswith(".tar.gz"):
        with tarfile.open(archive, "w:gz") as tf:
            tf.add(binary, arcname=binary.name)
        return
    raise SystemExit(f"unsupported archive type: {archive}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True)
    parser.add_argument("--archive", required=True)
    parser.add_argument("--metadata-json")
    args = parser.parse_args(argv)

    binary = Path(args.binary)
    archive = Path(args.archive)
    build_archive(binary, archive)

    metadata = {
        "binary": {
            "filename": binary.name,
            "size_bytes": binary.stat().st_size,
            "sha256": sha256_for_path(binary),
        },
        "archive": {
            "filename": archive.name,
            "size_bytes": archive.stat().st_size,
            "sha256": sha256_for_path(archive),
        },
    }

    print(json.dumps(metadata, indent=2))
    if args.metadata_json:
        Path(args.metadata_json).write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
