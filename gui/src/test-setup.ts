import '@testing-library/jest-dom/vitest';
import { afterEach, expect } from 'vitest';
import { cleanup } from '@testing-library/react';
import { toHaveNoViolations } from 'jest-axe';

// #587: extend vitest's global expect with jest-axe's a11y matcher so
// individual screen / modal tests can assert
// `expect(container).toHaveNoViolations()`.
expect.extend(toHaveNoViolations);

afterEach(() => {
  cleanup();
});
