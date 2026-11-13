"""同梱テンプレート (KO / ASSIST インジケータ検出用、#1106)。

実測の正: `docs/superpowers/specs/2026-11-12-l4-ko-assist-indicator-appearance.md`

テンプレートは **1080p の参照レイアウト**から切り出したグレースケール画像 (生値)。
ハイパスは読み出し側 (`indicators._high_pass`) がアンカーにだけ掛ける。

キーと切り出し元 (`20260116_1.mp4` / 1920x1080)。座標は `[y0:y1, x0:x1]`:

- `anchor`: 戦意値ゲージの**バー左キャップ**。42x20 px。`400.0 秒` の `[614:634, 618:660]`
  (インジケータテキストが写っていないフレームから採る)
- `ko`: `K.O.!!` の接尾辞のみ (数字を含まない)。81x18 px。`493.4 秒` の `[631:649, 672:753]`
- `assist`: `ASSISTED!`。154x15 px。`207.1 秒` の `[634:649, 602:756]`

実行時はキャリブレーションで求めたスケールに合わせて **ROI 側を参照サイズへ正規化**して
から照合する (テンプレートは参照サイズのまま使う)。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np

_REF_PATH = Path(__file__).with_name("indicators.npz")
_TEMPLATE_KEYS = ("anchor", "ko", "assist")


@lru_cache(maxsize=1)
def load_templates() -> dict[str, np.ndarray]:
    """同梱テンプレートを読み込む (グレースケール生値)。"""
    with np.load(_REF_PATH) as data:
        return {k: data[k].copy() for k in _TEMPLATE_KEYS}
