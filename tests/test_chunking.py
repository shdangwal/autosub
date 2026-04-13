"""Tests for silence-based chunk boundary calculation."""


# ── Audio shorter than one chunk ─────────────────────────────────


def test_short_audio_single_chunk(mod):
    """Audio shorter than target chunk size → one chunk covering everything."""
    boundaries = mod.build_chunk_boundaries(
        total_duration=120.0, target_chunk_size=300, silences=[]
    )
    assert boundaries == [(0.0, 120.0)]


def test_short_audio_with_region_start(mod):
    """Short remaining region after OOM resplit → one chunk."""
    boundaries = mod.build_chunk_boundaries(
        total_duration=500.0, target_chunk_size=300, silences=[], region_start=400.0
    )
    assert boundaries == [(400.0, 500.0)]


# ── No silences ──────────────────────────────────────────────────


def test_no_silences_falls_back_to_target(mod):
    """Without silence data, splits fall exactly at target_chunk_size."""
    boundaries = mod.build_chunk_boundaries(
        total_duration=700.0, target_chunk_size=300, silences=[]
    )
    assert len(boundaries) == 3
    assert boundaries[0] == (0.0, 300.0)
    assert boundaries[1] == (300.0, 600.0)
    # Last chunk is 100s which is within snap_window of 300, so it's merged
    assert boundaries[2] == (600.0, 700.0)


def test_no_silences_exact_multiple(mod):
    """Duration is exact multiple of chunk size."""
    boundaries = mod.build_chunk_boundaries(
        total_duration=600.0, target_chunk_size=300, silences=[]
    )
    assert len(boundaries) == 2
    assert boundaries[0] == (0.0, 300.0)
    assert boundaries[1] == (300.0, 600.0)


# ── Silence snapping ─────────────────────────────────────────────


def test_silence_snap_within_window(mod):
    """Split should snap to silence midpoint when within SILENCE_SNAP_WINDOW."""
    # Target split at 300s, silence at 290-292s → midpoint 291
    silences = [(290.0, 292.0)]
    boundaries = mod.build_chunk_boundaries(
        total_duration=600.0, target_chunk_size=300, silences=silences
    )
    assert len(boundaries) == 2
    assert boundaries[0][1] == 291.0  # snapped to silence midpoint
    assert boundaries[1][0] == 291.0


def test_silence_outside_window_ignored(mod):
    """Silences far from the target split should not affect the boundary."""
    # Target split at 300, silence at 200 → 100s away, well outside window (30s)
    silences = [(200.0, 202.0)]
    boundaries = mod.build_chunk_boundaries(
        total_duration=600.0, target_chunk_size=300, silences=silences
    )
    assert boundaries[0][1] == 300.0  # no snap, falls back to target


def test_picks_closest_silence(mod):
    """When multiple silences are in range, pick the closest to target."""
    # Target split at 300
    silences = [
        (285.0, 287.0),  # midpoint 286, distance 14
        (295.0, 297.0),  # midpoint 296, distance 4 ← closest
        (310.0, 312.0),  # midpoint 311, distance 11
    ]
    boundaries = mod.build_chunk_boundaries(
        total_duration=600.0, target_chunk_size=300, silences=silences
    )
    assert boundaries[0][1] == 296.0


# ── region_start (OOM resplit) ───────────────────────────────────


def test_region_start_offsets_boundaries(mod):
    """With region_start, chunks should begin at the offset, not at 0."""
    silences = [(748.0, 752.0)]  # midpoint 750, near target 450+300=750
    boundaries = mod.build_chunk_boundaries(
        total_duration=1200.0, target_chunk_size=300, silences=silences, region_start=450.0
    )
    assert boundaries[0][0] == 450.0
    assert boundaries[0][1] == 750.0
    assert boundaries[1][0] == 750.0
    assert boundaries[-1][1] == 1200.0


def test_region_start_entire_remainder_fits(mod):
    """If remaining audio from region_start fits in one chunk, return single chunk."""
    boundaries = mod.build_chunk_boundaries(
        total_duration=500.0, target_chunk_size=300, silences=[], region_start=250.0
    )
    assert boundaries == [(250.0, 500.0)]


# ── Tail merging ─────────────────────────────────────────────────


def test_small_tail_merged_into_last_chunk(mod):
    """If remaining audio is ≤ chunk_size + snap_window, it becomes the last chunk."""
    # 620s total, 300s chunks → first chunk 0-300, remaining 320s ≤ 300+30 → merged
    boundaries = mod.build_chunk_boundaries(
        total_duration=620.0, target_chunk_size=300, silences=[]
    )
    assert len(boundaries) == 2
    assert boundaries[1] == (300.0, 620.0)


def test_large_tail_not_merged(mod):
    """If remaining audio exceeds chunk_size + snap_window, it's a separate chunk."""
    # 640s total, 300s chunks → 340s remaining > 330 → not merged
    boundaries = mod.build_chunk_boundaries(
        total_duration=640.0, target_chunk_size=300, silences=[]
    )
    assert len(boundaries) == 3
    assert boundaries[2] == (600.0, 640.0)


# ── Coverage check ───────────────────────────────────────────────


def test_boundaries_cover_full_duration(mod):
    """Boundaries should seamlessly cover [0, total_duration] with no gaps or overlaps."""
    silences = [(i * 50.0, i * 50.0 + 1.5) for i in range(1, 40)]
    boundaries = mod.build_chunk_boundaries(
        total_duration=2000.0, target_chunk_size=300, silences=silences
    )

    # First chunk starts at 0
    assert boundaries[0][0] == 0.0
    # Last chunk ends at total_duration
    assert boundaries[-1][1] == 2000.0
    # No gaps: each chunk starts where the previous ended
    for i in range(1, len(boundaries)):
        assert boundaries[i][0] == boundaries[i - 1][1]
