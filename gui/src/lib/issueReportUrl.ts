/**
 * #669 — GitHub Issue form pre-fill URL builder for the ErrorModal `Issue で
 * 報告する` link. Targets the bug_report.yml form (Group G #688 frozen field
 * ids) and pre-fills `actual` / `environment` / `log_file_attachment` while
 * keeping the total URL within the GitHub form pre-fill safety budget
 * (~8KB; truncates the log_file_attachment first, then drops it entirely if
 * needed).
 *
 * Field id mapping (issue #669 prose vs implementation):
 *   description       → actual
 *   system_info       → environment
 *   crash_log_excerpt → log_file_attachment
 *
 * Truncation strategy: the log_file_attachment is reduced through line-count
 * steps (300 → 150 → 75 → 50 → 0). Each step appends a "ログが切り詰められました
 * — 完全なログは <logPath> を参照" notice. If even the notice doesn't fit, the
 * field is dropped from the URL (so the form still opens with actual +
 * environment pre-filled).
 */

export const BUG_REPORT_BASE_URL =
  'https://github.com/Idios/kobutachan-allaganeye/issues/new?template=bug_report.yml';

/**
 * Soft cap on the total query-string portion of the URL, in encoded bytes.
 * GitHub's form pre-fill silently drops parameters past ~8KB; we keep a margin
 * for the base URL itself plus a safety buffer for the `template=` param.
 */
export const URL_BUDGET = 7800;

const PER_FIELD_BUDGET = { actual: 2000, environment: 2000 } as const;

/**
 * Line-count fallback steps for log_file_attachment when the full log exceeds
 * the per-field budget. The 0-step degrades to a notice-only field (no log
 * lines, just the "truncated, see <logPath>" message).
 */
const LOG_LINE_STEPS = [300, 150, 75, 50, 0] as const;

const TRUNCATION_NOTICE = (logPath: string): string =>
  `\n\n⚠️ ログが切り詰められました。完全なログは ${logPath} を参照してください。`;

export interface IssueReportInput {
  /** ErrorModal の errorMessage + (optional stack trace). */
  actual: string;
  /** `formatSystemInfo()` で組み立てた environment 文字列。 */
  environment: string;
  /** `read_error_log_tail` で取得した log 末尾。 */
  logExcerpt: string;
  /** logExcerpt が切り詰められたとき notice に表示する完全なログのファイルパス。 */
  logPath: string;
}

export interface TruncationResult {
  /** Resulting log text (possibly with a truncation notice appended). */
  text: string;
  /** Whether any truncation happened (line reduction or notice-only). */
  truncated: boolean;
  /** Whether even the notice didn't fit, so the field should be omitted. */
  dropped: boolean;
}

/**
 * Truncate `log` to fit within `budget` (encoded bytes). Tries the full log
 * first, then steps down through `LOG_LINE_STEPS`. Each truncated form has
 * the truncation notice (referencing `logPath`) appended. Returns
 * `dropped=true` only when even the notice alone exceeds the budget.
 */
export function truncateLogToBudget(
  log: string,
  budget: number,
  logPath: string,
): TruncationResult {
  const notice = TRUNCATION_NOTICE(logPath);

  // Try full log first
  if (encodeURIComponent(log).length <= budget) {
    return { text: log, truncated: false, dropped: false };
  }

  const lines = log.split('\n');

  for (const step of LOG_LINE_STEPS) {
    if (step === 0) {
      // 0 lines → notice only (trim leading "\n\n")
      const noticeOnly = notice.trimStart();
      if (encodeURIComponent(noticeOnly).length <= budget) {
        return { text: noticeOnly, truncated: true, dropped: false };
      }
      // even the notice doesn't fit
      return { text: '', truncated: true, dropped: true };
    }
    const candidate = lines.slice(-step).join('\n') + notice;
    if (encodeURIComponent(candidate).length <= budget) {
      return { text: candidate, truncated: true, dropped: false };
    }
  }

  // Should be unreachable (LOG_LINE_STEPS ends in 0 which is handled above)
  return { text: '', truncated: true, dropped: true };
}

/**
 * Build the bug_report.yml pre-fill URL. `actual` and `environment` are
 * trimmed to their per-field byte budget pessimistically (`/3` for CJK
 * worst-case 3-byte UTF-8). `log_file_attachment` consumes the remaining
 * budget via `truncateLogToBudget()`; if it can't fit at all, the field is
 * omitted from the URL so the form still opens with the other two fields
 * pre-filled.
 */
export function buildIssueReportUrl(input: IssueReportInput): string {
  const params = new URLSearchParams();

  const actual = trimToFieldBudget(input.actual, PER_FIELD_BUDGET.actual);
  const environment = trimToFieldBudget(input.environment, PER_FIELD_BUDGET.environment);

  params.set('actual', actual);
  params.set('environment', environment);

  // Reserve budget for the log_file_attachment param.
  // params.toString() so far accounts for actual + environment + their `&`/`=`/key bytes.
  const usedBudget = params.toString().length;
  const reservedForKey = 'log_file_attachment='.length + 1; // +1 for the leading `&`
  const logBudget = Math.max(URL_BUDGET - usedBudget - reservedForKey, 100);

  const logResult = truncateLogToBudget(input.logExcerpt, logBudget, input.logPath);
  if (!logResult.dropped) {
    params.set('log_file_attachment', logResult.text);
  }

  return `${BUG_REPORT_BASE_URL}&${params.toString()}`;
}

/** Trim a single field's text so its encoded form fits the per-field budget. */
function trimToFieldBudget(text: string, budget: number): string {
  if (encodeURIComponent(text).length <= budget) return text;
  // Pessimistic CJK: assume worst-case 3 bytes per char. Slicing by char count
  // (not byte) is safe — `String.prototype.slice` operates on UTF-16 code units
  // but URLSearchParams encoding will not exceed 3x for any BMP char.
  return text.slice(0, Math.floor(budget / 3));
}
