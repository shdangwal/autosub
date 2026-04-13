"""Tests for SRT formatting, timestamp parsing, and manifest-to-SRT assembly."""

import os
import tempfile


# ── format_srt_time ──────────────────────────────────────────────


def test_format_srt_time_zero(mod):
    assert mod.format_srt_time(0) == "00:00:00,000"


def test_format_srt_time_basic(mod):
    assert mod.format_srt_time(1.5) == "00:00:01,500"


def test_format_srt_time_minutes(mod):
    assert mod.format_srt_time(61.234) == "00:01:01,234"


def test_format_srt_time_hours(mod):
    assert mod.format_srt_time(3661.0) == "01:01:01,000"


def test_format_srt_time_ms_rounds_to_1000(mod):
    """When rounding pushes ms to 1000, it should cascade into seconds."""
    # 0.9999 seconds → round(999.9) = 1000ms → should become 1s, 0ms
    result = mod.format_srt_time(0.9999)
    assert result == "00:00:01,000"


def test_format_srt_time_cascade_seconds_to_minutes(mod):
    """59.9999s → rounds up to 60s → should become 1m 0s."""
    result = mod.format_srt_time(59.9999)
    assert result == "00:01:00,000"


def test_format_srt_time_cascade_minutes_to_hours(mod):
    """3599.9999s → rounds up through seconds → minutes → hours."""
    result = mod.format_srt_time(3599.9999)
    assert result == "01:00:00,000"


def test_format_srt_time_large_value(mod):
    # 2 hours, 30 minutes, 45.678 seconds
    assert mod.format_srt_time(9045.678) == "02:30:45,678"


# ── format_duration ──────────────────────────────────────────────


def test_format_duration_sub_minute(mod):
    assert mod.format_duration(42.7) == "42.7s"


def test_format_duration_exactly_60(mod):
    assert mod.format_duration(60) == "1m 00s"


def test_format_duration_minutes_and_seconds(mod):
    assert mod.format_duration(154) == "2m 34s"


def test_format_duration_hours(mod):
    assert mod.format_duration(3661) == "1h 01m 01s"


def test_format_duration_just_under_minute(mod):
    assert mod.format_duration(59.9) == "59.9s"


# ── process_srt_entries ──────────────────────────────────────────


def _write_temp_txt(content):
    """Write content to a temp file and return the path."""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8")
    f.write(content)
    f.close()
    return f.name


def test_process_srt_entries_basic(mod):
    path = _write_temp_txt("0.0-2.5: Hello world\n3.0-5.0: Second line\n")
    try:
        entries = mod.process_srt_entries(path, time_offset=100.0, min_keep_time=0.0, max_keep_time=200.0)
        assert len(entries) == 2
        assert entries[0] == (100.0, 102.5, "Hello world")
        assert entries[1] == (103.0, 105.0, "Second line")
    finally:
        os.unlink(path)


def test_process_srt_entries_boundary_filtering(mod):
    """Entries outside [min_keep, max_keep) should be dropped."""
    path = _write_temp_txt("0.0-2.0: too early\n5.0-7.0: in range\n15.0-17.0: too late\n")
    try:
        entries = mod.process_srt_entries(path, time_offset=100.0, min_keep_time=104.0, max_keep_time=110.0)
        assert len(entries) == 1
        assert entries[0][2] == "in range"
    finally:
        os.unlink(path)


def test_process_srt_entries_malformed_lines_skipped(mod):
    content = "0.0-2.0: Valid line\nthis is garbage\n\n3.0-5.0: Also valid\n"
    path = _write_temp_txt(content)
    try:
        entries = mod.process_srt_entries(path, time_offset=0.0, min_keep_time=0.0, max_keep_time=100.0)
        assert len(entries) == 2
        assert entries[0][2] == "Valid line"
        assert entries[1][2] == "Also valid"
    finally:
        os.unlink(path)


def test_process_srt_entries_empty_file(mod):
    """Empty file (no speech) should return no entries, not crash."""
    path = _write_temp_txt("")
    try:
        entries = mod.process_srt_entries(path, time_offset=0.0, min_keep_time=0.0, max_keep_time=100.0)
        assert entries == []
    finally:
        os.unlink(path)


def test_process_srt_entries_text_with_colons(mod):
    """Text part can contain colons (e.g., timestamps in dialogue)."""
    path = _write_temp_txt("0.0-2.0: Time is 3:00 PM\n")
    try:
        entries = mod.process_srt_entries(path, time_offset=0.0, min_keep_time=0.0, max_keep_time=100.0)
        assert len(entries) == 1
        assert entries[0][2] == "Time is 3:00 PM"
    finally:
        os.unlink(path)


# ── build_srt_from_manifest ─────────────────────────────────────


def test_build_srt_from_manifest_basic(mod):
    """Complete chunks should appear in the SRT output."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Write fake raw text files
        raw0 = os.path.join(tmpdir, "chunk_000_raw.txt")
        raw1 = os.path.join(tmpdir, "chunk_001_raw.txt")
        with open(raw0, "w") as f:
            f.write("0.0-2.0: First chunk speech\n")
        with open(raw1, "w") as f:
            f.write("0.0-3.0: Second chunk speech\n")

        manifest = {
            "chunks": [
                {"index": 0, "start": 0.0, "end": 100.0, "status": "complete",
                 "raw_txt": "chunk_000_raw.txt", "trans_txt": "chunk_000_trans.txt"},
                {"index": 1, "start": 100.0, "end": 200.0, "status": "complete",
                 "raw_txt": "chunk_001_raw.txt", "trans_txt": "chunk_001_trans.txt"},
            ]
        }

        # Temporarily override CACHE_DIR
        original_cache = mod.CACHE_DIR
        mod.CACHE_DIR = tmpdir
        try:
            srt = mod.build_srt_from_manifest(manifest, "raw")
            assert "First chunk speech" in srt
            assert "Second chunk speech" in srt
            # Counter should be sequential
            assert srt.startswith("1\n")
            assert "\n2\n" in srt
        finally:
            mod.CACHE_DIR = original_cache


def test_build_srt_skips_pending_chunks(mod):
    """Pending chunks should not appear in the output."""
    with tempfile.TemporaryDirectory() as tmpdir:
        raw0 = os.path.join(tmpdir, "chunk_000_raw.txt")
        with open(raw0, "w") as f:
            f.write("0.0-2.0: Done chunk\n")

        manifest = {
            "chunks": [
                {"index": 0, "start": 0.0, "end": 100.0, "status": "complete",
                 "raw_txt": "chunk_000_raw.txt", "trans_txt": "chunk_000_trans.txt"},
                {"index": 1, "start": 100.0, "end": 200.0, "status": "pending",
                 "raw_txt": "chunk_001_raw.txt", "trans_txt": "chunk_001_trans.txt"},
            ]
        }

        original_cache = mod.CACHE_DIR
        mod.CACHE_DIR = tmpdir
        try:
            srt = mod.build_srt_from_manifest(manifest, "raw")
            assert "Done chunk" in srt
            assert "\n2\n" not in srt  # only one entry
        finally:
            mod.CACHE_DIR = original_cache


def test_build_srt_raw_includes_asr_complete(mod):
    """raw SRT should include asr_complete chunks (they have raw text)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        raw0 = os.path.join(tmpdir, "chunk_000_raw.txt")
        with open(raw0, "w") as f:
            f.write("0.0-2.0: ASR only chunk\n")

        manifest = {
            "chunks": [
                {"index": 0, "start": 0.0, "end": 100.0, "status": "asr_complete",
                 "raw_txt": "chunk_000_raw.txt", "trans_txt": "chunk_000_trans.txt"},
            ]
        }

        original_cache = mod.CACHE_DIR
        mod.CACHE_DIR = tmpdir
        try:
            raw_srt = mod.build_srt_from_manifest(manifest, "raw")
            trans_srt = mod.build_srt_from_manifest(manifest, "trans")
            assert "ASR only chunk" in raw_srt
            assert trans_srt == ""  # trans requires "complete" status
        finally:
            mod.CACHE_DIR = original_cache


def test_build_srt_empty_file_chunk(mod):
    """Chunks with empty text files (no speech) should produce no SRT entries."""
    with tempfile.TemporaryDirectory() as tmpdir:
        raw0 = os.path.join(tmpdir, "chunk_000_raw.txt")
        raw1 = os.path.join(tmpdir, "chunk_001_raw.txt")
        with open(raw0, "w") as f:
            f.write("0.0-2.0: Has speech\n")
        with open(raw1, "w") as f:
            f.write("")  # empty — no speech in this chunk

        manifest = {
            "chunks": [
                {"index": 0, "start": 0.0, "end": 100.0, "status": "complete",
                 "raw_txt": "chunk_000_raw.txt", "trans_txt": "chunk_000_trans.txt"},
                {"index": 1, "start": 100.0, "end": 147.0, "status": "complete",
                 "raw_txt": "chunk_001_raw.txt", "trans_txt": "chunk_001_trans.txt"},
            ]
        }

        original_cache = mod.CACHE_DIR
        mod.CACHE_DIR = tmpdir
        try:
            srt = mod.build_srt_from_manifest(manifest, "raw")
            assert "Has speech" in srt
            assert "\n2\n" not in srt  # only one actual entry
        finally:
            mod.CACHE_DIR = original_cache
