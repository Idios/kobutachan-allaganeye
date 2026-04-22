import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { invokeMock } = vi.hoisted(() => ({ invokeMock: vi.fn() }));

vi.mock('@tauri-apps/api/core', () => ({
  invoke: invokeMock,
}));

import { ExportScreen } from './ExportScreen';
import { useAppStateStore } from '../state/appStateStore';
import { useMetadataStore } from '../state/metadataStore';

beforeEach(() => {
  invokeMock.mockReset();
  invokeMock.mockResolvedValue(undefined);
  useAppStateStore.getState().reset();
  useMetadataStore.getState().clear();
  useMetadataStore.getState().loadSample();
  useAppStateStore.getState().navigate('export');
});

afterEach(() => {
  vi.useRealTimers();
});

describe('ExportScreen', () => {
  it('renders empty state when metadata is null', () => {
    useMetadataStore.getState().clear();
    render(<ExportScreen />);
    expect(screen.getByText(/No metadata/i)).toBeInTheDocument();
  });

  it('renders with idle phase and [書き出し開始] button', () => {
    render(<ExportScreen />);
    expect(screen.getByTestId('export-screen').dataset.phase).toBe('idle');
    expect(screen.getByRole('button', { name: /書き出し開始/ })).toBeInTheDocument();
  });

  it('[◀ プレビュー] returns to preview when idle', async () => {
    render(<ExportScreen />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /プレビュー/ }));
    expect(useAppStateStore.getState().screen).toBe('preview');
  });

  it('[書き出し開始] transitions to running and advances dummy progress', () => {
    vi.useFakeTimers();
    render(<ExportScreen />);
    const button = screen.getByRole('button', { name: /書き出し開始/ });
    act(() => {
      button.click();
    });
    expect(screen.getByTestId('export-screen').dataset.phase).toBe('running');
    act(() => {
      vi.advanceTimersByTime(500);
    });
    // Progress has started — we should see the progress label
    expect(screen.getByText(/分割・書き出し中/)).toBeInTheDocument();
  });

  it('[中断] transitions running -> cancelling -> idle (progress reset)', () => {
    vi.useFakeTimers();
    render(<ExportScreen />);
    act(() => {
      screen.getByRole('button', { name: /書き出し開始/ }).click();
    });
    act(() => {
      vi.advanceTimersByTime(400);
    });
    act(() => {
      screen.getByRole('button', { name: '中断' }).click();
    });
    // effects resolve synchronously in act
    expect(screen.getByTestId('export-screen').dataset.phase).toBe('idle');
  });

  it('running progress completes to 100% → shows [✓ フォルダを開く]', () => {
    vi.useFakeTimers();
    render(<ExportScreen />);
    act(() => {
      screen.getByRole('button', { name: /書き出し開始/ }).click();
    });
    act(() => {
      vi.advanceTimersByTime(9000);
    });
    expect(screen.getByTestId('export-screen').dataset.phase).toBe('completed');
    expect(
      screen.getByRole('button', { name: /フォルダを開く/ }),
    ).toBeInTheDocument();
  });

  it('codec selection toggles via aria-pressed', async () => {
    render(<ExportScreen />);
    const user = userEvent.setup();
    const h264 = screen.getByRole('button', { name: /H\.264/ });
    expect(h264.getAttribute('aria-pressed')).toBe('false');
    await user.click(h264);
    expect(h264.getAttribute('aria-pressed')).toBe('true');
  });
});
