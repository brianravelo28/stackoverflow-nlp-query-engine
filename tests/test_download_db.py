"""Tests for src/download_db.py with the network call replaced (no download happens)."""
import gzip
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import download_db  # noqa: E402


def _fake_download(tmp_path, monkeypatch, payload: bytes):
    monkeypatch.setattr(download_db, "DB_PATH", tmp_path / "stackoverflow.db")

    def fake_retrieve(url, dest):
        Path(dest).write_bytes(gzip.compress(payload))

    monkeypatch.setattr(download_db.urllib.request, "urlretrieve", fake_retrieve)
    return tmp_path / "stackoverflow.db"


def test_matching_checksum_unpacks_the_database(tmp_path, monkeypatch):
    db = _fake_download(tmp_path, monkeypatch, b"database bytes")
    # gzip embeds a timestamp, so fix one archive and serve the same bytes every time
    archive = gzip.compress(b"database bytes")
    monkeypatch.setattr(download_db, "EXPECTED_SHA256", download_db.hashlib.sha256(archive).hexdigest())
    monkeypatch.setattr(download_db.urllib.request, "urlretrieve", lambda url, dest: Path(dest).write_bytes(archive))
    download_db.main()
    assert db.read_bytes() == b"database bytes"
    assert not (tmp_path / "stackoverflow.db.gz").exists()


def test_wrong_checksum_stops_and_cleans_up(tmp_path, monkeypatch):
    db = _fake_download(tmp_path, monkeypatch, b"tampered")
    with pytest.raises(SystemExit) as info:
        download_db.main()
    assert "Checksum mismatch" in str(info.value)
    assert not db.exists() and not (tmp_path / "stackoverflow.db.gz").exists()


def test_existing_database_is_not_downloaded_again(tmp_path, monkeypatch):
    db = _fake_download(tmp_path, monkeypatch, b"x")
    db.write_bytes(b"already here")
    download_db.main()
    assert db.read_bytes() == b"already here"


def test_published_checksum_matches_the_release_asset_format():
    assert len(download_db.EXPECTED_SHA256) == 64 and set(download_db.EXPECTED_SHA256) <= set("0123456789abcdef")
