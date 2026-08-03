"""Derived SQLite + FTS5 memory catalog."""

from .query import CatalogQuery, CatalogTextMode

from .sqlite import (
    CATALOG_SCHEMA_VERSION,
    CatalogFailure,
    CatalogRebuildResult,
    CatalogStats,
    CatalogVerification,
    CatalogQueryFailure,
    CatalogWriteFailure,
    SQLiteMemoryCatalog,
)

__all__ = [
    "CATALOG_SCHEMA_VERSION",
    "CatalogFailure",
    "CatalogQuery",
    "CatalogQueryFailure",
    "CatalogRebuildResult",
    "CatalogStats",
    "CatalogTextMode",
    "CatalogVerification",
    "CatalogWriteFailure",
    "SQLiteMemoryCatalog",
]
