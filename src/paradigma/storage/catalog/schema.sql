PRAGMA foreign_keys = ON;
PRAGMA journal_mode = DELETE;
PRAGMA synchronous = FULL;

CREATE TABLE catalog_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
) WITHOUT ROWID;

CREATE TABLE memories (
    memory_id TEXT PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    content TEXT NOT NULL,
    memory_type TEXT NOT NULL,
    tags_json TEXT NOT NULL,
    status TEXT NOT NULL,
    scope_json TEXT NOT NULL,
    scope_namespace TEXT NOT NULL,
    workspace_id TEXT,
    project_id TEXT,
    task_id TEXT,
    session_id TEXT,
    entity_ids_json TEXT NOT NULL,
    valid_from TEXT,
    valid_until TEXT,
    confidence REAL,
    sensitivity TEXT NOT NULL,
    provenance_json TEXT NOT NULL,
    provenance_summary TEXT NOT NULL,
    relations_json TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision >= 1),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX memories_status_idx ON memories(status, memory_id);
CREATE INDEX memories_type_idx ON memories(memory_type, memory_id);
CREATE INDEX memories_scope_idx ON memories(
    scope_namespace, workspace_id, project_id, task_id, session_id, memory_id
);
CREATE INDEX memories_validity_idx ON memories(valid_from, valid_until, memory_id);

CREATE TABLE memory_tags (
    memory_id TEXT NOT NULL REFERENCES memories(memory_id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    tag TEXT NOT NULL,
    PRIMARY KEY (memory_id, position),
    UNIQUE (memory_id, tag)
) WITHOUT ROWID;
CREATE INDEX memory_tags_lookup_idx ON memory_tags(tag, memory_id);

CREATE TABLE memory_relations (
    memory_id TEXT NOT NULL REFERENCES memories(memory_id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    relation_type TEXT NOT NULL,
    target_memory_id TEXT NOT NULL,
    PRIMARY KEY (memory_id, position),
    UNIQUE (memory_id, relation_type, target_memory_id)
) WITHOUT ROWID;
CREATE INDEX memory_relations_target_idx ON memory_relations(
    target_memory_id, relation_type, memory_id
);

CREATE VIRTUAL TABLE memory_fts USING fts5(
    memory_id UNINDEXED,
    title,
    description,
    content,
    tags,
    tokenize = 'unicode61 remove_diacritics 2'
);
