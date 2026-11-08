import React, { FormEvent, useEffect, useRef, useState } from 'react';
import { Insights } from './InsightsPanel';
import { sessionFetch } from './session';

export type EmailContent = 'transcript' | 'insights' | 'both';

export default function EmailDialog({open, onClose, jobId, videoId, recipientHint, insights, csrfToken, initialContent = 'transcript'}: {
  open: boolean;
  onClose: () => void;
  jobId: string;
  videoId: string;
  recipientHint?: string;
  insights: Insights | null;
  csrfToken: string;
  initialContent?: EmailContent;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [recipient, setRecipient] = useState(recipientHint || '');
  const [content, setContent] = useState<EmailContent>('transcript');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  useEffect(() => { if (open) { setRecipient(recipientHint || ''); setContent(initialContent); setMessage(''); setError(''); dialogRef.current?.showModal(); } else if (dialogRef.current?.open) dialogRef.current.close(); }, [open, recipientHint, initialContent]);
  useEffect(() => { if (!insights && content !== 'transcript') setContent('transcript'); }, [insights, content]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy || (content !== 'transcript' && !insights)) return;
    setBusy(true); setError(''); setMessage('');
    try {
      const response = await sessionFetch(`/transcripts/${encodeURIComponent(jobId)}/email`, {
        method: 'POST',
        headers: {'Content-Type':'application/json', 'X-CSRF-Token':csrfToken},
        body: JSON.stringify({recipient: recipient.trim(), content, ...(content === 'transcript' ? {} : {insights})}),
      });
      const data = await response.json();
      if (!response.ok) {
        setError(typeof data.detail === 'string' ? data.detail : data.detail?.message || 'Could not send the email. Review the address and try again.');
        return;
      }
      if (data.status === 'sent') setMessage('SMTP accepted the message. Delivery is not confirmed.');
      else setError('The email service returned an unexpected response. Check before trying again.');
    } catch {
      setError('Could not confirm the email request. Check the service status before trying again.');
    } finally { setBusy(false); }
  }

  return <dialog ref={dialogRef} className="email-dialog" aria-labelledby="email-title" onCancel={event => { if (busy) event.preventDefault(); else onClose(); }} onClose={() => { if (open) onClose(); }}>
    <div className="email-dialog-head"><div><span className="eyebrow">SHARE A COPY</span><h2 id="email-title">Email transcript</h2><p>Send a copy of this completed transcript.</p></div><button type="button" className="dialog-close" aria-label="Close email dialog" disabled={busy} onClick={onClose}>×</button></div>
    <form onSubmit={submit}>
      <label>Recipient email<input type="email" autoComplete="email" value={recipient} onChange={event => setRecipient(event.target.value)} maxLength={320} required disabled={busy || !!message} /></label>
      <fieldset className="email-content"><legend>Include</legend>
        <label><input type="radio" name="email-content" value="transcript" checked={content === 'transcript'} onChange={() => setContent('transcript')} disabled={busy || !!message}/>Transcript as a TXT attachment</label>
        <label><input type="radio" name="email-content" value="insights" checked={content === 'insights'} onChange={() => setContent('insights')} disabled={!insights || busy || !!message}/>Generated insights in the email body {!insights && <span className="field-help">Generate insights first</span>}</label>
        <label><input type="radio" name="email-content" value="both" checked={content === 'both'} onChange={() => setContent('both')} disabled={!insights || busy || !!message}/>Transcript and insights {!insights && <span className="field-help">Generate insights first</span>}</label>
      </fieldset>
      <div className="email-includes"><strong>This email will include</strong><ul>
        {(content !== 'insights') && <li>Transcript attached as a plain text file</li>}
        {(content !== 'transcript') && <li>Generated summary, key insights, actions, and source timestamps in the message</li>}
        <li><a href={`https://www.youtube.com/watch?v=${encodeURIComponent(videoId)}`} target="_blank" rel="noreferrer">Link to the source video</a></li>
      </ul></div>
      <div aria-live="polite">{error && <p className="error email-feedback" role="alert">{error}</p>}{message && <p className="email-success" role="status">{message}</p>}</div>
      <div className="email-dialog-actions"><button type="button" className="secondary-button" onClick={onClose} disabled={busy}>Close</button>{!message && <button className="primary" type="submit" disabled={busy}>{busy ? 'Sending…' : 'Send email'}</button>}</div>
    </form>
  </dialog>;
}
