/** The session id outlives the tab, which is what makes a refresh continue a conversation
 *  rather than start one. The server keys its transcript on exactly this string.
 *
 *  The name is cached beside it only so the header is not blank for the first second after a
 *  reload -- the server remains the source of truth and overwrites it on the next turn. */
const KEYS = { session: "tokokita.session", name: "tokokita.name" };

export function sessionId(): string {
  const stored = localStorage.getItem(KEYS.session);
  if (stored) return stored;
  const fresh = "web-" + Math.random().toString(36).slice(2, 10);
  localStorage.setItem(KEYS.session, fresh);
  return fresh;
}

export const recallName = () => localStorage.getItem(KEYS.name);

export function rememberName(name: string | null): void {
  if (name) localStorage.setItem(KEYS.name, name);
  else localStorage.removeItem(KEYS.name);
}

/** Switching to a stored conversation makes it the one a refresh will reopen. */
export function adoptSession(id: string): void {
  localStorage.setItem(KEYS.session, id);
  localStorage.removeItem(KEYS.name);
}

export function clearSession(): void {
  localStorage.removeItem(KEYS.session);
  localStorage.removeItem(KEYS.name);
}
