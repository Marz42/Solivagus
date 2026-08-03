-- Solivagus workspace schema (Phase 1)
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_path TEXT NOT NULL,
  source_sha256 TEXT NOT NULL,
  display_name TEXT NOT NULL,
  page_count INTEGER,
  language TEXT,
  status TEXT NOT NULL,
  ocr_status TEXT,
  translation_status TEXT,
  qa_status TEXT,
  artifact_dir TEXT NOT NULL,
  active_config_hash TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(source_sha256)
);

CREATE TABLE IF NOT EXISTS ocr_batches (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  page_start INTEGER NOT NULL,
  page_end INTEGER NOT NULL,
  status TEXT NOT NULL,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  source_hash TEXT,
  config_hash TEXT,
  output_path TEXT,
  error_type TEXT,
  error_message TEXT,
  started_at TEXT,
  finished_at TEXT
);

CREATE TABLE IF NOT EXISTS structural_nodes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  parent_id INTEGER REFERENCES structural_nodes(id) ON DELETE SET NULL,
  node_type TEXT NOT NULL,
  sequence_index INTEGER NOT NULL,
  heading_level INTEGER,
  heading_path TEXT,
  source_pages TEXT,
  source_text TEXT,
  source_hash TEXT,
  token_count INTEGER,
  metadata_json TEXT
);

CREATE TABLE IF NOT EXISTS cache_partitions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  sequence_index INTEGER NOT NULL,
  source_tokens INTEGER,
  context_tokens INTEGER,
  unit_count INTEGER,
  prefix_hash TEXT,
  user_id TEXT,
  warmup_status TEXT,
  expected_cache_tokens INTEGER,
  actual_probe_hit_tokens INTEGER,
  status TEXT NOT NULL DEFAULT 'pending'
);

CREATE TABLE IF NOT EXISTS translation_units (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  partition_id INTEGER REFERENCES cache_partitions(id) ON DELETE SET NULL,
  unit_key TEXT NOT NULL,
  sequence_index INTEGER NOT NULL,
  heading_path TEXT,
  source_pages TEXT,
  source_text TEXT NOT NULL,
  source_hash TEXT NOT NULL,
  source_tokens INTEGER,
  estimated_output_tokens INTEGER,
  status TEXT NOT NULL,
  translation_text TEXT,
  translation_hash TEXT,
  provider TEXT,
  model TEXT,
  prompt_version TEXT,
  style_capsule_version TEXT,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  warning_flags TEXT,
  source_file TEXT,
  translated_file TEXT,
  UNIQUE(document_id, unit_key)
);

CREATE TABLE IF NOT EXISTS translation_attempts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  unit_id INTEGER NOT NULL REFERENCES translation_units(id) ON DELETE CASCADE,
  attempt_number INTEGER NOT NULL,
  request_hash TEXT,
  started_at TEXT,
  finished_at TEXT,
  latency_ms INTEGER,
  http_status INTEGER,
  finish_reason TEXT,
  prompt_tokens INTEGER,
  cache_hit_tokens INTEGER,
  cache_miss_tokens INTEGER,
  completion_tokens INTEGER,
  error_type TEXT,
  error_message TEXT,
  raw_response_path TEXT
);

CREATE TABLE IF NOT EXISTS style_capsules (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  version INTEGER NOT NULL,
  source_partition_id INTEGER,
  rules_json TEXT,
  terminology_json TEXT,
  examples_json TEXT,
  boundary_context_json TEXT,
  content_hash TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS artifacts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  artifact_type TEXT NOT NULL,
  path TEXT NOT NULL,
  content_hash TEXT,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
CREATE INDEX IF NOT EXISTS idx_units_document ON translation_units(document_id, sequence_index);
CREATE INDEX IF NOT EXISTS idx_units_status ON translation_units(status);
CREATE INDEX IF NOT EXISTS idx_nodes_document ON structural_nodes(document_id, sequence_index);
CREATE INDEX IF NOT EXISTS idx_partitions_document ON cache_partitions(document_id, sequence_index);
