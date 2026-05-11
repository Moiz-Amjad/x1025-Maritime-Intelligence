import { useRef } from 'react';
import type { UploadState } from './App';

interface Props {
  onSelect: (text: string) => void;
  onUpload: (file: File) => void;
  upload: UploadState | null;
  onDismissUpload: () => void;
}

const PROMPTS: string[] = [
  'What are the man-overboard procedures?',
  'How should I respond to a fire on deck?',
  'Steps for engine-room flooding',
  'Abandon-ship checklist',
  'Medical emergency at sea — first response',
  'Collision response protocol',
];

export default function Guardrails({ onSelect, onUpload, upload, onDismissUpload }: Props) {
  const fileRef = useRef<HTMLInputElement>(null);
  const isActive = !!upload && upload.status !== 'done' && upload.status !== 'error';

  function pickFile() {
    fileRef.current?.click();
  }

  function onFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) onUpload(file);
    e.target.value = ''; // allow re-selecting the same file later
  }

  return (
    <div className="flex flex-col h-full">
      <header className="px-5 py-5 border-b border-slate-200">
        <div className="flex items-center gap-2.5">
          <ShieldIcon />
          <h2 className="text-base font-semibold tracking-tight text-slate-900">Guardrails</h2>
        </div>
        <p className="text-[13px] text-slate-500 mt-1.5 leading-5">
          Add a manual or pick a vetted prompt to keep responses scoped to safety procedures.
        </p>
      </header>

      <div className="px-4 pt-4">
        <UploadPanel
          upload={upload}
          isActive={isActive}
          onPick={pickFile}
          onDismiss={onDismissUpload}
        />
        <input
          ref={fileRef}
          type="file"
          accept="application/pdf,.pdf"
          className="hidden"
          onChange={onFileChange}
        />
      </div>

      <div className="px-4 pt-3 pb-2">
        <div className="text-[11px] font-semibold tracking-wider uppercase text-slate-400 px-1">
          Suggested prompts
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-4 pb-4 flex flex-col gap-2 min-h-0">
        {PROMPTS.map((p) => (
          <button
            key={p}
            type="button"
            onClick={() => onSelect(p)}
            disabled={isActive}
            className="group w-full text-left text-[13.5px] leading-5 text-slate-700 bg-white hover:bg-slate-50 border border-slate-200 hover:border-slate-300 rounded-lg px-3.5 py-2.5 transition-colors flex items-start gap-2.5 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-white disabled:hover:border-slate-200"
          >
            <span className="mt-[3px] text-slate-400 group-hover:text-slate-600 transition-colors">
              <ArrowRightIcon />
            </span>
            <span className="flex-1">{p}</span>
          </button>
        ))}
      </div>

      <footer className="px-5 py-4 border-t border-slate-200 text-[11px] text-slate-400 leading-5">
        Prompts are inserted into the input box — review before sending.
      </footer>
    </div>
  );
}

function UploadPanel({
  upload,
  isActive,
  onPick,
  onDismiss,
}: {
  upload: UploadState | null;
  isActive: boolean;
  onPick: () => void;
  onDismiss: () => void;
}) {
  const done = upload?.status === 'done';
  const err = upload?.status === 'error';
  const completed = upload ? Math.max(0, Math.min(upload.step, upload.total)) : 0;
  const pct = upload ? Math.round((completed / upload.total) * 100) : 0;

  return (
    <div className="rounded-xl border border-slate-200 bg-white">
      <div className="px-3.5 py-3 flex items-center gap-2.5 border-b border-slate-100">
        <UploadIcon />
        <div className="flex-1">
          <div className="text-[13.5px] font-semibold tracking-tight text-slate-900">
            Add a manual
          </div>
          <div className="text-[11.5px] text-slate-500">PDF · ingested in 3 stages</div>
        </div>
      </div>

      <div className="px-3.5 py-3">
        <button
          type="button"
          onClick={onPick}
          disabled={isActive}
          className="w-full inline-flex items-center justify-center gap-2 bg-slate-900 hover:bg-slate-800 text-white text-[13px] font-medium rounded-lg px-3.5 py-2 transition-colors disabled:bg-slate-200 disabled:text-slate-500 disabled:cursor-not-allowed"
        >
          <UploadIconSmall />
          {isActive ? 'Processing…' : 'Upload PDF'}
        </button>

        {upload && (
          <div className="mt-3">
            <div className="flex items-center gap-2 text-[12px]">
              <span className="truncate font-medium text-slate-700 flex-1">{upload.file}</span>
              <span
                className={`tabular-nums text-[11.5px] font-medium ${
                  err ? 'text-rose-600' : done ? 'text-emerald-600' : 'text-slate-500'
                }`}
              >
                {err ? 'failed' : `${completed} / ${upload.total}`}
              </span>
            </div>
            <div className="mt-1.5 h-1.5 w-full rounded-full bg-slate-200 overflow-hidden">
              <div
                className={`h-full transition-all duration-300 ${
                  err ? 'bg-rose-400' : done ? 'bg-emerald-500' : 'bg-slate-900'
                }`}
                style={{ width: `${err ? 100 : pct}%` }}
              />
            </div>
            <div className="mt-2 text-[11.5px] text-slate-500 leading-4">
              {err ? upload.error || 'Upload failed' : upload.stepName}
            </div>
            {(done || err) && (
              <button
                type="button"
                onClick={onDismiss}
                className="mt-2 text-[11.5px] text-slate-500 hover:text-slate-700 underline underline-offset-2"
              >
                Dismiss
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function ShieldIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M12 3l8 3v6c0 4.5-3.5 8.3-8 9-4.5-.7-8-4.5-8-9V6l8-3z"
        stroke="#0f172a"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
      <path
        d="M9 12l2 2 4-4"
        stroke="#0f172a"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function ArrowRightIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M5 12h14M13 6l6 6-6 6"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function UploadIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M12 16V4M7 9l5-5 5 5M5 20h14"
        stroke="#0f172a"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function UploadIconSmall() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M12 16V4M7 9l5-5 5 5M5 20h14"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
