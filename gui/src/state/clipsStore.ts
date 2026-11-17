/**
 * #1131 Phase B1 -- `allaganeye clips` の実行状態を持つ zustand store。
 *
 * Rust 側 `start_clips` (gui/src-tauri/src/lib.rs) を invoke し、
 * `clips-progress` event を購読して進捗を溜める。画面 (Phase B2) は
 * この store だけを見れば良く、`listen` / `invoke` の後始末を持たない。
 *
 * 購読の寿命・run の重なり禁止・`cancel` の契約は `indicatorsStore` と
 * 同じ設計に揃える (progress payload に run id が無いため、走行中の
 * `start()` を許すと前の run の event が今の run の state を上書きする)。
 *
 * wire 形状は `export` と同一 (`progress` / `result` / `fallback` / `error` を
 * Rust がそのまま emit する) ので、payload は snake_case のまま受ける
 * (`minimap-progress` / `export-progress` と同じ流儀)。
 */
import { invoke } from '@tauri-apps/api/core';
import { listen, type UnlistenFn } from '@tauri-apps/api/event';
import { create } from 'zustand';

import { toErrorState, type ErrorState } from '../lib/appError';

/**
 * `clips-progress` event の payload (Rust `ExportProgress` と同じ形)。
 *
 * - `stage === 'done'` — そのクリップの書き出しが成功した (percent 100)
 * - `stage === 'error'` — そのクリップが失敗した (`message` に理由)
 * - `stage === 'fallback'` — GPU エンコーダ初期化失敗で libx264 に切り替えた
 *   (`fallback_from` に `h264_nvenc -> libx264` 等)
 * - それ以外 — エンコード中の進捗 (percent)
 */
export interface ClipsProgressPayload {
  match_index: number;
  percent: number;
  stage: string;
  message?: string;
  fallback_from?: string;
}

/** `start_clips` の戻り値 (CLI `--json` 最終行 `summary` + 書き出したパス)。 */
export interface ClipsResult {
  success: number;
  failure: number;
  skipped: number;
  cancelled: boolean;
  /** 書き出したクリップの絶対パス (GUI が「どこに出たか」を出すため)。 */
  output_paths: string[];
}

/**
 * `start_clips` に渡す request (Rust 側 `StartClipsRequest` と対)。
 * `null` / `undefined` はいずれも「CLI 既定に委ねる」を意味する。
 */
export interface ClipsRequest {
  metadataPath: string;
  /** CLI `--output-dir` (既定は `<metadata.json の親>/clips`)。 */
  outputDir?: string | null;
  /** CLI `--pre` (イベント開始の何秒前から切り抜くか)。 */
  pre?: number | null;
  /** CLI `--post` (イベント終端の何秒後まで切り抜くか)。 */
  post?: number | null;
  /** CLI `--gap` (この秒数以内に始まるイベントを同じクリップへ束ねる)。 */
  gap?: number | null;
  /** CLI `--codec`。既定は `copy` (無劣化・キーフレーム丸め)。 */
  codec?: 'copy' | 'h264' | null;
  /** CLI `--name-pattern` (トークン: `{idx}` / `{idx:03}` / `{type}` / `{start}` / `{date}`)。 */
  namePattern?: string | null;
  /**
   * CLI `--event-index` に写す **1 始まりの `events[]` 位置**。
   * 空 / 未指定は全クリップ。
   */
  eventIndexes?: number[];
  /**
   * CLI `--overwrite`。既定 false なので、前回と同じ出力があると CLI が
   * exit 5 で拒否する (無確認の truncate を防ぐ)。GUI はユーザーの明示的な
   * 同意があるときだけ true にする。
   */
  overwrite?: boolean;
}

export type ClipsStatus = 'idle' | 'running' | 'complete' | 'error';

/**
 * `start()` / `reset()` が走行中の再入を拒否したときに throw する型付き error。
 *
 * `isAppError` / `appErrorCodeIs` (gui/src/lib/appError.ts) がそのまま使えるよう
 * `code` を持たせる (`indicators.busy` と同じ設計)。
 */
export class ClipsRunActiveError extends Error {
  readonly code = 'clips.busy';

  constructor(action: 'start' | 'reset') {
    super(
      `clips: cannot ${action} while a run is active; call cancel() and wait for it to settle first`,
    );
    this.name = 'ClipsRunActiveError';
  }
}

/**
 * spawn 前に `cancel()` された run を畳むときに throw する error。
 *
 * Rust 側が中断時に返す `subprocess.cancelled` と同じ code にして、呼び出し側が
 * `appErrorCodeIs(e, 'subprocess.cancelled')` の 1 分岐で両方を扱えるようにする。
 */
export class ClipsCancelledError extends Error {
  readonly code = 'subprocess.cancelled';

  constructor() {
    super('clips: cancelled before the CLI was spawned');
    this.name = 'ClipsCancelledError';
  }
}

export interface ClipsState {
  status: ClipsStatus;
  /**
   * 直近の run の対象 metadata.json path。
   *
   * `metadataStore.filePath` と比較して、**別のファイル向けの結果を表示しない**
   * ためのスコープキー (`indicatorsStore.metadataPath` と同じ役割)。
   * `metadataPath: null` の run (sample mode で path が無い場合) は
   * 「特定ファイルに紐づかない」を意味する。
   */
  metadataPath: string | null;
  /** 直近の `clips-progress` payload (実行していないときは null)。 */
  progress: ClipsProgressPayload | null;
  /** 完了した run の集計 (失敗 / 未実行なら null)。 */
  result: ClipsResult | null;
  /** 失敗時の正規化済み error (`toErrorState`)。 */
  error: ErrorState | null;

  /**
   * 実行を開始し、CLI が返した summary を解決する。
   *
   * `status === 'running'` のときに呼ぶと **何も spawn せずに**
   * `ClipsRunActiveError` を throw する。`listen` の登録に失敗した場合と、
   * 登録待ちの間に `cancel()` された場合も reject する (`state.error` にも入る)。
   */
  start: (request: ClipsRequest) => Promise<ClipsResult>;
  /**
   * 走行中の CLI を止める (best effort)。Rust 側 `kill_tracked_processes` は
   * 追跡中の全プロセスを kill するので、clips 以外が動いていない前提。
   *
   * spawn 前に呼ばれた場合はキャンセル要求として記録し、`start()` が購読の
   * 登録完了後にそれを見て CLI を起動しない (途中まで書けたクリップを増やさない)。
   */
  cancel: () => void;
  /**
   * 状態を初期化する。走行中は拒否する (`ClipsRunActiveError`) — ここで
   * 黙って初期化すると、走り続けている CLI が書き出しうるまま購読だけ失う。
   */
  reset: () => void;
}

function initialState() {
  return {
    status: 'idle' as ClipsStatus,
    metadataPath: null,
    progress: null,
    result: null,
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

/** `cancel()` が要求された走行世代 (spawn 前キャンセルの記録)。 */
let cancelRequestedFor: number | null = null;

function unsubscribe(): void {
  if (detachEvents !== null) {
    detachEvents();
    detachEvents = null;
  }
}

export const useClipsStore = create<ClipsState>((set, get) => ({
  ...initialState(),

  async start(request: ClipsRequest) {
    if (get().status === 'running') {
      throw new ClipsRunActiveError('start');
    }
    const runId = ++runSeq;
    cancelRequestedFor = null;
    set({
      ...initialState(),
      status: 'running',
      metadataPath: request.metadataPath ?? null,
    });

    // 購読を invoke より先に張る: spawn 直後の progress を取りこぼさない。
    let unlisten: UnlistenFn;
    try {
      unlisten = await listen<ClipsProgressPayload>('clips-progress', (event) => {
        // 前の run の遅延 event は捨てる (run は重ならないので通常は起きない)。
        if (runId !== runSeq) return;
        set({ progress: event.payload });
      });
    } catch (e) {
      set({ status: 'error', error: toErrorState(e) });
      throw e;
    }

    if (runId !== runSeq) {
      // 現状は到達しない防御 (重なりと reset は上のガードで拒否する)。
      unlisten();
      throw new Error('clips: run superseded before the progress listener resolved');
    }
    detachEvents = unlisten;

    if (cancelRequestedFor === runId) {
      // 購読の登録待ちの間に cancel された: CLI を起動せずに畳む。
      cancelRequestedFor = null;
      unsubscribe();
      const cancelled = new ClipsCancelledError();
      set({ status: 'error', error: toErrorState(cancelled) });
      throw cancelled;
    }

    try {
      const result = await invoke<ClipsResult>('start_clips', { req: request });
      if (runId === runSeq) {
        set({ status: 'complete', result, error: null });
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
    cancelRequestedFor = runSeq;
    void invoke('kill_tracked_processes').catch(() => undefined);
  },

  reset() {
    if (get().status === 'running') {
      throw new ClipsRunActiveError('reset');
    }
    runSeq += 1;
    cancelRequestedFor = null;
    unsubscribe();
    set({ ...initialState() });
  },
}));
