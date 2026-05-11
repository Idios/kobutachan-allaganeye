/**
 * #669 — Builder for the Markdown text that the ErrorModal "Issue 本文を
 * コピー" button writes to the clipboard. The user then opens the
 * `bug_report.yml` form via the "Issue で報告する" link and pastes this body
 * into the form.
 *
 * Why clipboard instead of URL pre-fill: PR #669 originally tried to pre-fill
 * via `?template=bug_report.yml&actual=…&environment=…&log_file_attachment=…`,
 * but live verification found the form opened blank. The root cause turned
 * out to be that `bug_report.yml` does not yet exist on the repository's
 * default branch (`main`) — it lives only on `develop-0.2.0` until the
 * v0.2.0 release. GitHub Issue Templates are loaded from the default
 * branch, so `?template=bug_report.yml` silently falls back to the
 * free-form "Create new issue" page where any `?actual=…` etc. params are
 * meaningless. (Issue #728 tracks moving the template to `main`. Whether
 * GitHub Issue Forms honor URL pre-fill for custom textarea fields once
 * the template renders is a separate question that was not conclusively
 * tested here — see GitHub Community discussion
 * https://github.com/orgs/community/discussions/22335 for the surrounding
 * context.) Clipboard copy works regardless of template state, so Plan B
 * was adopted instead of waiting for #728.
 *
 * The body uses the same field labels that `bug_report.yml` shows to
 * reporters, so the user can either paste the whole block into the
 * "実際の動作" textarea (works as a single dump) or split it across the
 * matching form fields manually.
 */

export const BUG_REPORT_BASE_URL =
  'https://github.com/Idios/kobutachan-allaganeye/issues/new?template=bug_report.yml';

export interface IssueReportInput {
  /** ErrorModal の errorMessage + (optional stack trace). */
  actual: string;
  /** `formatSystemInfo()` で組み立てた environment 文字列。 */
  environment: string;
  /** `read_error_log_tail` で取得した log 末尾。空のときは「ログファイル」section を省略。 */
  logExcerpt: string;
}

/**
 * Build the clipboard body for the bug_report form. Sections match the
 * form's textarea labels in `bug_report.yml` so the reporter can paste
 * into the matching textarea, or paste the whole thing into "実際の動作"
 * as a single dump.
 *
 * No truncation — `read_error_log_tail` already caps the log at 300 lines
 * and clipboard has no practical size limit (vs. 8KB URL safe budget).
 */
export function buildIssueReportBody(input: IssueReportInput): string {
  const sections: string[] = [];

  sections.push('## 実際の動作');
  sections.push('');
  sections.push(input.actual.length > 0 ? input.actual : '(なし)');
  sections.push('');
  sections.push('## 環境情報');
  sections.push('');
  sections.push(input.environment.length > 0 ? input.environment : '(なし)');

  if (input.logExcerpt.trim().length > 0) {
    sections.push('');
    sections.push('## ログファイル (末尾抜粋)');
    sections.push('');
    sections.push('```text');
    sections.push(input.logExcerpt);
    sections.push('```');
  }

  return sections.join('\n');
}
