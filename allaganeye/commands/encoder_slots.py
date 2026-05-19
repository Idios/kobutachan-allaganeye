"""Hidden ``allaganeye encoder-slots`` CLI command (#761).

Used by GUI Tauri ``enumerate_h264_encoders`` to spawn a Python subprocess
once per ExportScreen mount, retrieving the EncoderSlot list as JSON.
"""

from __future__ import annotations

import json

import typer

from allaganeye.export.encoder import enumerate_h264_encoders


def _split_csv(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def register(app: typer.Typer) -> None:
    """Register the hidden command into ``app``. Called from ``allaganeye/cli.py``."""

    @app.command(name="encoder-slots", hidden=True)
    def encoder_slots(
        vendors: str = typer.Option(
            "", "--vendors", help="Comma-separated vendor list."
        ),
        preference: str = typer.Option(
            "nvidia,amd,intel",
            "--preference",
            help="Comma-separated vendor preference order.",
        ),
        gpu_models: str = typer.Option(
            "", "--gpu-models", help="Comma-separated GPU model names."
        ),
    ) -> None:
        """Return the parallel encoder slot list as a JSON array on stdout."""
        slots = enumerate_h264_encoders(
            vendors=_split_csv(vendors),
            preference=_split_csv(preference),
            gpu_models=_split_csv(gpu_models),
        )
        out = [
            {
                "slot_index": s.slot_index,
                "encoder_kind": s.encoder_kind.name.capitalize(),  # "Nvenc" / "Libx264" / ...
                "display_label": s.display_label,
            }
            for s in slots
        ]
        typer.echo(json.dumps(out, ensure_ascii=False))
