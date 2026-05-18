"""Tests for hidden 'allaganeye encoder-slots' CLI used by GUI subprocess."""

from __future__ import annotations

import json

import pytest
import typer
from typer.testing import CliRunner

from allaganeye.commands.encoder_slots import register

runner = CliRunner()


@pytest.fixture
def app() -> typer.Typer:
    a = typer.Typer()

    @a.callback()
    def _root() -> None:
        """Test app root."""

    register(a)
    return a


def test_encoder_slots_outputs_json_array_for_nvenc(
    app: typer.Typer, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.delenv("ALLAGANEYE_EXPORT_CONCURRENCY", raising=False)
    result = runner.invoke(
        app,
        [
            "encoder-slots",
            "--vendors",
            "nvidia",
            "--preference",
            "nvidia,amd,intel",
            "--gpu-models",
            "NVIDIA GeForce RTX 5090",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert len(parsed) == 3
    assert all(s["encoder_kind"] == "Nvenc" for s in parsed)
    assert [s["slot_index"] for s in parsed] == [0, 1, 2]
    assert [s["display_label"] for s in parsed] == ["NVENC #1", "NVENC #2", "NVENC #3"]


def test_encoder_slots_libx264_when_no_vendors(
    app: typer.Typer, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.delenv("ALLAGANEYE_EXPORT_CONCURRENCY", raising=False)
    result = runner.invoke(
        app,
        [
            "encoder-slots",
            "--vendors",
            "",
            "--preference",
            "nvidia,amd,intel",
            "--gpu-models",
            "",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert parsed == [
        {"slot_index": 0, "encoder_kind": "Libx264", "display_label": "libx264 (CPU)"}
    ]


def test_encoder_slots_multiple_vendors_first_pref_wins(
    app: typer.Typer, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.delenv("ALLAGANEYE_EXPORT_CONCURRENCY", raising=False)
    result = runner.invoke(
        app,
        [
            "encoder-slots",
            "--vendors",
            "nvidia,amd",
            "--preference",
            "amd,nvidia",
            "--gpu-models",
            "AMD Radeon,NVIDIA RTX 4060",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert parsed == [{"slot_index": 0, "encoder_kind": "Amf", "display_label": "AMF"}]
