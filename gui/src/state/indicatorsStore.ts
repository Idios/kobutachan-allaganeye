/**
 * #1106 Phase 1 -- `allaganeye indicators` の実行状態を持つ zustand store。
 *
 * Rust 側 `start_indicators` (gui/src-tauri/src/lib.rs) を invoke し、
 * `indicators-progress` event を購読して進捗を溜める。画面 (Phase 2) は
 * この store だけを見れば良く、`listen` / `invoke` の後始末を持たない。
 *
 * 購読は ExportScreen / MinimapScreen と同じ `@tauri-apps/api/event` の
 * `listen` を使い、`start()` の中で張って完了 / 失敗で外す
 * (画面側 useEffect と違い、store は実行主体なので購読の寿命を実行に合わせる)。
 *
 * run は重ねられない: `indicators-progress` の payload に run id が無いため、
 * 走行中の `start()` を許すと前の run の event が今の run の state を上書きする。
 * `start()` / `reset()` は running 中に呼ばれると拒否する
 * (`IndicatorsRunActiveError`、code = `indicators.busy`)。
 *
 * payload は CLI の JSON Lines (= Rust が emit する payload) をそのまま写した
 * snake_case の型で受ける。zod による runtime 検証はしない — 既存の
 * `minimap-progress` / `export-progress` 購読 (ExportScreen / MinimapScreen の
 * `MinimapProgressPayload` 等) も plain interface で受けているため、同じ流儀に
 * 揃える (Rust 側で deserialize 済みの値が来る前提)。
 */
import { invoke } from '@tauri-apps/api/core';
import { listen, type UnlistenFn } from '@tauri-apps/api/event';
import { create } from 'zustand';

import type { HighlightEvent } from '../types/metadata.generated';
import { toErrorState, type ErrorState } from '../lib/appError';

/**
 * `indicator_layout` (metadata.json に永続化されるのと同じ形)。
 * `anchor_x` / `anchor_y` はフレーム幅・高さで正規化したアンカー位置、
 * `scale` は 1080p 参照レイアウトに対する倍率、`source` は自動解決 (`anchor`)
 * か `--region` 由来 (`user`) か。
 */
export interface IndicatorsLayout {
  anchor_x: number;
  anchor_y: number;
  scale: number;
  support: number;
  confidence: number;
  source: 'anchor' | 'user';
}

/**
 * KO / ASSIST の 1 区間 (#127)。形の正は schema の `$defs/HighlightEvent`
 * (生成型をそのまま使う)。`timestamp` / `end` は元録画先頭からの絶対秒、
 * `match_index` は試合外なら null。
 */
export type IndicatorsEvent = HighlightEvent;

/** `start_indicators` の戻り値 (CLI `--json` 最終行 `complete` の本体)。 */
export interface IndicatorsResult {
  metadata: string;
  layout: IndicatorsLayout;
  recalibrated: boolean;
  events: IndicatorsEvent[];
  wrote_metadata: boolean;
}

/**
 * `indicators-progress` event の payload。
 *
 * - `{ phase: 'calibrating' }` — 自動キャリブレーション開始
 * - `{ phase: 'scanning', layout }` — 走査開始 (解決済み layout の通知)
 * - `{ phase: 'scanning', processed_s, total_s }` — 30 秒ごとの進捗
 * - `{ phase: 'scanning', processed_s, total_s, eta_s }` — 同上 + 推定残り秒 (#1140)
 */
export interface IndicatorsProgressPayload {
  phase: 'calibrating' | 'scanning';
  layout?: IndicatorsLayout;
  processed_s?: number;
  total_s?: number;
  /** 推定残り秒 (CLI が実測から計算する SSoT。GUI は表示のみ)。 */
  eta_s?: number;
}

/**
 * `start_indicators` に渡す request (Rust 側 `StartIndicatorsRequest` と対)。
 * `null` / `undefined` はいずれも「CLI 既定に委ねる」を意味する。
 */
export interface IndicatorsRequest {
  metadataPath: string;
  /** CLI `-o` (検出イベントの JSON レポート出力先)。 */
  outputPath?: string | null;
  /** CLI `--interval` (走査間隔秒。CLI 下限は 0.05)。 */
  interval?: number | null;
  /** CLI `--recalibrate` (キャッシュされた layout を無視して再解決)。 */
  recalibrate?: boolean | null;
  /**
   * CLI `--write/--no-write`。`false` のときだけ `--no-write` を渡すので、
   * `true` / `null` は「CLI 既定 (書き戻す)」と同じ意味になる。
   */
  write?: boolean | null;
  /** CLI `--expected-mtime` (書き戻し CAS ガード、ms)。 */
  expectedMtime?: number | null;
  /** CLI `--region X,Y,W,H` (ピクセル)。`--recalibrate` とは排他 (CLI が exit 5)。 */
  region?: [number, number, number, number] | null;
}

export type IndicatorsStatus = 'idle' | 'running' | 'complete' | 'error';

/**
 * `start()` / `reset()` が走行中の再入を拒否したときに throw する型付き error。
 *
 * `isAppError` / `appErrorCodeIs` (gui/src/lib/appError.ts) がそのまま使えるよう
 * `code` を持たせる。run の重なりを許すと、run id を持たない progress payload の
 * せいで前の run の event が今の run の state を壊すため、ここで止める。
 */
export class IndicatorsRunActiveError extends Error {
  readonly code = 'indicators.busy';

  constructor(action: 'start' | 'reset') {
    super(
      `indicators: cannot ${action} while a run is active; call cancel() and wait for it to settle first`,
    );
    this.name = 'IndicatorsRunActiveError';
  }
}

/**
 * spawn 前に `cancel()` された run を畳むときに throw する error。
 *
 * Rust 側が中断時に返す `subprocess.cancelled` と同じ code にして、呼び出し側が
 * `appErrorCodeIs(e, 'subprocess.cancelled')` の 1 分岐で両方を扱えるようにする。
 */
export class IndicatorsCancelledError extends Error {
  readonly code = 'subprocess.cancelled';

  constructor() {
    super('indicators: cancelled before the CLI was spawned');
    this.name = 'IndicatorsCancelledError';
  }
}

export interface IndicatorsState {
  status: IndicatorsStatus;
  /**
   * 直近の run の対象 metadata.json path (#1106 Phase 2 review R1)。
   *
   * `metadataStore.filePath` と比較して、**別のファイル向けの結果を表示しない**
   * ためのスコープキー。run を起こした側が path を知っているので、画面ではなく
   * store が保持する (画面を離れても run は続くため、画面ローカルでは追えない)。
   * `status === 'running'` の間は走行中の対象、`complete` / `error` では終了した
   * run の対象が残る。`reset()` で `null` に戻る。
   */
  metadataPath: string | null;
  /** CLI が通知した現在 phase (実行していないときは null)。 */
  phase: IndicatorsProgressPayload['phase'] | null;
  processedSeconds: number | null;
  totalSeconds: number | null;
  /** 推定残り秒 (#1140)。CLI が算出した値をそのまま保持する。 */
  etaSeconds: number | null;
  /** 走査開始時に CLI が解決した layout (未解決なら null)。 */
  layout: IndicatorsLayout | null;
  events: IndicatorsEvent[];
  /** 失敗時の正規化済み error (`toErrorState`)。 */
  error: ErrorState | null;

  /**
   * 実行を開始し、CLI が返した `complete` payload を解決する。
   *
   * `status === 'running'` のときに呼ぶと **何も spawn せずに**
   * `IndicatorsRunActiveError` を throw する (run の重なりは progress payload に
   * run id が無いため state を壊す)。`listen` の登録に失敗した場合と、登録待ちの
   * 間に `cancel()` された場合も reject する (`state.error` にも入る)。
   */
  start: (request: IndicatorsRequest) => Promise<IndicatorsResult>;
  /**
   * 走行中の CLI を止める (best effort)。Rust 側 `kill_tracked_processes` は
   * 追跡中の全プロセスを kill するので、indicators 以外が動いていない前提。
   *
   * spawn 前に呼ばれた場合はキャンセル要求として記録し、`start()` が購読の
   * 登録完了後にそれを見て CLI を起動しない (metadata / レポートの書き戻しを
   * 防ぐ)。status は 'running' のままにし、遷移は走行中の `start()` の reject
   * (code = `subprocess.cancelled`) が受ける。
   */
  cancel: () => void;
  /**
   * 状態を初期化する。走行中は拒否する (`IndicatorsRunActiveError`) — ここで
   * 黙って初期化すると、走り続けている CLI が書き戻しうるまま購読だけ失う
   * (orphan 化する) ため。止めたいときは `cancel()` → `start()` の settle を
   * 待ってから呼ぶ。
   */
  reset: () => void;
}

function initialState() {
  return {
    status: 'idle' as IndicatorsStatus,
    metadataPath: null,
    phase: null,
    processedSeconds: null,
    totalSeconds: null,
    etaSeconds: null,
    layout: null,
    events: [] as IndicatorsEvent[],
    error: null,
  };
}

/**
 * 走行世代。`start()` と `reset()` で進める。解決が遅れた `listen` や、
 * 購読解除後に遅れて届いた event を `runId !== runSeq` で捨てるためのもの。
 */
let runSeq = 0;

/** 現在の run の購読解除関数。 */
let detachEvents: UnlistenFn | null = null;

/**
 * `cancel()` が要求された走行世代。spawn 前にキャンセルされた run を起動しない
 * ための記録 (CLI は metadata / レポートを書き戻せるので、購読の登録待ちの間に
 * cancel された run を起動してはいけない)。
 */
let cancelRequestedFor: number | null = null;

function unsubscribe(): void {
  if (detachEvents !== null) {
    detachEvents();
    detachEvents = null;
  }
}

export const useIndicatorsStore = create<IndicatorsState>((set, get) => ({
  ...initialState(),

  async start(request: IndicatorsRequest) {
    // run の重なりは禁止 (progress payload に run id が無いため、前の run の
    // event が今の run の state を上書きしてしまう)。
    if (get().status === 'running') {
      throw new IndicatorsRunActiveError('start');
    }
    const runId = ++runSeq;
    cancelRequestedFor = null;
    set({
      ...initialState(),
      status: 'running',
      metadataPath: request.metadataPath,
    });

    // 購読を invoke より先に張る: spawn 直後の progress を取りこぼさない。
    let unlisten: UnlistenFn;
    try {
      unlisten = await listen<IndicatorsProgressPayload>(
        'indicators-progress',
        (event) => {
          // 前の run の遅延 event は捨てる (run は重ならないので通常は起きない)。
          if (runId !== runSeq) return;
          const payload = event.payload;
          set((state) => ({
            phase: payload.phase,
            layout: payload.layout ?? state.layout,
            processedSeconds: payload.processed_s ?? state.processedSeconds,
            totalSeconds: payload.total_s ?? state.totalSeconds,
            etaSeconds: payload.eta_s ?? state.etaSeconds,
          }));
        },
      );
    } catch (e) {
      // 購読できないまま running で固まると UI が進退不能になるので、
      // error に落として理由を見せる (CLI は起動しない)。
      set({ status: 'error', error: toErrorState(e) });
      throw e;
    }

    if (runId !== runSeq) {
      // 現状は到達しない防御 (重なりと reset は上のガードで拒否する)。
      unlisten();
      throw new Error('indicators: run superseded before the progress listener resolved');
    }
    detachEvents = unlisten;

    if (cancelRequestedFor === runId) {
      // 購読の登録待ちの間に cancel された: CLI を起動せずに畳む。
      cancelRequestedFor = null;
      unsubscribe();
      const cancelled = new IndicatorsCancelledError();
      set({ status: 'error', error: toErrorState(cancelled) });
      throw cancelled;
    }

    try {
      const result = await invoke<IndicatorsResult>('start_indicators', {
        req: request,
      });
      if (runId === runSeq) {
        set({
          status: 'complete',
          phase: null,
          layout: result.layout,
          events: result.events,
          error: null,
        });
      }
      return result;
    } catch (e) {
      if (runId === runSeq) {
        set({ status: 'error', error: toErrorState(e) });
      }
      throw e;
    } finally {
      if (runId === runSeq) unsubscribe();
    }
  },

  cancel() {
    if (get().status !== 'running') return;
    // spawn 前でも要求を残す: start() が購読の登録後に見て起動を中止する。
    cancelRequestedFor = runSeq;
    void invoke('kill_tracked_processes').catch(() => undefined);
  },

  reset() {
    if (get().status === 'running') {
      throw new IndicatorsRunActiveError('reset');
    }
    runSeq += 1;
    cancelRequestedFor = null;
    unsubscribe();
    set({ ...initialState() });
  },
}));
