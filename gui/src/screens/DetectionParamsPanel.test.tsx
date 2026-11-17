import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { axe } from 'jest-axe';
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

// #1135: 3 項目の意味・効果の help (docs/ui-interaction-spec.md §1.7)。
describe('DetectionParamsPanel field help (#1135)', () => {
  async function openPanel() {
    const user = userEvent.setup();
    render(<DetectionParamsPanel />);
    await user.click(screen.getByTestId('detection-params-toggle'));
    return user;
  }

  it('renders a help trigger for each of the three settings', async () => {
    await openPanel();
    expect(
      screen.getByTestId('detection-params-blackout-help-trigger'),
    ).toHaveAccessibleName('検知しきい値の説明');
    expect(
      screen.getByTestId('detection-params-workers-help-trigger'),
    ).toHaveAccessibleName('ワーカー数の説明');
    expect(
      screen.getByTestId('detection-params-gpu-help-trigger'),
    ).toHaveAccessibleName('GPU の説明');
  });

  it('reveals the threshold explanation on hover', async () => {
    const user = await openPanel();
    await user.hover(screen.getByTestId('detection-params-blackout-help-trigger'));
    expect(
      screen.getByTestId('detection-params-blackout-help-popover'),
    ).toHaveTextContent('平均輝度');
  });

  it('reveals every explanation through the keyboard alone', async () => {
    const user = await openPanel();
    // 詳細設定 toggle → blackout help → slider → workers help →
    // workers input → gpu help
    await user.tab();
    expect(
      screen.getByTestId('detection-params-blackout-help-popover'),
    ).toHaveTextContent('平均輝度');
    await user.tab();
    await user.tab();
    expect(
      screen.getByTestId('detection-params-workers-help-popover'),
    ).toHaveTextContent('CPU コア数');
    await user.tab();
    await user.tab();
    expect(
      screen.getByTestId('detection-params-gpu-help-popover'),
    ).toHaveTextContent('コーデック');
  });

  it('has no axe violations with the panel expanded', async () => {
    const user = userEvent.setup();
    const { container } = render(<DetectionParamsPanel />);
    await user.click(screen.getByTestId('detection-params-toggle'));
    expect(await axe(container)).toHaveNoViolations();
  });
});

// #1136: 検知経路 (`--masked` / `--vtuber`) の radio 3 択。
// 相互排他を型で表すため store は 3 値 1 本 (`detectionPath`)。
describe('DetectionParamsPanel detection path (#1136)', () => {
  async function openPanel() {
    const user = userEvent.setup();
    render(<DetectionParamsPanel />);
    await user.click(screen.getByTestId('detection-params-toggle'));
    return user;
  }

  it('renders a radiogroup with the three paths and standard checked by default', async () => {
    await openPanel();
    const group = screen.getByTestId('detection-params-path');
    expect(group).toHaveAttribute('role', 'radiogroup');
    expect(within(group).getAllByRole('radio')).toHaveLength(3);
    expect(screen.getByTestId('detection-params-path-standard')).toHaveAttribute(
      'aria-checked',
      'true',
    );
    expect(screen.getByTestId('detection-params-path-masked')).toHaveAttribute(
      'aria-checked',
      'false',
    );
    expect(screen.getByTestId('detection-params-path-vtuber')).toHaveAttribute(
      'aria-checked',
      'false',
    );
  });

  it.each([
    { testid: 'detection-params-path-masked', expected: 'masked' as const },
    { testid: 'detection-params-path-vtuber', expected: 'vtuber' as const },
    { testid: 'detection-params-path-standard', expected: 'standard' as const },
  ])('$testid sets detectionPath=$expected', async ({ testid, expected }) => {
    const user = await openPanel();
    // 最初に別の値を入れておき、standard を押したときに戻ることが観測できるようにする。
    useAppStateStore.getState().setDetectionParams({ detectionPath: 'masked' });
    await user.click(screen.getByTestId(testid));
    expect(useAppStateStore.getState().detectionParams.detectionPath).toBe(
      expected,
    );
  });

  it('keeps exactly one path checked after selecting another', async () => {
    const user = await openPanel();
    await user.click(screen.getByTestId('detection-params-path-vtuber'));
    const group = screen.getByTestId('detection-params-path');
    const checked = within(group)
      .getAllByRole('radio')
      .filter((el) => el.getAttribute('aria-checked') === 'true');
    expect(checked).toHaveLength(1);
    expect(checked[0]).toBe(screen.getByTestId('detection-params-path-vtuber'));
  });

  it('does not touch the other detection fields when switching path', async () => {
    const user = await openPanel();
    useAppStateStore.getState().setDetectionParams({
      blackoutThreshold: 22,
      workers: 8,
      gpu: true,
    });
    await user.click(screen.getByTestId('detection-params-path-masked'));
    const dp = useAppStateStore.getState().detectionParams;
    expect(dp.blackoutThreshold).toBe(22);
    expect(dp.workers).toBe(8);
    expect(dp.gpu).toBe(true);
  });

  it('shows the "(変更あり)" hint while collapsed when only the path differs', () => {
    useAppStateStore.getState().setDetectionParams({ detectionPath: 'vtuber' });
    render(<DetectionParamsPanel />);
    expect(screen.getByLabelText('変更あり')).toBeInTheDocument();
  });

  it('exposes a help trigger labelled 検知経路の説明 that explains the three choices', async () => {
    const user = await openPanel();
    const trigger = screen.getByTestId('detection-params-path-help-trigger');
    expect(trigger).toHaveAccessibleName('検知経路の説明');
    await user.hover(trigger);
    const popover = screen.getByTestId('detection-params-path-help-popover');
    expect(popover).toHaveTextContent('マスクのない領域');
    expect(popover).toHaveTextContent('スコアバー');
    expect(popover).toHaveTextContent('同時に選べません');
  });

  it('reveals the path explanation through the keyboard alone', async () => {
    const user = await openPanel();
    // toggle → blackout help → slider → workers help → numeric → gpu help
    // → gpu auto → gpu on → gpu off → path help
    for (let i = 0; i < 9; i += 1) {
      await user.tab();
    }
    expect(
      screen.getByTestId('detection-params-path-help-popover'),
    ).toHaveTextContent('配信レイアウト');
  });

  it('has no axe violations with the path radio group', async () => {
    const user = userEvent.setup();
    const { container } = render(<DetectionParamsPanel />);
    await user.click(screen.getByTestId('detection-params-toggle'));
    await user.click(screen.getByTestId('detection-params-path-vtuber'));
    expect(await axe(container)).toHaveNoViolations();
  });
});
