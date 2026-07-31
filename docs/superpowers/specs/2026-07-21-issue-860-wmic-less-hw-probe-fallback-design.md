# #860 wmic 非搭載環境の hw probe fallback 設計 (2026-07-21)

> **Status**: design (approved by Idios via brainstorming, 2026-07-21)
> **Issue**: #860 (bug, P2-medium) / audit 2026-06-10 P2-12 [要検証]
> **Base**: develop-0.3.0 (v0.3.0 scope、2026-07-21 rescope で released regression として v0.3.0 に取り込み)
> **由来**: session `l3-residual-plan` brainstorming で Idios が scope / fallback 構成 / 警告範囲の 3 点を確定

## 1. 背景 / 問題

`allaganeye/system_info.py` の Windows hw probe 4 箇所がすべて `wmic` に依存している:

| probe | 行 | wmic コマンド | 用途 |
| --- | --- | --- | --- |
| GPU names | L445 (`_probe_gpu_names_platform`) | `wmic path win32_VideoController get Name` | vendor 検出 (`probe_gpu_vendors`) |
| CPU name | L99 (`_detect_cpu_models`) | `wmic cpu get name` | verbose header |
| CPU cores | L182 (`_detect_physical_cores`) | `wmic cpu get NumberOfCores` | verbose header |
| memory | L324 (`_detect_total_memory_bytes`) | `wmic ComputerSystem get TotalPhysicalMemory` | verbose header |

`wmic` は Windows 11 24H2 以降デフォルト非搭載 (Features on Demand 化)。NVIDIA 機は `nvidia-smi` で GPU vendor が救済されるが、**AMD/Intel-only 機は wmic 経路しかなく vendor 検出が全滅**する。

### ユーザー影響 (実害)

GPU vendor 検出が空になると `metadata.json system_info.gpu_vendors_available` が空 → GUI export の `enumerate_h264_encoders` が QSV/AMF を提示できず **silent に libx264 固定へ degrade** する (エラーなし・ユーザーが気づく手段なし)。CPU/memory probe 失敗は verbose header が `(unavailable)` になるのみで機能影響なし。

## 2. 確定スコープ (brainstorming)

| 論点 | 選択肢 | 採用 | 根拠 |
| --- | --- | --- | --- |
| 修正スコープ | GPU のみ / 全 wmic 経路 4 箇所 | **全 4 経路** | 同一 root cause (wmic 非搭載) の一括解消。fallback helper 1 つで限界コスト小。verbose header の `(unavailable)` 化も同時に防ぐ |
| fallback 構成 | wmic 優先+PS fallback / PS 優先 / PS 優先+wmic fallback | **wmic 優先 + PS fallback** | validated 済 wmic parsing を非改変で保持 → released path regression ゼロ (additive)。issue の「fallback を追加」文言と整合 |
| 警告範囲 | verbose CLI のみ / verbose+GUI / 警告なし | **verbose CLI のみ** | GUI 側可視化 (metadata signal + React/Rust wiring) は released encode path 非接触のため別 issue に切り出し。本 PR は CLI 完結 |

## 3. アーキテクチャ (additive、validated path 非破壊)

### 3.1 新規ヘルパ `_windows_ps_values`

```python
_PS_TIMEOUT_S = 10.0  # PowerShell cold start は wmic より遅い (5s では tight)


def _windows_ps_values(cim_class: str, prop: str) -> list[str]:
    """Return `prop` values from `Get-CimInstance <cim_class>` via PowerShell.

    wmic-less (Win11 24H2+) fallback (#860).  Uses `-ExpandProperty` so
    output is header-less, one value per line.  `powershell.exe`
    (Windows PowerShell 5.1) is in-box on Win10/11 incl. 24H2/25H2
    (only wmic etc. were moved to Features on Demand).  Returns [] on
    any failure (never raises).
    """
    stdout = _run_text(
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            f"Get-CimInstance -ClassName {cim_class} "
            f"| Select-Object -ExpandProperty {prop}",
        ],
        timeout=_PS_TIMEOUT_S,
    )
    if not stdout:
        return []
    return [line.strip() for line in stdout.splitlines() if line.strip()]
```

- `_run_text` 経由なので例外は全て握り潰し `[]` に縮退。`powershell.exe` が PATH に無い希少ケースも `None` → `[]`。
- 値は GPU/CPU 名 (ASCII 主体) + digit のみ。`_run_text` の `encoding="utf-8", errors="replace"` で decode 安全 (PS 5.1 の redirected stdout code page 差異は ASCII 値では無害)。
- `-NoProfile` で profile 副作用回避、`-NonInteractive` で prompt hang 回避。

### 3.2 各 probe への挿入 (wmic 分岐は 1 行も変えない)

**方針**: 既存の wmic 分岐をそのまま残し、「wmic が結果を出せなかったとき」の位置に PS fallback を挿入する。

| probe | 挿入位置 | PS fallback |
| --- | --- | --- |
| GPU names | wmic が空 list → PS、それも空なら `[]` | `_windows_ps_values("Win32_VideoController", "Name")` |
| CPU name | wmic 失敗 → **PS** → `platform.processor()` の間 | `_windows_ps_values("Win32_Processor", "Name")` |
| CPU cores | wmic が digit 拾えず → PS (socket ごとに 1 行 → 合算) | `_windows_ps_values("Win32_Processor", "NumberOfCores")` |
| memory | wmic 失敗 → PS (最初の digit を採用) | `_windows_ps_values("Win32_ComputerSystem", "TotalPhysicalMemory")` |

擬似コード (GPU names):

```python
if system == "Windows":
    stdout = _run_text(["wmic", "path", "win32_VideoController", "get", "Name"])
    if stdout:
        names = [l.strip() for l in stdout.splitlines()[1:] if l.strip()]
        if names:
            return names
    return _windows_ps_values("Win32_VideoController", "Name")  # NEW
```

擬似コード (CPU cores、既存の early-return を「found なら return」に微修正して fallthrough を許す):

```python
if system == "Windows":
    stdout = _run_text(["wmic", "cpu", "get", "NumberOfCores"])
    if stdout:
        total, found = 0, False
        for line in stdout.splitlines():
            line = line.strip()
            if line.isdigit():
                total += int(line)
                found = True
        if found:
            return total
    ps = _windows_ps_values("Win32_Processor", "NumberOfCores")  # NEW
    total, found = 0, False
    for v in ps:
        if v.isdigit():
            total += int(v)
            found = True
    return total if found else None
```

- **挙動差 (許容)**: 旧 CPU cores は「wmic 存在するが digit 無し」で `None` を early-return していたが、新版はその退化ケースで PS fallback に進む。より頑健になる方向で、正常機 (wmic が digit を返す) では従来どおり early-return し PS を呼ばない。

CPU name / memory も同型 (wmic 分岐後、既存の非 wmic fallback の**手前**に PS を挿入)。

## 4. 警告の可視化 (verbose CLI)

```python
def gpu_vendor_probe_warning() -> str | None:
    """Return a warning string when Windows GPU vendor probe found nothing (#860).

    wmic/PS 両方失敗 (または真に GPU 無し) を verbose で可視化し、export の
    libx264 silent degrade をユーザーが気づけるようにする。Windows 以外・
    vendor 検出 1 件以上なら None。
    """
    if platform.system() != "Windows":
        return None
    if probe_gpu_vendors():
        return None
    return (
        "GPU vendor を検出できませんでした (wmic 非搭載環境では PowerShell "
        "fallback も失敗した可能性)。GPU エンコーダ (NVENC/QSV/AMF) は提示されず "
        "export は libx264 になります。"
    )
```

- 呼び出し側: verbose header の GPU 行付近で `None` でなければ 1 行追記 (既存 verbose 出力箇所に配線)。
- **metadata / GUI / Rust は非接触** (別 issue に切り出し)。
- 既知の割り切り: CPU-only VM でも空になり得るが、verbose は opt-in のため過剰警告を許容。

## 5. テスト方針 (TDD, Red-Green)

`_run_text` を `cmd[0]` で分岐 mock (`wmic` → `None`、`powershell` → CIM 出力) して検証する。

1. **fallback red → green** (GPU / CPU name / CPU cores / memory の 4 経路):
   - wmic 非搭載を模擬 (`wmic` → `None`)、PS が有効値を返す設定で、実装前は空/`(unavailable)`、実装後に vendor/値が埋まる。
   - GPU: `probe_gpu_vendors()` が `["amd"]` 等。CPU cores: 複数 socket 行を合算。memory: digit を int 化。
2. **warning red** (`feedback_protective_mechanism_red_verification`: 発火側 red まで):
   - Windows × 空 vendors を注入し `gpu_vendor_probe_warning()` が非 `None` を実証。
   - 非空 vendors / 非 Windows で `None` の pin。
3. **regression pin**: wmic が正常値を返すとき `powershell` が呼ばれないことを mock で assert (validated path 保持)。
4. **portability pin**: 非 Windows (`platform.system()` mock) では wmic/PS 経路に入らない。

## 6. 実機検証 (Iron Law 6)

system_info は released path (metadata `system_info` + GUI encoder 選択) を feed するため、mock 単体 green では不十分。Idios 機 (Win11 build 26200 / 25H2 系、本 bug 当事者環境の可能性大) で:

- `where wmic` で wmic 在否を確認 (非搭載なら bug を live 再現できる)。
- 修正後 `allaganeye detect <video> -v` で GPU / CPU / memory 行が埋まるか。
- `metadata.json system_info.gpu_vendors_available` が非空か。
- (RTX 5090 機のため nvidia は nvidia-smi で元々埋まる。wmic 非搭載時に **iGPU/AMD vendor と CPU/memory 行**が PS fallback で復活するかが検証の焦点。)

着手後に `AskUserQuestion` で依頼する。

## 7. スコープ外 (別 issue 候補)

- GUI export 画面での encoder degrade 警告表示 (metadata signal + React/Rust wiring)。本 PR は CLI 完結のため切り出し。
- `pwsh` (PowerShell 7) 対応。`powershell.exe` 5.1 が in-box のため YAGNI。

## 8. 参照

- issue: #860 / 監査: docs/audits/2026-06-10-full-audit.md P2-12 / spec: docs/superpowers/specs/2026-06-10-audit-remediation-design.md Wave 3 表
- 実装対象: `allaganeye/system_info.py`
- 関連 memory: `feedback_ffmpeg_qsv_stderr_pattern` (encoder fallback は実機 stderr 依存) / `feedback_protective_mechanism_red_verification` (保護機構は発火側 red まで) / `feedback_ps1_script_utf8_no_bom_cp932` (PS encoding 留意)
