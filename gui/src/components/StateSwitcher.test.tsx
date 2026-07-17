import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useAppStateStore } from '../state/appStateStore';
import { StateSwitcher } from './StateSwitcher';

beforeEach(() => {
  useAppStateStore.getState().reset();
});

describe('StateSwitcher', () => {
  it('renders all 6 screen labels', () => {
    render(<StateSwitcher />);
    expect(screen.getByRole('button', { name: 'インポート' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '検知中' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '一覧' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '境界調整' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '書出し' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'ミニマップ' })).toBeInTheDocument();
  });

  it('marks the active tab with aria-pressed="true"', () => {
    render(<StateSwitcher />);
    const drop = screen.getByRole('button', { name: 'インポート' });
    expect(drop.getAttribute('aria-pressed')).toBe('true');
  });

  it('navigates the app store on click', async () => {
    const user = userEvent.setup();
    render(<StateSwitcher />);
    await user.click(screen.getByRole('button', { name: '一覧' }));
    expect(useAppStateStore.getState().screen).toBe('complete');
  });
});

// #653 -- production build (Tauri bundle / Portable ZIP) では
// StateSwitcher を render しない。dev only に絞って topBar との
// z-index 重複を原理的に解消する (spec 2026-05-03-l2-tier1-stateswitcher-dev-only-design.md §3)。
describe('StateSwitcher production gating', () => {
  beforeEach(() => {
    // import.meta.env.DEV / PROD は Vite が build-time に boolean として inline 展開する。
    // vitest の vi.stubEnv は DEV/PROD/SSR 特殊キーで boolean 値を受け取る (vitest 4.x 型定義)。
    // production build の真の状態 (DEV=false かつ PROD=true) を再現する。
    vi.stubEnv('DEV', false);
    vi.stubEnv('PROD', true);
  });
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('returns null when import.meta.env.DEV is falsy (production build)', () => {
    const { container } = render(<StateSwitcher />);
    expect(container).toBeEmptyDOMElement();
  });
});
