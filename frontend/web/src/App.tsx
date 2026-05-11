import { useState } from 'react';
import Chat from './Chat';
import Guardrails from './Guardrails';
import { uploadPdf } from './api';

export interface UploadState {
  file: string;
  step: number;        // 0..3 — 0 = uploading, 1..3 = step in progress / done
  total: number;       // always 3
  stepName: string;    // human label
  status: 'uploading' | 'running' | 'done' | 'error';
  error?: string;
}

export interface SelectManualSignal {
  name: string;
  nonce: number;       // bump to retrigger even if name unchanged
}

export default function App() {
  const [input, setInput] = useState<string>('');
  const [upload, setUpload] = useState<UploadState | null>(null);
  const [selectManual, setSelectManual] = useState<SelectManualSignal | null>(null);

  async function handleUpload(file: File) {
    if (upload && upload.status !== 'done' && upload.status !== 'error') return;

    setUpload({
      file: file.name,
      step: 0,
      total: 3,
      stepName: 'Uploading file…',
      status: 'uploading',
    });

    try {
      for await (const ev of uploadPdf(file)) {
        if (ev.error) {
          setUpload((prev) =>
            prev
              ? { ...prev, status: 'error', error: ev.error, stepName: ev.name ?? prev.stepName }
              : prev,
          );
          return;
        }
        if (ev.done && ev.manual) {
          setUpload((prev) =>
            prev
              ? { ...prev, step: 3, status: 'done', stepName: `Ready · ${ev.manual}` }
              : prev,
          );
          setSelectManual({ name: ev.manual, nonce: Date.now() });
          return;
        }
        if (typeof ev.step === 'number' && ev.name) {
          // step.phase=start -> show step as "in progress"; phase=done -> advance
          setUpload((prev) =>
            prev
              ? {
                  ...prev,
                  step: ev.phase === 'done' ? ev.step! : ev.step! - 1,
                  total: ev.total ?? 3,
                  stepName: ev.name!,
                  status: 'running',
                }
              : prev,
          );
        }
      }
    } catch (e) {
      setUpload((prev) =>
        prev ? { ...prev, status: 'error', error: (e as Error).message } : prev,
      );
    }
  }

  function dismissUpload() {
    setUpload(null);
  }

  return (
    <div className="min-h-screen flex flex-col bg-slate-50">
      <header className="h-14 bg-white border-b border-slate-200 px-6 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <WaveLogo />
          <span className="text-[15px] font-semibold tracking-tight text-slate-900">
            x1025 Maritime Intelligence
          </span>
        </div>
        <button
          type="button"
          className="text-sm font-medium text-slate-700 hover:text-slate-900 border border-slate-200 hover:border-slate-300 rounded-lg px-3.5 py-1.5 transition-colors"
        >
          Dashboard
        </button>
      </header>

      <main className="flex-1 w-full max-w-7xl mx-auto px-6 py-6">
        <div className="grid gap-6 lg:grid-cols-[1fr_340px] lg:h-[calc(100vh-3.5rem-3rem)]">
          <section className="bg-white border border-slate-200 shadow-card rounded-card overflow-hidden flex flex-col min-h-0">
            <Chat input={input} setInput={setInput} selectManual={selectManual} upload={upload} />
          </section>

          <aside className="bg-white border border-slate-200 shadow-card rounded-card overflow-hidden flex flex-col min-h-0">
            <Guardrails
              onSelect={setInput}
              onUpload={handleUpload}
              upload={upload}
              onDismissUpload={dismissUpload}
            />
          </aside>
        </div>
      </main>
    </div>
  );
}

function WaveLogo() {
  return (
    <svg
      width="28"
      height="28"
      viewBox="0 0 28 28"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <rect width="28" height="28" rx="7" fill="#0f172a" />
      <path
        d="M5 17c2-2 3.5-2 5.5 0s3.5 2 5.5 0 3.5-2 5.5 0M5 12c2-2 3.5-2 5.5 0s3.5 2 5.5 0 3.5-2 5.5 0"
        stroke="#60a5fa"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
