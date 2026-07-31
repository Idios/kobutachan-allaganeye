# #860 wmic-less hw probe fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** wmic 非搭載 (Win11 24H2+) 環境で GPU vendor / CPU / memory 検出が全滅する bug を、PowerShell `Get-CimInstance` fallback で解消する。

**Architecture:** `allaganeye/system_info.py` の Windows hw probe 4 箇所に、既存の wmic 分岐を**非改変のまま**、wmic が結果を出せないときだけ発火する PowerShell CIM fallback を挿入する (additive、released path regression ゼロ)。加えて Windows で GPU vendor が 0 件のとき verbose CLI に警告を出す純粋関数を追加する。

**Tech Stack:** Python 3 (stdlib subprocess), pytest + unittest.mock, Windows PowerShell 5.1 (`powershell.exe`, in-box)。

## Global Constraints

- 実装対象は `allaganeye/system_info.py` のみ + verbose 配線で `allaganeye/commands/split_matches.py`。**GUI / Rust / metadata schema は非接触** (spec §7、別 issue)。
- 各 probe の **wmic 分岐は 1 行も変更しない** (validated path 非破壊)。PS fallback は wmic が結果を出せなかった位置に**挿入のみ**。例外は CPU cores の early-return を「found なら return」に微修正 (spec §3.2)。
- PS 呼び出しは `["powershell", "-NoProfile", "-NonInteractive", "-Command", <script>]`、`timeout=_PS_TIMEOUT_S`（`_PS_TIMEOUT_S = 10.0`）。
- すべての probe は失敗時に既存契約どおり `[]` / `None` / `(unavailable)` に縮退し、**例外を送出しない / split を止めない**。
- base ブランチ = `develop-0.3.0`。Co-Authored-By は `Claude Fable 5 <noreply@anthropic.com>` (CLAUDE.md memory)。
- テストは `@patch("allaganeye.system_info._run_text")` の `side_effect` を `cmd[:1]` で分岐する既存パターンに従う (`tests/test_system_info.py` 参照)。

---

### Task 1: `_windows_ps_values` ヘルパ + `_PS_TIMEOUT_S`

**Files:**

- Modify: `allaganeye/system_info.py` (定数 `_SUBPROCESS_TIMEOUT_S` 付近に `_PS_TIMEOUT_S` 追加、`_probe_gpu_names_platform` の手前あたりに helper 追加)
- Test: `tests/test_system_info.py`

**Interfaces:**

- Consumes: 既存 `_run_text(cmd, *, timeout) -> str | None`
- Produces: `_windows_ps_values(cim_class: str, prop: str) -> list[str]` — `Get-CimInstance <cim_class> | Select -ExpandProperty <prop>` の header-less 値行リスト。失敗時 `[]`。定数 `_PS_TIMEOUT_S: float = 10.0`。

- [ ] **Step 1: Write the failing tests**

`tests/test_system_info.py` の末尾に追加:

```python
# --- _windows_ps_values (wmic-less CIM fallback, #860) ---


@patch("allaganeye.system_info._run_text")
def test_windows_ps_values_parses_expandproperty_output(mock_run):
    from allaganeye.system_info import _windows_ps_values

    mock_run.return_value = "AMD Radeon RX 7900 XTX\nIntel UHD Graphics\n"
    result = _windows_ps_values("Win32_VideoController", "Name")
    assert result == ["AMD Radeon RX 7900 XTX", "Intel UHD Graphics"]

    cmd = mock_run.call_args.args[0]
    assert cmd[0] == "powershell"
    assert "-NoProfile" in cmd
    assert "-NonInteractive" in cmd
    assert "Get-CimInstance -ClassName Win32_VideoController" in cmd[-1]
    assert "-ExpandProperty Name" in cmd[-1]
    assert mock_run.call_args.kwargs["timeout"] == 10.0


@patch("allaganeye.system_info._run_text", return_value=None)
def test_windows_ps_values_empty_on_failure(_run):
    from allaganeye.system_info import _windows_ps_values

    assert _windows_ps_values("Win32_Processor", "Name") == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_system_info.py -k windows_ps_values -v`
Expected: FAIL with `ImportError: cannot import name '_windows_ps_values'`

- [ ] **Step 3: Write minimal implementation**

`allaganeye/system_info.py` の定数部に追加:

```python
_PS_TIMEOUT_S = 10.0  # PowerShell cold start は wmic より遅い (#860)
```

`_probe_gpu_names_platform` の直前に追加:

```python
def _windows_ps_values(cim_class: str, prop: str) -> list[str]:
    """Return `prop` values from ``Get-CimInstance <cim_class>`` via PowerShell.

    wmic-less (Win11 24H2+) fallback for Windows hw probes (#860).
    ``powershell.exe`` (Windows PowerShell 5.1) is in-box on Win10/11
    incl. 24H2/25H2 (only wmic etc. moved to Features on Demand).
    ``-ExpandProperty`` yields header-less output, one value per line.
    Returns ``[]`` on any failure (never raises).
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

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_system_info.py -k windows_ps_values -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add allaganeye/system_info.py tests/test_system_info.py
git commit --no-gpg-sign -m "feat(#860): _windows_ps_values PowerShell CIM fallback helper

Refs #860

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: GPU names / vendor の PS fallback

**Files:**

- Modify: `allaganeye/system_info.py:434-467` (`_probe_gpu_names_platform` の Windows 分岐)
- Test: `tests/test_system_info.py`

**Interfaces:**

- Consumes: `_windows_ps_values` (Task 1)
- Produces: 変更なし (既存 `_probe_gpu_names_platform` / `probe_gpu_vendors` の挙動を wmic-less 環境で拡張)

- [ ] **Step 1: Write the failing tests**

```python
# --- GPU vendor PS fallback (#860) ---


@patch("allaganeye.system_info.platform.system", return_value="Windows")
@patch("allaganeye.system_info._run_text")
def test_probe_gpu_vendors_ps_fallback_when_wmic_absent(mock_run, _system):
    from allaganeye.system_info import probe_gpu_vendors

    def side_effect(cmd, **_kwargs):
        if cmd[:1] == ["nvidia-smi"]:
            return None
        if cmd[:1] == ["wmic"]:
            return None  # wmic-less env (Win11 24H2+)
        if cmd[:1] == ["powershell"]:
            return "AMD Radeon RX 7900 XTX\nIntel UHD Graphics\n"
        return None

    mock_run.side_effect = side_effect
    assert probe_gpu_vendors() == ["amd", "intel"]


@patch("allaganeye.system_info.platform.system", return_value="Windows")
@patch("allaganeye.system_info._run_text")
def test_probe_gpu_vendors_no_ps_call_when_wmic_ok(mock_run, _system):
    """Regression pin: validated wmic path must not invoke PowerShell."""
    from allaganeye.system_info import probe_gpu_vendors

    seen = []

    def side_effect(cmd, **_kwargs):
        seen.append(cmd[0])
        if cmd[:1] == ["nvidia-smi"]:
            return None
        if cmd[:1] == ["wmic"]:
            return "Name\nAMD Radeon RX 7900 XTX\n"
        return None

    mock_run.side_effect = side_effect
    assert probe_gpu_vendors() == ["amd"]
    assert "powershell" not in seen
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_system_info.py -k "probe_gpu_vendors_ps_fallback or no_ps_call" -v`
Expected: `test_probe_gpu_vendors_ps_fallback_when_wmic_absent` FAILs (`assert [] == ["amd", "intel"]`)。regression pin は既に PASS。

- [ ] **Step 3: Modify implementation**

`_probe_gpu_names_platform` の Windows 分岐 (現状):

```python
    if system == "Windows":
        stdout = _run_text(["wmic", "path", "win32_VideoController", "get", "Name"])
        if stdout:
            return [line.strip() for line in stdout.splitlines()[1:] if line.strip()]
```

を次に置換:

```python
    if system == "Windows":
        stdout = _run_text(["wmic", "path", "win32_VideoController", "get", "Name"])
        if stdout:
            names = [line.strip() for line in stdout.splitlines()[1:] if line.strip()]
            if names:
                return names
        return _windows_ps_values("Win32_VideoController", "Name")  # #860
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_system_info.py -k "probe_gpu_vendors_ps_fallback or no_ps_call" -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add allaganeye/system_info.py tests/test_system_info.py
git commit --no-gpg-sign -m "feat(#860): GPU names PowerShell CIM fallback for wmic-less env

Refs #860

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: CPU name の PS fallback

**Files:**

- Modify: `allaganeye/system_info.py:98-108` (`_detect_cpu_models` の Windows 分岐)
- Test: `tests/test_system_info.py`

**Interfaces:**

- Consumes: `_windows_ps_values` (Task 1)
- Produces: 変更なし (wmic 失敗時 PS → 既存 `platform.processor()` の順)

- [ ] **Step 1: Write the failing test**

```python
# --- CPU name PS fallback (#860) ---


@patch("allaganeye.system_info.platform.system", return_value="Windows")
@patch("allaganeye.system_info._run_text")
def test_cpu_models_ps_fallback_when_wmic_absent(mock_run, _system):
    from allaganeye.system_info import _detect_cpu_models

    def side_effect(cmd, **_kwargs):
        if cmd[:1] == ["wmic"]:
            return None
        if cmd[:1] == ["powershell"]:
            return "AMD Ryzen 9 9950X3D 16-Core Processor\n"
        return None

    mock_run.side_effect = side_effect
    assert _detect_cpu_models() == ["AMD Ryzen 9 9950X3D 16-Core Processor"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_system_info.py -k cpu_models_ps_fallback -v`
Expected: FAIL (`platform.processor()` の実値 or 空を返し、期待値と不一致)

- [ ] **Step 3: Modify implementation**

`_detect_cpu_models` の Windows 分岐 (現状):

```python
    if system == "Windows":
        stdout = _run_text(["wmic", "cpu", "get", "name"])
        if stdout:
            lines = [line.strip() for line in stdout.splitlines() if line.strip()]
            # First line is the "Name" header; subsequent lines are per-CPU.
            if len(lines) >= 2:
                return lines[1:]
        # Fall back to platform.processor() which on Windows returns
        # the CPU brand via registry lookup.
        proc = platform.processor().strip()
        return [proc] if proc else None
```

を次に置換 (wmic 分岐は非改変、PS を `platform.processor()` の手前に挿入):

```python
    if system == "Windows":
        stdout = _run_text(["wmic", "cpu", "get", "name"])
        if stdout:
            lines = [line.strip() for line in stdout.splitlines() if line.strip()]
            # First line is the "Name" header; subsequent lines are per-CPU.
            if len(lines) >= 2:
                return lines[1:]
        ps = _windows_ps_values("Win32_Processor", "Name")  # #860
        if ps:
            return ps
        # Fall back to platform.processor() which on Windows returns
        # the CPU brand via registry lookup.
        proc = platform.processor().strip()
        return [proc] if proc else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_system_info.py -k cpu_models_ps_fallback -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add allaganeye/system_info.py tests/test_system_info.py
git commit --no-gpg-sign -m "feat(#860): CPU name PowerShell CIM fallback for wmic-less env

Refs #860

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: CPU physical cores の PS fallback (early-return 微修正込み)

**Files:**

- Modify: `allaganeye/system_info.py:180-192` (`_detect_physical_cores` の Windows 分岐)
- Test: `tests/test_system_info.py`

**Interfaces:**

- Consumes: `_windows_ps_values` (Task 1)
- Produces: 変更なし。挙動差: 「wmic 応答あり但し digit 無し」で従来 `None` early-return → PS fallthrough に変更 (spec §3.2、正常機は従来どおり early-return し PS 非呼出)。

- [ ] **Step 1: Write the failing tests**

```python
# --- CPU cores PS fallback (#860) ---


@patch("allaganeye.system_info.platform.system", return_value="Windows")
@patch("allaganeye.system_info._run_text")
def test_physical_cores_ps_fallback_single_socket(mock_run, _system):
    from allaganeye.system_info import _detect_physical_cores

    def side_effect(cmd, **_kwargs):
        if cmd[:1] == ["wmic"]:
            return None
        if cmd[:1] == ["powershell"]:
            return "16\n"
        return None

    mock_run.side_effect = side_effect
    assert _detect_physical_cores() == 16


@patch("allaganeye.system_info.platform.system", return_value="Windows")
@patch("allaganeye.system_info._run_text")
def test_physical_cores_ps_fallback_sums_sockets(mock_run, _system):
    from allaganeye.system_info import _detect_physical_cores

    def side_effect(cmd, **_kwargs):
        if cmd[:1] == ["wmic"]:
            return None
        if cmd[:1] == ["powershell"]:
            return "64\n64\n"  # dual socket
        return None

    mock_run.side_effect = side_effect
    assert _detect_physical_cores() == 128
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_system_info.py -k physical_cores_ps_fallback -v`
Expected: FAIL (現状 wmic None → `return None`)

- [ ] **Step 3: Modify implementation**

`_detect_physical_cores` の Windows 分岐 (現状):

```python
    if system == "Windows":
        stdout = _run_text(["wmic", "cpu", "get", "NumberOfCores"])
        if stdout:
            total = 0
            found = False
            for line in stdout.splitlines():
                line = line.strip()
                if line.isdigit():
                    total += int(line)
                    found = True
            return total if found else None
        return None
```

を次に置換 (wmic の集計ロジックは非改変、early-return を「found なら return」にし PS へ fallthrough):

```python
    if system == "Windows":
        stdout = _run_text(["wmic", "cpu", "get", "NumberOfCores"])
        if stdout:
            total = 0
            found = False
            for line in stdout.splitlines():
                line = line.strip()
                if line.isdigit():
                    total += int(line)
                    found = True
            if found:
                return total
        ps = _windows_ps_values("Win32_Processor", "NumberOfCores")  # #860
        total = 0
        found = False
        for value in ps:
            if value.isdigit():
                total += int(value)
                found = True
        return total if found else None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_system_info.py -k physical_cores_ps_fallback -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add allaganeye/system_info.py tests/test_system_info.py
git commit --no-gpg-sign -m "feat(#860): CPU cores PowerShell CIM fallback for wmic-less env

Refs #860

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: memory の PS fallback

**Files:**

- Modify: `allaganeye/system_info.py:322-337` (`_detect_total_memory_bytes` の Windows 分岐)
- Test: `tests/test_system_info.py`

**Interfaces:**

- Consumes: `_windows_ps_values` (Task 1)
- Produces: 変更なし

- [ ] **Step 1: Write the failing test**

```python
# --- memory PS fallback (#860) ---


@patch("allaganeye.system_info.platform.system", return_value="Windows")
@patch("allaganeye.system_info._run_text")
def test_total_memory_ps_fallback_when_wmic_absent(mock_run, _system):
    from allaganeye.system_info import _detect_total_memory_bytes

    def side_effect(cmd, **_kwargs):
        if cmd[:1] == ["wmic"]:
            return None
        if cmd[:1] == ["powershell"]:
            return "137438953472\n"
        return None

    mock_run.side_effect = side_effect
    assert _detect_total_memory_bytes() == 137438953472
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_system_info.py -k total_memory_ps_fallback -v`
Expected: FAIL (現状 wmic None → `return None`)

- [ ] **Step 3: Modify implementation**

`_detect_total_memory_bytes` の Windows 分岐 (現状):

```python
    if system == "Windows":
        stdout = _run_text(
            [
                "wmic",
                "ComputerSystem",
                "get",
                "TotalPhysicalMemory",
            ]
        )
        if stdout:
            for line in stdout.splitlines():
                line = line.strip()
                if line.isdigit():
                    return int(line)
        return None
```

を次に置換 (wmic 分岐は非改変、PS を末尾 `return None` の手前に挿入):

```python
if system == "Windows":
    stdout = _run_text(
        [
            "wmic",
            "ComputerSystem",
            "get",
            "TotalPhysicalMemory",
        ]
    )
    if stdout:
        for line in stdout.splitlines():
            line = line.strip()
            if line.isdigit():
                return int(line)
    for value in _windows_ps_values(
        "Win32_ComputerSystem", "TotalPhysicalMemory"
    ):  # #860
        if value.isdigit():
            return int(value)
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_system_info.py -k total_memory_ps_fallback -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add allaganeye/system_info.py tests/test_system_info.py
git commit --no-gpg-sign -m "feat(#860): memory PowerShell CIM fallback for wmic-less env

Refs #860

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: `gpu_vendor_probe_warning` + verbose header 配線

**Files:**

- Modify: `allaganeye/system_info.py` (`probe_gpu_vendors` の後ろに追加)
- Modify: `allaganeye/commands/split_matches.py:1752-1776` (`_print_verbose_header` の import + GPU ブロック直後)
- Test: `tests/test_system_info.py` / `tests/test_split_matches.py`

**Interfaces:**

- Consumes: `probe_gpu_vendors` (既存)
- Produces: `gpu_vendor_probe_warning() -> str | None` — Windows で GPU vendor 0 件のとき警告文、それ以外 `None`。

- [ ] **Step 1: Write the failing tests (system_info)**

`tests/test_system_info.py` に追加:

```python
# --- gpu_vendor_probe_warning (verbose silent-degrade visibility, #860) ---


@patch("allaganeye.system_info.platform.system", return_value="Windows")
@patch("allaganeye.system_info.probe_gpu_vendors", return_value=[])
def test_gpu_vendor_probe_warning_fires_on_empty_windows(_vendors, _system):
    from allaganeye.system_info import gpu_vendor_probe_warning

    msg = gpu_vendor_probe_warning()
    assert msg is not None
    assert "libx264" in msg


@patch("allaganeye.system_info.platform.system", return_value="Windows")
@patch("allaganeye.system_info.probe_gpu_vendors", return_value=["nvidia"])
def test_gpu_vendor_probe_warning_none_when_vendor_present(_vendors, _system):
    from allaganeye.system_info import gpu_vendor_probe_warning

    assert gpu_vendor_probe_warning() is None


@patch("allaganeye.system_info.platform.system", return_value="Linux")
@patch("allaganeye.system_info.probe_gpu_vendors", return_value=[])
def test_gpu_vendor_probe_warning_none_on_non_windows(_vendors, _system):
    from allaganeye.system_info import gpu_vendor_probe_warning

    assert gpu_vendor_probe_warning() is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_system_info.py -k gpu_vendor_probe_warning -v`
Expected: FAIL with `ImportError: cannot import name 'gpu_vendor_probe_warning'`

- [ ] **Step 3: Implement the warning function**

`allaganeye/system_info.py` の `probe_gpu_vendors` 直後に追加:

```python
def gpu_vendor_probe_warning() -> str | None:
    """Return a warning when Windows GPU vendor detection found nothing (#860).

    wmic/PowerShell 両方の probe 失敗 (または真に GPU 無し) を verbose header
    で可視化し、GUI export が GPU エンコーダを提示できず libx264 へ silent
    degrade する事態にユーザーが気づけるようにする。Windows 以外、または
    vendor を 1 件以上検出できた場合は ``None``。
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

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_system_info.py -k gpu_vendor_probe_warning -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Write the failing test (verbose wiring)**

`tests/test_split_matches.py` に追加 (import は既存パターンに合わせる):

```python
def test_verbose_header_echoes_gpu_vendor_warning(capsys, monkeypatch, tmp_path):
    """_print_verbose_header surfaces gpu_vendor_probe_warning() when set (#860)."""
    from allaganeye.commands import split_matches

    # Keep the header hermetic: stub the probe getters so no real subprocess runs.
    monkeypatch.setattr("allaganeye.system_info.get_cpu_info", lambda: "CPU-X")
    monkeypatch.setattr("allaganeye.system_info.get_gpu_info_lines", lambda: [])
    monkeypatch.setattr("allaganeye.system_info.get_memory_info", lambda: "1.0 GB")
    monkeypatch.setattr(
        "allaganeye.system_info.gpu_vendor_probe_warning",
        lambda: "WARN-GPU-SENTINEL",
    )

    split_matches._print_verbose_header(tmp_path)

    out = capsys.readouterr().out
    assert "WARN-GPU-SENTINEL" in out
```

- [ ] **Step 6: Run test to verify it fails**

Run: `pytest tests/test_split_matches.py -k verbose_header_echoes_gpu_vendor_warning -v`
Expected: FAIL (warning line not echoed)

- [ ] **Step 7: Wire the warning into the verbose header**

`allaganeye/commands/split_matches.py` の `_print_verbose_header` 内 import (L1752-1757) に `gpu_vendor_probe_warning` を追加:

```python
    from allaganeye.system_info import (
        get_cpu_info,
        get_disk_info,
        get_gpu_info_lines,
        get_memory_info,
        gpu_vendor_probe_warning,
    )
```

GPU ブロック (L1767-1775) の直後、`Memory:` 行の手前に追加:

```python
    gpu_warning = gpu_vendor_probe_warning()
    if gpu_warning is not None:
        typer.echo(f"  ! {gpu_warning}")
```

- [ ] **Step 8: Run test to verify it passes**

Run: `pytest tests/test_split_matches.py -k verbose_header_echoes_gpu_vendor_warning -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add allaganeye/system_info.py allaganeye/commands/split_matches.py tests/test_system_info.py tests/test_split_matches.py
git commit --no-gpg-sign -m "feat(#860): verbose CLI warning on empty GPU vendor probe

Refs #860

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: 全体チェック (lint / 型 / 全テスト)

**Files:** なし (検証のみ)

- [ ] **Step 1: 全 system_info テスト**

Run: `pytest tests/test_system_info.py -v`
Expected: 既存 42 + 新規 ~11 = 全 PASS

- [ ] **Step 2: lint / format / 型**

Run: `ruff check . && ruff format --check . && pyright allaganeye/system_info.py allaganeye/commands/split_matches.py`
Expected: エラーなし

- [ ] **Step 3: 影響範囲テスト**

Run: `pytest tests/test_split_matches.py -v`
Expected: 全 PASS

- [ ] **Step 4: 実機検証依頼 (Iron Law 6)**

controller が Idios に `AskUserQuestion` で以下を依頼 (mock 不可):

- `where wmic` で wmic 在否確認 (Win11 build 26200)
- 修正後 `allaganeye detect <video> -v` で CPU / GPU / Memory 行が埋まるか
- `metadata.json system_info.gpu_vendors_available` が非空か (nvidia は元々埋まる → wmic 非搭載時に iGPU/AMD vendor + CPU/memory 行が PS fallback で復活するかが焦点)

## Self-Review

**1. Spec coverage:**

- spec §2 scope=全4経路 → Task 2 (GPU) / 3 (CPU name) / 4 (cores) / 5 (memory)。✓
- spec §3.1 `_windows_ps_values` → Task 1。✓
- spec §3.2 挿入方針 + CPU cores 微修正 → Task 4 に明記。✓
- spec §4 warning + verbose 配線 → Task 6。✓
- spec §5 TDD 4 種 (fallback red / warning red / regression pin / portability) → Task 2 (regression pin) / Task 6 (warning + portability pin) / 各 fallback task。✓
- spec §6 実機検証 → Task 7 Step 4。✓
- spec §7 scope 外 (GUI/pwsh) → 本 plan は touch せず。✓

**2. Placeholder scan:** "TBD"/"handle edge cases"/"similar to" なし。全 step にコード/コマンド/期待出力あり。✓

**3. Type consistency:** `_windows_ps_values(cim_class: str, prop: str) -> list[str]` を Task 2-5 で一貫使用。`gpu_vendor_probe_warning() -> str | None` を Task 6 で定義・配線一貫。`_PS_TIMEOUT_S = 10.0` を Task 1 で定義し test で `10.0` を assert。✓
