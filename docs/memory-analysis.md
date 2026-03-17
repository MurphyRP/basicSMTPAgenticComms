# OpenClaw Memory Architecture: Deep Analysis

> **Purpose:** Decompose the full OpenClaw memory subsystem with critical analysis of how each component could be leveraged for a shared human/AI memory approach.
> **Source:** OpenClaw `/src/memory/` — ~15 core files, ~5,000 lines of TypeScript.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Storage Layer](#storage-layer)
3. [Embedding Pipeline](#embedding-pipeline)
4. [Search System](#search-system)
5. [Sync & Lifecycle](#sync--lifecycle)
6. [Configuration & Scoping](#configuration--scoping)
7. [Critical Analysis: Strengths](#critical-analysis-strengths)
8. [Critical Analysis: Weaknesses](#critical-analysis-weaknesses)
9. [Shared Human/AI Memory: Opportunities](#shared-humanai-memory-opportunities)
10. [Shared Human/AI Memory: Architecture Sketch](#shared-humanai-memory-architecture-sketch)
11. [Extraction Feasibility](#extraction-feasibility)

---

## Architecture Overview

The memory system is a **local-first, file-backed semantic search engine** built on SQLite. It watches markdown files and session transcripts, chunks them, embeds them with pluggable providers, and serves hybrid vector+keyword search results to AI agents.

```
┌─────────────────────────────────────────────────────────────────────┐
│                         MEMORY SOURCES                               │
│  MEMORY.md │ memory/*.md │ session/*.jsonl │ multimodal (img/audio) │
└──────────────────────────────┬──────────────────────────────────────┘
                               │  file watcher (chokidar, 5s debounce)
┌──────────────────────────────▼──────────────────────────────────────┐
│                        SYNC PIPELINE                                 │
│  listMemoryFiles() → buildFileEntry() → hash compare → indexFile()  │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────────────────────┐   │
│  │ Chunker  │  │ Embedding    │  │ Batch Providers              │   │
│  │ (token-  │  │ Cache        │  │ (OpenAI/Gemini/Voyage batch  │   │
│  │  based)  │  │ (hash→vec)   │  │  APIs + direct fallback)     │   │
│  └──────────┘  └──────────────┘  └──────────────────────────────┘   │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────┐
│                        SQLITE DATABASE                               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────────────┐   │
│  │ files    │  │ chunks   │  │chunks_vec│  │ chunks_fts (FTS5) │   │
│  │ (paths,  │  │ (text,   │  │(sqlite-  │  │ (BM25 full-text)  │   │
│  │  hashes) │  │  embeds) │  │  vec)    │  │                   │   │
│  └──────────┘  └──────────┘  └──────────┘  └───────────────────┘   │
│  ┌──────────────────────┐  ┌──────────────────────────────┐         │
│  │ embedding_cache      │  │ meta (key-value config)      │         │
│  │ (provider+model+hash │  │                              │         │
│  │  → vector)           │  │                              │         │
│  └──────────────────────┘  └──────────────────────────────┘         │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────┐
│                        SEARCH PIPELINE                               │
│  query → [embedQuery + BM25 keyword] → mergeHybrid → MMR → decay   │
│  → filter by minScore → slice by maxResults → return snippets       │
└─────────────────────────────────────────────────────────────────────┘
```

**Inheritance chain** for the manager:
```
MemoryIndexManager
  → extends MemoryManagerEmbeddingOps
    → extends MemoryManagerSyncOps
```

---

## Storage Layer

### Database Schema (`memory-schema.ts`)

The schema is created by `ensureMemoryIndexSchema()` with migration support via `ensureColumn()`.

**Tables:**

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `meta` | Key-value config store | `key TEXT PRIMARY KEY`, `value TEXT` |
| `files` | Tracked source files | `path TEXT PRIMARY KEY`, `source TEXT`, `hash TEXT`, `mtime REAL`, `size INTEGER` |
| `chunks` | Core memory units | `id TEXT PRIMARY KEY`, `path TEXT`, `source TEXT`, `start_line INT`, `end_line INT`, `text TEXT`, `embedding TEXT (JSON)`, `hash TEXT`, `model TEXT`, `updated_at TEXT` |
| `embedding_cache` | Provider-agnostic vector cache | PK: `(provider, model, provider_key, hash)` → `embedding TEXT (JSON)`, `dims INT` |
| `chunks_vec` | Virtual sqlite-vec table | `id TEXT PRIMARY KEY`, `embedding FLOAT[N]` |
| `chunks_fts` | Virtual FTS5 table | `text`, `id`, `path`, `source`, `model`, `start_line`, `end_line` |

**Critical observation:** Embeddings are stored *twice* — as JSON in `chunks.embedding` AND as native vectors in `chunks_vec`. The JSON copy acts as a portable backup that survives sqlite-vec extension failures. The vector table is recreated from the JSON on dimension mismatch.

### SQLite Configuration (`sqlite.ts`)

- Uses Node's native `node:sqlite` module (Node >= 22)
- WAL mode for concurrent read/write
- sqlite-vec loaded as a dynamic extension via `loadSqliteVecExtension()`
- Extension resolution: custom path → npm package auto-resolution

### Chunking Algorithm (`internal.ts` / `memory-chunk.ts`)

```
chunkMarkdown(content, { maxTokens, overlapLines }) →
  for each line:
    accumulate into current chunk
    if charCount > maxTokens * 4:  // rough token estimate
      flush chunk
      carry forward overlapLines into next chunk
  → MemoryChunk[] with { startLine, endLine, text, hash }
```

**Design decisions:**
- Token estimation uses `chars / 4` heuristic — fast but imprecise
- Overlap is line-based, not token-based — preserves semantic boundaries
- SHA256 hash per chunk enables change detection without re-embedding
- Session JSONL files get special line-remapping (`remapChunkLines()`) to map back to original message positions

**Multimodal support:**
- Images/audio get `MultimodalMemoryChunk` with structured input bytes
- File validation checks size limits and MIME types
- Separate embedding path for multimodal content

### Shared Human/AI Relevance: Storage

| Aspect | Current Design | Human/AI Adaptation |
|--------|---------------|-------------------|
| **File-backed source of truth** | Markdown files on disk | Could be shared Obsidian/LogSeq vaults, shared docs |
| **Change detection** | SHA256 hash + mtime | Works as-is for collaborative editing |
| **Chunk granularity** | Token-limited text blocks | Needs semantic units (paragraphs, thoughts, decisions) for human readability |
| **Schema** | Single-user, single-workspace | Needs `author` column, access control, provenance tracking |

---

## Embedding Pipeline

### Provider Abstraction (`embeddings.ts`)

```typescript
type EmbeddingProvider = {
  id: string;
  model: string;
  maxInputTokens?: number;
  embedQuery: (text: string) => Promise<number[]>;
  embedBatch: (texts: string[]) => Promise<number[][]>;
  embedBatchInputs?: (inputs: EmbeddingInput[]) => Promise<number[][]>;
};
```

**Supported providers:**
- **Remote:** OpenAI, Gemini, Voyage, Mistral
- **Local:** Ollama, node-llama-cpp
- **Auto mode:** Tries local first, then remote providers in order (OpenAI → Gemini → Voyage → Mistral)
- **Graceful degradation:** Missing API keys → FTS-only mode (no error thrown)

### Batch Embedding (`manager-embedding-ops.ts`)

**Constants:**
```
EMBEDDING_BATCH_MAX_TOKENS = 8000
EMBEDDING_INDEX_CONCURRENCY = 4
EMBEDDING_RETRY_MAX_ATTEMPTS = 3
BATCH_FAILURE_LIMIT = 2
```

**Pipeline:**
```
indexFile(fileEntry) →
  chunkMarkdown(content) →
  collectCachedEmbeddings(chunks) →       // check hash-based cache first
  buildEmbeddingBatches(uncachedChunks) →  // group by 8000-token budget
  embedChunksWithBatch(batches) →          // route to provider batch API
  upsertEmbeddingCache(results) →          // cache new embeddings
  INSERT into chunks + chunks_vec + chunks_fts
```

**Provider-specific batch routing:**
- **OpenAI:** `/v1/embeddings` batch endpoint, 24h window, 50k max requests
- **Gemini:** `asyncBatchEmbedContent` via file upload, 50k max
- **Voyage:** `/v1/embeddings` batch, 12h window, 50k max
- **Fallback:** Direct `embedBatch()` calls with concurrency control

**Resilience features:**
- Batch failure tracking: After 2 consecutive failures, batch API auto-disables
- Exponential backoff retry: 500ms base → 8s max on rate limits/429/5xx
- Timeout differentiation: 60s remote, 300s local (queries); 120s/600s (batches)
- Successful batch resets failure counter to 0

### Embedding Cache

- Composite key: `(provider, model, provider_key, hash)`
- Provider key is computed from config details (baseUrl, model, headers) — allows cache reuse across minor config changes
- LRU eviction by `updated_at` when exceeding max entries
- Batch cache queries: 400 hashes per DB query

### Shared Human/AI Relevance: Embeddings

| Aspect | Current Design | Human/AI Adaptation |
|--------|---------------|-------------------|
| **Provider flexibility** | 6 providers + auto-selection | Enables teams to share a consistent embedding space regardless of individual setup |
| **Cache architecture** | Local SQLite per workspace | Could be a shared cache service — same hash = same vector |
| **Batch resilience** | Auto-fallback from batch to direct | Critical for production shared memory with mixed reliability |
| **FTS fallback** | Works without any embedding provider | Ensures human users without API keys still get search functionality |

---

## Search System

### Hybrid Search (`hybrid.ts`, `manager-search.ts`)

The default search mode runs **vector** and **keyword** in parallel, then merges:

```
search(query) →
  ┌── searchVector(query) → cosine similarity via sqlite-vec
  │     score = 1 - cosine_distance
  │
  ├── searchKeyword(query) → BM25 via FTS5
  │     tokens → quoted AND-connected query
  │     score = rank / (1 + rank)  // normalize to [0,1)
  │
  └── mergeHybridResults(vectorResults, keywordResults)
        combined_score = vectorWeight * vectorScore + textWeight * textScore
```

**Fallback chain:**
1. Both available → Hybrid (default)
2. No embedding provider → FTS-only (keyword search)
3. FTS unavailable → Vector-only
4. Neither → No search results

### Maximal Marginal Relevance (`mmr.ts`)

Post-processing re-ranker for result diversity:

```
MMR formula: λ * relevance - (1 - λ) * max_similarity_to_selected
```

- Uses **Jaccard similarity** on tokenized text (not embeddings — avoids recomputation)
- Default λ = 0.7 (relevance-biased)
- Default: disabled, must be explicitly enabled
- Iteratively selects results that balance relevance with diversity

### Temporal Decay (`temporal-decay.ts`)

Recency-aware scoring adjustment:

```
adjusted_score = score * exp(-λ * ageInDays)
where λ = ln(2) / halfLifeDays
```

- Detects dates from file paths (e.g., `memory/2025-03-17.md`)
- **Evergreen files** (`MEMORY.md`, `memory.md`) are exempt from decay
- Default half-life: 30 days
- Default: disabled, must be explicitly enabled

### Search Configuration (`backend-config.ts`)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `maxResults` | 6 | Maximum results returned |
| `maxSnippetChars` | 700 | Snippet truncation limit |
| `maxInjectChars` | 4000 | Total injection character limit |
| `vectorWeight` | (configurable) | Weight for vector score in hybrid |
| `textWeight` | (configurable) | Weight for BM25 score in hybrid |

### Shared Human/AI Relevance: Search

| Aspect | Current Design | Human/AI Adaptation |
|--------|---------------|-------------------|
| **Hybrid search** | Vector + BM25 merge | Humans benefit more from keyword precision; AI benefits more from semantic recall. Hybrid serves both. |
| **MMR diversity** | Reduces redundancy | Critical when AI and human have overlapping but different knowledge needs |
| **Temporal decay** | Recency bias with evergreen exceptions | Natural fit — recent conversations and decisions matter more, but core knowledge persists |
| **Snippet extraction** | Character-limited excerpts | Humans need longer context; AI needs concise injection. Could serve different limits per consumer. |

---

## Sync & Lifecycle

### File Watcher

```
chokidar watcher →
  watches: memory/*.md, session/*.jsonl, configured multimodal extensions
  ignores: .git, node_modules, .venv, __pycache__, ...
  debounce: 100ms poll, configurable stability threshold
  on change: sets dirty = true (5s debounce before sync)
```

### Sync Pipeline (`manager-sync-ops.ts`)

```
sync(params) →
  runSyncWithReadonlyRecovery() →
    runSync() {
      listMemoryFiles() + listSessionFiles()
      → buildFileEntry() for each (path, hash, mtime, size)
      → compare with DB records (hash + mtime)
      → indexFile() for modified/new files
      → deleteFileRecord() for removed files
      → writeMeta() (vector dims, provider info)
    }
```

**Sync triggers:**
- File watcher detects change → `dirty = true`
- Session transcript update → targeted session sync
- Periodic interval (configurable)
- On-search sync if dirty and `sync.onSearch` enabled
- On-session-start sync if `sync.onSessionStart` enabled

**Session delta tracking:**
```
Per-file tracking: { lastSize, pendingBytes, pendingMessages }
Reads in 64KB chunks, counts newlines (byte 10) for message count
Sync when pendingBytes or pendingMessages exceeds threshold
```

**Reindex strategies:**
- **Safe reindex:** Creates temp DB → indexes everything → atomic swap (production)
- **Unsafe reindex:** Direct reset → reindex (test-only)
- Full reindex triggered when: provider changed, model changed, sources differ, config hash differs, chunking params differ, vector dims differ

**Readonly recovery:**
- Detects `SQLITE_READONLY` errors
- Closes DB connection → reopens → resets vector state → retries once
- Tracks attempts/successes/failures in status

### Manager Instance Caching

```
INDEX_CACHE: Map<string, MemoryIndexManager>
INDEX_CACHE_PENDING: Map<string, Promise<MemoryIndexManager>>
Cache key: `${agentId}:${workspaceDir}:${JSON.stringify(settings)}`
```

Static `get()` factory ensures singleton per agent+workspace+config combination.

### Shared Human/AI Relevance: Lifecycle

| Aspect | Current Design | Human/AI Adaptation |
|--------|---------------|-------------------|
| **File watcher** | Local filesystem only | Could extend to watch shared network drives, synced folders (Dropbox, Drive) |
| **Safe reindex** | Atomic DB swap | Essential for shared systems — no downtime during reindex |
| **Session tracking** | JSONL transcript delta sync | Natural container for conversation memories from both human and AI participants |
| **Instance caching** | Per-agent singletons | Could become per-user or per-team singletons in shared deployment |

---

## Configuration & Scoping

### Memory Configuration

Sources are defined as collections of memory directories:
```
sources: Set<"memory" | "sessions">
collections: configured memory directories and session paths
update interval: periodic sync frequency
search mode: hybrid | vector | keyword
```

### Multi-Agent Scoping (`qmd-scope.ts`)

QMD (Query Memory Database) scope rules control which memories are accessible:

```
isQmdScopeAllowed(scope, sessionKey) →
  parse sessionKey → { channel, chatType }
  match against rules: channel match, chatType match, keyPrefix match
  action: allow | deny
```

This enables **per-channel, per-chat-type memory isolation** — different Slack channels can have different memory views.

### Shared Human/AI Relevance: Scoping

| Aspect | Current Design | Human/AI Adaptation |
|--------|---------------|-------------------|
| **Channel-based scoping** | Isolates memories per messaging channel | Maps to team/project/topic scoping in shared memory |
| **chatType filtering** | channel / group / direct | Maps to public / team / private memory tiers |
| **Session key parsing** | Platform-specific key format | Could generalize to `user:context:scope` patterns |

---

## Critical Analysis: Strengths

### 1. Graceful Degradation is Exemplary

The system works across a remarkable range of environments:
- No API keys → FTS-only search (still functional)
- No sqlite-vec → FTS-only (JSON embeddings preserved for future)
- Batch API fails → automatic fallback to direct embedding
- DB becomes readonly → automatic recovery
- Provider changes → full reindex with safe atomic swap

**This is the single most important property for a shared human/AI system.** Mixed environments are the norm, not the exception.

### 2. Hash-Based Change Detection is Efficient

SHA256 hashing of chunks means:
- No re-embedding of unchanged content
- Cache works across provider changes (same text, same hash → same cache key with provider qualifier)
- Incremental sync only processes actual changes

### 3. Provider Abstraction is Clean

The `EmbeddingProvider` interface is minimal and well-designed. Adding a new provider requires implementing just three methods. The auto-selection chain with fallback is production-grade.

### 4. Hybrid Search Covers Both Precision and Recall

BM25 catches exact keyword matches that vector search might miss (names, IDs, specific terms). Vector search catches semantic similarity. The merge with configurable weights is the right approach.

### 5. File-Based Source of Truth

Memory lives as markdown files, not locked in a database. This is:
- Human-readable and editable
- Version-controllable via git
- Portable across tools
- Debuggable without special tooling

---

## Critical Analysis: Weaknesses

### 1. Token Estimation is Crude

`chars / 4` for token estimation is a rough heuristic. For code-heavy content, CJK text, or mixed-language documents, this can lead to significantly uneven chunk sizes. The embedding batch budget (`8000 tokens`) could overflow or underflow.

**Shared memory impact:** In a multi-lingual team, chunk quality would vary significantly by language.

### 2. No Provenance or Attribution

The schema tracks `source` (memory vs sessions) and `path` but has no concept of:
- **Who** wrote or last modified a memory
- **When** a memory was created vs. last updated (only `updated_at` for indexing timestamp)
- **Why** a memory exists (no tags, categories, or intent)
- **Confidence** level (is this a fact, an opinion, a decision, a question?)

**Shared memory impact:** This is the **largest gap** for human/AI collaboration. Both parties need to know who said what and how authoritative it is.

### 3. No Memory Consolidation or Contradiction Detection

Memories are write-only. There is no mechanism to:
- Merge overlapping memories
- Detect contradictions between old and new information
- Summarize or compress accumulated knowledge
- Expire outdated information (temporal decay only affects search ranking, not storage)

**Shared memory impact:** Over time, a shared memory would accumulate contradictory facts from different participants without resolution.

### 4. Single-Writer Assumption

The SQLite database assumes single-process writes. While WAL mode helps with concurrent reads, the sync pipeline serializes through a single `syncing` promise. The readonly recovery is reactive, not preventive.

**Shared memory impact:** Multiple humans + multiple AI agents writing simultaneously would require a fundamentally different concurrency model.

### 5. Chunk Boundaries Are Arbitrary

Token-based chunking splits on character count, not semantic boundaries. A key decision could be split across two chunks, with only one half surfacing in search results.

**Shared memory impact:** Humans would find partial memories frustrating. AI can tolerate it better but still loses context.

### 6. No Access Control

The scoping system controls which *sources* are visible, but within a source, everything is accessible. There's no per-memory or per-chunk access control.

**Shared memory impact:** Teams need private memories (personal notes, drafts) alongside shared ones.

---

## Shared Human/AI Memory: Opportunities

### Opportunity 1: Dual-Interface Memory

The file-backed architecture is a **natural bridge**:
- **Humans** interact with memories as markdown files — edit in VS Code, Obsidian, or any text editor
- **AI** interacts via the search API — vector + keyword retrieval
- The file watcher ensures both views stay synchronized

```
Human writes/edits: memory/decisions/api-auth-approach.md
  → file watcher detects change
  → re-chunks and re-embeds
  → AI can now search for "authentication decisions"

AI appends: memory/sessions/2025-03-17-standup.jsonl
  → session sync processes transcript
  → Human can read the raw session or search highlights
```

### Opportunity 2: Memory as Shared Context Protocol

The existing `MemorySearchResult` interface could serve as a **shared context protocol** between humans and AI:

```typescript
// Current interface - already suitable
type MemorySearchResult = {
  path: string;       // what file
  startLine: number;  // where exactly
  endLine: number;
  score: number;      // how relevant
  snippet: string;    // preview
  source: string;     // memory vs sessions
};
```

Both human UIs and AI agents can consume this same result format to understand what the other participant knows and has referenced.

### Opportunity 3: Session Transcripts as Shared History

The JSONL session format already captures conversation turns. Extending it to include:
- Human-to-human conversations (meeting notes)
- Human-to-AI conversations (existing)
- AI-to-AI conversations (agent coordination)

...would create a unified searchable history of all project communication.

### Opportunity 4: Temporal Decay for Knowledge Freshness

The temporal decay algorithm is directly applicable to shared memory:
- Recent decisions override older ones naturally
- Evergreen files (project principles, architecture docs) remain stable
- Half-life tuning per category: decisions (7d), meeting notes (14d), architecture (∞)

### Opportunity 5: Scoping as Team Topology

The QMD scope system maps cleanly to team structures:
```
channel  → project/team scope
chatType → visibility level (public/team/private)
keyPrefix → role-based filtering (engineer/pm/designer)
```

---

## Shared Human/AI Memory: Architecture Sketch

Building on OpenClaw's memory system, a shared human/AI memory would need these extensions:

### Extended Schema

```sql
-- Add to chunks table
ALTER TABLE chunks ADD COLUMN author TEXT;      -- 'human:alice' or 'ai:agent-1'
ALTER TABLE chunks ADD COLUMN created_at TEXT;   -- distinct from updated_at
ALTER TABLE chunks ADD COLUMN confidence REAL;   -- 0.0-1.0
ALTER TABLE chunks ADD COLUMN memory_type TEXT;  -- 'fact'|'decision'|'question'|'opinion'|'action'
ALTER TABLE chunks ADD COLUMN supersedes TEXT;   -- id of chunk this replaces
ALTER TABLE chunks ADD COLUMN visibility TEXT;   -- 'public'|'team'|'private'

-- Contradiction detection support
CREATE TABLE contradictions (
  chunk_a TEXT REFERENCES chunks(id),
  chunk_b TEXT REFERENCES chunks(id),
  detected_at TEXT,
  resolved_by TEXT,  -- chunk id of resolution, or null
  PRIMARY KEY (chunk_a, chunk_b)
);

-- Access control
CREATE TABLE memory_access (
  scope TEXT,        -- 'project:foo' or 'team:backend'
  principal TEXT,    -- 'human:alice' or 'ai:*' or 'team:backend'
  permission TEXT,   -- 'read' | 'write' | 'admin'
  PRIMARY KEY (scope, principal)
);
```

### Search Modifications

```
Extended scoring:
  base_score = vectorWeight * vectorScore + textWeight * textScore
  recency    = exp(-λ * ageInDays)
  authority  = authorWeight(author) * confidence
  final      = base_score * recency * authority

Author weighting:
  human decisions > human notes > AI summaries > AI inferences
```

### Concurrency Model

Replace single-writer SQLite with:
- **Option A:** PostgreSQL with pgvector (proven, scalable)
- **Option B:** SQLite with distributed WAL (Litestream/LiteFS for replication)
- **Option C:** Keep SQLite per-agent with a merge protocol (git-like)

Option C is most aligned with OpenClaw's local-first philosophy and our SMTP-based architecture.

### Sync Protocol Over SMTP

```
Agent A writes memory → generates memory delta (new/modified chunks)
  → SMTP message to shared memory topic
  → Agent B receives, merges into local index
  → Contradiction detection runs on merge
  → Unresolved contradictions surfaced to human

Human edits file → file watcher generates delta
  → Same SMTP sync path
  → All agents receive update
```

This maps directly to our basicSMTPAgenticComms architecture — memory sync becomes just another message type.

---

## Extraction Feasibility

### Can Be Extracted Directly (Low Effort)

| Component | Files | Dependencies |
|-----------|-------|-------------|
| Chunking algorithm | `internal.ts` (chunkMarkdown) | None beyond Node builtins |
| Embedding provider interface | `embeddings.ts` | Minimal (fetch, crypto) |
| Hybrid search merge | `hybrid.ts` | None |
| MMR re-ranker | `mmr.ts` | None |
| Temporal decay | `temporal-decay.ts` | None |
| SQLite schema | `memory-schema.ts` | `node:sqlite` |

### Needs Adaptation (Medium Effort)

| Component | Files | Adaptation Needed |
|-----------|-------|-------------------|
| Embedding cache | `manager-embedding-ops.ts` | Extract from class hierarchy |
| Batch embedding | `manager-embedding-ops.ts` + `batch-*.ts` | Decouple from manager state |
| File watcher | `manager-sync-ops.ts` | Extract watcher setup from sync logic |
| Vector search | `manager-search.ts` + `sqlite-vec.ts` | Package sqlite-vec loading separately |

### Needs Redesign (High Effort)

| Component | Reason |
|-----------|--------|
| Manager class hierarchy | Too tightly coupled — embedding, sync, and search in one inheritance chain |
| Session sync | Deeply tied to OpenClaw's JSONL format and session management |
| QMD scoping | Tied to OpenClaw's channel/chatType model |

---

## Summary

OpenClaw's memory system is a **well-engineered local-first semantic search engine** with excellent graceful degradation and provider flexibility. Its file-backed architecture is a natural fit for shared human/AI memory because both participants can interact with the same underlying files — humans via editors, AI via search APIs.

The **critical gaps** for shared memory are:
1. **Provenance** — who wrote what, and how authoritative is it
2. **Consolidation** — no merging, contradiction detection, or knowledge compression
3. **Concurrency** — single-writer assumption breaks with multiple participants
4. **Access control** — no per-memory visibility or permissions

The **most promising extraction targets** are the hybrid search pipeline (vector + BM25 + MMR + temporal decay) and the embedding provider abstraction with its batch/cache/fallback system. These are production-grade components that would significantly accelerate building a shared memory system.

The **key architectural decision** for our project: use SMTP as the memory sync transport, keeping local SQLite per-agent (aligned with OpenClaw's local-first design) and adding a merge protocol for cross-agent memory convergence. This turns memory sync into just another message type in our existing agentic communication framework.
