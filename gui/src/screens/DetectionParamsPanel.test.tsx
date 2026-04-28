import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

import {
  DEFAULT_DETECTION_PARAMS,
  useAppStateStore,
} from '../state/appStateStore';
import { DetectionParamsPanel } from './DetectionParamsPanel';

beforeEach(() => {
  useAppStateStore.getState().reset();
});

describe('DetectionParamsPanel (#613)', () => {
  it('starts collapsed: body is not rendered', () => {
    render(<DetectionParamsPanel />);
    const toggle = screen.getByTestId('detection-params-toggle');
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByTestId('detection-params-body')).toBeNull();
  });

  it('expands when the header toggle is clicked', async () => {
    render(<DetectionParamsPanel />);
    const user = userEvent.setup();
    await user.click(screen.getByTestId('detection-params-toggle'));
    expect(screen.getByTestId('detection-params-toggle')).toHaveAttribute(
      'aria-expanded',
      'true',
    );
    expect(screen.getByTestId('detection-params-body')).toBeInTheDocument();
  });

  it('collapses again on a second click', async () => {
    render(<DetectionParamsPanel />);
    const user = userEvent.setup();
    const toggle = screen.getByTestId('detection-params-toggle');
    await user.click(toggle);
    await user.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByTestId('detection-params-body')).toBeNull();
  });

  it('shows a "(変更あり)" hint while collapsed when params differ from defaults', async () => {
    useAppStateStore.getState().setDetectionParams({ gpu: false });
    render(<DetectionParamsPanel />);
    expect(screen.getByLabelText('変更あり')).toBeInTheDocument();
  });

  it('blackout slider mutates the store and reflects in the value display', async () => {
    render(<DetectionParamsPanel />);
    const user = userEvent.setup();
    await user.click(screen.getByTestId('detection-params-toggle'));
    const slider = screen.getByTestId(
      'detection-params-blackout',
    ) as HTMLInputElement;
    // jsdom does not interpret arrow keys on type=range as value changes,
    // so drive the change handler directly via fireEvent (the canonical
    // pattern for range inputs in @testing-library/react).
    fireEvent.change(slider, { target: { value: '22' } });
    expect(useAppStateStore.getState().detectionParams.blackoutThreshold).toBe(
      22,
    );
    expect(screen.getByText('22')).toBeInTheDocument();
  });

  it('workers numeric input mutates the store', async () => {
    render(<DetectionParamsPanel />);
    const user = userEvent.setup();
    await user.click(screen.getByTestId('detection-params-toggle'));
    const input = screen.getByTestId(
      'detection-params-workers',
    ) as HTMLInputElement;
    await user.clear(input);
    await user.type(input, '8');
    expect(useAppStateStore.getState().detectionParams.workers).toBe(8);
  });

  it.each([
    {
      testid: 'detection-params-gpu-on',
      expected: true as boolean | null,
    },
    {
      testid: 'detection-params-gpu-off',
      expected: false as boolean | null,
    },
    {
      testid: 'detection-params-gpu-auto',
      expected: null as boolean | null,
    },
  ])('GPU tri-state $testid sets gpu=$expected', async ({ testid, expected }) => {
    render(<DetectionParamsPanel />);
    const user = userEvent.setup();
    await user.click(screen.getByTestId('detection-params-toggle'));
    // First flip away from auto so the auto button click is observable.
    if (expected === null) {
      useAppStateStore.getState().setDetectionParams({ gpu: true });
    }
    await user.click(screen.getByTestId(testid));
    expect(useAppStateStore.getState().detectionParams.gpu).toBe(expected);
  });

  it('reset button is disabled while params equal defaults', async () => {
    render(<DetectionParamsPanel />);
    const user = userEvent.setup();
    await user.click(screen.getByTestId('detection-params-toggle'));
    expect(screen.getByTestId('detection-params-reset')).toBeDisabled();
  });

  it('reset button restores defaults when clicked', async () => {
    useAppStateStore.getState().setDetectionParams({
      blackoutThreshold: 30,
      workers: 8,
      gpu: false,
    });
    render(<DetectionParamsPanel />);
    const user = userEvent.setup();
    await user.click(screen.getByTestId('detection-params-toggle'));
    const reset = screen.getByTestId('detection-params-reset');
    expect(reset).not.toBeDisabled();
    await user.click(reset);
    expect(useAppStateStore.getState().detectionParams).toEqual(
      DEFAULT_DETECTION_PARAMS,
    );
  });
});
