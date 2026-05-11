// All requests go through Vite's dev proxy (/api -> http://localhost:8001).
// In production, serve the built dist/ behind any reverse proxy that maps /api
// to the FastAPI server.
const API = '/api';

export interface ManualsResponse {
  manuals: string[];
  current: string;
}

export async function getManuals(): Promise<ManualsResponse> {
  const r = await fetch(`${API}/manuals`);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

export async function switchManual(name: string): Promise<void> {
  const r = await fetch(`${API}/switch`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
}

export interface ChatEvent {
  phase?: 'retrieved';
  count?: number;
  token?: string;
  done?: boolean;
  error?: string;
}

async function* sseEvents<T>(res: Response): AsyncGenerator<T> {
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  if (!res.body) throw new Error('no response body');

  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const events = buf.split('\n\n');
    buf = events.pop() ?? '';
    for (const ev of events) {
      const line = ev.split('\n').find((l) => l.startsWith('data: '));
      if (!line) continue;
      try {
        yield JSON.parse(line.slice(6)) as T;
      } catch {
        // skip malformed event
      }
    }
  }
}

export async function* chatStream(query: string): AsyncGenerator<ChatEvent> {
  const r = await fetch(`${API}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query }),
  });
  yield* sseEvents<ChatEvent>(r);
}

export interface UploadEvent {
  step?: number;
  total?: number;
  name?: string;
  phase?: 'start' | 'done';
  done?: boolean;
  manual?: string;
  error?: string;
}

export async function* uploadPdf(file: File): AsyncGenerator<UploadEvent> {
  const form = new FormData();
  form.append('file', file);
  const r = await fetch(`${API}/upload`, { method: 'POST', body: form });
  yield* sseEvents<UploadEvent>(r);
}
