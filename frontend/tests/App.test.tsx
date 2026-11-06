import React from 'react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { cleanup, render, screen, fireEvent } from '@testing-library/react';
import App from '../src/App';

beforeEach(() => { localStorage.clear(); delete document.documentElement.dataset.theme; });
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

test('starts dark and persists the light-mode selection across mounts', () => {
  const view = render(<App user={{id:"alice",name:"Alice"}} csrfToken="csrf" onLogout={()=>{}}/>);
  expect(document.documentElement.dataset.theme).toBe('dark');
  fireEvent.click(screen.getByRole('button', {name:'Switch to light mode'}));
  expect(document.documentElement.dataset.theme).toBe('light');
  expect(localStorage.getItem('transcript-studio-theme')).toBe('light');
  view.unmount();
  render(<App user={{id:"alice",name:"Alice"}} csrfToken="csrf" onLogout={()=>{}}/>);
  expect(document.documentElement.dataset.theme).toBe('light');
  fireEvent.click(screen.getByRole('button', {name:'Switch to dark mode'}));
  expect(document.documentElement.dataset.theme).toBe('dark');
});

test('handles unavailable browser storage without breaking the toggle', () => {
  vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked'); });
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked'); });
  render(<App user={{id:"alice",name:"Alice"}} csrfToken="csrf" onLogout={()=>{}}/>);
  fireEvent.click(screen.getByRole('button', {name:'Switch to light mode'}));
  expect(document.documentElement.dataset.theme).toBe('light');
});

test('invalid stored themes fall back to dark', () => {
  localStorage.setItem('transcript-studio-theme','unknown');
  render(<App user={{id:"alice",name:"Alice"}} csrfToken="csrf" onLogout={()=>{}}/>);
  expect(document.documentElement.dataset.theme).toBe('dark');
});
