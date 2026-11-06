export type Session = { configured: boolean; user: {id: string; name: string} | null; csrf_token: string | null };
export async function sessionFetch(url: string, options?: RequestInit) {
  const response = await fetch(url, options);
  if (response.headers.get('X-Session-Expired') === '1') window.dispatchEvent(new Event('session-expired'));
  return response;
}
