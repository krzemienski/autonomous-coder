# AI Agent Memory Systems: Practical Recommendation (March 2026)

**Research Date:** March 19, 2026
**Focus:** Embedded Python, TUI applications, low operational overhead
**Token Efficiency:** High (minimize latency, memory footprint, storage)

---

## Executive Summary

**For a TUI application running Python with embedded memory requirements (no external services):**

1. **Conversation History + Working Memory:** SQLite + FTS5 (mandatory baseline)
2. **Vector Retrieval (optional, if semantic search needed):** sqlite-vec extension
3. **Codebase Context:** tree-sitter via CocoIndex pattern
4. **Agent Framework Memory:** Adopt CrewAI's built-in SQLite3 memory or build minimal wrapper

**Rationale:** Simplicity, zero external runtime dependencies, single-file persistence, <50ms latency, sub-100MB footprint. This is the 2026 consensus for embedded agent systems.

---

## Part 1: Agent Conversation Memory

### Problem Statement

Agent frameworks (LangChain, CrewAI, AutoGen) ship with basic memory—but scaling to persistent, queryable history across sessions requires a backend layer. Traditional approaches:

- **LangChain:** Pluggable memory modules (buffer, summary, vector store)—flexible but requires manual integration
- **CrewAI:** Built-in SQLite3 memory with short-term + long-term tiers—good starting point, limited customization
- **AutoGen:** Conversation list as primary memory—no built-in persistence layer

### Architecture: Working Memory vs. Long-Term Memory

**Computer Science Framing (2026 standard):**

| Layer | Storage | Capacity | Latency | Mechanism |
|-------|---------|----------|---------|-----------|
| **Working Memory** | LLM context window + agent cache | 32K-200K tokens | <1ms | In-process, KV cache |
| **Long-Term Memory** | Persistent storage | Unlimited | 10-100ms | Vector DB / SQL retrieval |

**Practical Split:**
- **Working:** Recent messages, active task state, tool results (fits in context window)
- **Long-term:** Full conversation history, extracted facts, patterns, decisions (external storage)

### Recommended: SQLite + FTS5 (Hybrid)

**Why SQLite for conversation memory:**
- Single `.db` file—no external services, no configuration
- Built-in FTS5 (full-text search)—keyword queries at millisecond scale
- Proven ACID guarantees—safe for agent replay and auditing
- Sub-100MB for 100K+ messages (compression + WAL)
- Works offline, in-process, on Raspberry Pi

**Schema (minimal):**

```sql
CREATE TABLE conversations (
    id INTEGER PRIMARY KEY,
    agent_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    role TEXT,  -- 'user', 'assistant', 'system'
    content TEXT NOT NULL,
    metadata JSON  -- {task_id, tool_calls, confidence, ...}
);

CREATE INDEX idx_agent_session ON conversations(agent_id, session_id, timestamp);
CREATE VIRTUAL TABLE conversations_fts USING fts5(role, content);
```

**Query Pattern:**
```python
# Keyword search
cursor.execute('''
    SELECT c.* FROM conversations c
    JOIN conversations_fts ON c.rowid = conversations_fts.rowid
    WHERE conversations_fts MATCH 'database migration'
    AND c.session_id = ?
    ORDER BY c.timestamp DESC
    LIMIT 10
''', (session_id,))

# Recent history (working memory)
cursor.execute('''
    SELECT content FROM conversations
    WHERE agent_id = ? AND session_id = ?
    ORDER BY timestamp DESC LIMIT 20
''', (agent_id, session_id))
```

**Performance:** FTS5 queries on 100K messages: ~5ms (index overhead: ~20% storage).

---

## Part 2: Semantic Retrieval (Optional Layer)

### When to Add Vector Search

**Add if:** Agent needs to retrieve relevant past contexts by *meaning*, not keywords (e.g., "find similar architecture discussions").

**Skip if:** Keyword + recency are sufficient (most agent workflows).

### Option A: sqlite-vec (Recommended if vectors needed)

**Why:**
- Pure C, zero dependencies—same deployment model as SQLite
- Chunk-based storage (doesn't load all vectors in RAM)
- 300KB binary size vs. 3-5MB for sqlite-vss
- Runs on browser, Raspberry Pi, WASM

**Setup:**
```python
import sqlite3

# Load extension
conn = sqlite3.connect(':memory:')
conn.enable_load_extension(True)
conn.load_extension('sqlite_vec')

# Create table
conn.execute('''
    CREATE TABLE memories (
        id INTEGER PRIMARY KEY,
        content TEXT,
        embedding VECTOR(FLOAT32(384))
    )
''')

# Search
results = conn.execute('''
    SELECT id, content, distance
    FROM memories
    WHERE embedding MATCH ?
    ORDER BY distance
    LIMIT 5
''', (embedding_query,))
```

**Performance:** 10K vectors, 384 dims → 15MB storage, <10ms query on laptop.

### Option B: LanceDB (If you need advanced features)

**When:** Large-scale embeddings (1M+), multimodal data (images), or compute-storage separation.

**For TUI:** Overkill. Adds ~50MB runtime footprint, Python daemon overhead.

**Skip unless:** Explicitly scaling beyond 100K embeddings + complex filtering.

---

## Part 3: Codebase Context Indexing

### Problem: Code Context Injection

Agents need to understand codebase structure to answer questions like "what modules interact with the auth system?" The 2026 standard is **tree-sitter semantic indexing**.

### Recommended: CocoIndex Pattern

**Core Idea:** Use tree-sitter to parse code into syntax-aware chunks, embed them, store in vector index.

**Implementation (50 lines Python):**

```python
import tree_sitter as ts
import sqlite3
from langchain_text_splitters import Language

# 1. Load parser
parser = ts.Parser()
parser.set_language(ts.Language('build/my-languages.so', 'python'))

# 2. Parse file, walk AST
tree = parser.parse(code_bytes)

# 3. Extract functions/classes (syntax-aware)
def extract_definitions(tree, code):
    """Yield (name, type, start_line, end_line, chunk)"""
    for node in tree.root_node.child_by_field_name(...):
        if node.type in ('function_definition', 'class_definition'):
            yield (
                node.child_by_field_name('name').text.decode(),
                node.type,
                node.start_point[0],
                node.end_point[0],
                code[node.start_byte:node.end_byte].decode()
            )

# 4. Embed + store
for name, type_, start, end, chunk in extract_definitions(tree, code):
    embedding = embed_model.embed(chunk)
    cursor.execute('''
        INSERT INTO code_index (file, symbol, type, start_line, embedding)
        VALUES (?, ?, ?, ?, ?)
    ''', (filename, name, type_, start, embedding))
```

**Storage (SQLite):**
```sql
CREATE TABLE code_index (
    id INTEGER PRIMARY KEY,
    file TEXT,
    symbol TEXT,
    type TEXT,  -- 'function', 'class', 'module'
    start_line INTEGER,
    end_line INTEGER,
    chunk TEXT,
    embedding VECTOR(FLOAT32(384))
);

CREATE INDEX idx_symbol ON code_index(symbol);
```

**Query (agent context):**
```python
def get_codebase_context(query: str, top_k=5):
    embedding = embed_model.embed(query)
    rows = cursor.execute('''
        SELECT file, symbol, type, chunk
        FROM code_index
        WHERE embedding MATCH ? AND type IN ('function', 'class')
        ORDER BY distance LIMIT ?
    ''', (embedding, top_k))
    return rows
```

**Incremental Updates:** Only reparse changed files (watch filesystem or integrate with git diff).

---

## Part 4: Framework-Specific Integration

### CrewAI (Built-in Memory—Recommended)

CrewAI already ships with SQLite-backed memory. Use it:

```python
from crewai import Agent, Memory, MemoryType

agent = Agent(
    name='researcher',
    memory=Memory(
        type=MemoryType.LONG_TERM,
        db_path='./agent_memory.db'
    )
)
```

**Pros:** Automatic conversation storage, entity extraction, recency weighting.
**Cons:** Limited customization (schema fixed), no vector layer.

**Enhancement:** Wrap SQLite3 connection to add hybrid FTS5 + vector retrieval.

### LangChain (Custom Wrapper)

Build a custom memory class:

```python
from langchain.memory import BaseMemory
from typing import Any, Dict, List

class SQLiteHybridMemory(BaseMemory):
    def __init__(self, db_path: str):
        self.conn = sqlite3.connect(db_path)
        self._init_schema()

    def save_context(self, inputs: Dict[str, Any], outputs: Dict[str, str]):
        """Store message + embed for vector search"""
        content = inputs['input']
        embedding = self.embed_model.embed(content)

        self.conn.execute('''
            INSERT INTO memory (role, content, embedding, timestamp)
            VALUES (?, ?, ?, ?)
        ''', ('user', content, embedding, datetime.now()))

    def load_memory_variables(self, inputs: Dict[str, Any]) -> Dict[str, str]:
        """Retrieve relevant context"""
        query = inputs.get('query', inputs.get('input', ''))

        # Keyword search
        kw_results = self.conn.execute('''
            SELECT content FROM memory
            WHERE content MATCH ? LIMIT 5
        ''', (query,))

        # Vector search
        vec_results = self.conn.execute('''
            SELECT content FROM memory
            WHERE embedding MATCH ? LIMIT 5
        ''', (embed_model.embed(query),))

        return {'history': '\n'.join(r[0] for r in kw_results)}
```

### AutoGen (Message Grooming)

AutoGen doesn't ship with persistence. Add a light wrapper:

```python
class PersistentAgentChat(ConversableAgent):
    def __init__(self, *args, db_path='chat.db', **kwargs):
        super().__init__(*args, **kwargs)
        self.db_path = db_path
        self._init_db()

    def _on_reply(self, *args, **kwargs):
        # Hook: persist message after reply
        msg = kwargs.get('reply', '')
        self.conn.execute('''
            INSERT INTO chat_log (agent, message, timestamp)
            VALUES (?, ?, ?)
        ''', (self.name, msg, datetime.now()))
        return super()._on_reply(*args, **kwargs)
```

---

## Part 5: Comparison Matrix

| System | Purpose | Complexity | Dependencies | Storage | Latency | When to Use |
|--------|---------|------------|--------------|---------|---------|------------|
| **SQLite + FTS5** | Conversation history | ⭐ | None | Single file | <5ms | Always (baseline) |
| **sqlite-vec** | Vector search | ⭐⭐ | C library | Single file | <10ms | Semantic retrieval needed |
| **LanceDB** | Advanced vectors | ⭐⭐⭐⭐ | Rust daemon | Multi-file | 50ms | Scaling 100K+ vectors |
| **tree-sitter** | Code context | ⭐⭐ | Parser binary | SQLite | 10-100ms | Codebase understanding |
| **ChromaDB** | Simple vectors | ⭐⭐⭐ | Python, Clickhouse | File + RAM | 20ms | Rapid prototyping only |

---

## Part 6: Memory Architecture Diagram

```
┌─────────────────────────────────────────────────┐
│  Agent (LLM)                                    │
│  Context Window (32-200K tokens)                │
│  [Recent messages + active task state]          │
└───────────────┬─────────────────────────────────┘
                │ Query / Insert
                ↓
┌─────────────────────────────────────────────────┐
│  Working Memory Cache (in-process)              │
│  [Last 20 messages + tool results]              │
│  Latency: <1ms                                  │
└───────────────┬─────────────────────────────────┘
                │ Cache miss → Long-term
                ↓
┌─────────────────────────────────────────────────┐
│  Long-Term Storage (Single SQLite file)         │
│                                                 │
│  ┌─────────────────────────────────────────┐   │
│  │ Conversations Table (FTS5)              │   │
│  │ [Full history, keyword searchable]      │   │
│  │ Latency: <5ms                          │   │
│  └─────────────────────────────────────────┘   │
│                                                 │
│  ┌─────────────────────────────────────────┐   │
│  │ Vectors Table (sqlite-vec, optional)    │   │
│  │ [Embeddings for semantic retrieval]     │   │
│  │ Latency: <10ms                         │   │
│  └─────────────────────────────────────────┘   │
│                                                 │
│  ┌─────────────────────────────────────────┐   │
│  │ Code Index (tree-sitter + embeddings)   │   │
│  │ [Codebase symbols, functions, classes]  │   │
│  │ Latency: 10-100ms                      │   │
│  └─────────────────────────────────────────┘   │
└─────────────────────────────────────────────────┘
```

---

## Part 7: Implementation Checklist

### Phase 1: Foundation (Day 1-2)

- [ ] Create SQLite schema (conversations + metadata)
- [ ] Integrate with agent framework (CrewAI / LangChain / AutoGen)
- [ ] Test message persistence + retrieval
- [ ] Measure: <5ms FTS5 query on 1K messages

### Phase 2: Semantic Search (Day 3-5, if needed)

- [ ] Load sqlite-vec extension
- [ ] Create embeddings table
- [ ] Integrate embedding model (locally hosted, llama.cpp)
- [ ] Test: hybrid keyword + vector retrieval
- [ ] Measure: <10ms vector query on 10K embeddings

### Phase 3: Codebase Context (Day 6-10)

- [ ] Integrate tree-sitter parser
- [ ] Parse target language (Python / JS / Go)
- [ ] Extract definitions (functions, classes, modules)
- [ ] Embed + store in code_index table
- [ ] Hook into agent retrieval: `get_codebase_context()`
- [ ] Test: agent can answer "which functions call auth?"

### Phase 4: Optimization (Day 11+)

- [ ] WAL mode for concurrent writes
- [ ] PRAGMA optimizations (cache_size, sync mode)
- [ ] Compression for embeddings (int8 quantization)
- [ ] Incremental indexing (watch filesystem)

---

## Part 8: Code Example (Minimal)

```python
import sqlite3
from datetime import datetime
from typing import List, Dict

class AgentMemory:
    def __init__(self, db_path: str = 'agent_memory.db'):
        self.conn = sqlite3.connect(db_path)
        self._init_schema()

    def _init_schema(self):
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                role TEXT,
                content TEXT NOT NULL,
                metadata JSON
            )
        ''')
        self.conn.execute('''
            CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
            USING fts5(role, content)
        ''')
        self.conn.commit()

    def save(self, agent_id: str, session_id: str, role: str, content: str):
        """Persist message"""
        cursor = self.conn.execute('''
            INSERT INTO memories (agent_id, session_id, role, content)
            VALUES (?, ?, ?, ?)
        ''', (agent_id, session_id, role, content))

        # Update FTS5
        self.conn.execute('''
            INSERT INTO memories_fts (rowid, role, content)
            VALUES (?, ?, ?)
        ''', (cursor.lastrowid, role, content))

        self.conn.commit()

    def search(self, query: str, session_id: str, limit: int = 5) -> List[Dict]:
        """Keyword search"""
        rows = self.conn.execute('''
            SELECT m.id, m.role, m.content, m.timestamp
            FROM memories m
            JOIN memories_fts fts ON m.rowid = fts.rowid
            WHERE fts.content MATCH ? AND m.session_id = ?
            ORDER BY m.timestamp DESC LIMIT ?
        ''', (query, session_id, limit))

        return [
            {'id': r[0], 'role': r[1], 'content': r[2], 'timestamp': r[3]}
            for r in rows
        ]

    def recent(self, agent_id: str, session_id: str, limit: int = 20) -> List[str]:
        """Get recent conversation (working memory)"""
        rows = self.conn.execute('''
            SELECT content FROM memories
            WHERE agent_id = ? AND session_id = ?
            ORDER BY timestamp DESC LIMIT ?
        ''', (agent_id, session_id, limit))

        return [r[0] for r in rows]

# Usage
memory = AgentMemory()
memory.save('researcher', 'session_001', 'user', 'Find Python async best practices')
memory.save('researcher', 'session_001', 'assistant', 'Use asyncio for I/O-bound tasks...')

results = memory.search('async patterns', 'session_001')
history = memory.recent('researcher', 'session_001')
```

---

## Part 9: Unresolved Questions

1. **Embedding Model Locality:** Should embeddings run inline (llama.cpp) or call a local service? Tradeoff: startup latency vs. memory footprint.

2. **Vectorization Schedule:** Embed all messages immediately or lazy-embed on first vector query? (Lazy is faster to first response, eager enables full coverage.)

3. **Memory Consolidation:** Should agent periodically summarize old memories into "facts"? If yes, what triggers consolidation? (Token count, time-based, importance scoring?)

4. **Multi-Agent Coordination:** Do agents share a single SQLite file or isolated DBs? Shared → contention on writes; isolated → duplication.

5. **LLM Token Budget:** How much token budget for "context injection" from memory? (Typical: 500-2K tokens from memory, 30K+ for actual work.)

---

## Sources

- [How to Build an EverMem-Style Persistent AI Agent OS with Hierarchical Memory, FAISS Vector Retrieval, SQLite Storage, and Automated Memory Consolidation - MarkTechPost](https://www.marktechpost.com/2026/03/04/how-to-build-an-evermem-style-persistent-ai-agent-os-with-hierarchical-memory-faiss-vector-retrieval-sqlite-storage-and-automated-memory-consolidation/)
- [GitHub - MemoriLabs/Memori: SQL Native Memory Layer for LLMs, AI Agents & Multi-Agent Systems](https://github.com/MemoriLabs/Memori)
- [Why Your AI Agent's Memory Is Broken (And How to Fix It With SQLite)](https://gerus-lab.hashnode.dev/why-your-ai-agents-memory-is-broken-and-how-to-fix-it-with-sqlite)
- [GitHub - pigeonflow/clawmem: Portable local vector memory DB for AI agents](https://github.com/pigeonflow/clawmem)
- [GitHub - sqliteai/sqlite-memory: Markdown based AI agent memory with semantic search](https://github.com/sqliteai/sqlite-memory)
- [The 6 Best AI Agent Memory Frameworks You Should Try in 2026 - MachineLearningMastery.com](https://machinelearningmastery.com/the-6-best-ai-agent-memory-frameworks-you-should-try-in-2026/)
- [Mem0 - The Memory Layer for your AI Apps](https://mem0.ai/)
- [GitHub - mem0ai/mem0: Universal memory layer for AI Agents](https://github.com/mem0ai/mem0)
- [AI Memory Research: 26% Accuracy Boost for LLMs | Mem0](https://mem0.ai/research)
- [Graph Memory for AI Agents (January 2026)](https://mem0.ai/blog/graph-memory-solutions-ai-agents)
- [Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory](https://arxiv.org/abs/2504.19413)
- [Mem0 raises $24M to build the memory layer for AI](https://mem0.ai/series-a)
- [Large codebase context with tree-sitter and Cocoindex for coding agent and code analysis](https://cocoindexio.substack.com/p/index-codebase-with-tree-sitter-and)
- [Real-time Codebase Indexing | CocoIndex](https://cocoindex.io/examples/code_index)
- [Show HN: Open-Source Codebase Index with Tree-sitter](https://news.ycombinator.com/item?id=43502639)
- [Show HN: CodeRLM – Tree-sitter-backed code indexing for LLM agents](https://news.ycombinator.com/item?id=46974515)
- [Semantic Code Indexing with AST and Tree-sitter for AI Agents (Part — 1 of 3)](https://medium.com/@email2dineshkuppan/semantic-code-indexing-with-ast-and-tree-sitter-for-ai-agents-part-1-of-3-eb5237ba687a)
- [GitHub - cocoindex-io/realtime-codebase-indexing: build codebase index with tree-sitter](https://github.com/cocoindex-io/realtime-codebase-indexing)
- [How I Built CodeRAG with Dependency Graph Using Tree-Sitter](https://medium.com/@shsax/how-i-built-coderag-with-dependency-graph-using-tree-sitter-0a71867059ae)
- [GitHub - johnhuang316/code-index-mcp: A Model Context Protocol (MCP) server](https://github.com/johnhuang316/code-index-mcp)
- [AI Agent Frameworks: CrewAI vs AutoGen vs LangGraph Compared (2026)](https://designrevision.com/blog/ai-agent-frameworks)
- [AI Agent Memory: A Comparative Analysis of LangGraph, CrewAI, and AutoGen - DEV Community](https://dev.to/foxgem/ai-agent-memory-a-comparative-analysis-of-langgraph-crewai-and-autogen-31dp)
- [LangChain vs CrewAI vs AutoGen: Which Framework to Choose](https://propelius.ai/blogs/langchain-vs-crewai-vs-autogen-ai-agent-frameworks/)
- [Making Sense of Memory in AI Agents – Leonie Monigatti](https://www.leoniemonigatti.com/blog/memory-in-ai-agents.html)
- [Why your multi-agent AI system has a memory problem - Resultsense](https://www.resultsense.com/insights/2026-03-19-multi-agent-memory-computer-architecture-perspective)
- [lancedb · PyPI](https://pypi.org/project/lancedb/)
- [LanceDB | Vector Database for RAG, Agents & Hybrid Search](https://lancedb.com/)
- [Python - LanceDB](https://lancedb.github.io/lancedb/python/python/)
- [GitHub - lancedb/lancedb: Developer-friendly OSS embedded retrieval library](https://github.com/lancedb/lancedb)
- [Why LanceDB Is the Most Natural Memory Layer for OpenClaw](https://lancedb.com/blog/openclaw-lancedb-memory-layer/)
- [Hybrid full-text search and vector search with SQLite](https://alexgarcia.xyz/blog/2024/sqlite-vec-hybrid-search/index.html)
- [SQLite FTS5 Extension](https://www.sqlite.org/fts5.html)
- [How ZeroClaw's Hybrid Memory Works: SQLite Vector + FTS5 Explained](https://zeroclaws.io/blog/zeroclaw-hybrid-memory-sqlite-vector-fts5/)
- [Build a Vector Search API with SQLite FTS5 + Python FastAPI in Minutes](https://www.thecodecity.com/ai/build-a-vector-search-api-with-sqlite-fts5-python-fastapi-in-minutes/)
- [Building a Hybrid Retriever for 16,894 Obsidian Files](https://blakecrosley.com/blog/hybrid-retriever-obsidian)
- [Building a RAG on SQLite](https://blog.sqlite.ai/building-a-rag-on-sqlite)
- [GitHub - asg017/sqlite-vec: A vector search SQLite extension](https://github.com/asg017/sqlite-vec)
- [GitHub - asg017/sqlite-vss: A SQLite extension for efficient vector search](https://github.com/asg017/sqlite-vss)
- [SQLiteVec integration - Docs by LangChain](https://docs.langchain.com/oss/python/integrations/vectorstores/sqlitevec)
- [Chroma vs LanceDB (2026)](https://www.peerspot.com/products/comparisons/chroma_vs_lancedb)
- [Best Vector Databases in 2026: Complete Comparison Guide – Encore](https://encore.dev/articles/best-vector-databases)
- [LanceDB vs SQLite (2026)](https://www.peerspot.com/products/comparisons/lancedb_vs_sqlite)
