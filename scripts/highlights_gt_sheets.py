"""Build contact sheets for the L6 scoring GT (#1049 Q3-B).

The GT adjudication (design note
``docs/superpowers/specs/2026-11-25-l6-streak-scoring-design.md`` 5.1) needs a
human to rank every streak 1 (weak) / 2 (medium) / 3 (strong).  Judging from
timestamps alone is not practical, so this dev-only script decodes a strip of
frames around each streak and writes an HTML index where the tiers can be
picked.

Usage::

    # roots default to the ALLAGANEYE_SAMPLE_VIDEO_DIR[*] env vars
    python scripts/highlights_gt_sheets.py \
        --ref-root E:/royalstraightflesh/videos \
        --vtuber-root E:/allaganeye-samples

    # one case only
    python scripts/highlights_gt_sheets.py --case ref5

Output (``output/`` is git-ignored)::

    output/highlights_gt/index.html     -- pick tiers here, then copy the JSON
    output/highlights_gt/strips/*.png   -- one strip per streak

The JSON the page produces maps ``"<case>|<start>"`` to a tier.  Applying it to
``tests/fixtures/highlights_gt/scoring_gt.json`` is a separate (reviewable)
edit; this script never writes the fixture.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# Make `allaganeye` importable when this script is run directly via
# `python scripts/highlights_gt_sheets.py` (sys.path[0] is `scripts/` then).
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from allaganeye.ffmpeg_path import find_ffmpeg  # noqa: E402

GT_FILE = ROOT / "tests" / "fixtures" / "highlights_gt" / "scoring_gt.json"
INDICATOR_GT_DIR = ROOT / "tests" / "fixtures" / "indicators_gt"
DEFAULT_OUT = ROOT / "output" / "highlights_gt"

# 判定に必要な文脈。KO / ASSIST は 1.5 秒程度しか表示されないので、その前後を広めに取る。
PRE_SECONDS = 2.5
POST_SECONDS = 4.0
FRAME_COUNT = 6
FRAME_WIDTH = 400
LABEL_BAR_HEIGHT = 30


@dataclass(frozen=True)
class Group:
    case: str
    index: int
    start: float
    last_start: float
    ko: int
    assist: int
    tier: int | None

    @property
    def key(self) -> str:
        return f"{self.case}|{self.start:.2f}"

    @property
    def label(self) -> str:
        return (
            f"{self.case} #{self.index:02d}  {self.start:.2f}s  "
            f"ko={self.ko} assist={self.assist}  "
            f"events={self.ko + self.assist}  span={self.last_start - self.start:.1f}s"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build contact sheets for the L6 scoring GT (#1049 Q3-B)."
    )
    parser.add_argument(
        "--ref-root",
        type=Path,
        default=None,
        help="Video root for ALLAGANEYE_SAMPLE_VIDEO_DIR cases (default: the env var)",
    )
    parser.add_argument(
        "--vtuber-root",
        type=Path,
        default=None,
        help="Video root for ALLAGANEYE_SAMPLE_VIDEO_DIR_VTUBER cases "
        "(default: the env var)",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--case", action="append", help="Limit to these case labels")
    return parser.parse_args()


def _video_roots(args: argparse.Namespace) -> dict[str, Path]:
    roots: dict[str, Path] = {}
    for name, explicit in (
        ("ALLAGANEYE_SAMPLE_VIDEO_DIR", args.ref_root),
        ("ALLAGANEYE_SAMPLE_VIDEO_DIR_VTUBER", args.vtuber_root),
    ):
        value = explicit or os.environ.get(name)
        if value:
            roots[name] = Path(value)
    return roots


def _indicator_cases() -> dict[str, tuple[str, str]]:
    """label -> (video_env, video_rel)."""
    cases = {}
    for path in sorted(INDICATOR_GT_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        cases[payload["label"]] = (payload["video_env"], payload["video_rel"])
    return cases


def _groups(only: list[str] | None) -> list[Group]:
    payload = json.loads(GT_FILE.read_text(encoding="utf-8"))
    groups: list[Group] = []
    for case in payload["cases"]:
        if only and case["label"] not in only:
            continue
        ordered = sorted(case["groups"], key=lambda group: group["events"][0]["start"])
        for index, raw in enumerate(ordered, start=1):
            events = raw["events"]
            starts = [float(event["start"]) for event in events]
            groups.append(
                Group(
                    case=case["label"],
                    index=index,
                    start=min(starts),
                    last_start=max(starts),
                    ko=sum(1 for event in events if event["kind"] == "ko"),
                    assist=sum(1 for event in events if event["kind"] == "assist"),
                    tier=raw.get("tier"),
                )
            )
    return groups


def _extract_frames(
    video: Path, start: float, span: float, scratch: Path
) -> list[Path]:
    """Decode `FRAME_COUNT` evenly spaced frames from `start` for `span` seconds.

    `-ss` goes before `-i` and `-t` after it (same order the frames module pins;
    swapping them changes which frames come out).
    """
    if scratch.exists():
        for stale in scratch.glob("f_*.png"):
            stale.unlink()
    scratch.mkdir(parents=True, exist_ok=True)
    fps = FRAME_COUNT / span
    command = [
        find_ffmpeg(),
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{start:.3f}",
        "-i",
        str(video),
        "-t",
        f"{span:.3f}",
        "-vf",
        f"fps={fps:.6f},scale={FRAME_WIDTH}:-2",
        "-frames:v",
        str(FRAME_COUNT),
        str(scratch / "f_%02d.png"),
    ]
    subprocess.run(command, check=True)  # fixed argv, trusted input
    frames = sorted(scratch.glob("f_*.png"))
    if not frames:
        raise RuntimeError(f"ffmpeg produced no frames for {video} at {start:.2f}s")
    return frames


def _compose(frames: list[Path], label: str, step: float) -> np.ndarray:
    images = []
    for offset, path in enumerate(frames):
        image = cv2.imread(str(path))
        if image is None:
            raise RuntimeError(f"cannot read {path}")
        cv2.putText(
            image,
            f"+{offset * step:.1f}s",
            (10, image.shape[0] - 12),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 0, 0),
            3,
            cv2.LINE_AA,
        )
        cv2.putText(
            image,
            f"+{offset * step:.1f}s",
            (10, image.shape[0] - 12),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
        images.append(image)
    height = min(image.shape[0] for image in images)
    resized = [
        cv2.resize(image, (round(image.shape[1] * height / image.shape[0]), height))
        for image in images
    ]
    strip = np.hstack(resized)
    bar = np.zeros((LABEL_BAR_HEIGHT, strip.shape[1], 3), np.uint8)
    cv2.putText(
        bar,
        label,
        (8, 21),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )
    return np.vstack([bar, strip])


def _write_html(groups: list[Group], strips: dict[str, str], out: Path) -> None:
    rows = []
    for group in groups:
        options = "".join(
            f'<option value="{tier}"'
            f"{' selected' if group.tier == tier else ''}>{tier}</option>"
            for tier in (1, 2, 3)
        )
        rows.append(
            f'<tr data-key="{html.escape(group.key)}">'
            f"<td>{group.index}</td>"
            f"<td>{html.escape(group.case)}<br>{group.start:.1f}s<br>"
            f"ko{group.ko}/a{group.assist}</td>"
            f'<td><select><option value="">-</option>{options}</select></td>'
            f'<td><img loading="lazy" src="{html.escape(strips[group.key])}"></td>'
            "</tr>"
        )
    document = f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<title>L6 scoring GT: contact sheets</title>
<style>
body {{ background: #14161a; color: #e6e6e6; font-family: sans-serif; margin: 16px; }}
h1 {{ font-size: 18px; }}
table {{ border-collapse: collapse; }}
td, th {{ border-bottom: 1px solid #333; padding: 4px 8px; vertical-align: top; }}
img {{ width: 100%; min-width: 900px; display: block; }}
select {{ font-size: 16px; padding: 2px; }}
#out {{ width: 100%; height: 160px; background: #0c0d10; color: #9fe; }}
</style>
</head>
<body>
<h1>L6 ストリーク GT: 1=弱 / 2=中 / 3=強</h1>
<p>画像は {PRE_SECONDS:g} 秒前から {POST_SECONDS:g} 秒後までを {FRAME_COUNT} 枚に等間隔で
切り出したもの（画像内の +Xs は streak 先頭からの経過秒）。採点後に
[JSON を表示] を押してコピーし、エージェントに渡す。</p>
<table>
<thead><tr><th>#</th><th>streak</th><th>tier</th><th>strip</th></tr></thead>
<tbody>
{chr(10).join(rows)}
</tbody>
</table>
<p><button id="build">JSON を表示</button></p>
<textarea id="out" readonly></textarea>
<script>
document.getElementById('build').addEventListener('click', () => {{
  const result = {{}};
  document.querySelectorAll('tr[data-key]').forEach((row) => {{
    const value = row.querySelector('select').value;
    if (value) result[row.dataset.key] = Number(value);
  }});
  document.getElementById('out').value = JSON.stringify(result, null, 2);
}});
</script>
</body>
</html>
"""
    (out / "index.html").write_text(document, encoding="utf-8")


def main() -> int:
    args = parse_args()
    roots = _video_roots(args)
    cases = _indicator_cases()
    groups = _groups(args.case)
    out: Path = args.out
    (out / "strips").mkdir(parents=True, exist_ok=True)

    missing = []
    strips: dict[str, str] = {}
    scratch = out / ".scratch"
    for group in groups:
        video_env, video_rel = cases[group.case]
        root = roots.get(video_env)
        if root is None:
            missing.append(f"{group.case}: {video_env} root not given")
            continue
        video = root / video_rel
        if not video.is_file():
            missing.append(f"{group.case}: {video} not found")
            continue
        span = group.last_start - group.start + PRE_SECONDS + POST_SECONDS
        frames = _extract_frames(
            video, max(0.0, group.start - PRE_SECONDS), span, scratch
        )
        strip = _compose(frames, group.label, span / FRAME_COUNT)
        relative = f"strips/{group.case}_{group.index:02d}.png"
        cv2.imwrite(str(out / relative), strip)
        strips[group.key] = relative
        print(f"[{len(strips):2d}/{len(groups)}] {group.label}")

    if not strips:
        print("no strips produced:")
        for line in missing:
            print(f"  - {line}")
        return 1

    _write_html([group for group in groups if group.key in strips], strips, out)
    if missing:
        print("skipped:")
        for line in missing:
            print(f"  - {line}")
    print(f"\nopen: {out / 'index.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
