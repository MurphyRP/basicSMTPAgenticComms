# OpenClaw Architecture Analysis

> **Purpose:** Understand OpenClaw's architecture to identify components useful independently.
> **Goal:** Cherry-pick reusable subsystems — not run OpenClaw itself.
> **Source:** [github.com/openclaw/openclaw](https://github.com/openclaw/openclaw) (MIT License, TypeScript, Node >= 22)

---

## Table of Contents

1. [High-Level Architecture](#high-level-architecture)
2. [Core Subsystems](#core-subsystems)
3. [Memory System (Deep Dive)](#memory-system-deep-dive)
4. [Multi-Agent Memory Sharing](#multi-agent-memory-sharing)
5. [Reusable Components](#reusable-components)
6. [Extraction Guide](#extraction-guide)
7. [Component Dependency Map](#component-dependency-map)

---

## High-Level Architecture

OpenClaw is a **multi-channel AI gateway** — a middleware layer between messaging platforms (Slack, Telegram, WhatsApp, Discord, IRC, etc.) and LLM providers (OpenAI, Anthropic, Google, Ollama, etc.). It routes conversations through configurable AI agents.

```
┌──────────────────────────────────────────────────────────────────┐
│                        MESSAGING CHANNELS                        │
│  Slack │ Telegram │ Discord │ WhatsApp │ iMessage │ IRC │ ...    │
└────────────────────────────┬─────────────────────────────────────┘
                             │ inbound/outbound adapters
┌────────────────────────────▼─────────────────────────────────────┐
│                      GATEWAY SERVER (WebSocket + HTTP)            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐ │
│  │ Routing   │  │ Sessions │  │ Auth     │  │ Plugin Registry  │ │
│  │ Engine    │  │ Manager  │  │ System   │  │ & Hook Lifecycle │ │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────────┘ │
└────────────────────────────┬─────────────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────────────┐
│                        AGENT LAYER                               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────────┐   │
│  │ Auto-    │  │ Memory   │  │ Context  │  │ Tools/Skills   │   │
│  │ Reply    │  │ System   │  │ Engine   │  │ Framework      │   │
│  └──────────┘  └──────────┘  └──────────┘  └────────────────┘   │
└────────────────────────────┬─────────────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────────────┐
│                      LLM PROVIDERS                               │
│  OpenAI │ Anthropic │ Google │ Ollama │ Mistral │ xAI │ ...      │
└──────────────────────────────────────────────────────────────────┘
```

### Key Design Principles

- **Plugin-first:** Core is lean; capabilities ship as extensions (~70 bundled)
- **Adapter pattern:** Channels abstract platform differences via contracts
- **Hook system:** Plugins intercept at lifecycle points (before/after agent, message, tool calls)
- **Session isolation:** Conversations keyed by `agentId + channel + peer` binding
- **Contract-driven:** Plugin interfaces verified by test suites

### Project Structure

```
openclaw/
├── src/                    # Core implementation (~9K files)
│   ├── gateway/            # WebSocket/HTTP server, protocol, auth
│   ├── channels/           # Channel abstraction layer
│   ├── providers/          # LLM provider integration
│   ├── plugins/            # Plugin loader, registry, hooks
│   ├── routing/            # Message routing engine
│   ├── agents/             # Agent framework, tools, sandbox
│   ├── auto-reply/         # Reply generation pipeline
│   ├── memory/             # Vector search + semantic memory
│   ├── context-engine/     # Pluggable context management
│   ├── config/             # Zod-validated JSON5 config
│   ├── secrets/            # Encrypted credential management
│   ├── security/           # Audit, SSRF protection, exec approval
│   ├── infra/              # Process mgmt, fs-safe, networking
│   ├── cli/                # CLI with subcommands + profiles
│   ├── daemon/             # OS service (systemd/launchd/schtasks)
│   ├── cron/               # Scheduled task execution
│   └── ...                 # tui, browser, media, tts, etc.
├── extensions/             # ~70 channel/provider plugins
├── skills/                 # ~55 standalone skill definitions
├── packages/               # Legacy compatibility (clawdbot, moltbot)
└── ui/                     # Vite + React web dashboard
```

---

## Core Subsystems

### Gateway Server (`src/gateway/`)

The central control plane. WebSocket + HTTP server handling:
- Client connections (CLI, web, mobile)
- RPC method dispatch (~70+ methods)
- Authentication/authorization with scoped operators
- Session key resolution for routing
- Plugin HTTP handler integration

**Protocol:** AJV-validated JSON schemas for every method/event. Frames: `RequestFrame`, `ResponseFrame`, `EventFrame`.

### Channel Abstraction (`src/channels/`)

Pluggable adapters for messaging platforms. Each channel implements contracts:

| Contract | Purpose |
|----------|---------|
| `ChannelInboundAdapter` | Receive/parse messages from platform |
| `ChannelOutboundAdapter` | Send messages to platform |
| `ChannelThreadingAdapter` | Thread binding and context |
| `ChannelSecurityContext` | DM policy, mentions, group access |
| `ChannelStreamingAdapter` | Draft streams and typing indicators |
| `ChannelStatusAdapter` | Health probes, account state |

**Routing:** Hierarchical binding resolution: `peer → parent → guild+roles → guild → team → account → channel → default`

### Plugin System (`src/plugins/`)

Runtime extension architecture. Plugins register via `OpenClawPluginApi`:

```typescript
api.registerProvider(...)        // LLM/speech/search providers
api.registerChannel(...)         // Messaging channels
api.registerTool(...)            // Agent tools
api.registerCommand(...)         // CLI commands
api.registerGatewayMethod(...)   // RPC methods
api.registerHttpRoute(...)       // HTTP endpoints
api.registerContextEngine(...)   // Context providers
api.registerService(...)         // Background services
api.on('hook_name', handler)     // Lifecycle hooks
```

**Hook lifecycle points:** `before_agent_start`, `before_model_resolve`, `before_tool_call`, `after_tool_call`, `message_*`, `session_*`, `gateway_start/stop`, `subagent_spawning`

### Provider Integration (`src/providers/`)

LLM model management: discovery, catalog, auth (OAuth/API key/device code), usage tracking, cost calculation. Supports 20+ providers.

---

## Memory System (Deep Dive)

### Architecture Overview

The memory system provides **vector-based semantic search** over agent knowledge, combining embeddings with full-text search for hybrid retrieval.

```
┌─────────────────────────────────────────────────────┐
│                  MemoryIndexManager                  │
│  ┌─────────┐  ┌───────────┐  ┌───────────────────┐  │
│  │ Sync    │  │ Search    │  │ Embedding         │  │
│  │ Engine  │  │ Engine    │  │ Provider          │  │
│  └────┬────┘  └─────┬─────┘  └────────┬──────────┘  │
│       │             │                 │              │
│  ┌────▼─────────────▼─────────────────▼──────────┐   │
│  │           SQLite Database                      │   │
│  │  ┌───────┐  ┌──────┐  ┌────────┐  ┌────────┐  │   │
│  │  │ files │  │chunks│  │chunks_ │  │chunks_ │  │   │
│  │  │       │  │      │  │fts (5) │  │vec     │  │   │
│  │  └───────┘  └──────┘  └────────┘  └────────┘  │   │
│  └────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

### Storage Schema

**`files` table** — Tracks indexed source files:
- `path` (PK): relative path within workspace
- `source`: `"memory"` or `"sessions"`
- `hash`: content hash for change detection
- `mtime`, `size`: dirty tracking metadata

**`chunks` table** — Indexed text segments:
- `id` (PK), `path`, `source`, `start_line`, `end_line`
- `text`: actual chunk content
- `hash`: content hash
- `model`: embedding model used
- `embedding`: stored as JSON string

**`chunks_fts`** — FTS5 virtual table for BM25 keyword search

**`chunks_vec`** — sqlite-vec extension for vector cosine distance

**`embedding_cache`** — Provider-specific embedding cache keyed by `(provider, model, provider_key, content_hash)`

**`meta`** — Tracks embedding model, provider, dimensions, chunk settings

### Memory Sources

Two independent sources, tracked separately:

1. **"memory"** — File-backed knowledge: `MEMORY.md`, `memory.md`, or `memory/**/*.md` in workspace. Extra paths configurable per agent.
2. **"sessions"** — Conversation transcripts: Agent-specific JSONL files in `.openclaw/sessions/{agentId}/`. Auto-indexed from conversations.

### Search Algorithms

Three search modes depending on configuration:

**FTS-Only** (no embedding provider):
- SQLite FTS5 with BM25 ranking
- Keyword extraction via query expansion

**Vector-Only** (provider available, no FTS):
- Cosine similarity on embeddings via sqlite-vec
- Query embedding generated at search time

**Hybrid** (default when both available):
1. Vector search and keyword search run in parallel
2. Results merged with configurable weights:
   - `vectorWeight`: 0.7 (default)
   - `textWeight`: 0.3 (default)
   - `candidateMultiplier`: 4x expansion for ranking
3. Optional **MMR** (Maximal Marginal Relevance) for diversity: `MMR(x) = λ * relevance(x) - (1-λ) * max_similarity_to_selected(x)` (λ=0.7)
4. Optional **temporal decay**: `score *= e^(-(ln2/halfLifeDays) * ageInDays)` for recency weighting
5. Filter by `minScore` threshold (default 0.35)

### Embedding Providers

| Provider | Default Model | Notes |
|----------|--------------|-------|
| OpenAI | `text-embedding-3-small` | Batch API support |
| Gemini | `embedding-001` | Batch API support |
| Voyage | `voyage-4-large` | Batch API support |
| Mistral | `mistral-embed` | — |
| Ollama | `nomic-embed-text` | Local, offline |
| Local | node-llama-cpp | Fully offline |
| Auto | (tries remote first) | Intelligent fallback |

**Batch processing:** OpenAI/Gemini/Voyage support async batch API with configurable concurrency (default 2), poll-based status, fallback to sync on failure.

**Caching:** Multi-provider cache with LRU eviction. Key: `(provider_id, model, provider_key, content_hash)`.

### Sync Mechanisms

**Dirty tracking:** Two independent flags — `dirty` (memory files via chokidar watcher, 1500ms debounce) and `sessionsDirty` (session transcripts, 5000ms debounce).

**Sync types:**
1. **Full reindex** — When provider/model/settings change. Atomic swap: build in temp DB, move to production.
2. **Incremental sync** — Normal case. Hash comparison, chunk only modified files, embed only new/changed chunks.
3. **Targeted session sync** — Post-compaction. Refreshes specific session files only.

**Triggers:** Configurable — on session start, on search query (if dirty), on file watch, on interval timer, or manual.

### Configuration

```yaml
agents:
  defaults:
    memorySearch:
      enabled: true
      provider: "openai"           # or gemini, voyage, ollama, local, auto
      model: "text-embedding-3-small"
      sources: ["memory", "sessions"]
      extraPaths: []               # Additional dirs to index
      chunking:
        tokens: 400                # Chunk size
        overlap: 80                # Overlap between chunks
      store:
        path: null                 # Custom path ({agentId} template)
        vector:
          enabled: true
      query:
        maxResults: 6
        minScore: 0.35
        hybrid:
          vectorWeight: 0.7
          textWeight: 0.3
      sync:
        onSessionStart: true
        onSearch: true
        watch: true
```

### Key Implementation Files

| File | LOC | Purpose |
|------|-----|---------|
| `memory/manager.ts` | 840 | Main API, caching, search dispatch |
| `memory/manager-sync-ops.ts` | 1,391 | Sync logic, file indexing |
| `memory/manager-embedding-ops.ts` | 925 | Batch processing, embedding cache |
| `memory/manager-search.ts` | — | Vector + keyword search impl |
| `memory/hybrid.ts` | — | Hybrid merge, BM25 scoring |
| `memory/mmr.ts` | — | Maximal Marginal Relevance |
| `memory/temporal-decay.ts` | — | Recency weighting |
| `memory/memory-schema.ts` | — | SQLite table definitions |
| `memory/sqlite-vec.ts` | — | sqlite-vec extension loader |
| `memory/embeddings-*.ts` | — | Per-provider embedding implementations |
| `agents/memory-search.ts` | — | Config resolution per agent |

---

## Multi-Agent Memory Sharing

### Default: Complete Isolation

**Each agent has its own isolated SQLite database.** This is the fundamental design choice.

```
Agent A ──► ~/.openclaw/state/memory/agent-a.sqlite
              └── indexes agent-a's workspace/memory/ files
              └── indexes agent-a's session transcripts

Agent B ──► ~/.openclaw/state/memory/agent-b.sqlite
              └── indexes agent-b's workspace/memory/ files
              └── indexes agent-b's session transcripts
```

**Three layers of isolation:**
1. **Database isolation:** Each agent's `{agentId}.sqlite` is separate
2. **Workspace isolation:** Each non-default agent gets `~/.openclaw/state/workspace-{agentId}/`
3. **Session isolation:** Transcripts stored per-agent in `.openclaw/sessions/{agentId}/`

**Manager caching:** Singleton per composite key `agentId:workspaceDir:JSON(settings)`. Different agents never share manager instances.

### Sharing Via Shared Store Path

The only way to share memory between agents is configuring them to use the **same SQLite database path**:

```yaml
agents:
  - id: agent-a
    memorySearch:
      store:
        path: "/shared/path/shared-memory.sqlite"
  - id: agent-b
    memorySearch:
      store:
        path: "/shared/path/shared-memory.sqlite"
```

**Concurrency considerations:**
- SQLite uses `PRAGMA busy_timeout = 5000` for write contention
- Multiple readers work in parallel (WAL mode)
- Writers serialize via SQLite's exclusive lock
- **No application-level coordination** between agents — just SQLite-level locking

### QMD Backend (External Tool Alternative)

For group-chat scenarios, the QMD backend provides scope-aware filtering:

```typescript
// qmd-scope.ts
function isQmdScopeAllowed(scope, sessionKey): boolean {
  // Filter by channel, chatType (channel/group/direct), keyPrefix
}
```

This allows agents in the same group chat to access shared memory while respecting scope rules, but requires an external QMD tool.

### What's NOT Provided

- No real-time memory synchronization between agents
- No conflict resolution for concurrent writes
- No "memory federation" or distributed memory
- No pub/sub for memory updates across agents
- No access control lists on memory entries

**The architecture prioritizes isolation and safety over shared state.**

---

## Reusable Components

### Tier 1: Extract Immediately (Minimal Changes)

| Component | Size | What It Does | Why It's Useful |
|-----------|------|-------------|-----------------|
| **Context Engine** | ~400 LOC | Pluggable context management contract (`ingest`, `assemble`, `compact`) | Pure interface, almost no deps. Drop-in for any agent framework. |
| **Image Generation** | ~600 LOC | Provider abstraction for DALL-E, Imagen, etc. | Clean provider pattern, request/response types. |
| **TTS System** | ~500 LOC | Multi-provider speech synthesis (OpenAI, ElevenLabs, Edge TTS) | Clean provider pattern, voice selection, preprocessing. |
| **Markdown IR** | ~500 LOC | Markdown → intermediate representation → channel-specific output | Platform-specific message formatting (WhatsApp, Signal, plain). |
| **Link Understanding** | ~150 LOC | URL extraction + configurable CLI processing | Simple, focused, well-defined. |
| **Web Search** | ~200 LOC | Provider abstraction for web search | Thin wrapper, easy to adapt. |
| **Schema Utils** | ~200 LOC | TypeBox helpers for AI tool/function schemas | Pure utilities, zero internal deps. |
| **Skills** (individual) | Varies | 55+ standalone tool definitions (GitHub, 1Password, Discord, etc.) | Already self-contained. SKILL.md format with frontmatter. |

### Tier 2: Medium Effort (Config Refactoring Needed)

| Component | Size | What It Does | Extraction Work |
|-----------|------|-------------|-----------------|
| **Media Understanding** | ~2K LOC | Multi-provider transcription (Deepgram, OpenAI, Groq for audio; Google, Moonshot for video) | Abstract config dependency. Providers are modular. |
| **Hooks System** | 7K LOC | Plugin lifecycle hook framework with module loading | Abstract config/workspace deps. Core hook contract is solid. |
| **Memory — Embedding Providers** | ~3K LOC | OpenAI, Gemini, Voyage, Ollama, local embedding abstractions | Extract providers individually. Batch API logic is reusable. |
| **Memory — Search Algorithms** | ~2K LOC | Hybrid BM25+vector merge, MMR, temporal decay | Algorithm code is standalone. Needs DB abstraction. |
| **Logging + Redaction** | ~1K LOC | Structured logging with automatic secret redaction | Winston-based, redaction patterns are valuable. |
| **Secrets Management** | ~2K LOC | Encrypted credential store with audit trails | Production-grade. Needs config abstraction. |

### Tier 3: High Effort (Significant Refactoring)

| Component | Size | What It Does | Why It's Hard |
|-----------|------|-------------|--------------|
| **Sandbox System** | 9.5K LOC | Docker/SSH code execution isolation with filesystem bridge | Deep config integration, Docker/SSH orchestration complex. |
| **Daemon Service Mgmt** | ~3K LOC | Cross-platform OS service install (systemd, launchd, schtasks) | Platform-specific code is comprehensive but tightly coupled. |
| **ACP Protocol** | ~2K LOC | Agent Communication Protocol gateway translation | Tightly integrated with gateway. |
| **Process Supervisor** | ~1K LOC | Cross-platform process tree management, PTY support | Useful but intertwined with OpenClaw restart/bridge logic. |

### Not Worth Extracting

- **Gateway Server** — _is_ OpenClaw; can't separate
- **Auto-Reply Pipeline** — too integrated with agent runtime
- **Web UI** — tightly coupled to gateway APIs
- **Channel implementations** — useful only with the channel abstraction layer

---

## Extraction Guide

### Pattern: Provider Abstraction

Many OpenClaw subsystems follow the same pattern that makes extraction straightforward:

```typescript
// 1. Provider interface (extract this)
interface Provider<TRequest, TResult> {
  id: string;
  generate(request: TRequest): Promise<TResult>;
}

// 2. Registry (extract this)
class ProviderRegistry<T> {
  register(id: string, provider: T): void;
  resolve(id: string): T;
}

// 3. Config resolution (replace with your own)
function resolveProvider(config: YourConfig): Provider { ... }
```

This pattern appears in: Image Generation, TTS, Media Understanding, Embedding Providers, Web Search.

### Extraction Steps (General)

1. **Copy** the `src/{component}/` directory
2. **Replace** imports from `config/config.js` with your own config type
3. **Replace** imports from `logging/subsystem.js` with your logger
4. **Replace** `resolveAgentDir`/`resolveAgentWorkspaceDir` with your path resolution
5. **Remove** OpenClaw plugin registration calls
6. **Test** — most components have co-located `.test.ts` files

### Memory System Extraction (Specific)

To extract the memory/vector search system:

1. **Core files needed:**
   - `memory/manager.ts`, `manager-sync-ops.ts`, `manager-embedding-ops.ts`
   - `memory/manager-search.ts`, `hybrid.ts`, `mmr.ts`, `temporal-decay.ts`
   - `memory/memory-schema.ts`, `memory-chunk.ts`
   - `memory/sqlite.ts`, `sqlite-vec.ts`
   - Embedding providers you want (`embeddings-openai.ts`, etc.)

2. **Interfaces to replace:**
   - `OpenClawConfig` → your config type
   - `resolveAgentDir()` → your workspace path
   - `resolveStateDir()` → your state directory
   - Logger subsystem → your logger

3. **Dependencies:**
   - Node.js >= 22 (uses `node:sqlite`)
   - `sqlite-vec` native extension
   - `chokidar` (file watching, optional)
   - Provider SDK (OpenAI, etc.)

---

## Component Dependency Map

```
                    ┌──────────────┐
                    │   Gateway    │
                    │   Server     │
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
        ┌─────▼────┐ ┌────▼─────┐ ┌───▼──────┐
        │ Channels │ │ Plugins  │ │ Providers│
        │ Layer    │ │ System   │ │ Layer    │
        └─────┬────┘ └────┬─────┘ └───┬──────┘
              │            │            │
              └────────────┼────────────┘
                           │
                    ┌──────▼───────┐
                    │   Agent      │
                    │   Layer      │
                    └──────┬───────┘
                           │
         ┌─────────┬───────┼───────┬──────────┐
         │         │       │       │          │
    ┌────▼───┐ ┌──▼───┐ ┌─▼──┐ ┌─▼────┐ ┌───▼────┐
    │ Memory │ │ Auto │ │Tools│ │Skills│ │Context │
    │ System │ │Reply │ │     │ │      │ │Engine  │
    └────┬───┘ └──────┘ └─────┘ └──────┘ └────────┘
         │
    ┌────▼──────────────────────────────────────┐
    │ Embedding Providers (standalone)           │
    │ OpenAI │ Gemini │ Voyage │ Ollama │ Local  │
    └───────────────────────────────────────────┘

INDEPENDENT (no gateway dependency):
┌────────────┐ ┌────────┐ ┌─────┐ ┌──────────┐ ┌──────────┐
│ Image Gen  │ │  TTS   │ │ Web │ │ Markdown │ │ Security │
│ Providers  │ │ System │ │Srch │ │    IR    │ │  Audit   │
└────────────┘ └────────┘ └─────┘ └──────────┘ └──────────┘

INFRASTRUCTURE (standalone utilities):
┌────────┐ ┌─────────┐ ┌────────┐ ┌─────────┐ ┌────────┐
│ Config │ │ Secrets │ │Process │ │ Daemon  │ │  Cron  │
│ System │ │  Mgmt   │ │ Supvsr │ │ Service │ │Schduler│
└────────┘ └─────────┘ └────────┘ └─────────┘ └────────┘
```

### Standalone vs. Coupled

**Fully standalone** (no OpenClaw deps needed):
- Embedding providers, Schema utils, Individual skills, Markdown IR

**Needs config abstraction** (replace ~3 imports):
- Image Generation, TTS, Media Understanding, Web Search, Link Understanding

**Needs significant refactoring** (deep internal coupling):
- Memory manager (full system), Sandbox, ACP, Auto-Reply

---

## Key Takeaways

1. **Most valuable for extraction:** The provider abstraction pattern (embedding, image gen, TTS, media understanding) — clean interfaces, modular implementations, easy to adapt.

2. **Memory system is sophisticated but isolated:** Per-agent SQLite databases with hybrid search (BM25 + vector + MMR + temporal decay). No built-in multi-agent sharing — you'd need to configure shared DB paths manually.

3. **Plugin/hook architecture is well-designed:** Could serve as a template for building your own extensible agent system, even if you don't use OpenClaw's specific implementation.

4. **Skills are immediately reusable:** 55+ self-contained tool definitions in SKILL.md format. No extraction needed — just read and adapt the format.

5. **Infrastructure utilities are production-grade:** Config system (Zod + JSON5), secrets management with audit, cross-platform daemon service, process supervision — all battle-tested.
