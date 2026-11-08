import React from 'react';
import {afterEach, beforeEach, expect, test, vi} from 'vitest';
import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import EmailDialog from '../src/EmailDialog';

const insights = {summary:'Summary', key_insights:[{text:'Takeaway',segment_index:2,start:18}], action_items:[{action:'Follow up',owner:'Ada',due_date:null,segment_index:2,start:18}], provider:'openai' as const, model:'gpt-4.1-mini'};
beforeEach(() => {
  HTMLDialogElement.prototype.showModal = function() { this.setAttribute('open',''); };
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

test('prefills recipient, requires generated insights, and submits selected combined content with metadata', async () => {
  const fetch = vi.fn().mockResolvedValue({ok:true,headers:new Headers(),json:async()=>({status:'sent'})});
  vi.stubGlobal('fetch',fetch);
  render(<EmailDialog open onClose={()=>{}} jobId="job-1" videoId="abcdefghijk" recipientHint="person@example.com" insights={insights} csrfToken="csrf"/>);
  expect((screen.getByLabelText('Recipient email') as HTMLInputElement).value).toBe('person@example.com');
  fireEvent.click(screen.getByLabelText('Transcript and insights'));
  expect(screen.getByText(/Transcript attached as a plain text file/)).toBeTruthy();
  expect(screen.getByText(/Generated summary, key insights, actions, and source timestamps/)).toBeTruthy();
  expect(screen.getByRole('link',{name:'Link to the source video'}).getAttribute('href')).toContain('abcdefghijk');
  fireEvent.click(screen.getByRole('button',{name:'Send email'}));
  await screen.findByRole('status');
  const [url, options] = fetch.mock.calls[0];
  expect(url).toBe('/transcripts/job-1/email');
  expect(options.headers['X-CSRF-Token']).toBe('csrf');
  expect(JSON.parse(options.body)).toEqual({recipient:'person@example.com',content:'both',insights});
  expect(screen.getByRole('status').textContent).toContain('SMTP accepted');
  expect(screen.getByRole('status').textContent).toContain('not confirmed');
});

test('keeps insight choices unavailable until generation and submits transcript only without insight data', async () => {
  const fetch = vi.fn().mockResolvedValue({ok:true,headers:new Headers(),json:async()=>({status:'sent'})});
  vi.stubGlobal('fetch',fetch);
  render(<EmailDialog open onClose={()=>{}} jobId="job-2" videoId="abcdefghijk" insights={null} csrfToken="csrf"/>);
  expect((screen.getByRole('radio',{name:/Generated insights in the email body/}) as HTMLInputElement).disabled).toBe(true);
  fireEvent.change(screen.getByLabelText('Recipient email'),{target:{value:'person@example.com'}});
  fireEvent.click(screen.getByRole('button',{name:'Send email'}));
  await waitFor(()=>expect(fetch).toHaveBeenCalledTimes(1));
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({recipient:'person@example.com',content:'transcript'});
});

test('shows safe service errors and never retries automatically', async () => {
  const fetch = vi.fn().mockResolvedValue({ok:false,headers:new Headers(),json:async()=>({detail:{code:'email_submission_uncertain',message:'Check the recipient before retrying.'}})});
  vi.stubGlobal('fetch',fetch);
  render(<EmailDialog open onClose={()=>{}} jobId="job-3" videoId="abcdefghijk" insights={null} csrfToken="csrf"/>);
  fireEvent.change(screen.getByLabelText('Recipient email'),{target:{value:'person@example.com'}});
  fireEvent.click(screen.getByRole('button',{name:'Send email'}));
  expect((await screen.findByRole('alert')).textContent).toContain('Check the recipient before retrying');
  expect(fetch).toHaveBeenCalledTimes(1);
});
