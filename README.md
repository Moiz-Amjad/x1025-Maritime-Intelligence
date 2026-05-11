# x1025-Maritime-Intelligence

**Autonomous Maritime Intelligence — multi-layer agent system over self-hosted models.**

This repository is the production home for the x1025 maritime AI stack. It builds on the Layer 1 RAG prototype (originally `x1025-maritime-rag`) and extends it with: a router/specialist agent system, a dynamic-data pipeline, IoT integration, and a SaaS frontend.

The Layer 1 RAG pipeline is **production-grade**: it ingests, searches, and reasons over highly technical maritime engineering manuals (e.g. the *N.S. SAVANNAH Safety Analysis Report*) and returns 100% grounded answers without hallucinating — a critical requirement under the ISM Code.

A FastAPI server (`backend/api/server.py`) exposes the warm-loaded `SafetyAgent` over HTTP, and a React/Vite web frontend (`frontend/web/`) wraps it in a light-themed chat interface with a `Guardrails` sidebar of vetted prompts and a built-in three-stage **upload pipeline** that lets crews drop in a new PDF, watch the docling → vision → LanceDB ingestion progress live, and have the agent switch onto the freshly-indexed manual the moment it's ready.

## Repository layout

```
x1025-Maritime-Intelligence/
├── agents/
│   └── safety_agent.py           # Layer 1 — Procedural/ISM specialist (RAG)
│
├── backend/
│   ├── api/
│   │   └── server.py             # FastAPI: /chat (SSE), /manuals, /switch, /upload (3-stage SSE)
│   ├── ingestion/
│   │   ├── docling_parser.py     # PDF → Markdown via Docling
│   │   └── vision_captioner.py   # InternVL2.5-38B-AWQ image-to-text
│   ├── storage/
│   │   └── lancedb_client.py     # NV-Embed-v2 + macro-chunker + LanceDB hybrid search
│   └── stream/                   # (empty — dynamic-data ingestion to come)
│
├── frontend/
│   ├── chat_interface/
│   │   └── cli.py                # Interim Python REPL — warm-loads SafetyAgent, supports `switch`
│   └── web/                      # React/Vite chat UI (light theme, Guardrails sidebar, upload pipeline)
│
├── data/                         # Raw PDFs + ingestion outputs (gitignored)
│
├── .env.example                  # HF_HOME / HF_TOKEN / OPENAI_* template
├── .gitignore
├── LICENSE
├── README.md
├── requirements.txt              # Top-level deps (use environment.yml for exact lock)
└── environment.yml               # Conda lockfile (canonical)
```

### What's implemented today (Layer 1)

The four files marked ✅ above form a complete, runnable RAG pipeline:

* **`backend/ingestion/docling_parser.py`** — converts a PDF to `manual.md` + `images/` + `image_manifest.json`. Uses Docling with native-text extraction (no OCR), table-structure parsing, and a heavy navigation/header-noise scrubber for marine-manual artifacts (e.g. `PREVIOUS PAGE`, page numbers, revision stamps). Replaces inline image refs with `<!-- IMAGE_PLACEHOLDER -->` blocks for the captioner to fill.
* **`backend/ingestion/vision_captioner.py`** — walks the manifest, runs **InternVL2.5-38B-AWQ** (via `lmdeploy` Turbomind, tp=1, 8K context) over each non-trivial image with a marine-engineering-specific prompt, detects refusal/empty outputs, sanitizes embedded HTML-comment markers, and writes descriptions back into both the manifest and the markdown placeholders. Skips images <5 KB as decorative.
* **`backend/storage/lancedb_client.py`** — owns the shared **NV-Embed-v2** embedder, the macro-chunker (1000-word cap, 5-line overlap, header-aware sectioning, image-chunk type), the `_SCHEMA` (text + 4096-d vector + section + chunk_type + image fields), the FTS index, and `hybrid_search()` (cosine + BM25 fused via `RRFReranker`). Patches the upstream `modeling_nvembed.py` on first load to fix two transformers incompatibilities (rotary embeddings not threaded through gradient checkpointing; KV-cache tensor handling). Used by both the ingestion write path and the agent read path.
* **`agents/safety_agent.py`** — the `SafetyAgent` lifecycle wrapper. Loads the embedder + **Qwen3-Reranker-0.6B** in the parent process, spawns the **Qwen3.6-35B-A3B Q6_K** (`llama.cpp`) generator in a `multiprocessing.spawn` child pinned to one MIG slice via `CUDA_VISIBLE_DEVICES`, exposes `retrieve()` / `generate()` / `query()` / `switch_table()` / `close()`. Also provides a `--retrieve-only` CLI for inspecting reranked chunks without spinning up the LLM.
* **`frontend/chat_interface/cli.py`** — interim REPL. Lists `data/lancedb/*.lance`, prompts the user to pick one, warm-loads `SafetyAgent` once, and supports a `switch` command that swaps the table without reloading any model.
* **`backend/api/server.py`** — FastAPI server that warm-loads `SafetyAgent` once at startup (~3 min) and exposes four endpoints: `GET /manuals`, `POST /switch`, `POST /chat` (SSE token stream), and `POST /upload` (multipart PDF + SSE three-step progress). The `/upload` endpoint orchestrates the full ingestion pipeline — docling → vision → LanceDB — runs each step inside `loop.run_in_executor`, serializes the embedding step against the chat lock to prevent NV-Embed-v2 contention, and switches the live agent onto the newly-indexed manual on completion. Reuses the agent's NV-Embed-v2 embedder during ingest so the embedder is never double-loaded.
* **`frontend/web/`** — React/Vite light-themed chat UI (Inter font, navy + slate palette, soft-shadow white cards). Streams tokens from `/chat`, swaps manuals via `/switch`, drives the three-stage ingestion via `/upload` with a live `X / 3` progress card rendered both in the Guardrails sidebar and in the chat log. The Guardrails sidebar holds the upload affordance plus a list of vetted maritime-safety prompts that prefill the chat input. Markdown bleed-through from the LLM (occasional `**` and `#` despite the no-Markdown system rule) is stripped at render time.

## Layer 1 — Key architectural innovations (RAG pipeline)

* **Macro-Chunking:** Instead of naive line-splitting, we group text under shared Markdown headers up to a strict 1000-word limit, with a 5-line overlap on splits. This keeps large tables ingested as single, cohesive units, preventing fragmentation of rows from their column headers.
* **Vision-Language Processing:** We bypass faulty OCR and extract pristine native text via Docling. For diagrams, **InternVL2.5-38B-AWQ** translates imagery into highly accurate text descriptions, which are then embedded directly back into the Markdown source.
* **Three-Stage Hybrid Retrieval & Generation:**
  * **Stage 1 (Recall)** — `LanceDB` hybrid search combining `NV-Embed-v2` cosine similarity with BM25, fused via Reciprocal Rank Fusion, fetches up to 100 candidates.
  * **Stage 2 (Precision)** — `Qwen3-Reranker-0.6B` cross-encoder scores each candidate via yes/no logits and extracts the top-N.
  * **Stage 3 (Synthesis)** — locally-hosted `Qwen3.6-35B-A3B` (Q6_K GGUF, ~29 GB) generates a strictly grounded answer over the reranked context, with thinking mode disabled for deterministic output.
* **Multi-Slice GPU Orchestration:** Embedder, reranker, and generator are pinned to separate MIG slices. The LLM runs in an isolated child subprocess because `llama.cpp` dedupes devices by PCI BDF — all MIG slices share one BDF, so single-slice pinning only works when the slice is the only one visible to the process.
* **100% Self-Hosted Security:** Designed specifically to run on local **NVIDIA H200 MIG slices**. No sensitive fleet data or proprietary company manuals are ever sent to third-party APIs.

## Hardware requirements

* **Minimum:** 3× NVIDIA H200 MIG slices (each ~`1g.35gb`, ~34.9 GB VRAM), or equivalent GPUs with combined ~105 GB of VRAM.
* **Slice layout at runtime:**
  * `cuda:0` — NV-Embed-v2 (~15.7 GB) — parent process
  * `cuda:1` — Qwen3-Reranker (~16.4 GB) — parent process
  * slice 2 — Qwen3.6-35B-A3B Q6_K (~28–30 GB) — child subprocess, single-slice pinned
* **Why three slices?** llama.cpp's BDF deduplication forces the LLM into a process where only one MIG slice is visible. Override the slice index with `LLM_MIG_UUID` if needed.
* **Slurm:** request `--gres=gpu:3` minimum.

## Installation & setup

```bash
# Clone the repository
git clone https://github.com/<org>/x1025-Maritime-Intelligence.git
cd x1025-Maritime-Intelligence

# Create the Conda environment from the exported file
conda env create -f environment.yml

# Activate the environment
conda activate x1025
```

`llama-cpp-python` must be built with CUDA support for the generation stage:

```bash
CMAKE_ARGS="-DGGML_CUDA=on" pip install llama-cpp-python --no-cache-dir \
    --force-reinstall --no-binary=llama-cpp-python
```

Copy `.env.example` to `.env` and configure `HF_HOME` and `HF_TOKEN` so HuggingFace models download to your designated persistent cache (the first run pulls ~80 GB of weights across all stages).

## Quickstart — Layer 1 RAG

All commands run from the repository root.

### Phase 1: Data ingestion & indexing

Place your raw PDF in `data/`, then run the three ingestion stages in order:

1. **PDF → Markdown** — Docling extracts native text and saves diagrams as PNGs.
   ```bash
   python -m backend.ingestion.docling_parser data/<file-name>.pdf --output-dir data/<output-dir>
   ```
2. **Vision extraction** — InternVL2.5-38B-AWQ describes each image and writes back into `manual.md`.
   ```bash
   python -m backend.ingestion.vision_captioner data/<output-dir>
   ```
3. **Embedding & indexing** — Macro-chunks the markdown, embeds with `NV-Embed-v2`, writes to `data/lancedb/<folder>_lancedb.lance` with FTS index for hybrid search.
   ```bash
   python -m backend.storage.lancedb_client data/<output-dir>
   ```

### Phase 2: Querying & generation

**Interactive chat (recommended)** — loads all three models once and keeps them warm. Switch manuals without reloading.
```bash
python -m frontend.chat_interface.cli
```
Inside the chat: type a question, `switch` to pick a different manual, or `quit`/Ctrl+D to exit.

**One-shot CLI** — useful for scripted evaluation or single questions.
```bash
python -m agents.safety_agent data/lancedb/<folder>_lancedb.lance "your question here"
```

**Retrieval only (no generation)** — inspect reranked chunks without spinning up the LLM.
```bash
python -m agents.safety_agent --retrieve-only data/lancedb/<folder>_lancedb.lance "your query"
```

### Phase 3: Web frontend (FastAPI + React)

The web stack lets crews chat against the agent and drop in new PDFs from a browser — the API server runs the three-stage ingestion inline and switches the agent onto the new manual the moment indexing completes.

1. **Start the FastAPI server** (from project root). Warm-loads `SafetyAgent` once, then serves `/manuals`, `/switch`, `/chat`, `/upload`:
   ```bash
   uvicorn backend.api.server:app --host 0.0.0.0 --port 8001
   ```
2. **Start the Vite dev server** (from `frontend/web/`). Proxies `/api/*` → `http://localhost:8001`:
   ```bash
   cd frontend/web
   npm install        # first time only
   npm run dev
   ```
3. **Open** `http://localhost:5173`. The Guardrails sidebar holds the "Add a manual" PDF upload button and a list of vetted safety prompts; the chat card streams tokens from the active manual.

## Performance demonstration

The pipeline has been extensively tested against the *N.S. SAVANNAH Safety Analysis Report*. By combining Macro-Chunking with a cross-encoder reranker and a strictly-grounded generator, the system extracts and synthesizes correct answers from highly complex, tabular engineering data where standard RAG systems fail.

## Engineering "war stories"

Building this pipeline involved solving several real limitations of modern LLMs and toolchains:

* **Token truncation.** Embedding models silently amputated the bottom 200 tokens of 1500-word chunks. Fixed by reducing chunk thresholds to 1000 words.
* **NV-Embed-v2 patches.** The upstream `modeling_nvembed.py` had multiple incompatibilities with current `transformers` (rotary embeddings not threaded through gradient checkpointing, KV-cache tensor handling). `backend/storage/lancedb_client.py` patches the cached file in-place on first load — see `patch_nvembed()`.
* **MIG slice pinning for llama.cpp.** All MIG slices on an H200 share a single PCI BDF, which `llama.cpp` deduplicates. We isolate the LLM in a `multiprocessing.spawn` child with `CUDA_VISIBLE_DEVICES` pinned to a single slice UUID — the only reliable way to run llama.cpp on one MIG partition while the parent uses the others.
* **Ground-truth discrepancies.** When the LLM supposedly "failed" test queries, programmatic PDF-extraction scripts proved the LLM was actually 100% correct — the expected test answers were factually missing from the original source documents.

## Project status

| Layer | Component | Status |
|------|-----------|--------|
| 1 | `agents/safety_agent.py` (RAG) | ✅ Working (migrated from prototype) |
| 1 | `backend/ingestion/docling_parser.py` | ✅ Working |
| 1 | `backend/ingestion/vision_captioner.py` | ✅ Working |
| 1 | `backend/storage/lancedb_client.py` | ✅ Working |
| 1 | `frontend/chat_interface/cli.py` (interim Python REPL) | ✅ Working |
| 1 | `backend/api/server.py` (FastAPI: `/chat`, `/manuals`, `/switch`, `/upload`) | ✅ Working |
| 1 | `frontend/web/` (React/Vite chat UI + upload pipeline + Guardrails sidebar) | ✅ Working |
| 2 | `agents/analytics_agent.py`, `backend/stream/`, `backend/storage/timeseries_db.py` | ⏸ Not yet scaffolded |
| 3 | `agents/superintendent.py` | ⏸ Stretch goal |
| — | `agents/supervisor.py` | ⏸ Not yet scaffolded |

---
*Developed for the IMPACT Program — UMass Boston Venture Development Center*
