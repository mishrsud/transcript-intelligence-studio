import React, { useEffect, useRef, useState } from 'react';
import { useTheme } from './theme';
import InsightsPanel from './InsightsPanel';
import { Session, sessionFetch } from './session';

type Segment = { text: string; start: number; duration: number };
type Job = { id: string; status: 'queued'|'processing'|'completed'|'failed'; error?: {code: string; message: string}; transcript?: { video_id: string; language: string; source: string; retrieved_at: string; segments: Segment[] } };
const clock = (s: number) => `${Math.floor(s / 60).toString().padStart(2,'0')}:${Math.floor(s % 60).toString().padStart(2,'0')}`;
async function request(url: string, options?: RequestInit) {
  const response = await sessionFetch(url, options);
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : data.detail?.message || 'Check your input and try again.');
  return data;
}
export default function App({user, csrfToken, onLogout}: {user: NonNullable<Session['user']>; csrfToken: string; onLogout: () => void}) {
  const [theme, toggleTheme] = useTheme();
  const [url,setUrl] = useState('');
  const [language,setLanguage] = useState('en');
  const [job,setJob] = useState<Job|null>(null);
  const [jobId,setJobId] = useState<string|null>(null);
  const [error,setError] = useState('');
  const [submitting,setSubmitting] = useState(false);
  const [timestamps,setTimestamps] = useState(false);
  const [copied,setCopied] = useState(false);
  const [upload,setUpload] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const busy = submitting || (jobId !== null && (!job || ['queued','processing'].includes(job.status)));
  useEffect(() => {
    if (!jobId) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const next: Job = await request(`/transcripts/${jobId}`);
        if (!active) return;
        setJob(next);
        if (['queued','processing'].includes(next.status)) timer = setTimeout(poll, 1000);
      } catch (e) { if (active) { setError((e as Error).message); setJobId(null); } }
    };
    poll();
    return () => { active = false; clearTimeout(timer); };
  },[jobId]);
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setSubmitting(true); setError(''); setJob(null); setJobId(null); setCopied(false);
    try {
      let response;
      if (upload) {
        const file = fileRef.current?.files?.[0];
        if (!file) throw new Error('Select an audio or video file.');
        const body = new FormData(); body.append('file',file); body.append('language',language);
        response = await request('/uploads', {method:'POST', headers:{'X-CSRF-Token':csrfToken}, body});
      } else response = await request('/transcripts', {method:'POST', headers:{'Content-Type':'application/json', 'X-CSRF-Token':csrfToken}, body:JSON.stringify({url,language})});
      setJobId(response.id);
    } catch(e) { setError((e as Error).message); }
    finally { setSubmitting(false); }
  }
  const transcript = job?.transcript;
  const paragraphs: string[] = [];
  transcript?.segments.forEach((s,i) => { const group = Math.floor(i/6); paragraphs[group] = (paragraphs[group] || '') + (i%6 ? ' ' : '') + s.text.replace(/\s+/g,' ').trim(); });
  async function copy() {
    try { await navigator.clipboard.writeText(paragraphs.join('\n\n')); setCopied(true); }
    catch { setError('Clipboard access failed. Use Download TXT instead.'); }
  }
  function showSource(index: number) {
    setTimestamps(true);
    requestAnimationFrame(() => document.getElementById(`segment-${index}`)?.scrollIntoView({behavior:'smooth', block:'center'}));
  }
  return <div className="shell">
    <header className="app-bar"><a className="brand" href="/"><span className="brand-icon" aria-hidden="true">▤</span><span>Transcript Studio</span></a><span className="workspace-badge">Personal workspace</span><div className="header-actions"><span className="local">{user.name}</span><button onClick={onLogout}>Sign out</button><button className="theme-button" onClick={toggleTheme} aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`} title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}><span aria-hidden="true">{theme === 'dark' ? '☀' : '☾'}</span><span>{theme === 'dark' ? 'Light mode' : 'Dark mode'}</span></button></div></header>
    <div className="workspace-layout"><aside className="sidebar" aria-label="Workspace navigation"><div className="nav-label">WORKSPACE</div><a className="nav-item active" href="#workspace" aria-current="page"><span aria-hidden="true">▤</span> Transcripts</a><a className="nav-item" href="/docs" target="_blank" rel="noreferrer"><span aria-hidden="true">⌘</span> API documentation <span className="external" aria-hidden="true">↗</span></a><div className="sidebar-note"><span className="status-dot"/> Caption-first transcription<p>Read, copy and export.<br/>Your workflow, simplified.</p></div></aside>
    <main id="workspace"><div className="breadcrumb">Workspace <span>/</span> Transcripts</div><div className="intro"><div><h1>Transcripts</h1><p>Convert YouTube captions or your recordings into readable text.</p></div><span className="page-badge">Personal workspace</span></div>
    <section className="input-panel" aria-label="Create transcript"><div className="panel-heading"><h2>Create a transcript</h2><p>Select a source and choose the language of the spoken content.</p></div>
      <div className="tabs"><button aria-pressed={!upload} className={!upload?'selected':''} onClick={()=>setUpload(false)} disabled={busy}>YouTube link</button><button aria-pressed={upload} className={upload?'selected':''} onClick={()=>setUpload(true)} disabled={busy}>Upload a file</button></div>
      <form onSubmit={submit}><div className="fields"><label className="url-field">{upload?'Audio or video file':'Video URL'}{upload?<input ref={fileRef} type="file" accept="audio/*,video/*" required disabled={busy}/>:<input type="url" placeholder="https://www.youtube.com/watch?v=…" value={url} onChange={e=>setUrl(e.target.value)} required disabled={busy}/>}</label>
      <label>Language code<input list="languages" aria-label="Language code" value={language} onChange={e=>setLanguage(e.target.value)} required pattern="[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*" maxLength={35} disabled={busy}/><datalist id="languages"><option value="en">English</option><option value="hi">Hindi</option><option value="es">Spanish</option><option value="fr">French</option><option value="de">German</option><option value="pt-BR">Portuguese (Brazil)</option><option value="ja">Japanese</option></datalist></label>
      <button className="primary" disabled={busy}>{busy?'Working…':'Generate transcript'} <span>↗</span></button></div>
      <p className="hint">{upload?'Transcribed locally · Up to 60 minutes / 200 MB · First use downloads a model · Temporary audio deleted':'Manual captions first, automatic captions next. No captions? Upload the audio.'}</p></form>
    </section>
    <div aria-live="polite">{busy && <div className="notice"><span className="spinner"/>{job?.status==='processing'?'Retrieving your transcript…':'Your transcript is queued…'} {upload && 'Local transcription can take several minutes.'}</div>}{(error || job?.error) && <div role="alert" className="error">{error || job?.error?.message}{job?.error?.code==='captions_missing' && <p>Switch to Upload a file to transcribe audio you have.</p>}</div>}</div>
    {transcript ? <><section className="result"><div className="result-top"><div><span className="eyebrow"><span className="status-dot"/> COMPLETED</span><h2>Your transcript</h2><p>{{manual:'Manual captions',automatic:'Automatic captions',speech_to_text:'Local speech recognition'}[transcript.source] || transcript.source} · {transcript.language.toUpperCase()} · {transcript.segments.length} segments</p></div><div className="actions"><button onClick={copy}>{copied?'Copied ✓':'Copy text'}</button><a href={`/transcripts/${jobId}/export?format=txt`}>Download TXT ↓</a><a href={`/transcripts/${jobId}/export?format=srt`}>SRT ↓</a></div></div><label className="toggle"><input type="checkbox" checked={timestamps} onChange={e=>setTimestamps(e.target.checked)}/> Show timestamps</label><article>{timestamps?transcript.segments.map((s,i)=><p className="segment" id={`segment-${i}`} key={i}><time>{clock(s.start)}</time><span>{s.text}</span></p>):paragraphs.map((p,i)=><p key={i}>{p}</p>)}</article></section><InsightsPanel key={jobId} jobId={jobId!} onSource={showSource} csrfToken={csrfToken}/></>:!busy && <section className="empty"><div className="paper-icon" aria-hidden="true">▤</div><h2>No transcript yet</h2><p>Add a YouTube link or upload a recording to get started.<br/>Your transcript will appear here, ready to copy or download.</p><div className="features"><span>Timestamped segments</span><span>TXT and SRT exports</span><span>Local audio processing</span></div></section>}
    <footer><span>Transcript Studio</span><span>Caption-first · Local audio fallback</span></footer></main></div>
  </div>;
}
