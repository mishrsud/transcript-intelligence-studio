import React, { useEffect, useState } from 'react';
import App from './App';
import { Session, sessionFetch } from './session';
import { useTheme } from './theme';

export default function AuthGate() {
  const [session, setSession] = useState<Session | null>(null);
  const [error, setError] = useState('');
  const [theme, toggleTheme] = useTheme();
  useEffect(() => {
    let active = true;
    const refresh = async () => {
      try {
        const response = await fetch('/auth/session', {cache:'no-store'});
        if (!response.ok) throw new Error();
        const data: Session = await response.json();
        if (active) { setSession(data); setError(''); }
      } catch { if (active) setError('Could not check your session. Refresh to try again.'); }
    };
    const expired = () => { setSession(previous => previous ? {...previous, user:null, csrf_token:null} : null); };
    window.addEventListener('session-expired', expired);
    window.addEventListener('focus', refresh);
    refresh();
    return () => { active = false; window.removeEventListener('session-expired', expired); window.removeEventListener('focus', refresh); };
  }, []);
  async function logout() {
    try {
      const response = await sessionFetch('/auth/logout', {method:'POST', headers:{'X-CSRF-Token':session?.csrf_token || ''}});
      if (!response.ok) throw new Error();
      const data = await response.json();
      setSession(previous => previous ? {...previous,user:null,csrf_token:null} : null);
      window.location.assign(data.url);
    } catch { setError('Could not sign out. Refresh and try again.'); }
  }
  if (session?.user) return <>{error && <div role="alert" className="error">{error}</div>}<App key={session.user.id} user={session.user} csrfToken={session.csrf_token!} onLogout={logout}/></>;
  const loginFailed = new URLSearchParams(window.location.search).has('auth_error');
  return <div className="auth-shell"><header className="app-bar"><a className="brand" href="/">▤ Transcript Studio</a><button onClick={toggleTheme}>Switch to {theme === 'dark' ? 'light' : 'dark'} mode</button></header><main className="auth-main"><section className="input-panel auth-card"><span className="eyebrow">YOUR PRIVATE WORKSPACE</span><h1>Words into understanding.</h1><p>Capture transcripts, find key insights and turn ideas into action.</p>{error ? <p role="alert" className="error">{error}</p> : !session ? <p role="status">Checking your session…</p> : !session.configured ? <div role="alert" className="notice">Kinde setup is required. Add your client secret to the local .env file and follow the authentication instructions in README, then restart the app.</div> : <>{loginFailed && <p role="alert" className="error">Sign-in could not be completed. Try again; if it persists, check your Kinde configuration.</p>}<a className="sign-in" href="/auth/login">Sign in with Kinde →</a><p className="hint">Your transcripts are private to your account. Sign in to create transcripts and generate AI insights.</p></>}</section></main></div>;
}
