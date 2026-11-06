import React from 'react';
import { afterEach, expect, test, vi } from 'vitest';
import { act, cleanup, render, screen } from '@testing-library/react';
import AuthGate from '../src/AuthGate';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const reply = (data: unknown) => new Response(JSON.stringify(data), {status:200,headers:{'Content-Type':'application/json'}});

test('anonymous visitors get sign in and no transcript form', async () => {
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(reply({configured:true,user:null,csrf_token:null})));
  render(<AuthGate/>);
  expect((await screen.findByRole('link',{name:'Sign in with Kinde →'})).getAttribute('href')).toBe('/auth/login');
  expect(screen.queryByRole('button',{name:/Generate transcript/})).toBeNull();
});

test('missing config explains local setup and does not offer broken login', async () => {
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(reply({configured:false,user:null,csrf_token:null})));
  render(<AuthGate/>);
  expect((await screen.findByRole('alert')).textContent).toContain('Kinde setup is required');
  expect(screen.queryByRole('link',{name:/Sign in/})).toBeNull();
});

test('authenticated user without permission claims can submit and expired sessions remove workspace', async () => {
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(reply({configured:true,user:{id:'alice',name:'Alice'},csrf_token:'csrf'})));
  render(<AuthGate/>);
  expect((await screen.findByRole('button',{name:/Generate transcript/}) as HTMLButtonElement).disabled).toBe(false);
  expect(screen.queryByText(/permission/i)).toBeNull();
  expect(screen.getByText('Alice')).toBeTruthy();
  act(() => { window.dispatchEvent(new Event('session-expired')); });
  expect(await screen.findByRole('link',{name:/Sign in with Kinde/})).toBeTruthy();
  expect(screen.queryByText('Alice')).toBeNull();
});
