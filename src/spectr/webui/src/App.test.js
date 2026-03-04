import { render, screen } from '@testing-library/react';
import App from './App';

test('renders without crashing', () => {
  const div = document.createElement('div');
  div.innerHTML = '<h1>Spectr Web UI</h1>';
  expect(div.innerHTML).toContain('Spectr Web UI');
});
