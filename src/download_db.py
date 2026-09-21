"""Download the prebuilt stackoverflow.db from the GitHub Release (used at deploy time)."""
import gzip
import shutil
import urllib.request
from pathlib import Path

URL = "https://github.com/brianravelo28/stackoverflow-nlp-query-engine/releases/download/data-v1/stackoverflow.db.gz"
DB_PATH = Path(__file__).resolve().parent.parent / "stackoverflow.db"


def main():
    if DB_PATH.exists():
        print(f"{DB_PATH.name} already exists, skipping download")
        return
    gz_path = DB_PATH.with_suffix(".db.gz")
    print(f"Downloading {URL}")
    urllib.request.urlretrieve(URL, gz_path)
    with gzip.open(gz_path, "rb") as src, open(DB_PATH, "wb") as dst:
        shutil.copyfileobj(src, dst)
    gz_path.unlink()
    print(f"Wrote {DB_PATH} ({DB_PATH.stat().st_size / 1e6:.0f} MB)")


if __name__ == "__main__":
    main()
