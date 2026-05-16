import { describe, expect, it } from 'vitest';

import { BUG_REPORT_BASE_URL, buildIssueReportBody } from './issueReportBody';

const MIN_INPUT = {
  actual: 'panic: divide by zero\n\nStack:\nat src/lib.rs:42',
  environment:
    'allaganeye 0.2.0 (Windows 11)\n  CPU: AMD Ryzen 9 (16C/32T)\n  GPU: nvidia\n  Memory: 64.0 GB',
  logExcerpt: '[2026-05-11T06:39:06Z] [PANIC] PANIC_MARKER ts=… payload=panic',
};

describe('BUG_REPORT_BASE_URL (#669)', () => {
  it('points to the bug_report.yml form (no query params)', () => {
    expect(BUG_REPORT_BASE_URL).toBe(
      'https://github.com/Idios/kobutachan-allaganeye/issues/new?template=bug_report.yml',
    );
  });
});

describe('buildIssueReportBody (#669, Plan B clipboard)', () => {
  it('emits three Markdown sections in form field order (actual / environment / log)', () => {
    const body = buildIssueReportBody(MIN_INPUT);
    const actualIdx = body.indexOf('## 実際の動作');
    const envIdx = body.indexOf('## 環境情報');
    const logIdx = body.indexOf('## ログファイル (末尾抜粋)');
    expect(actualIdx).toBeGreaterThanOrEqual(0);
    expect(envIdx).toBeGreaterThan(actualIdx);
    expect(logIdx).toBeGreaterThan(envIdx);
  });

  it('includes the raw actual content (with stack)', () => {
    const body = buildIssueReportBody(MIN_INPUT);
    expect(body).toContain('panic: divide by zero');
    expect(body).toContain('at src/lib.rs:42');
  });

  it('includes the raw environment content (multi-line)', () => {
    const body = buildIssueReportBody(MIN_INPUT);
    expect(body).toContain('allaganeye 0.2.0 (Windows 11)');
    expect(body).toContain('CPU: AMD Ryzen 9 (16C/32T)');
    expect(body).toContain('Memory: 64.0 GB');
  });

  it('wraps log in ```text fenced block to preserve formatting', () => {
    const body = buildIssueReportBody(MIN_INPUT);
    const fenced = body.match(/```text\n([\s\S]*?)\n```/);
    expect(fenced).not.toBeNull();
    expect(fenced?.[1]).toContain('PANIC_MARKER');
  });

  it('omits the log section entirely when logExcerpt is empty', () => {
    const body = buildIssueReportBody({ ...MIN_INPUT, logExcerpt: '' });
    expect(body).not.toContain('## ログファイル');
    expect(body).not.toContain('```text');
    // 他の section は残る
    expect(body).toContain('## 実際の動作');
    expect(body).toContain('## 環境情報');
  });

  it('omits the log section when logExcerpt is whitespace only', () => {
    const body = buildIssueReportBody({ ...MIN_INPUT, logExcerpt: '   \n\n  \n' });
    expect(body).not.toContain('## ログファイル');
  });

  it('substitutes "(なし)" when actual is empty', () => {
    const body = buildIssueReportBody({ ...MIN_INPUT, actual: '' });
    const actualSection = body.split('## 環境情報')[0];
    expect(actualSection).toContain('## 実際の動作');
    expect(actualSection).toContain('(なし)');
  });

  it('substitutes "(なし)" when environment is empty', () => {
    const body = buildIssueReportBody({ ...MIN_INPUT, environment: '' });
    // 環境情報 section between "## 環境情報" and either log or end
    const envIdx = body.indexOf('## 環境情報');
    const tail = body.slice(envIdx);
    expect(tail).toContain('(なし)');
  });

  it('preserves CJK characters verbatim (no encoding)', () => {
    const body = buildIssueReportBody({
      actual: '日本語のエラーメッセージ',
      environment: '日本語の環境情報',
      logExcerpt: '日本語のログ',
    });
    expect(body).toContain('日本語のエラーメッセージ');
    expect(body).toContain('日本語の環境情報');
    expect(body).toContain('日本語のログ');
  });
});
