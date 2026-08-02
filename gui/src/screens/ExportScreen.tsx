import { invoke } from '@tauri-apps/api/core';
import { listen, type UnlistenFn } from '@tauri-apps/api/event';
import { open as openDialog } from '@tauri-apps/plugin-dialog';
import { useEffect, useReducer, useState } from 'react';

import { DisabledTooltip } from '../components/DisabledTooltip';
import { InlineErrorHint } from '../components/InlineErrorHint';
import { SampleModeBanner } from '../components/SampleModeBanner';
import { toErrorState } from '../lib/appError';
import { useAppStateStore } from '../state/appStateStore';
import { useMetadataStore } from '../state/metadataStore';
import { formatMatchFilename } from '../utils/filename';
import { splitPath, stripExtendedPathPrefix } from '../utils/path';
import pathStyles from '../styles/path-display.module.css';
import { fmtMatchDuration, fmtTime } from '../utils/time';
import { exportReducer } from './reducers/export';
import type { ExportPhase } from './types';
import styles from './ExportScreen.module.css';

type Codec = 'copy' | 'h264';

type MatchStatus = 'pending' | 'running' | 'done' | 'error' | 'skipped';

interface MatchState {
  status: MatchStatus;
  percent: number;
  error?: string;
  /**
   * #663 — corrective hint rendered as a 2nd line below `error` in the
   * per-match list. Sourced from AppError throw sites; absent for
   * progress-event errors and bare `Error` instances.
   */
  errorHint?: string;
  outputPath?: string;
  /**
   * #591 -- non-null when the GPU encoder failed and the export was
   * retried with libx264. Surfaced inline so the user understands why
   * the run is slower than expected for this match.
   */
  fallbackNotice?: string;
}

interface ExportProgressPayload {
  match_index: number;
  percent: number;
  stage: 'encoding' | 'done' | 'error' | 'fallback';
  message?: string;
  /** #591 -- e.g. `"h264_nvenc -> libx264"`. Present when stage === 'fallback'. */
  fallback_from?: string;
}

/**
 * #761 -- payload returned by `enumerate_h264_encoders` Tauri command.
 * Each slot represents one available H.264 encoder (e.g. NVENC, QSV, AMF,
 * libx264). The frontend displays a badge like "NVENC ×3" when multiple
 * GPU slots are available.
 */
interface EncoderSlot {
  slot_index: number;
  encoder_kind: 'Libx264' | 'Nvenc' | 'Qsv' | 'Amf';
  display_label: string;
}

/**
 * #761 -- libx264 fallback used when metadata.json has no system_info
 * (pre-#591 metadata) or the probe came back empty (CPU-only env).
 */
const LIBX264_SLOT: EncoderSlot = {
  slot_index: 0,
  encoder_kind: 'Libx264',
  display_label: 'libx264 (CPU)',
};

interface ExportSummary {
  success: number;
  failure: number;
  skipped: number;
  cancelled: boolean;
}

/**
 * #466 Phase 4 export screen. Real ffmpeg invocation driven by the Rust
 * `start_export` command (single invoke → Python pool spawns N parallel
 * ffmpeg processes); per-match progress arrives via the
 * `export-progress` Tauri event.
 *
 * ## review 反映 (2026-04-25)
 *
 * - **#1**: per-match の include/exclude チェックボックス (ad-hoc)。
 *   `excludedIndexes` ローカル state が制御。`type_override === 'skip'`
 *   (preview で永続設定) は強制 disable で別軸。
 * - **#2**: 出力先 default は `<dirname(videoSource)>` のみ
 *   (#680 で旧 `<dirname>/output` から変更、存在しないフォルダの
 *   プリセット問題を解消、{@link deriveDefaultOutDir})。videoSource は
 *   `selectedVideoPath ?? metadata.source`。
 * - **#3**: 参照ボタンは `@tauri-apps/plugin-dialog` の `open({directory})`
 *   経由 (`dialog:allow-open` permission を `capabilities/default.json` に
 *   明示)。
 * - **#4**: 出力先親ディレクトリが存在しない場合は Rust 側で error。以前の
 *   `create_dir_all` (silent mkdir) は廃止 (タイポ事故防止)。
 * - **#5**: 「フォルダを開く」は `shell.open` のみで完了画面に navigate
 *   しない。失敗時は `openFolderError` で UI に表示。
 * - **#6 (再書き出し)**: 「設定変更して再書き出し」は同じ metadata を別設定
 *   (出力先 / 命名 / コーデック / 試合選択) で再実行する用途。既存ファイル
 *   は ffmpeg `-y` で silent overwrite される。
 * - **#7 (boundary)**: `m.edited?.start_time ?? m.start_time` を
 *   `start_export` の metadata payload に含めて渡す (`end_time` も同様)。
 *   preview で調整した境界が export に反映される。
 *
 * ## 2026-04-25 追加修正 (#545 実機テスト)
 *
 * - **filePath 早期 return 廃止**: 旧実装は `if (!metadata || !filePath)
 *   return` だったが、Phase 3 dummy detect が `loadSample()` のみで
 *   `filePath = null` のまま preview/export に来るため、書き出し開始ボタンが
 *   常に disable + クリックしても無反応になっていた。`start_export` invoke
 *   は metadata JSON を stdin 経由で渡すため `filePath` 不要。`videoSource`
 *   (実 video の path) がある限り動くため、ガードを `!videoSource` に変更。
 * - **list duration の edited 反映**: 旧実装は `m.duration_display` を
 *   そのまま表示していたため、preview で `m.edited.end_time` を変えても
 *   一覧の duration が CLI 初期値のまま固定だった。`m.edited` がある場合は
 *   `effectiveEnd - effectiveStart` を {@link fmtMatchDuration} で再 format
 *   して表示する (CLI `_format_duration` と同一フォーマット)。
 */
export function ExportScreen() {
  const metadata = useMetadataStore((s) => s.metadata);
  const navigate = useAppStateStore((s) => s.navigate);
  const setLastExportOutputDir = useAppStateStore((s) => s.setLastExportOutputDir);

  // #466 review (C): drop で確定した実 path を最優先で使用する。sample mode
  // (selectedVideoPath = null) では metadata.source にフォールバック。
  const selectedVideoPath = useAppStateStore((s) => s.selectedVideoPath);
  const videoSource = selectedVideoPath ?? metadata?.source ?? null;

  // #633 / Task 1.7: sample mode disables all write operations.
  const isSample = useMetadataStore(
    (s) => s.filePath === null && s.metadata !== null,
  );
  const sampleReason = 'サンプル動画では保存できません';

  const [phase, dispatch] = useReducer(exportReducer, 'idle' as ExportPhase);
  // #680 (旧 #466 review #2): default 出力先は source video の親ディレクトリ
  // のみ (存在保証のある既存フォルダを preset)。旧 `<parent>/output` 仕様は
  // 存在しないフォルダがプリセットされる UX 問題のため #680 で廃止。
  // videoSource が無い場合 (sample mode で何も load してない等) は空文字列
  // にしておき、ユーザーに必須選択させる。
  const [outDir, setOutDir] = useState<string>(() => deriveDefaultOutDir(videoSource));
  const [codec, setCodec] = useState<Codec>('copy');
  // #761 -- H.264 encoder slots are enumerated from metadata.system_info on
  // every metadata change via `enumerate_h264_encoders`. Initial value
  // defaults to [LIBX264_SLOT]; useEffect overwrites with the real
  // probe-derived slots once metadata is loaded.
  const [encoderSlots, setEncoderSlots] = useState<EncoderSlot[]>([LIBX264_SLOT]);
  const [namePattern, setNamePattern] = useState('match_{idx:03}.mp4');
  const [matchStates, setMatchStates] = useState<Record<number, MatchState>>({});
  // #466 review #1: per-match の選択 (default: 全選択 = 全試合書き出し)。
  // ユーザーは個別行のチェックボックスで除外でき、「1 試合だけ書き出す」
  // ような ad-hoc な選択も可能。type_override === 'skip' (preview で永続
  // 設定済み) は強制 exclude (UI でも切替不可)。本 set は ad-hoc な exclude
  // のみ追跡。
  const [excludedIndexes, setExcludedIndexes] = useState<ReadonlySet<number>>(
    () => new Set(),
  );
  // #545 review #7 (2026-04-25): progress bar 下の「経過 / 残り」時間表示用。
  // START_CLICKED 時の wall-clock を記録し、`elapsedSec` / `remainingSec` を
  // 描画ループで更新する。残り時間は `(elapsed / done) * remaining` の線形
  // 推定 (done=0 のときは null = 「-」表示)。
  const [exportStartMs, setExportStartMs] = useState<number | null>(null);
  const [nowMs, setNowMs] = useState<number>(() => Date.now());

  // 1 秒間隔の wall-clock tick (running 中のみ)。完了 / 中断 / idle に
  // なれば clearInterval。
  useEffect(() => {
    if (exportStartMs === null) return;
    if (phase !== 'running') return;
    const iv = setInterval(() => {
      setNowMs(Date.now());
    }, 1000);
    return () => clearInterval(iv);
  }, [exportStartMs, phase]);

  // #761 -- enumerate H.264 encoder slots from metadata.system_info on
  // every metadata source change. Falls back to [LIBX264_SLOT] silently
  // when the probe is empty / missing or when the Tauri command rejects
  // (e.g. sample mode without a backing system_info). The effect
  // intentionally calls setEncoderSlots synchronously in the no-system_info
  // branch so that switching from a probe-equipped metadata back to a sample
  // (legacy) one resets the sub label; per-frame cascading renders are
  // not a concern here (encoderSlots updates are bounded and infrequent).
  // `metadata?.source` is used as the dep so the effect re-runs when the
  // user loads a different file (system_info changes with source).
  useEffect(() => {
    if (!metadata?.system_info) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setEncoderSlots([LIBX264_SLOT]);
      return;
    }
    invoke<EncoderSlot[]>('enumerate_h264_encoders', {
      req: {
        vendors: metadata.system_info.gpu_vendors_available ?? [],
        preference: metadata.system_info.vendor_preference ?? ['nvidia', 'amd', 'intel'],
        gpuModels: metadata.system_info.gpu ?? [],
      },
    })
      .then((slots) => setEncoderSlots(slots.length > 0 ? slots : [LIBX264_SLOT]))
      .catch(() => setEncoderSlots([LIBX264_SLOT]));
  }, [metadata?.source]); // eslint-disable-line react-hooks/exhaustive-deps

  // #761 -- encoder badge: "NVENC ×3" when multiple GPU slots are available,
  // single label otherwise. Rebuilt from encoderSlots so the H.264 sub label
  // reflects "(NVENC ×3)" / "(NVENC)" / "(QSV)" / "(AMF)" / "(libx264 (CPU))".
  const encoderBadge =
    encoderSlots.length > 1
      ? `${encoderSlots[0].display_label.split(' ')[0]} ×${encoderSlots.length}`
      : encoderSlots[0].display_label;

  const codecs: { v: Codec; l: string; sub: string }[] = [
    { v: 'copy', l: '無損失 copy', sub: '高速 / 前 I フレーム吸着' },
    {
      v: 'h264',
      l: 'H.264 再エンコード',
      sub: `遅い / 正確な秒指定 (${encoderBadge})`,
    },
  ];

  function toggleMatchExclusion(matchIndex: number) {
    setExcludedIndexes((prev) => {
      const next = new Set(prev);
      if (next.has(matchIndex)) {
        next.delete(matchIndex);
      } else {
        next.add(matchIndex);
      }
      return next;
    });
  }

  /**
   * #545 review #3 (2026-04-25): 一覧の全選択 / 全解除トグル。
   * `type_override === 'skip'` (preview で永続 skip 設定済) は対象外
   * (UI でも個別 checkbox が disabled なので、bulk からも除外する)。
   *
   * - select-all: excludedIndexes から bulk 対象 index を全 remove
   * - deselect-all: bulk 対象 index を全 add
   */
  function toggleSelectAll(selectAll: boolean) {
    if (!metadata) return;
    setExcludedIndexes((prev) => {
      const next = new Set(prev);
      for (const m of metadata.matches) {
        // #805 Phase 2: post_match は個別 checkbox 同様 bulk からも除外。
        if (m.type_override === 'skip' || m.post_match) continue;
        if (selectAll) {
          next.delete(m.index);
        } else {
          next.add(m.index);
        }
      }
      return next;
    });
  }

  // #466 -- listen for per-match progress updates emitted by Rust.
  // #591 -- also handle stage="fallback" events emitted when a GPU
  // encoder fails to initialise and the export retries with libx264.
  useEffect(() => {
    let unlisten: UnlistenFn | null = null;
    // #837 (P3-a) -- unmount-before-listen-resolves race の guard。cleanup が
    // 先に走った場合 disposed=true を見て、解決した unlisten を即時呼んで leak
    // を防ぐ (DetectingScreen #813 と同パターン)。
    let disposed = false;
    // review R3 #1: 迷子 event warn の per-match dedup。invariant が実際に
    // 破れた場合の毎秒 tick で同一 warn が数百件流れるのを 1 件/match に抑制。
    const warnedStray = new Set<number>();
    (async () => {
      const u = await listen<ExportProgressPayload>('export-progress', (event) => {
        const p = event.payload;
        // #805 Phase 2 (review R1 #2、P3-1 と同根): post_match 行への迷子
        // event は state ごと無視する。mark の '—' pin (render 側) に加え、
        // progress fill / error 行 / fallbackNotice も「export.py が emit
        // しない前提」に依存させない。metadata は store から都度取得
        // (deps [] の stale closure を回避)。
        const strayTarget = useMetadataStore
          .getState()
          .metadata?.matches.find((mm) => mm.index === p.match_index);
        if (strayTarget?.post_match === true) {
          // review R2 #1: silent drop にしない。この event は Phase 1
          // invariant (export.py は post_match を処理しない) の破れの
          // 唯一の GUI 可視証拠なので、UI は凍結したまま dev console に
          // 痕跡を残す (errorStore.ts の warn precedent と同方針)。
          if (!warnedStray.has(p.match_index)) {
            warnedStray.add(p.match_index);
            console.warn(
              '[export] dropped stray export-progress event for post_match match',
              p.match_index,
            );
          }
          return;
        }
        setMatchStates((prev) => {
          const prior = prev[p.match_index] ?? {
            status: 'pending' as MatchStatus,
            percent: 0,
          };
          let status: MatchStatus = prior.status;
          if (p.stage === 'encoding') status = 'running';
          else if (p.stage === 'done') status = 'done';
          else if (p.stage === 'error') status = 'error';
          // #591 -- "fallback" stamps the per-match notice so the UI can
          // surface why this match is slower (the libx264 attempt restarts
          // encoding, so percent legitimately rewinds to 0).
          //
          // It also forces the row to `running`: a NVENC init failure dies
          // before a single frame is encoded, so the fallback event is
          // typically the *first* event for that match. Keeping `prior`
          // would leave the row at `○` (pending) while showing a "retrying
          // with libx264" notice -- a contradictory state.
          else if (p.stage === 'fallback') status = 'running';
          const fallbackNotice =
            p.stage === 'fallback'
              ? p.message ?? `${p.fallback_from ?? 'GPU encoder'} 失敗、libx264 で再試行`
              : prior.fallbackNotice;
          return {
            ...prev,
            [p.match_index]: {
              ...prior,
              status,
              percent: p.percent,
              error: p.stage === 'error' ? p.message : prior.error,
              // #663 — `export-progress` event payload does not currently
              // carry an AppError hint (Rust-side enhancement is future
              // work). errorHint の最終 source of truth は catch handler
              // (catch handler が MatchState を全置換するため、progress
              // event 時点では prior.errorHint は基本 undefined のまま
              // preserved。この event handler は errorHint を能動的に
              // セットせず、catch handler の結果が後から確定する形)。
              errorHint: prior.errorHint,
              fallbackNotice,
            },
          };
        });
      });
      if (disposed) {
        // cleanup が先行した: 取得した listener を即 teardown して return
        u();
        return;
      }
      unlisten = u;
    })();
    return () => {
      disposed = true;
      unlisten?.();
    };
  }, []);

  function formatName(index: number, type: string, startSec: number): string {
    // #932: 展開処理の実体は utils/filename.ts に移設 (MinimapScreen と共有)。
    return formatMatchFilename(namePattern, index, type, startSec);
  }

  async function handlePickDir() {
    const picked = await openDialog({ directory: true, multiple: false });
    if (typeof picked === 'string') {
      // PR #655 Round 2: same `\\?\` prefix leak the recent-list saw —
      // Tauri's directory picker hands back the extended-length form on
      // Windows and it shows up verbatim in the textbox. Normalize before
      // storing so display + ffmpeg invocation see the conventional form.
      setOutDir(stripExtendedPathPrefix(picked));
    }
  }

  async function handleStartExport() {
    // 2026-04-25 修正: filePath は metadata.json の path であり、
    // export invoke 自体は videoSource (実 video path) だけで動く。
    // dummy detect で loadSample() のみ走った場合 filePath は null のため、
    // 旧 `!filePath` early return + button disabled 条件は誤検知になる。
    if (!metadata) return;
    if (!videoSource) return;

    // Initialize per-match state. Skip = `type_override === 'skip'` (永続)
    // または excludedIndexes に含まれる (ad-hoc UI 選択、#466 review #1)。
    const nextStates: Record<number, MatchState> = {};
    for (const m of metadata.matches) {
      // #805 Phase 2: post_match は export.py 側で常に skip されるため
      // UI 側も最初から skipped 表示にする。この branch は mark の '—' pin
      // (render 側) + listener の迷子 event guard により render 出力では
      // 観測不能な意図的 defense-in-depth — dead branch ではない (review R2 #3、
      // 除外点 6 箇所の一貫性維持のため残す)。
      if (
        m.type_override === 'skip' ||
        m.post_match ||
        excludedIndexes.has(m.index)
      ) {
        nextStates[m.index] = { status: 'skipped', percent: 0 };
      } else {
        nextStates[m.index] = { status: 'pending', percent: 0 };
      }
    }
    setMatchStates(nextStates);
    // #545 review #7: 経過 / 残り時間計測の起点。
    const startMs = Date.now();
    setExportStartMs(startMs);
    setNowMs(startMs);
    // #893 R2: record the export output dir so MinimapScreen can default to it.
    setLastExportOutputDir(outDir);
    dispatch({ type: 'START_CLICKED' });

    // #761 -- single invoke: hand entire metadata + settings to Python
    // subprocess via stdin. The existing export-progress event listener
    // continues to update per-match state as events arrive (match_index
    // keyed payload works unchanged with the new parallel export arch).
    try {
      const summary = await invoke<ExportSummary>('start_export', {
        req: {
          metadataJson: metadata,
          outputDir: outDir,
          codec,
          namePattern,
          excludedIndexes: Array.from(excludedIndexes),
        },
      });
      if (summary.cancelled) {
        dispatch({ type: 'CANCEL_CONFIRMED' });
      } else if (summary.success === 0 && summary.failure > 0) {
        // Zero matches finished -- surface the error phase. If at least one
        // match succeeded we declare the run "completed" and keep per-match
        // errors inline for the user to review.
        dispatch({ type: 'EXPORT_ERROR' });
      } else {
        dispatch({ type: 'PROGRESS_COMPLETE' });
      }
    } catch {
      // Unexpected (Python subprocess spawn failure / metadata parse failure / etc.)
      dispatch({ type: 'EXPORT_ERROR' });
    }
  }

  function handleCancelClicked() {
    dispatch({ type: 'CANCEL_CLICKED' });
    // #523: kill any tracked ffmpeg child so the current export can't run
    // to completion after the user asked to stop.
    void invoke('kill_tracked_processes').catch(() => undefined);
  }

  // #466 review #5: 旧実装は shell.open 後に navigate('complete') を必ず
  // 呼んでおり、Explorer が開く前に画面遷移してしまう (実態として開いて
  // いないように見える) 不具合があった。新実装は shell.open のみで
  // 画面遷移は行わない。`完了` ステータスは画面に残す。
  //
  // #545 review #6 (2026-04-25): shell.open は default scope が URL
  // (`mailto:` / `tel:` / `https?://`) しか許可せず、ローカル path で
  // `Scoped command argument failed regex validation` を返していた。
  // Rust 側に `open_folder_in_explorer` 独自 command を追加して explorer.exe
  // を直接 spawn する形に変更。
  // #678 Lane II-b §2.1 — catch path で `e instanceof Error ? e.message :
  // String(e)` を使うと AppError struct (`{code, message, hint}`) が
  // `[object Object]` に化ける。`toErrorState(e)` の戻り値 `.message` / `.hint`
  // で統一処理し、hint がある場合は 2 行目として並べる。
  const [openFolderError, setOpenFolderError] = useState<string | null>(null);
  const [openFolderErrorHint, setOpenFolderErrorHint] = useState<string | null>(
    null,
  );

  async function handleOpenFolder() {
    setOpenFolderError(null);
    setOpenFolderErrorHint(null);
    try {
      await invoke('open_folder_in_explorer', { path: outDir });
    } catch (e) {
      const errorState = toErrorState(e);
      setOpenFolderError(errorState.message);
      setOpenFolderErrorHint(errorState.hint);
    }
  }

  if (!metadata) {
    return (
      <div className={styles.screen} data-testid="export-screen">
        <div className={styles.emptyNote}>No metadata loaded.</div>
      </div>
    );
  }

  const running = phase === 'running';
  const completed = phase === 'completed';
  const error = phase === 'error';
  const cancelling = phase === 'cancelling';

  // #466 review #1: counted = 永続 skip 除外 + ad-hoc exclude 除外
  // #805 Phase 2: post_match trailing も常に対象外 (機能除外は export.py 側
  // で Phase 1 済。UI では non-selectable として数にも入れない)。
  const countedMatches = metadata.matches.filter(
    (m) =>
      m.type_override !== 'skip' &&
      !m.post_match &&
      !excludedIndexes.has(m.index),
  );
  const doneCount = countedMatches.filter(
    (m) => matchStates[m.index]?.status === 'done',
  ).length;
  const errorCount = countedMatches.filter(
    (m) => matchStates[m.index]?.status === 'error',
  ).length;
  // #545 review #7 / 5 回目テスト #4 (2026-04-25):
  // 旧実装は `doneCount / total * 100` で「完了ファイル数のみ」ベースだった
  // ため、1 ファイル目 encode 中は overall progress が 0% 固定で動かず、
  // 「左下の進捗バーが機能していない」というユーザー体験になっていた。
  // ffmpeg は `out_time_ms` を 1 秒間隔で emit するので Rust 側から
  // export-progress event の `percent` (per-file %) が届く。これを overall
  // に合算して滑らかに動かす。
  const totalPercentSum = countedMatches.reduce((acc, m) => {
    const s = matchStates[m.index];
    if (!s) return acc;
    if (s.status === 'done') return acc + 100;
    if (s.status === 'running') return acc + s.percent;
    // pending / skipped / error は 0 として扱う
    return acc;
  }, 0);
  const overallPercent = countedMatches.length === 0
    ? 0
    : Math.round(totalPercentSum / countedMatches.length);

  // #545 review #7 / 5 回目テスト #4: 経過 / 残り時間 (秒)。
  // - 経過: `nowMs - exportStartMs` (running 中は 1s tick で更新)
  // - 残り: `(elapsed / progress) * remaining` の線形推定。progress は
  //   per-file 進捗込みの fractional unit (0..countedMatches.length)。
  //   進捗 0 のとき null (= 表示は `—`)、完了 / 中断時も null。
  const elapsedSec =
    exportStartMs === null ? null : Math.max(0, (nowMs - exportStartMs) / 1000);
  const totalProgressUnits = totalPercentSum / 100;
  const remainingUnits = Math.max(0, countedMatches.length - totalProgressUnits);
  const remainingSec =
    !running || elapsedSec === null || totalProgressUnits === 0
      ? null
      : (elapsedSec / totalProgressUnits) * remainingUnits;

  return (
    <div className={styles.screen} data-testid="export-screen" data-phase={phase}>
      <SampleModeBanner />
      <div className={styles.header}>
        {/* #587 §2.5.1: explain why [◀ プレビュー] is disabled mid-export. */}
        <DisabledTooltip
          disabled={running || cancelling}
          reason="書き出し中はプレビューに戻れません。先に [中断] してください"
        >
          {(p) => (
            <button
              type="button"
              className={styles.backButton}
              disabled={running || cancelling}
              onClick={() => navigate('preview')}
              {...p}
            >
              ◀ プレビュー
            </button>
          )}
        </DisabledTooltip>
        <div>
          {videoSource && (() => {
            const { fileName, parentDir } = splitPath(videoSource);
            return (
              <div
                className={pathStyles.pathDisplay}
                title={videoSource}
                data-testid="export-path"
              >
                <div className={styles.headerFileName}>{fileName || '(video)'}</div>
                {parentDir && (
                  <div className={pathStyles.pathSecondary}>{parentDir}</div>
                )}
              </div>
            );
          })()}
          <div className={styles.caption}>エクスポート</div>
          <div className={styles.title}>
            {countedMatches.length} 試合を書き出す
          </div>
        </div>
      </div>

      <div className={styles.grid}>
        <div className={styles.panel}>
          <div className={styles.panelCaption}>設定</div>

          <div>
            <div className={styles.fieldLabel}>出力先</div>
            <div className={styles.outDirRow}>
              <DisabledTooltip
                disabled={isSample}
                reason={sampleReason}
                inlineHint={true}
              >
                {(p) => (
                  <input
                    className={styles.outDirInput}
                    value={outDir}
                    onChange={(e) => setOutDir(e.target.value)}
                    aria-label="output directory"
                    disabled={isSample || running || cancelling}
                    {...p}
                  />
                )}
              </DisabledTooltip>
              {/* #587 §2.5.4: explain why [参照…] is disabled while running. */}
              <DisabledTooltip
                disabled={running || cancelling}
                reason="書き出し中は出力先を変更できません"
              >
                {(p) => (
                  <button
                    type="button"
                    className={styles.pickButton}
                    onClick={handlePickDir}
                    disabled={running || cancelling}
                    {...p}
                  >
                    参照…
                  </button>
                )}
              </DisabledTooltip>
            </div>
          </div>

          <div>
            <div className={styles.fieldLabel}>命名規則</div>
            <DisabledTooltip
              disabled={isSample}
              reason={sampleReason}
              inlineHint={true}
            >
              {(p) => (
                <input
                  className={styles.nameInput}
                  value={namePattern}
                  onChange={(e) => setNamePattern(e.target.value)}
                  aria-label="name pattern"
                  disabled={isSample || running || cancelling}
                  {...p}
                />
              )}
            </DisabledTooltip>
            <div className={styles.nameHint}>
              変数: {'{idx}'} {'{idx:03}'} {'{start}'} {'{type}'} {'{date}'}
            </div>
          </div>

          <div>
            <div className={styles.fieldLabel}>コーデック</div>
            <div className={styles.codecRow}>
              {codecs.map((c) => (
                <DisabledTooltip
                  key={c.v}
                  disabled={isSample}
                  reason={sampleReason}
                  inlineHint={true}
                >
                  {(p) => (
                    <button
                      type="button"
                      aria-label={`コーデック: ${c.l}`}
                      aria-pressed={codec === c.v}
                      onClick={() => setCodec(c.v)}
                      disabled={isSample || running || cancelling}
                      className={`${styles.codecButton}${codec === c.v ? ` ${styles.codecButtonActive}` : ''}`}
                      {...p}
                    >
                      <div className={styles.codecLabel}>{c.l}</div>
                      <div className={styles.codecSub}>{c.sub}</div>
                    </button>
                  )}
                </DisabledTooltip>
              ))}
            </div>
          </div>

          <div className={styles.bottomActions}>
            {error && (
              <div className={styles.errorMessage} role="alert">
                すべての試合の書き出しが失敗しました
              </div>
            )}
            {(running || completed || cancelling) && (
              <div className={styles.progressBox}>
                <div className={styles.progressHeader}>
                  <span className={styles.progressLabel}>
                    {running
                      ? '分割・書き出し中'
                      : cancelling
                        ? '中断中…'
                        : '完了'}
                  </span>
                  <span>
                    {doneCount} / {countedMatches.length} files
                    {errorCount > 0 && (
                      <span
                        style={{ marginLeft: 8, color: 'var(--ae-danger)' }}
                      >
                        ({errorCount} 失敗)
                      </span>
                    )}
                    <span style={{ marginLeft: 12 }}>{overallPercent}%</span>
                  </span>
                </div>
                <div className={styles.progressBar}>
                  <div
                    className={`${styles.progressFill}${completed ? ` ${styles.progressFillDone}` : ''}`}
                    style={{ width: `${overallPercent}%` }}
                  />
                </div>
                {/* #545 review #7: 経過 / 残り時間 (design mock 準拠)。
                    完了時は残りは `—` で固定、cancelling は経過のみ表示。 */}
                {elapsedSec !== null && (
                  <div className={styles.progressTime}>
                    <span>経過 {fmtTime(elapsedSec)}</span>
                    <span>
                      残り{' '}
                      {remainingSec !== null ? fmtTime(remainingSec) : '—'}
                    </span>
                  </div>
                )}
              </div>
            )}

            {!completed && !error && (() => {
              // #587 §2.5.9: surface why [⬦ 書き出し開始] is disabled.
              // Multi-condition reason picker. Sample mode takes priority
              // (#633 / Task 1.7); missing video source is next.
              const startDisabled = isSample || running || cancelling || !videoSource;
              const startReason = isSample
                ? sampleReason
                : !videoSource
                  ? '動画ファイルが選択されていません。drop 画面に戻って選択してください'
                  : running
                    ? '書き出し中です'
                    : cancelling
                      ? '中断処理中です'
                      : '';
              return (
                <DisabledTooltip
                  disabled={startDisabled}
                  reason={startReason}
                  inlineHint
                >
                  {(p) => (
                    <button
                      type="button"
                      className={styles.primaryButton}
                      onClick={() => {
                        void handleStartExport();
                      }}
                      disabled={startDisabled}
                      aria-label="書き出し開始"
                      {...p}
                    >
                      {running
                        ? '書き出し中…'
                        : cancelling
                          ? '中断中…'
                          : '⬦ 書き出し開始'}
                    </button>
                  )}
                </DisabledTooltip>
              );
            })()}

            {running && (
              <button
                type="button"
                className={styles.cancelButton}
                onClick={handleCancelClicked}
              >
                中断
              </button>
            )}

            {completed && (
              <button
                type="button"
                className={styles.primaryButton}
                onClick={() => {
                  void handleOpenFolder();
                }}
              >
                ✓ 完了 — フォルダを開く
              </button>
            )}
            {/*
             * #678 Lane II-b §2.1: AppError struct から取り出した
             * `message` を 1 行目、`hint` を 2 行目として表示する。
             * 各テキストを個別 span に分けることで `getByText` の exact
             * match が message / hint 単独で機能する (旧実装の
             * 「フォルダを開けませんでした: <msg>」連結だと exact match
             * が成立せず TDD test も書けなかった)。
             */}
            {completed && openFolderError && (
              <div className={styles.openFolderError} role="alert">
                <span className={styles.openFolderErrorPrefix}>
                  フォルダを開けませんでした:
                </span>
                <span>{openFolderError}</span>
                {openFolderErrorHint && (
                  <span
                    className={styles.openFolderErrorHint}
                    data-testid="open-folder-error-hint"
                  >
                    <InlineErrorHint hint={openFolderErrorHint} />
                  </span>
                )}
              </div>
            )}
            {completed && (
              <button
                type="button"
                className={styles.cancelButton}
                title={
                  '同じ metadata を別設定 (出力先 / 命名 / コーデック / 試合選択) で再書き出しします。' +
                  '既に出力先に同名ファイルがある場合は ffmpeg `-y` で上書きされます。'
                }
                onClick={() => {
                  setMatchStates({});
                  setOpenFolderError(null);
                  setOpenFolderErrorHint(null);
                  dispatch({ type: 'RESTART' });
                }}
              >
                設定変更して再書き出し
              </button>
            )}
            {completed && (
              <button
                type="button"
                className={styles.cancelButton}
                onClick={() => navigate('minimap')}
                disabled={metadata.matches.length === 0}
                aria-label="ミニマップ切抜きへ"
              >
                ⬦ ミニマップ切抜きへ
              </button>
            )}

            {error && (
              <button
                type="button"
                className={styles.primaryButton}
                title={
                  '出力先 / 命名 / コーデック / 試合選択 を変更してから ' +
                  '再度書き出しを試行します。'
                }
                onClick={() => {
                  setMatchStates({});
                  setOpenFolderError(null);
                  setOpenFolderErrorHint(null);
                  dispatch({ type: 'DISMISS_ERROR' });
                }}
              >
                設定変更して再試行
              </button>
            )}
          </div>
        </div>

        <div className={styles.listPanel}>
          <div className={styles.listHeaderRow}>
            <div className={styles.listCaption}>
              書き出し一覧 ⸱ {countedMatches.length} ファイル
            </div>
            {/* #545 review #3 (2026-04-25): 全選択 / 全解除トグル。
                preview で永続 skip 設定済 (type_override === 'skip') の試合は
                bulk 対象から除外。export 中は disable。 */}
            <div className={styles.listBulkActions}>
              {/*
               * #587 §2.5.14: surface why bulk toggles are disabled.
               *
               * - running / cancelling: "書き出し中は変更できません"
               * - eligible (= matches neither persist-skipped nor
               *   post_match, #805 Phase 2) length === 0: the bulk toggle
               *   has nothing to act on.
               *
               * `countedMatches` reflects ad-hoc exclusion too (used for
               * "N 試合を書き出す" copy), so we instead derive eligibility
               * from the persist-skip + post_match filter, which doesn't
               * change as the user toggles checkboxes.
               */}
              {(() => {
                const eligibleCount = metadata.matches.filter(
                  (mm) => mm.type_override !== 'skip' && !mm.post_match,
                ).length;
                const bulkDisabled =
                  isSample || running || cancelling || eligibleCount === 0;
                const baseReason = isSample
                  ? sampleReason
                  : running || cancelling
                    ? '書き出し中は変更できません'
                    : '';
                const selectAllReason =
                  !isSample && eligibleCount === 0
                    ? '対象が 0 件のため全選択できません'
                    : baseReason;
                const deselectAllReason =
                  !isSample && eligibleCount === 0
                    ? '対象が 0 件のため全解除できません'
                    : baseReason;
                return (
                  <>
                    <DisabledTooltip
                      disabled={bulkDisabled}
                      reason={selectAllReason}
                    >
                      {(p) => (
                        <button
                          type="button"
                          className={styles.listBulkButton}
                          disabled={bulkDisabled}
                          onClick={() => toggleSelectAll(true)}
                          aria-label="select all matches"
                          {...p}
                        >
                          全選択
                        </button>
                      )}
                    </DisabledTooltip>
                    <DisabledTooltip
                      disabled={bulkDisabled}
                      reason={deselectAllReason}
                    >
                      {(p) => (
                        <button
                          type="button"
                          className={styles.listBulkButton}
                          disabled={bulkDisabled}
                          onClick={() => toggleSelectAll(false)}
                          aria-label="deselect all matches"
                          {...p}
                        >
                          全解除
                        </button>
                      )}
                    </DisabledTooltip>
                  </>
                );
              })()}
            </div>
          </div>
          <ul className={styles.listBody}>
            {metadata.matches.map((m) => {
              const s = matchStates[m.index] ?? {
                status: 'pending' as MatchStatus,
                percent: 0,
              };
              // 2026-04-25 修正: preview で調整した境界 (m.edited) を一覧
              // duration にも反映する。m.duration_display は CLI 初期値で
              // 固定なので、edited がある場合は再計算した duration を表示。
              const effectiveStart = m.edited?.start_time ?? m.start_time;
              const effectiveEnd = m.edited?.end_time ?? m.end_time;
              const durationDisplay = m.edited
                ? fmtMatchDuration(effectiveEnd - effectiveStart)
                : m.duration_display;
              const name = formatName(m.index, m.type, effectiveStart);
              // #805 Phase 2: post_match trailing は選択不可 (export.py 側の
              // 機能除外は Phase 1 済。行は skipped 扱いで表示のみ)。
              const isPostMatch = m.post_match === true;
              // post_match は常に '—' (export.py が event を emit しない前提に
              // 依存せず、迷子 event が来ても表示を上書きさせない、review P3-1)。
              const mark = isPostMatch
                ? '—'
                : s.status === 'done'
                  ? '✓'
                  : s.status === 'running'
                    ? '●'
                    : s.status === 'error'
                      ? '!'
                      : s.status === 'skipped'
                        ? '—'
                        : '○';
              const markClass =
                s.status === 'done'
                  ? styles.listMarkDone
                  : s.status === 'error'
                    ? styles.listMarkError
                    : '';
              // #466 review #1: 永続 skip は変更不可、ad-hoc exclude は
              // checkbox で個別 toggle 可能。export 中は disabled。
              const isPersistSkip = m.type_override === 'skip';
              const isAdHocExcluded = excludedIndexes.has(m.index);
              const isIncluded =
                !isPersistSkip && !isPostMatch && !isAdHocExcluded;
              return (
                <li
                  key={m.index}
                  className={`${styles.listItem}${isPostMatch ? ` ${styles.listItemPostMatch}` : ''}`}
                  data-testid={`export-row-${m.index}`}
                  {...(isPostMatch ? { 'data-post-match': 'true' } : {})}
                >
                  {/* #587: skip-checkbox disabled reason (§1.2 + #587
                      scope-extension #11). When the match isn't a persist
                      skip the existing help title is preserved.
                      #633 / Task 1.7: sample mode also disables checkbox. */}
                  <DisabledTooltip
                    disabled={isSample || isPersistSkip || isPostMatch}
                    reason={
                      isSample
                        ? sampleReason
                        : isPostMatch
                          ? '試合後の映像のため書き出し対象外です'
                          : 'preview で skip に設定されています'
                    }
                  >
                    {(p) => (
                      <input
                        type="checkbox"
                        className={styles.listCheckbox}
                        checked={isIncluded}
                        disabled={
                          isSample ||
                          isPersistSkip ||
                          isPostMatch ||
                          running ||
                          cancelling
                        }
                        onChange={() => toggleMatchExclusion(m.index)}
                        aria-label={`include match ${m.index}`}
                        title={p.title ?? '書き出し対象から除外/復帰'}
                      />
                    )}
                  </DisabledTooltip>
                  <span className={`${styles.listMark} ${markClass}`}>
                    {mark}
                  </span>
                  <span className={styles.listName}>{name}</span>
                  {isPostMatch && (
                    <span className={styles.postMatchBadge}>試合後</span>
                  )}
                  <span className={styles.listDur}>{durationDisplay}</span>
                  {(running ||
                    completed ||
                    s.status === 'done' ||
                    s.status === 'error') && (
                    <div className={styles.listProgress}>
                      <div
                        className={`${styles.listProgressFill}${
                          s.status === 'done' ? ` ${styles.listProgressFillDone}` : ''
                        }`}
                        style={{ width: `${s.percent}%` }}
                      />
                    </div>
                  )}
                  {s.status === 'error' && s.error && (
                    <span className={styles.listError} role="alert">
                      {s.error.slice(0, 120)}
                      {s.errorHint && (
                        <span className={styles.listErrorHint}>
                          <InlineErrorHint hint={s.errorHint} />
                        </span>
                      )}
                    </span>
                  )}
                  {/* #932: 旧実装は `--ae-accent` を参照していたが tokens.css に
                      該当 token がない。未定義 custom property を fallback なしで
                      参照すると宣言全体が IACVT で `unset` になり、inline style が
                      cascade で class に勝つため `.listError` の赤も失われ地の文と
                      同じ色で描画されていた (v0.2.0 から出荷。MinimapScreen が
                      mirror 時に複製)。token 名を `var(...)` 形で書かないのは
                      styles/tokens.test.ts の guard がコメントも走査対象に
                      含める (fail closed) ため。 */}
                  {s.fallbackNotice && (
                    <span
                      className={styles.listError}
                      role="status"
                      data-testid={`fallback-notice-${m.index}`}
                      style={{ color: 'var(--ae-gold-bright)' }}
                    >
                      {s.fallbackNotice}
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      </div>
    </div>
  );
}

/**
 * #680: source video の親ディレクトリを default 出力先に。
 * 旧実装 (#466 review #2) は `<parent>/output` を返していたが、Export 画面
 * 到達時点では `<parent>/output` が物理的に存在しない (Rust 側
 * `start_detect` は detect 出力先のみ create_dir_all する) ため、ユーザーが
 * 「存在しないフォルダが default にプリセットされている」と混乱した。
 * <parent> のみへ変更し、必ず存在するフォルダを default とする。
 *
 * #545 review #2 (2026-04-25): Windows の `\\?\` extended-length path prefix
 * は `stripExtendedPathPrefix` で取り除いてから親 dir を切り出す。
 * (なお Tauri 側からの flow としては `appStateStore.setSelectedVideoPath`
 * が pipeline 上の strip ポイントなので通常 prefix は来ないが、defense-in-depth
 * として deriveDefaultOutDir 内でも適用しておく。)
 */
export function deriveDefaultOutDir(videoSource: string | null): string {
  if (!videoSource) return '';
  const normalized = stripExtendedPathPrefix(videoSource);
  const idx = Math.max(
    normalized.lastIndexOf('/'),
    normalized.lastIndexOf('\\'),
  );
  if (idx <= 0) return '';
  return normalized.slice(0, idx);
}
