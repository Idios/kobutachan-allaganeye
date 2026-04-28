import { useId, useState } from 'react';

import {
  DEFAULT_DETECTION_PARAMS,
  useAppStateStore,
} from '../state/appStateStore';
import { isDetectionParamsModified } from '../utils/detection';
import styles from './DetectionParamsPanel.module.css';

/**
 * #613: 詳細設定パネル — DropScreen の SelectedCard 内に collapsible で
 * 配置され、`detectionParams` (appStateStore) を直接 mutate する。
 *
 * Default は折り畳み (panelOpen=false)。展開時に 4 controls + [リセット]
 * を表示する。各 control の挙動は `docs/ui-interaction-spec.md` §2.1.10。
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
          <label htmlFor={blackoutId} className={styles.fieldLabel}>
            検知しきい値
          </label>
          <div className={styles.sliderRow}>
            <input
              id={blackoutId}
              type="range"
              min={0}
              max={50}
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

          <label htmlFor={workersId} className={styles.fieldLabel}>
            ワーカー数
          </label>
          <div className={styles.numericRow}>
            <input
              id={workersId}
              type="number"
              min={0}
              max={32}
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

          <span className={styles.fieldLabel}>GPU</span>
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
