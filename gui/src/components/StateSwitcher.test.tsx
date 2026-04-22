import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

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
