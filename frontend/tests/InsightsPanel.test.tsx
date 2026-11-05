import React from 'react';
import { afterEach, expect, test, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import InsightsPanel from '../src/InsightsPanel';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); localStorage.clear(); });
const result = {summary:'Test the launch.', key_insights:[{text:'Testing is needed.', segment_index:0, start:12.5}], action_items:[{action:'Send the report.', owner:'Sam', due_date:'Friday', segment_index:0, start:12.5}], provider:'openai', model:'gpt-4.1-mini'};

test('sends a key only in the request header, clears it, and renders grounded results', async () => {
  const fetch = vi.fn().mockResolvedValue({ok:true,json:async()=>result});
  vi.stubGlobal('fetch',fetch);
  const source = vi.fn();
  render(<InsightsPanel jobId="job-one" onSource={source}/>);
  fireEvent.change(screen.getByLabelText('API key'),{target:{value:'private-test-key'}});
  fireEvent.click(screen.getByRole('button',{name:'Generate insights'}));
  await screen.findByText('Send the report.');
  expect((screen.getByLabelText('API key') as HTMLInputElement).value).toBe('');
  const [url,options] = fetch.mock.calls[0];
  expect(url).toBe('/transcripts/job-one/insights');
  expect(options.headers['X-AI-API-Key']).toBe('private-test-key');
  expect(options.body).not.toContain('private-test-key');
  expect(JSON.stringify(localStorage)).not.toContain('private-test-key');
  fireEvent.click(screen.getAllByRole('button',{name:'Go to transcript at 00:12'})[0]);
  expect(source).toHaveBeenCalledWith(0);
});

test('changing destination clears a previously entered key', () => {
  render(<InsightsPanel jobId="one" onSource={()=>{}}/>);
  fireEvent.change(screen.getByLabelText('API key'),{target:{value:'openai-key'}});
  fireEvent.change(screen.getByLabelText('AI provider'),{target:{value:'compatible'}});
  expect((screen.getByLabelText('API key') as HTMLInputElement).value).toBe('');
  fireEvent.change(screen.getByLabelText('API key'),{target:{value:'custom-key'}});
  fireEvent.change(screen.getByLabelText('API base URL'),{target:{value:'https://api.example.com/v1'}});
  expect((screen.getByLabelText('API key') as HTMLInputElement).value).toBe('');
});

test('shows provider errors without retaining the key', async () => {
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:false,json:async()=>({detail:{message:'The provider rejected the API key.'}})}));
  render(<InsightsPanel jobId="one" onSource={()=>{}}/>);
  fireEvent.change(screen.getByLabelText('API key'),{target:{value:'invalid-test-key'}});
  fireEvent.click(screen.getByRole('button',{name:'Generate insights'}));
  await screen.findByRole('alert');
  expect(screen.getByRole('alert').textContent).toContain('rejected');
  expect((screen.getByLabelText('API key') as HTMLInputElement).value).toBe('');
});

test('empty actions have an explicit empty state', async () => {
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:true,json:async()=>({...result,action_items:[]})}));
  render(<InsightsPanel jobId="one" onSource={()=>{}}/>);
  fireEvent.change(screen.getByLabelText('API key'),{target:{value:'test-key'}});
  fireEvent.click(screen.getByRole('button',{name:'Generate insights'}));
  await screen.findByText('No explicit action items were found in this transcript.');
});
