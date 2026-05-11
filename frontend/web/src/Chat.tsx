import { useEffect, useRef, useState } from 'react';
import { chatStream, getManuals, switchManual } from './api';
import type { SelectManualSignal, UploadState } from './App';

interface Msg {
  role: 'user' | 'bot';
  text: string;
  error?: boolean;
}

// LLM occasionally violates the "no Markdown" system rule and emits ** or # despite the
// instruction. Strip those markers at render time so token-boundary splits don't matter.
function stripMd(s: string): string {
  return s.replace(/\*+/g, '').replace(/^#{1,6} +/gm, '');
}

type StatusKind = 'ok' | 'busy' | 'error';

interface Props {
  input: string;
  setInput: (v: string) => void;
  selectManual: SelectManualSignal | null;
  upload: UploadState | null;
}

export default function Chat({ input, setInput, selectManual, upload }: Props) {
  const [manuals, setManuals] = useState<string[]>([]);
  const [current, setCurrent] = useState<string>('');
  const [status, setStatus] = useState<string>('connecting…');
  const [statusKind, setStatusKind] = useState<StatusKind>('busy');
  const [messages, setMessages] = useState<Msg[]>([]);
  const [sending, setSending] = useState<boolean>(false);
  const [ready, setReady] = useState<boolean>(false);

  const logRef = useRef<HTMLDivElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);
  const lastSelectNonce = useRef<number>(-1);

  async function refreshManuals(): Promise<{ manuals: string[]; current: string } | null> {
    try {
      const data = await getManuals();
      setManuals(data.manuals);
      setCurrent(data.current);
      setReady(true);
      return data;
    } catch (e) {
      setStatus(`backend unreachable — is uvicorn running? (${(e as Error).message})`);
      setStatusKind('error');
      return null;
    }
  }

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const data = await refreshManuals();
      if (cancelled || !data) return;
      setStatus(`${data.manuals.length} manual(s) loaded · current: ${data.current}`);
      setStatusKind('ok');
      setTimeout(() => taRef.current?.focus(), 0);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [messages, upload?.step, upload?.status, upload?.stepName]);

  useEffect(() => {
    if (input && taRef.current) taRef.current.focus();
  }, [input]);

  // When App signals a new manual is ready, refresh and switch into it.
  useEffect(() => {
    if (!selectManual || selectManual.nonce === lastSelectNonce.current) return;
    lastSelectNonce.current = selectManual.nonce;
    (async () => {
      const data = await refreshManuals();
      if (!data) return;
      if (data.manuals.includes(selectManual.name)) {
        await handleSwitch(selectManual.name, /* fromUpload */ true);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectManual]);

  async function handleSwitch(name: string, fromUpload = false) {
    if (!name || (!fromUpload && name === current)) return;
    setStatus(`switching to ${name}…`);
    setStatusKind('busy');
    try {
      if (!fromUpload) {
        // /upload already switches server-side; only call /switch for user-driven changes.
        await switchManual(name);
      }
      setCurrent(name);
      setMessages([]);
      setStatus(`current: ${name}`);
      setStatusKind('ok');
    } catch (e) {
      setStatus(`switch failed: ${(e as Error).message}`);
      setStatusKind('error');
    }
  }

  async function handleSend() {
    const query = input.trim();
    if (!query || sending || !ready) return;
    setInput('');
    setSending(true);
    setMessages((m) => [...m, { role: 'user', text: query }, { role: 'bot', text: '' }]);
    setStatus('retrieving + reranking…');
    setStatusKind('busy');

    let botText = '';
    try {
      for await (const ev of chatStream(query)) {
        if (ev.phase === 'retrieved') {
          setStatus(`retrieved ${ev.count} chunks · generating…`);
          continue;
        }
        if (ev.token) {
          botText += ev.token;
          setMessages((m) => {
            const next = m.slice();
            next[next.length - 1] = { role: 'bot', text: botText };
            return next;
          });
        }
        if (ev.error) {
          setMessages((m) => {
            const next = m.slice();
            next[next.length - 1] = { role: 'bot', text: `error: ${ev.error}`, error: true };
            return next;
          });
          setStatus('error');
          setStatusKind('error');
        }
        if (ev.done) break;
      }
      setStatus(`current: ${current}`);
      setStatusKind('ok');
    } catch (e) {
      setMessages((m) => {
        const next = m.slice();
        next[next.length - 1] = { role: 'bot', text: `error: ${(e as Error).message}`, error: true };
        return next;
      });
      setStatus(`error: ${(e as Error).message}`);
      setStatusKind('error');
    } finally {
      setSending(false);
      taRef.current?.focus();
    }
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  const dotColor =
    statusKind === 'ok'
      ? 'bg-emerald-500'
      : statusKind === 'error'
        ? 'bg-rose-500'
        : 'bg-amber-500 animate-pulse';

  const isUploading = !!upload && upload.status !== 'done' && upload.status !== 'error';
  const showEmptyState = messages.length === 0 && !upload;

  return (
    <div className="flex flex-col h-full">
      <header className="px-6 py-5 border-b border-slate-200">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div>
            <h2 className="text-lg font-semibold tracking-tight text-slate-900">
              Crew Emergency Chat
            </h2>
            <p className="text-[13px] text-slate-500 mt-0.5">
              Ask emergency-response questions grounded in your selected manual.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <label htmlFor="manual" className="text-xs font-medium text-slate-500 uppercase tracking-wide">
              Manual
            </label>
            <select
              id="manual"
              className="bg-white text-slate-800 border border-slate-200 hover:border-slate-300 rounded-lg px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900/10 focus:border-slate-400 disabled:opacity-50 disabled:cursor-not-allowed"
              value={current}
              disabled={!ready || sending || isUploading}
              onChange={(e) => handleSwitch(e.target.value)}
            >
              {manuals.length === 0 && <option value="">—</option>}
              {manuals.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="mt-3 flex items-center gap-2 text-xs text-slate-500">
          <span className={`inline-block w-1.5 h-1.5 rounded-full ${dotColor}`}></span>
          <span>{status}</span>
        </div>
      </header>

      <div ref={logRef} className="flex-1 overflow-y-auto px-6 py-5 flex flex-col gap-3 min-h-0">
        {showEmptyState && (
          <div className="flex-1 flex items-center justify-center text-center text-slate-400 text-sm">
            <div>
              <p className="font-medium text-slate-600">No messages yet</p>
              <p className="mt-1">Ask a question, upload a manual, or pick a prompt →</p>
            </div>
          </div>
        )}

        {upload && <UploadCard upload={upload} />}

        {messages.map((m, i) => {
          const base =
            'px-4 py-3 rounded-2xl max-w-[82%] whitespace-pre-wrap leading-6 text-[14.5px] break-words';
          const role =
            m.role === 'user'
              ? 'self-end bg-slate-900 text-white shadow-sm'
              : 'self-start bg-slate-100 text-slate-800 border border-slate-200/60';
          const err = m.error ? ' border-rose-300 text-rose-600 bg-rose-50' : '';
          const empty = m.role === 'bot' && !m.text;
          return (
            <div key={i} className={`${base} ${role}${err}`}>
              {empty ? (
                <span className="italic text-slate-400">thinking…</span>
              ) : m.role === 'bot' && !m.error ? (
                stripMd(m.text)
              ) : (
                m.text
              )}
            </div>
          );
        })}
      </div>

      <div className="px-6 py-4 border-t border-slate-200 bg-slate-50/40">
        <div className="flex gap-2 items-end">
          <textarea
            ref={taRef}
            className="flex-1 bg-white text-slate-900 placeholder-slate-400 border border-slate-200 rounded-xl px-3.5 py-2.5 resize-none text-sm leading-snug focus:outline-none focus:ring-2 focus:ring-slate-900/10 focus:border-slate-400 disabled:opacity-60 disabled:cursor-not-allowed"
            rows={2}
            placeholder={
              isUploading
                ? 'Processing upload — chat will resume shortly…'
                : 'Ask a question… (Enter to send, Shift+Enter for newline)'
            }
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            disabled={!ready || sending || isUploading}
          />
          <button
            className="bg-slate-900 hover:bg-slate-800 text-white rounded-xl px-5 h-11 font-medium text-sm transition-colors disabled:bg-slate-200 disabled:text-slate-400 disabled:cursor-not-allowed inline-flex items-center gap-2"
            onClick={handleSend}
            disabled={!ready || sending || isUploading || !input.trim()}
          >
            <span>Send</span>
            <SendIcon />
          </button>
        </div>
      </div>
    </div>
  );
}

function UploadCard({ upload }: { upload: UploadState }) {
  const done = upload.status === 'done';
  const err = upload.status === 'error';
  // Visible progress is the count of fully-completed steps; clamp to [0, total].
  const completed = Math.max(0, Math.min(upload.step, upload.total));
  const pct = Math.round((completed / upload.total) * 100);

  return (
    <div
      className={`self-stretch w-full rounded-xl border px-4 py-3.5 text-[13.5px] ${
        err
          ? 'bg-rose-50 border-rose-200 text-rose-700'
          : done
            ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
            : 'bg-slate-50 border-slate-200 text-slate-700'
      }`}
    >
      <div className="flex items-center gap-2 mb-2">
        <DocIcon />
        <span className="font-semibold tracking-tight truncate">{upload.file}</span>
        <span className="ml-auto text-xs font-medium tabular-nums">
          {err ? 'failed' : `${completed} / ${upload.total}`}
        </span>
      </div>
      <div className="text-[12.5px] mb-2">
        {err ? upload.error || 'Upload failed' : upload.stepName}
      </div>
      <div className="h-1.5 w-full rounded-full bg-slate-200 overflow-hidden">
        <div
          className={`h-full transition-all duration-300 ${
            err ? 'bg-rose-400' : done ? 'bg-emerald-500' : 'bg-slate-900'
          }`}
          style={{ width: `${err ? 100 : pct}%` }}
        />
      </div>
    </div>
  );
}

function SendIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M4 12l16-8-6 16-3-7-7-1z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function DocIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M7 3h7l5 5v13a1 1 0 01-1 1H7a1 1 0 01-1-1V4a1 1 0 011-1z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
      <path d="M14 3v5h5" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
    </svg>
  );
}
