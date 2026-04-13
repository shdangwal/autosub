"""Tests for manifest creation, persistence, validation, and OOM resplit logic."""

import json
import os
import tempfile


# ── create_manifest ──────────────────────────────────────────────


def test_create_manifest_structure(mod):
    """Manifest should have correct top-level keys and chunk structure."""
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        video_path = f.name

    try:
        boundaries = [(0.0, 300.0), (300.0, 500.0)]
        m = mod.create_manifest(video_path, "test_video", 500.0, 300, boundaries)

        assert m["version"] == 1
        assert m["video_path"] == video_path
        assert m["global_chunk_size"] == 300
        assert m["effective_chunk_size"] == 300
        assert m["total_duration"] == 500.0
        assert len(m["chunks"]) == 2

        chunk0 = m["chunks"][0]
        assert chunk0["index"] == 0
        assert chunk0["start"] == 0.0
        assert chunk0["end"] == 300.0
        assert chunk0["status"] == "pending"
        assert "_000_raw.txt" in chunk0["raw_txt"]
        assert "_000_trans.txt" in chunk0["trans_txt"]
    finally:
        os.unlink(video_path)


def test_create_manifest_mtime_captured(mod):
    """Manifest should capture the video file's modification time."""
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        video_path = f.name

    try:
        m = mod.create_manifest(video_path, "test_video", 100.0, 300, [(0.0, 100.0)])
        assert m["video_mtime"] == os.path.getmtime(video_path)
    finally:
        os.unlink(video_path)


# ── save / load round-trip ───────────────────────────────────────


def test_save_load_roundtrip(mod):
    """Saving and loading a manifest should produce identical data."""
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        video_path = f.name

    original_cache = mod.CACHE_DIR
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            mod.CACHE_DIR = tmpdir
            m = mod.create_manifest(video_path, "roundtrip_test", 600.0, 300,
                                    [(0.0, 300.0), (300.0, 600.0)])
            mod.save_manifest(m, "roundtrip_test")
            loaded = mod.load_manifest("roundtrip_test", video_path)

            assert loaded is not None
            assert loaded["total_duration"] == m["total_duration"]
            assert len(loaded["chunks"]) == len(m["chunks"])
            assert loaded["chunks"][0]["status"] == "pending"
    finally:
        mod.CACHE_DIR = original_cache
        os.unlink(video_path)


# ── mtime invalidation ──────────────────────────────────────────


def test_load_manifest_stale_mtime_returns_none(mod):
    """If the video file was modified after the manifest was saved, return None."""
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        video_path = f.name

    original_cache = mod.CACHE_DIR
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            mod.CACHE_DIR = tmpdir
            m = mod.create_manifest(video_path, "stale_test", 100.0, 300, [(0.0, 100.0)])
            mod.save_manifest(m, "stale_test")

            # Tamper with the stored mtime to simulate the video changing
            m["video_mtime"] = 0.0
            mod.save_manifest(m, "stale_test")

            loaded = mod.load_manifest("stale_test", video_path)
            assert loaded is None
    finally:
        mod.CACHE_DIR = original_cache
        os.unlink(video_path)


# ── corrupted manifest ──────────────────────────────────────────


def test_load_manifest_corrupted_json_returns_none(mod):
    """Corrupted JSON on disk should return None, not crash."""
    original_cache = mod.CACHE_DIR
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        video_path = f.name

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            mod.CACHE_DIR = tmpdir
            mp = os.path.join(tmpdir, "corrupt_test_manifest.json")
            with open(mp, "w") as f:
                f.write("{broken json!!!}")

            loaded = mod.load_manifest("corrupt_test", video_path)
            assert loaded is None
    finally:
        mod.CACHE_DIR = original_cache
        os.unlink(video_path)


def test_load_manifest_nonexistent_returns_none(mod):
    """Missing manifest file should return None."""
    original_cache = mod.CACHE_DIR
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        video_path = f.name

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            mod.CACHE_DIR = tmpdir
            loaded = mod.load_manifest("nonexistent_video", video_path)
            assert loaded is None
    finally:
        mod.CACHE_DIR = original_cache
        os.unlink(video_path)


# ── delete_manifest ──────────────────────────────────────────────


def test_delete_manifest(mod):
    """delete_manifest should remove the file from disk."""
    original_cache = mod.CACHE_DIR
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            mod.CACHE_DIR = tmpdir
            mp = os.path.join(tmpdir, "del_test_manifest.json")
            with open(mp, "w") as f:
                f.write("{}")

            mod.delete_manifest("del_test")
            assert not os.path.exists(mp)
    finally:
        mod.CACHE_DIR = original_cache


# ── resplit_remaining ────────────────────────────────────────────


def test_resplit_keeps_completed_chunks(mod):
    """Chunks before the failed index should be preserved unchanged."""
    m = {
        "total_duration": 900.0,
        "effective_chunk_size": 300,
        "chunks": [
            {"index": 0, "start": 0.0, "end": 300.0, "status": "complete",
             "raw_txt": "x_000_raw.txt", "trans_txt": "x_000_trans.txt"},
            {"index": 1, "start": 300.0, "end": 600.0, "status": "complete",
             "raw_txt": "x_001_raw.txt", "trans_txt": "x_001_trans.txt"},
            {"index": 2, "start": 600.0, "end": 900.0, "status": "pending",
             "raw_txt": "x_002_raw.txt", "trans_txt": "x_002_trans.txt"},
        ],
    }

    # Simulate a silent audio file (no silences detected)
    with tempfile.NamedTemporaryFile(suffix=".flac", delete=False) as f:
        audio_path = f.name

    original_detect = mod.detect_silences
    mod.detect_silences = lambda path: []  # mock: no silences
    try:
        result = mod.resplit_remaining(m, failed_index=2, new_size=150,
                                       video_basename="test", master_audio_path=audio_path)

        # First two chunks preserved
        assert result["chunks"][0]["status"] == "complete"
        assert result["chunks"][0]["start"] == 0.0
        assert result["chunks"][1]["status"] == "complete"
        assert result["chunks"][1]["start"] == 300.0

        # New chunks start from where chunk 2 was
        assert result["chunks"][2]["start"] == 600.0
        assert result["chunks"][2]["status"] == "pending"
        assert result["effective_chunk_size"] == 150
    finally:
        mod.detect_silences = original_detect
        os.unlink(audio_path)


def test_resplit_reindexes_correctly(mod):
    """New chunks after resplit should have sequential indices starting from kept count."""
    m = {
        "total_duration": 600.0,
        "effective_chunk_size": 300,
        "chunks": [
            {"index": 0, "start": 0.0, "end": 300.0, "status": "complete",
             "raw_txt": "x_000_raw.txt", "trans_txt": "x_000_trans.txt"},
            {"index": 1, "start": 300.0, "end": 600.0, "status": "pending",
             "raw_txt": "x_001_raw.txt", "trans_txt": "x_001_trans.txt"},
        ],
    }

    original_detect = mod.detect_silences
    mod.detect_silences = lambda path: []
    try:
        result = mod.resplit_remaining(m, failed_index=1, new_size=150,
                                       video_basename="test", master_audio_path="/dev/null")

        indices = [c["index"] for c in result["chunks"]]
        assert indices == list(range(len(result["chunks"])))

        # All new chunks should be pending
        for c in result["chunks"][1:]:
            assert c["status"] == "pending"
    finally:
        mod.detect_silences = original_detect


def test_resplit_chunk_filenames_match_new_indices(mod):
    """Resplit chunk filenames should reflect new indices, not old ones."""
    m = {
        "total_duration": 600.0,
        "effective_chunk_size": 300,
        "chunks": [
            {"index": 0, "start": 0.0, "end": 300.0, "status": "complete",
             "raw_txt": "x_000_raw.txt", "trans_txt": "x_000_trans.txt"},
            {"index": 1, "start": 300.0, "end": 600.0, "status": "pending",
             "raw_txt": "x_001_raw.txt", "trans_txt": "x_001_trans.txt"},
        ],
    }

    original_detect = mod.detect_silences
    mod.detect_silences = lambda path: []
    try:
        result = mod.resplit_remaining(m, failed_index=1, new_size=150,
                                       video_basename="myvid", master_audio_path="/dev/null")

        for c in result["chunks"][1:]:
            idx = c["index"]
            assert f"_{idx:03d}_raw.txt" in c["raw_txt"]
            assert f"_{idx:03d}_trans.txt" in c["trans_txt"]
    finally:
        mod.detect_silences = original_detect


def test_resplit_covers_full_remaining_duration(mod):
    """Resplit chunks should cover from the failed chunk's start to total_duration."""
    m = {
        "total_duration": 1000.0,
        "effective_chunk_size": 300,
        "chunks": [
            {"index": 0, "start": 0.0, "end": 300.0, "status": "complete",
             "raw_txt": "x_000_raw.txt", "trans_txt": "x_000_trans.txt"},
            {"index": 1, "start": 300.0, "end": 600.0, "status": "complete",
             "raw_txt": "x_001_raw.txt", "trans_txt": "x_001_trans.txt"},
            {"index": 2, "start": 600.0, "end": 1000.0, "status": "pending",
             "raw_txt": "x_002_raw.txt", "trans_txt": "x_002_trans.txt"},
        ],
    }

    original_detect = mod.detect_silences
    mod.detect_silences = lambda path: []
    try:
        result = mod.resplit_remaining(m, failed_index=2, new_size=150,
                                       video_basename="test", master_audio_path="/dev/null")

        new_chunks = [c for c in result["chunks"] if c["index"] >= 2]
        assert new_chunks[0]["start"] == 600.0
        assert new_chunks[-1]["end"] == 1000.0

        # No gaps
        for i in range(1, len(new_chunks)):
            assert new_chunks[i]["start"] == new_chunks[i - 1]["end"]
    finally:
        mod.detect_silences = original_detect
