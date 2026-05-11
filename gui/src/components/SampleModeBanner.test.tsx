import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { SampleModeBanner } from './SampleModeBanner';
import { useMetadataStore } from '../state/metadataStore';
import type { Metadata } from '../types/metadata';

/** Minimal stub for tests that only care about filePath/metadata presence. */
const stubMetadata = { matches: [], gaps: [] } as unknown as Metadata;

describe('SampleModeBanner', () => {
  afterEach(() => {
    // store を default state に戻す
    useMetadataStore.setState({ filePath: null, metadata: null });
  });

  it('renders banner in sample mode (filePath=null + metadata=non-null)', () => {
    useMetadataStore.setState({
      filePath: null,
      metadata: stubMetadata,
    });
    render(<SampleModeBanner />);
    const banner = screen.getByRole('status');
    expect(banner).toHaveTextContent('サンプル動画です');
    expect(banner).toHaveAttribute('aria-live', 'polite');
  });

  it('does not render in real-file mode (filePath=non-null)', () => {
    useMetadataStore.setState({
      filePath: '/some/path.mp4',
      metadata: stubMetadata,
    });
    render(<SampleModeBanner />);
    expect(screen.queryByRole('status')).toBeNull();
  });

  it('does not render in initial idle (metadata=null)', () => {
    useMetadataStore.setState({ filePath: null, metadata: null });
    render(<SampleModeBanner />);
    expect(screen.queryByRole('status')).toBeNull();
  });
});
