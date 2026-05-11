import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { SampleModeBanner } from './SampleModeBanner';
import { useMetadataStore } from '../state/metadataStore';

describe('SampleModeBanner', () => {
  afterEach(() => {
    // store を default state に戻す
    useMetadataStore.getState().clear();
  });

  it('renders banner in sample mode (filePath=null + metadata=non-null)', () => {
    useMetadataStore.getState().loadSample();
    render(<SampleModeBanner />);
    expect(screen.getByText(/サンプル動画/)).toBeInTheDocument();
  });

  it('does not render in real-file mode (filePath=non-null)', () => {
    useMetadataStore.getState().loadSample();
    useMetadataStore.setState({ filePath: '/some/path.mp4' });
    render(<SampleModeBanner />);
    expect(screen.queryByText(/サンプル動画/)).toBeNull();
  });

  it('does not render in initial idle (metadata=null)', () => {
    useMetadataStore.setState({ filePath: null, metadata: null });
    render(<SampleModeBanner />);
    expect(screen.queryByText(/サンプル動画/)).toBeNull();
  });
});
