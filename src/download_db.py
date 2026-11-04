"""Download the prebuilt stackoverflow.db from the GitHub Release (used at deploy time).

The download is checked against the SHA-256 of the published asset before it is
unpacked. Set DATA_REPO (owner/name) to fetch from a fork.
"""
import gzip
import hashlib
import os
import shutil
import urllib.request
from pathlib import Path

REPO = os.environ.get("DATA_REPO", "brianravelo28/stackoverflow-nlp-query-engine")
URL = f"https://github.com/{REPO}/releases/download/data-v1/stackoverflow.db.gz"
EXPECTED_SHA256 = "49bd3fdca6b53cee674813b984b60d9e9d0a413bbcc56c176eb9d10169455a95"
DB_PATH = Path(__file__).resolve().parent.parent / "stackoverflow.db"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    if DB_PATH.exists():
        print(f"{DB_PATH.name} already exists, skipping download")
        return
    gz_path = DB_PATH.with_suffix(".db.gz")
    print(f"Downloading {URL}")
    urllib.request.urlretrieve(URL, gz_path)
    actual = sha256_of(gz_path)
    if actual != EXPECTED_SHA256:
        gz_path.unlink()
        raise SystemExit(f"Checksum mismatch for {URL}\n  expected {EXPECTED_SHA256}\n  got      {actual}")
    with gzip.open(gz_path, "rb") as src, open(DB_PATH, "wb") as dst:
        shutil.copyfileobj(src, dst)
    gz_path.unlink()
    print(f"Wrote {DB_PATH} ({DB_PATH.stat().st_size / 1e6:.0f} MB)")


if __name__ == "__main__":
    main()
