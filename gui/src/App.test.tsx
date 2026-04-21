import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import App from './App';

describe('App (bootstrap placeholder)', () => {
  it('renders placeholder heading', () => {
    render(<App />);
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Allagan Eye');
  });

  it('renders bootstrap notice mentioning issue #483', () => {
    render(<App />);
    expect(screen.getByText(/bootstrap/i)).toBeInTheDocument();
    expect(screen.getByText(/#483/)).toBeInTheDocument();
  });
});
