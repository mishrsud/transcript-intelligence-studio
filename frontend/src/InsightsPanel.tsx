import { sessionFetch } from './session';
import React, { useEffect, useRef, useState } from 'react';

type Provider = 'openai' | 'anthropic' | 'openrouter' | 'compatible';
type Citation = { segment_index: number; start: number };
type Insights = {
  summary: string;
  key_insights: (Citation & { text: string })[];
  action_items: (Citation & { action: string; owner: string | null; due_date: string | null })[];
  provider: Provider;
  model: string;
};
const providers: Record<Provider, {name: string; model: string; destination: string}> = {
  openai: {name:'OpenAI', model:'gpt-4.1-mini', destination:'api.openai.com'},
  anthropic: {name:'Anthropic', model:'claude-haiku-4-5', destination:'api.anthropic.com'},
  openrouter: {name:'OpenRouter', model:'openai/gpt-4.1-mini', destination:'openrouter.ai'},
  compatible: {name:'OpenAI-compatible', model:'', destination:'your custom endpoint'},
};
const time = (seconds: number) => `${Math.floor(seconds / 60).toString().padStart(2,'0')}:${Math.floor(seconds % 60).toString().padStart(2,'0')}`;

export default function InsightsPanel({jobId, onSource, csrfToken = ''}: {csrfToken?: string; jobId: string; onSource: (index: number) => void}) {
  const [provider, setProvider] = useState<Provider>('openai');
  const [model, setModel] = useState(providers.openai.model);
  const [baseUrl, setBaseUrl] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [result, setResult] = useState<Insights | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState(false);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  let destination = providers[provider].destination;
  if (provider === 'compatible') {
    try { destination = new URL(baseUrl).host; } catch { /* Show generic destination until valid. */ }
  }
  function changeProvider(next: Provider) {
    setProvider(next); setModel(providers[next].model); setApiKey(''); setError('');
  }
  async function generate(e: React.FormEvent) {
    e.preventDefault();
    if (!apiKey.trim() || !model.trim() || busy) return;
    setError(''); setResult(null); setCopied(false); setBusy(true);
    const key = apiKey.trim();
    setApiKey('');
    const abort = new AbortController();
    controller.current = abort;
    let timedOut = false;
    const timer = setTimeout(() => { timedOut = true; abort.abort(); }, 120000);
    try {
      const response = await sessionFetch(`/transcripts/${encodeURIComponent(jobId)}/insights`, {
        method:'POST', headers:{'Content-Type':'application/json', 'X-AI-API-Key':key, 'X-CSRF-Token':csrfToken},
        body:JSON.stringify({provider,model:model.trim(), ...(provider === 'compatible' ? {base_url:baseUrl.trim()} : {})}), signal:abort.signal,
      });
      const data = await response.json();
      if (!response.ok) {
        setError(typeof data.detail === 'string' ? data.detail : data.detail?.message || 'Could not generate insights. Check the provider settings and try again.');
        return;
      }
      if (!abort.signal.aborted) setResult(data);
    } catch {
      if (timedOut) setError('The request timed out. The provider may still finish and charge for it; check usage before retrying.');
      else if (!abort.signal.aborted) setError('Could not reach the summary service. Check the connection and try again.');
    } finally {
      clearTimeout(timer);
      if (!abort.signal.aborted || timedOut) setBusy(false);
    }
  }
  async function copy() {
    if (!result) return;
    const lines = [result.summary, '', 'Key insights', ...result.key_insights.map(i=>`- ${i.text} [${time(i.start)}]`), '', 'Action items', ...result.action_items.map(i=>`- ${i.action}${i.owner ? ` — Owner: ${i.owner}` : ''}${i.due_date ? ` — Due: ${i.due_date}` : ''} [${time(i.start)}]`)];
    if (!result.action_items.length) lines.push('No explicit action items found.');
    try { await navigator.clipboard.writeText(lines.join('\n')); setCopied(true); }
    catch { setError('Clipboard access failed. Select and copy the insight text instead.'); }
  }
  const source = (item: Citation) => <button className="source-link" type="button" aria-label={`Go to transcript at ${time(item.start)}`} onClick={()=>onSource(item.segment_index)}>{time(item.start)} ↗</button>;
  return <section className="insights-panel" aria-label="AI insights">
    <div className="panel-heading insights-heading"><div><span className="eyebrow">OPTIONAL · BRING YOUR OWN KEY</span><h2>AI insights &amp; action items</h2><p>Turn this transcript into takeaways and clear next steps, with source timestamps.</p></div><span className="ai-symbol" aria-hidden="true">✦</span></div>
    <form onSubmit={generate}>
      <div className="ai-settings"><label>AI provider<select value={provider} onChange={e=>changeProvider(e.target.value as Provider)} disabled={busy}>{Object.entries(providers).map(([value,p])=><option key={value} value={value}>{p.name}</option>)}</select></label><label>Model ID<input value={model} onChange={e=>setModel(e.target.value)} placeholder="Your provider's model ID" required maxLength={200} disabled={busy}/></label></div>
      {provider === 'compatible' && <label className="endpoint-field">API base URL<input type="url" aria-label="API base URL" aria-describedby="endpoint-help" placeholder="https://api.example.com/v1" value={baseUrl} onChange={e=>{setBaseUrl(e.target.value);setApiKey('');}} required disabled={busy}/><span id="endpoint-help" className="field-help">Public HTTPS endpoint supporting Chat Completions and JSON mode. Include the version path; omit /chat/completions.</span></label>}
      <div className="ai-key-row"><label>API key<input type="password" name="ai-api-key" autoComplete="off" spellCheck={false} value={apiKey} onChange={e=>setApiKey(e.target.value)} placeholder={`Enter your ${providers[provider].name} API key`} maxLength={4096} disabled={busy} required/></label><button className="primary" disabled={busy || !apiKey.trim() || !model.trim() || (provider === 'compatible' && !baseUrl.trim())}>{busy?'Generating insights…':'Generate insights'}</button></div>
      <p className="ai-disclosure">Generate sends this transcript through the app server to <strong>{destination}</strong>. Provider API charges and data policies apply. Your key is used for this request only, cleared from this form, and never saved by the app. Insights are not saved after leaving this transcript.</p>
    </form>
    <div aria-live="polite">{busy && <div className="notice"><span className="spinner"/>Extracting insights and action items… This can take up to two minutes.</div>}{error && <div className="error" role="alert">{error}</div>}</div>
    {result && <div className="insights-output"><div className="insights-result-heading"><div><span className="eyebrow">AI GENERATED · REVIEW AGAINST THE SOURCE</span><p>{providers[result.provider].name} · {result.model}</p></div><div className="actions"><button type="button" onClick={copy}>{copied?'Copied ✓':'Copy insights'}</button></div></div><h3>Summary</h3><p className="summary-text">{result.summary}</p><div className="insights-columns"><div><h3>Key insights <span>{result.key_insights.length}</span></h3>{result.key_insights.length ? <ul>{result.key_insights.map((item,i)=><li key={i}><p>{item.text}</p>{source(item)}</li>)}</ul>:<p className="field-help">No key insights were identified.</p>}</div><div><h3>Action items <span>{result.action_items.length}</span></h3>{result.action_items.length ? <ol>{result.action_items.map((item,i)=><li key={i}><p>{item.action}</p><div className="action-meta"><span>Owner: {item.owner || 'Not stated'}</span><span>Due: {item.due_date || 'Not stated'}</span></div>{source(item)}</li>)}</ol>:<p className="field-help">No explicit action items were found in this transcript.</p>}</div></div></div>}
  </section>;
}
