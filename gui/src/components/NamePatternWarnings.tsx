import type { NamePatternIssue } from '../utils/namePatternSandbox';
import styles from './NamePatternWarnings.module.css';

/**
 * #964 — name-pattern プレビュー警告。
 *
 * `computeNamePatternIssues` (CLI `pool.py` 層 1 の TS mirror) の結果を表示する。
 * 警告は「書き出し時に CLI が exit 5 で拒否する」ことをプレビュー時点で知らせる
 * ためのもので、書き出し自体はブロックしない (最終 gate は CLI)。
 * issue が無いときは何も render しない。
 */
export function NamePatternWarnings({ issues }: { issues: NamePatternIssue[] }) {
  if (issues.length === 0) return null;
  return (
    <div className={styles.warnBox} role="status" data-testid="name-pattern-warning">
      <div className={styles.title}>⚠ この命名規則は書き出し時に拒否されます</div>
      <ul className={styles.list}>
        {issues.map((issue) => (
          <li
            key={`${issue.kind}:${issue.sampleName}`}
            className={styles.item}
            data-issue-kind={issue.kind}
          >
            {issue.message}
          </li>
        ))}
      </ul>
    </div>
  );
}
