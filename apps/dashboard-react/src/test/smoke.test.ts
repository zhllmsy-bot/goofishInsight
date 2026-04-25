import { createElement } from 'react';
import { render, screen } from '@testing-library/react';

describe('vitest smoke', () => {
  it('renders DOM assertions', () => {
    render(createElement('h1', null, 'Vitest smoke'));

    expect(screen.getByRole('heading', { name: 'Vitest smoke' })).toBeInTheDocument();
  });
});
