import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useAppStateStore } from '../state/appStateStore';
import { StateSwitcher } from './StateSwitcher';

beforeEach(() => {
  useAppStateStore.getState().reset();
});

describe('StateSwitcher', () => {
  it('renders all 5 screen labels', () => {
    render(<StateSwitcher />);
    expect(screen.getByRole('button', { name: 'インポート' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '検知中' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '一覧' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '境界調整' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '書出し' })).toBeInTheDocument();
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
    // import.meta.env.DEV を falsy 値 (空文字列) に上書きして production を simulate。
    // Vite が DEV を boolean として配布する一方、vi.stubEnv は string で受け取る。
    // `if (!import.meta.env.DEV)` は falsy 判定なので空文字列で OK。
    vi.stubEnv('DEV', '');
  });
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('returns null when import.meta.env.DEV is falsy (production build)', () => {
    const { container } = render(<StateSwitcher />);
    expect(container).toBeEmptyDOMElement();
  });
});
