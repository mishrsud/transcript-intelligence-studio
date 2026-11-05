import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';

type Segment = { text: string; start: number; duration: number };
type Job = { id: string; status: 'queued'|'processing'|'completed'|'failed'; error?: {code: string; message: string}; transcript?: { video_id: string; language: string; source: string; retrieved_at: string; segments: Segment[] } };
const clock = (s: number) => `${Math.floor(s / 60).toString().padStart(2,'0')}:${Math.floor(s % 60).toString().padStart(2,'0')}`;
async function request(url: string, options?: RequestInit) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : data.detail?.message || 'Check your input and try again.');
  return data;
}
function App() {
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
        response = await request('/uploads', {method:'POST', body});
      } else response = await request('/transcripts', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({url,language})});
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
  return <div className="shell">
    <header><a className="brand" href="/">≋ <span>Transcript Studio</span></a><span className="local"><i/> ON YOUR MAC</span></header>
    <main><div className="intro"><span className="eyebrow">LESS REWINDING. MORE READING.</span><h1>Turn watching<br/>into <em>understanding.</em></h1><p>A clear, readable transcript from your next YouTube video.<br/>Keep the words. Find your own pace.</p></div>
    <section className="input-panel" aria-label="Create transcript">
      <div className="tabs"><button className={!upload?'selected':''} onClick={()=>setUpload(false)} disabled={busy}>YouTube link</button><button className={upload?'selected':''} onClick={()=>setUpload(true)} disabled={busy}>Upload a file</button></div>
      <form onSubmit={submit}><div className="fields"><label className="url-field">{upload?'Audio or video file':'Video URL'}{upload?<input ref={fileRef} type="file" accept="audio/*,video/*" required disabled={busy}/>:<input type="url" placeholder="https://www.youtube.com/watch?v=…" value={url} onChange={e=>setUrl(e.target.value)} required disabled={busy}/>}</label>
      <label>Language code<input list="languages" aria-label="Language code" value={language} onChange={e=>setLanguage(e.target.value)} required pattern="[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*" maxLength={35} disabled={busy}/><datalist id="languages"><option value="en">English</option><option value="hi">Hindi</option><option value="es">Spanish</option><option value="fr">French</option><option value="de">German</option><option value="pt-BR">Portuguese (Brazil)</option><option value="ja">Japanese</option></datalist></label>
      <button className="primary" disabled={busy}>{busy?'Working…':'Generate transcript'} <span>↗</span></button></div>
      <p className="hint">{upload?'Transcribed locally · Up to 60 minutes / 200 MB · First use downloads a model · Temporary audio deleted':'Manual captions first, automatic captions next. No captions? Upload the audio.'}</p></form>
    </section>
    <div aria-live="polite">{busy && <div className="notice"><span className="spinner"/>{job?.status==='processing'?'Retrieving your transcript…':'Your transcript is queued…'} {upload && 'Local transcription can take several minutes.'}</div>}{(error || job?.error) && <div role="alert" className="error">{error || job?.error?.message}{job?.error?.code==='captions_missing' && <p>Switch to Upload a file to transcribe audio you have.</p>}</div>}</div>
    {transcript ? <section className="result"><div className="result-top"><div><span className="eyebrow">READY TO READ</span><h2>Your transcript</h2><p>{{manual:'Manual captions',automatic:'Automatic captions',speech_to_text:'Local speech recognition'}[transcript.source] || transcript.source} · {transcript.language.toUpperCase()} · {transcript.segments.length} segments</p></div><div className="actions"><button onClick={copy}>{copied?'Copied ✓':'Copy text'}</button><a href={`/transcripts/${jobId}/export?format=txt`}>Download TXT ↓</a><a href={`/transcripts/${jobId}/export?format=srt`}>SRT ↓</a></div></div><label className="toggle"><input type="checkbox" checked={timestamps} onChange={e=>setTimestamps(e.target.checked)}/> Show timestamps</label><article>{timestamps?transcript.segments.map((s,i)=><p className="segment" key={i}><time>{clock(s.start)}</time><span>{s.text}</span></p>):paragraphs.map((p,i)=><p key={i}>{p}</p>)}</article></section>:!busy && <section className="empty"><div className="paper-icon">≡</div><h2>A little less play. A little more clarity.</h2><p>Your transcript will appear here, ready to read, copy, or download.</p><div className="features"><span>01 &nbsp; Paste a link</span><span>02 &nbsp; Choose a language</span><span>03 &nbsp; Make it yours</span></div></section>}
    </main><footer><span>Words worth keeping.</span><span>Caption-first · Local audio fallback</span></footer>
  </div>;
}
createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);
