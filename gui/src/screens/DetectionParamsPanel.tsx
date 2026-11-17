import { useId, useState } from 'react';

import { HelpTip } from '../components/HelpTip';
import {
  DEFAULT_DETECTION_PARAMS,
  type DetectionPath,
  useAppStateStore,
} from '../state/appStateStore';
import { isDetectionParamsModified } from '../utils/detection';
import styles from './DetectionParamsPanel.module.css';

/**
 * #1135 -- しきい値スライダの可動域。JSX の min/max と help 文言の両方が
 * ここを参照する (片方だけ変えて「文言と実際の範囲がずれる」のを防ぐ)。
 */
const BLACKOUT_SLIDER_MIN = 0;
const BLACKOUT_SLIDER_MAX = 50;

/** #1135 -- ワーカー数の入力域 (0 = 自動)。 */
const WORKERS_INPUT_MIN = 0;
const WORKERS_INPUT_MAX = 32;

/**
 * #1136 -- 検知経路の radio 3 択。store の `DetectionPath` と 1:1 表示対応。
 * ここを増やすと「選べるが flag に変換されない」値を作れてしまうので、
 * `toStartDetectParams` の分岐と store の型を同時に更新すること。
 */
const DETECTION_PATH_OPTIONS: ReadonlyArray<{
  value: DetectionPath;
  label: string;
  testId: string;
}> = [
  {
    value: 'standard',
    label: '標準',
    testId: 'detection-params-path-standard',
  },
  {
    value: 'masked',
    label: 'マスク録画',
    testId: 'detection-params-path-masked',
  },
  {
    value: 'vtuber',
    label: '配信レイアウト',
    testId: 'detection-params-path-vtuber',
  },
];

/**
 * #1135 -- 各項目の help 本文 (docs/ui-interaction-spec.md §1.7)。
 *
 * 数値は定数 / `DEFAULT_DETECTION_PARAMS` から組み立てる。doc 側に数値を
 * 複製せず、正であるコードを参照させる方針 (`docs/coding-conventions.md`)。
 */
const BLACKOUT_HELP = [
  '暗転と判定する明るさの上限です。フレームの平均輝度がこの値以下の区間を暗転とみなし、その前後を試合の切れ目として扱います。',
  '値を上げるほど暗い画面を暗転とみなしやすくなり、切れ目を取りこぼしにくくなる一方、ダウン→リスポーン時のような試合中の短い暗転を切れ目と誤認しやすくなります。',
  `スライダーは実用域の ${BLACKOUT_SLIDER_MIN}-${BLACKOUT_SLIDER_MAX} を表示しています（CLI は 0-255、既定 ${DEFAULT_DETECTION_PARAMS.blackoutThreshold}）。`,
].join(' ');

const WORKERS_HELP = [
  '同時に動かす ffmpeg デコード処理の本数です。',
  `${WORKERS_INPUT_MIN} は自動（CPU コア数に応じて CLI が決定）を意味します。`,
  '値を増やすと速くなりますが CPU とディスク I/O を占有するため、他の作業と同時に使うときや PC が重いときは下げてください。',
].join(' ');

const GPU_HELP = [
  '自動は動画のコーデックから GPU デコードが使えるかを判定して選びます（H.264 / HEVC / AV1 / VP9 は対応 GPU で GPU、それ以外は CPU）。',
  'ON は GPU を強制し、GPU を初期化できなかった場合は CPU に自動で切り替わります。OFF は CPU を固定します。',
  'GPU 検知で結果がおかしいとき、ドライバが不調なとき、GPU を他の作業に空けたいときは OFF にしてください。',
  '複数 GPU の使い分け（ベンダー指定）は GUI からは指定できません（CLI の --gpu-vendor）。',
].join(' ');

/**
 * #1136 -- 検知経路の help 本文。3 択の違いと、選び分けの判断材料を書く。
 *
 * 「標準」でも 0 暗転時にマスク向け fallback が自動発動する (#821) ことに
 * 触れておかないと、「マスク録画」を選ぶ意味が伝わらない。
 */
const DETECTION_PATH_HELP = [
  '録画の種類に合わせて検知のしかたを選びます。',
  '標準は通常の暗転検知です。暗転が 1 件も見つからなかった録画では、マスク向けの fallback が自動で発動します。',
  'マスク録画は、チャット欄を画像でマスクした録画向けです。マスクのない領域を自動検出して検知します（CLI の --masked を強制）。',
  '配信レイアウトは、ゲーム画面が画面全体でない配信録画向けです。暗転ではなくスコアバーの有無と画面の動きから試合区間を抽出します（CLI の --vtuber）。',
  'マスク録画と配信レイアウトは同時に選べません。',
].join(' ');

/**
 * #613: 詳細設定パネル — DropScreen の SelectedCard 内に collapsible で
 * 配置され、`detectionParams` (appStateStore) を直接 mutate する。
 *
 * Default は折り畳み (panelOpen=false)。展開時に 5 controls + [リセット]
 * を表示する。各 control の挙動は `docs/ui-interaction-spec.md` §2.1.10。
 *
 * #1135: 3 項目とも値の意味が label だけでは分からないため、HelpTip で
 * 説明を添える (§1.7)。
 *
 * #1136: 検知経路 (`--masked` / `--vtuber`) の radio 3 択を追加。
 * 相互排他を型で表すため `detectionPath` は 3 値 1 本 (boolean 2 本にしない)。
 */
export function DetectionParamsPanel() {
  const detectionParams = useAppStateStore((s) => s.detectionParams);
  const setDetectionParams = useAppStateStore((s) => s.setDetectionParams);
  const resetDetectionParams = useAppStateStore((s) => s.resetDetectionParams);

  const [open, setOpen] = useState(false);
  const panelBodyId = useId();
  const blackoutId = useId();
  const workersId = useId();

  const modified = isDetectionParamsModified(detectionParams);

  return (
    <div className={styles.panel} data-testid="detection-params-panel">
      <button
        type="button"
        className={styles.panelHeaderToggle}
        aria-expanded={open}
        aria-controls={panelBodyId}
        onClick={() => setOpen((v) => !v)}
        data-testid="detection-params-toggle"
      >
        <span className={styles.panelHeaderChevron} aria-hidden>
          {open ? '▼' : '▶'}
        </span>
        詳細設定
        {!open && modified && (
          <span className={styles.panelHeaderModified} aria-label="変更あり">
            (変更あり)
          </span>
        )}
      </button>

      {open && (
        <div
          id={panelBodyId}
          className={styles.panelBody}
          data-testid="detection-params-body"
        >
          <div className={styles.labelRow}>
            <label htmlFor={blackoutId} className={styles.fieldLabel}>
              検知しきい値
            </label>
            <HelpTip
              label="検知しきい値の説明"
              testId="detection-params-blackout-help"
            >
              {BLACKOUT_HELP}
            </HelpTip>
          </div>
          <div className={styles.sliderRow}>
            <input
              id={blackoutId}
              type="range"
              min={BLACKOUT_SLIDER_MIN}
              max={BLACKOUT_SLIDER_MAX}
              step={1}
              value={detectionParams.blackoutThreshold}
              onChange={(e) =>
                setDetectionParams({
                  blackoutThreshold: Number.parseFloat(e.target.value),
                })
              }
              className={styles.slider}
              aria-label="blackout threshold"
              data-testid="detection-params-blackout"
            />
            <span className={styles.sliderValue}>
              {detectionParams.blackoutThreshold.toFixed(0)}
            </span>
          </div>

          <div className={styles.labelRow}>
            <label htmlFor={workersId} className={styles.fieldLabel}>
              ワーカー数
            </label>
            <HelpTip
              label="ワーカー数の説明"
              testId="detection-params-workers-help"
            >
              {WORKERS_HELP}
            </HelpTip>
          </div>
          <div className={styles.numericRow}>
            <input
              id={workersId}
              type="number"
              min={WORKERS_INPUT_MIN}
              max={WORKERS_INPUT_MAX}
              step={1}
              value={detectionParams.workers}
              onChange={(e) => {
                const n = Number.parseInt(e.target.value, 10);
                setDetectionParams({
                  workers: Number.isFinite(n) && n >= 0 ? n : 0,
                });
              }}
              className={styles.numericInput}
              aria-label="workers"
              data-testid="detection-params-workers"
            />
            <span className={styles.numericHint}>
              {detectionParams.workers === 0 ? '(自動)' : ''}
            </span>
          </div>

          <div className={styles.labelRow}>
            <span className={styles.fieldLabel}>GPU</span>
            <HelpTip label="GPU の説明" testId="detection-params-gpu-help">
              {GPU_HELP}
            </HelpTip>
          </div>
          <div
            className={styles.triStateRow}
            role="radiogroup"
            aria-label="gpu mode"
            data-testid="detection-params-gpu"
          >
            <button
              type="button"
              className={`${styles.triStateButton}${detectionParams.gpu === null ? ` ${styles.triStateButtonActive}` : ''}`}
              role="radio"
              aria-checked={detectionParams.gpu === null}
              onClick={() => setDetectionParams({ gpu: null })}
              data-testid="detection-params-gpu-auto"
            >
              自動
            </button>
            <button
              type="button"
              className={`${styles.triStateButton}${detectionParams.gpu === true ? ` ${styles.triStateButtonActive}` : ''}`}
              role="radio"
              aria-checked={detectionParams.gpu === true}
              onClick={() => setDetectionParams({ gpu: true })}
              data-testid="detection-params-gpu-on"
            >
              ON
            </button>
            <button
              type="button"
              className={`${styles.triStateButton}${detectionParams.gpu === false ? ` ${styles.triStateButtonActive}` : ''}`}
              role="radio"
              aria-checked={detectionParams.gpu === false}
              onClick={() => setDetectionParams({ gpu: false })}
              data-testid="detection-params-gpu-off"
            >
              OFF
            </button>
          </div>

          {/* #1136: 旧 #944 §D の「CLI からは指定できません」ノートを置き換え。
              `--masked` / `--vtuber` は相互排他 (CLI exit 5) なので、
              boolean 2 本ではなく radio 1 組で表現する。 */}
          <div className={styles.labelRow}>
            <span className={styles.fieldLabel}>検知経路</span>
            <HelpTip
              label="検知経路の説明"
              testId="detection-params-path-help"
            >
              {DETECTION_PATH_HELP}
            </HelpTip>
          </div>
          <div
            className={`${styles.triStateRow} ${styles.pathRow}`}
            role="radiogroup"
            aria-label="detection path"
            data-testid="detection-params-path"
          >
            {DETECTION_PATH_OPTIONS.map((option) => {
              const active =
                detectionParams.detectionPath === option.value;
              return (
                <button
                  key={option.value}
                  type="button"
                  className={`${styles.triStateButton}${active ? ` ${styles.triStateButtonActive}` : ''}`}
                  role="radio"
                  aria-checked={active}
                  onClick={() =>
                    setDetectionParams({ detectionPath: option.value })
                  }
                  data-testid={option.testId}
                >
                  {option.label}
                </button>
              );
            })}
          </div>

          <div className={styles.resetRow}>
            <button
              type="button"
              className={styles.resetButton}
              onClick={resetDetectionParams}
              disabled={!modified}
              aria-label={`reset to defaults (blackout ${DEFAULT_DETECTION_PARAMS.blackoutThreshold}, workers auto, gpu auto)`}
              data-testid="detection-params-reset"
            >
              リセット
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
