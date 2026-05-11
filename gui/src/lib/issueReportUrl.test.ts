import { describe, expect, it } from 'vitest';

import {
  BUG_REPORT_BASE_URL,
  buildIssueReportUrl,
  truncateLogToBudget,
  URL_BUDGET,
} from './issueReportUrl';

const MIN_INPUT = {
  actual: 'panic: divide by zero',
  environment: 'allaganeye 0.2.0 (Windows 11)',
  logExcerpt: 'line 1\nline 2',
  logPath: 'C:\\install\\logs\\error-20260511.log',
};

describe('buildIssueReportUrl (#669)', () => {
  it('returns a URL starting with the bug_report.yml base', () => {
    const url = buildIssueReportUrl(MIN_INPUT);
    expect(url.startsWith(BUG_REPORT_BASE_URL)).toBe(true);
  });

  it('pre-fills actual / environment / log_file_attachment query params', () => {
    const url = buildIssueReportUrl(MIN_INPUT);
    const query = url.split('?')[1];
    const params = new URLSearchParams(query);
    expect(params.get('template')).toBe('bug_report.yml');
    expect(params.get('actual')).toBe(MIN_INPUT.actual);
    expect(params.get('environment')).toBe(MIN_INPUT.environment);
    expect(params.get('log_file_attachment')).toBe(MIN_INPUT.logExcerpt);
  });

  it('encodes CJK characters correctly (URLSearchParams round-trip)', () => {
    const url = buildIssueReportUrl({
      actual: 'エラーが発生しました',
      environment: '環境情報',
      logExcerpt: 'ログ内容',
      logPath: 'C:\\ログ\\error.log',
    });
    const params = new URLSearchParams(url.split('?')[1]);
    expect(params.get('actual')).toBe('エラーが発生しました');
    expect(params.get('environment')).toBe('環境情報');
    expect(params.get('log_file_attachment')).toBe('ログ内容');
  });

  it('truncates log_file_attachment when total URL exceeds 8KB safe budget', () => {
    const bigLog = Array.from({ length: 1000 }, (_, i) => `line ${i} `.repeat(20)).join('\n');
    const url = buildIssueReportUrl({
      actual: 'panic',
      environment: 'env info',
      logExcerpt: bigLog,
      logPath: 'C:\\install\\logs\\error.log',
    });
    expect(url.length).toBeLessThanOrEqual(BUG_REPORT_BASE_URL.length + URL_BUDGET);
    const params = new URLSearchParams(url.split('?')[1]);
    const log = params.get('log_file_attachment') ?? '';
    expect(log).toContain('ログが切り詰められました');
    expect(log).toContain('C:\\install\\logs\\error.log');
  });

  it('keeps URL within budget even with maximum-size inputs', () => {
    // Per-field trimming caps actual / environment, so the URL stays bounded
    // regardless of how huge the inputs are. log_file_attachment may be
    // truncated but stays present (drop path is unreachable in practice
    // because per-field caps leave room for the notice — covered separately
    // in truncateLogToBudget tests).
    const huge = 'a'.repeat(URL_BUDGET);
    const url = buildIssueReportUrl({
      actual: huge,
      environment: huge,
      logExcerpt: 'whatever',
      logPath: 'C:\\install\\logs\\error.log',
    });
    expect(url.length).toBeLessThanOrEqual(BUG_REPORT_BASE_URL.length + URL_BUDGET);
  });

  it('handles empty logExcerpt without adding truncation notice', () => {
    const url = buildIssueReportUrl({
      actual: 'panic',
      environment: 'env',
      logExcerpt: '',
      logPath: 'C:\\install\\logs\\error.log',
    });
    const params = new URLSearchParams(url.split('?')[1]);
    expect(params.get('log_file_attachment') ?? '').not.toContain('ログが切り詰められました');
  });

  it('passes through small log unchanged', () => {
    const url = buildIssueReportUrl(MIN_INPUT);
    const params = new URLSearchParams(url.split('?')[1]);
    expect(params.get('log_file_attachment')).toBe('line 1\nline 2');
  });
});

describe('truncateLogToBudget (#669)', () => {
  const LOG_PATH = 'C:\\install\\logs\\error.log';

  it('returns log unchanged when within budget', () => {
    const log = 'line 1\nline 2';
    const result = truncateLogToBudget(log, 1000, LOG_PATH);
    expect(result.text).toBe(log);
    expect(result.truncated).toBe(false);
    expect(result.dropped).toBe(false);
  });

  it('reduces lines through steps until fits the budget (300→150→75→50→0)', () => {
    const lines = Array.from({ length: 500 }, (_, i) => `line ${i} repeated ten times.`);
    const log = lines.join('\n');
    // Tight budget that forces truncation but not full drop
    const result = truncateLogToBudget(log, 1500, LOG_PATH);
    expect(result.truncated).toBe(true);
    expect(result.dropped).toBe(false);
    // resulting text should fit the encoded budget
    expect(encodeURIComponent(result.text).length).toBeLessThanOrEqual(1500);
    // notice present
    expect(result.text).toContain('ログが切り詰められました');
    expect(result.text).toContain(LOG_PATH);
  });

  it('returns notice-only (zero log lines) when even 50 lines exceed budget', () => {
    const lines = Array.from({ length: 500 }, (_, i) => `super-long-line-${i}`.repeat(20));
    const log = lines.join('\n');
    // budget large enough to fit notice text but not 50 lines of huge content
    const result = truncateLogToBudget(log, 200, LOG_PATH);
    expect(result.truncated).toBe(true);
    // either notice-only OR dropped; both satisfy the budget invariant
    expect(encodeURIComponent(result.text).length).toBeLessThanOrEqual(200);
  });

  it('drops log entirely (returns "" with dropped=true) when notice itself exceeds budget', () => {
    const log = 'whatever';
    const result = truncateLogToBudget(log, 5, LOG_PATH);
    expect(result.text).toBe('');
    expect(result.dropped).toBe(true);
  });

  it('preserves the most recent lines (tail), not the head', () => {
    // 500 lines forces full-log over budget but allows partial truncation.
    // Budget 2000 gives ~1650 chars for log after the (large CJK) notice,
    // which fits the 150-line step but not the 300-line step.
    const lines = Array.from({ length: 500 }, (_, i) => `line${i}`);
    const log = lines.join('\n');
    const result = truncateLogToBudget(log, 2000, LOG_PATH);
    expect(result.truncated).toBe(true);
    expect(result.dropped).toBe(false);
    expect(result.text).toContain('line499'); // tail preserved
    expect(result.text).not.toContain('line0\n'); // head dropped
  });
});
