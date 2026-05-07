CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    summary TEXT,
    domain_id TEXT,
    memory_type TEXT,
    importance REAL DEFAULT 0.5,
    stability REAL DEFAULT 0.0,
    confidence REAL DEFAULT 0.5,
    csd_score REAL DEFAULT 0.0,
    surprise REAL DEFAULT 0.0,
    recall_score REAL DEFAULT 0.0,
    curiosity REAL DEFAULT 0.0,
    focus REAL DEFAULT 0.0,
    clc_state TEXT,
    namespace TEXT DEFAULT 'global',
    created_at TEXT,
    updated_at TEXT,
    last_recalled TEXT,
    deprecated INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS vectors (
    memory_id TEXT PRIMARY KEY,
    embedding BLOB NOT NULL,
    dim INTEGER NOT NULL,
    FOREIGN KEY(memory_id) REFERENCES memories(id)
);

CREATE TABLE IF NOT EXISTS domains (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    namespace TEXT DEFAULT 'global',
    anchor_vector BLOB,
    effective_dimension REAL DEFAULT 1.0,
    drift_ema REAL DEFAULT 0.0,
    drift_var REAL DEFAULT 0.0,
    curvature_ema REAL DEFAULT 0.0,
    stability REAL DEFAULT 0.0,
    memory_count INTEGER DEFAULT 0,
    previous_update_direction BLOB,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS relations (
    id TEXT PRIMARY KEY,
    source_memory_id TEXT,
    target_memory_id TEXT,
    relation_type TEXT NOT NULL,
    weight REAL DEFAULT 1.0,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS contradictions (
    id TEXT PRIMARY KEY,
    new_memory_id TEXT,
    old_memory_id TEXT,
    contradiction_score REAL DEFAULT 0.0,
    status TEXT DEFAULT 'unresolved',
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    memory_id TEXT,
    event_type TEXT NOT NULL,
    value REAL,
    metadata TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS memory_sources (
    memory_id TEXT PRIMARY KEY,
    source TEXT,
    chunk_index INTEGER DEFAULT 0,
    metadata TEXT,
    created_at TEXT,
    FOREIGN KEY(memory_id) REFERENCES memories(id)
);

CREATE TABLE IF NOT EXISTS retrieval_feedback (
    id TEXT PRIMARY KEY,
    query TEXT,
    memory_id TEXT NOT NULL,
    label TEXT NOT NULL,
    rating REAL DEFAULT 0.0,
    rank INTEGER,
    retrieval_score REAL,
    notes TEXT,
    metadata TEXT,
    created_at TEXT,
    FOREIGN KEY(memory_id) REFERENCES memories(id)
);

CREATE TABLE IF NOT EXISTS agent_sessions (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    title TEXT,
    metadata TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS session_turns (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    query TEXT,
    answer TEXT,
    confidence REAL,
    conflict INTEGER DEFAULT 0,
    evidence_memory_ids TEXT,
    metadata TEXT,
    created_at TEXT,
    FOREIGN KEY(session_id) REFERENCES agent_sessions(id)
);

CREATE TABLE IF NOT EXISTS session_memory (
    session_id TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    metadata TEXT,
    created_at TEXT,
    updated_at TEXT,
    PRIMARY KEY(session_id, key),
    FOREIGN KEY(session_id) REFERENCES agent_sessions(id)
);

CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    command TEXT NOT NULL,
    metadata TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS domain_stats (
    id TEXT PRIMARY KEY,
    domain_id TEXT NOT NULL,
    drift REAL DEFAULT 0.0,
    curvature REAL DEFAULT 0.0,
    memory_count INTEGER DEFAULT 0,
    metadata TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS runtime_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_memories_domain ON memories(domain_id);
CREATE INDEX IF NOT EXISTS idx_memories_namespace ON memories(namespace);
CREATE INDEX IF NOT EXISTS idx_domains_namespace_name ON domains(namespace, name);
CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(memory_type);
CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at);
CREATE INDEX IF NOT EXISTS idx_events_memory ON events(memory_id);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_at);
CREATE INDEX IF NOT EXISTS idx_memory_sources_source ON memory_sources(source);
CREATE INDEX IF NOT EXISTS idx_retrieval_feedback_memory ON retrieval_feedback(memory_id);
CREATE INDEX IF NOT EXISTS idx_retrieval_feedback_label ON retrieval_feedback(label);
CREATE INDEX IF NOT EXISTS idx_retrieval_feedback_created ON retrieval_feedback(created_at);
CREATE INDEX IF NOT EXISTS idx_agent_sessions_agent ON agent_sessions(agent_id);
CREATE INDEX IF NOT EXISTS idx_agent_sessions_updated ON agent_sessions(updated_at);
CREATE INDEX IF NOT EXISTS idx_session_turns_session ON session_turns(session_id);
CREATE INDEX IF NOT EXISTS idx_session_turns_created ON session_turns(created_at);
CREATE INDEX IF NOT EXISTS idx_session_memory_session ON session_memory(session_id);
CREATE INDEX IF NOT EXISTS idx_relations_source ON relations(source_memory_id);
CREATE INDEX IF NOT EXISTS idx_relations_target ON relations(target_memory_id);
