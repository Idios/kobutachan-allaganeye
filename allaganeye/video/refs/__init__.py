"""同梱テンプレート (KO / ASSIST インジケータ検出用、#1106)。

実測の正: `docs/superpowers/specs/2026-11-12-l4-ko-assist-indicator-appearance.md`

テンプレートは **1080p の参照レイアウト**から切り出したグレースケール画像。
実行時はキャリブレーションで求めたスケール `s` に合わせて **ROI 側を正規化**して
から照合する (テンプレートは参照サイズのまま使う)。

キー:

- `gauge`: 戦意値ゲージ (像アイコン + バー)。50x200 px。キャリブレーション用アンカー
- `ko`: `K.O.!!` の接尾辞のみ (数字を含まない)。34x76 px
- `assist`: `ASSISTED!`。22x160 px
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np

_REF_PATH = Path(__file__).with_name("indicators.npz")
_TEMPLATE_KEYS = ("gauge", "ko", "assist")


@lru_cache(maxsize=1)
def load_templates() -> dict[str, np.ndarray]:
    """同梱テンプレートを読み込む (グレースケール)。"""
    with np.load(_REF_PATH) as data:
        return {k: data[k].copy() for k in _TEMPLATE_KEYS}
