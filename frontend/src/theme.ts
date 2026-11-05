import { useEffect, useState } from 'react';

type Theme = 'dark' | 'light';
const key = 'transcript-studio-theme';

export function readTheme(): Theme {
  try { return localStorage.getItem(key) === 'light' ? 'light' : 'dark'; }
  catch { return 'dark'; }
}

export function applyTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;
}

export function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(readTheme);
  useEffect(() => {
    applyTheme(theme);
    try { localStorage.setItem(key, theme); } catch { /* Storage may be disabled. */ }
  }, [theme]);
  return [theme, () => setTheme(current => current === 'dark' ? 'light' : 'dark')];
}
