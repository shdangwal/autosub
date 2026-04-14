"""Tests for CJK detection, SRT parsing, and SRT round-trip in the retranslate module."""

import os
import tempfile


# ── contains_cjk (autosub_single) ──────────────────────────────


def test_contains_cjk_detects_chinese(mod):
    assert mod.contains_cjk("这是中文")


def test_contains_cjk_mixed_text(mod):
    assert mod.contains_cjk("Hello 你好 world")


def test_contains_cjk_english_only(mod):
    assert not mod.contains_cjk("Hello world")


def test_contains_cjk_empty(mod):
    assert not mod.contains_cjk("")


def test_contains_cjk_punctuation_only(mod):
    assert not mod.contains_cjk("!@#$%^&*()")


def test_contains_cjk_japanese_kanji(mod):
    """CJK range covers shared Chinese/Japanese kanji."""
    assert mod.contains_cjk("日本語")


def test_contains_cjk_numbers_and_ascii(mod):
    assert not mod.contains_cjk("12345 abc")


# ── contains_cjk (autosub_retranslate) ─────────────────────────


def test_retranslate_contains_cjk(retranslate_mod):
    """Retranslate module's CJK detection should match autosub_single's."""
    assert retranslate_mod.contains_cjk("这是中文")
    assert not retranslate_mod.contains_cjk("Hello world")


# ── parse_srt ───────────────────────────────────────────────────


def test_parse_srt_basic(retranslate_mod):
    content = (
        "1\n"
        "00:00:00,000 --> 00:00:02,500\n"
        "Hello world\n\n"
        "2\n"
        "00:00:03,000 --> 00:00:05,000\n"
        "Second line\n\n"
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".srt", delete=False, encoding="utf-8") as f:
        f.write(content)
        path = f.name

    try:
        entries = retranslate_mod.parse_srt(path)
        assert len(entries) == 2
        assert entries[0]["number"] == "1"
        assert "00:00:00,000" in entries[0]["timecodes"]
        assert entries[0]["text"] == "Hello world"
        assert entries[1]["number"] == "2"
        assert entries[1]["text"] == "Second line"
    finally:
        os.unlink(path)


def test_parse_srt_multiline_text(retranslate_mod):
    """Subtitle entries can have multiple lines of text."""
    content = (
        "1\n"
        "00:00:00,000 --> 00:00:02,500\n"
        "Line one\n"
        "Line two\n\n"
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".srt", delete=False, encoding="utf-8") as f:
        f.write(content)
        path = f.name

    try:
        entries = retranslate_mod.parse_srt(path)
        assert len(entries) == 1
        assert entries[0]["text"] == "Line one\nLine two"
    finally:
        os.unlink(path)


def test_parse_srt_empty_file(retranslate_mod):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".srt", delete=False, encoding="utf-8") as f:
        f.write("")
        path = f.name

    try:
        entries = retranslate_mod.parse_srt(path)
        assert entries == []
    finally:
        os.unlink(path)


# ── write_srt ───────────────────────────────────────────────────


def test_write_srt_basic(retranslate_mod):
    entries = [
        {"number": "1", "timecodes": "00:00:00,000 --> 00:00:02,500", "text": "Hello"},
        {"number": "2", "timecodes": "00:00:03,000 --> 00:00:05,000", "text": "World"},
    ]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".srt", delete=False, encoding="utf-8") as f:
        path = f.name

    try:
        retranslate_mod.write_srt(path, entries)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "1\n00:00:00,000 --> 00:00:02,500\nHello\n\n" in content
        assert "2\n00:00:03,000 --> 00:00:05,000\nWorld\n\n" in content
    finally:
        os.unlink(path)


# ── parse/write round-trip ──────────────────────────────────────


def test_srt_roundtrip(retranslate_mod):
    """Parsing then writing an SRT file should preserve content."""
    original = (
        "1\n"
        "00:00:00,000 --> 00:00:02,500\n"
        "First subtitle\n\n"
        "2\n"
        "00:00:03,000 --> 00:00:05,000\n"
        "Second subtitle\n\n"
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".srt", delete=False, encoding="utf-8") as f:
        f.write(original)
        path = f.name

    try:
        entries = retranslate_mod.parse_srt(path)
        out_path = path + ".out"
        retranslate_mod.write_srt(out_path, entries)
        with open(out_path, "r", encoding="utf-8") as f:
            result = f.read()

        assert result == original
    finally:
        os.unlink(path)
        if os.path.exists(out_path):
            os.unlink(out_path)


def test_srt_roundtrip_with_cjk(retranslate_mod):
    """CJK text should survive a parse/write round-trip unchanged."""
    original = (
        "1\n"
        "00:00:00,000 --> 00:00:02,500\n"
        "这是未翻译的文字\n\n"
        "2\n"
        "00:00:03,000 --> 00:00:05,000\n"
        "Translated line\n\n"
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".srt", delete=False, encoding="utf-8") as f:
        f.write(original)
        path = f.name

    try:
        entries = retranslate_mod.parse_srt(path)
        assert retranslate_mod.contains_cjk(entries[0]["text"])
        assert not retranslate_mod.contains_cjk(entries[1]["text"])

        out_path = path + ".out"
        retranslate_mod.write_srt(out_path, entries)
        with open(out_path, "r", encoding="utf-8") as f:
            result = f.read()
        assert result == original
    finally:
        os.unlink(path)
        if os.path.exists(out_path):
            os.unlink(out_path)
