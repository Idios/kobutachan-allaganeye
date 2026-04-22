import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { SideRail } from './SideRail';

describe('SideRail', () => {
  it('renders ALLAGAN wordmark and 4 decorative icons', () => {
    const { getByText, getByLabelText } = render(<SideRail />);
    expect(getByText('ALLAGAN')).toBeInTheDocument();
    const rail = getByLabelText('Allagan Eye navigation');
    // 1 label + 1 spacer + 4 icons = 6 children
    expect(rail.children.length).toBe(6);
  });
});
