"""Repository configuration loading and validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .diagnostics import Diagnostic, Severity
from .errors import ConfigFailure, ParseFailure
from .parser import FlatValue, load_flat_yaml_file


DEFAULT_KNOWLEDGE_ROOTS = ("memory-bank/knowledge", "docs/rfc")
DEFAULT_RESERVED_FILENAMES = ("index.md", "log.md")
DEFAULT_MACHINE_INDEX_PATH = ".paradigma/cache/knowledge-index.json"
DEFAULT_MEMORY_ROOT = "memory-bank/memories"
DEFAULT_CATALOG_PATH = ".paradigma/cache/catalog.sqlite3"


def _get_list(data: dict[str, FlatValue], key: str) -> tuple[str, ...]:
    value = data.get(key, [])
    if isinstance(value, list):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return (str(value).strip(),) if str(value).strip() else ()


def _get_scalar(
    data: dict[str, FlatValue], key: str, default: str = ""
) -> str:
    value = data.get(key, default)
    return "" if isinstance(value, list) else str(value).strip()


@dataclass(frozen=True)
class ParadigmaConfig:
    repository_root: Path
    config_path: Path
    config_schema_version: str
    okf_version: str
    installed_distribution_version: str
    knowledge_root_names: tuple[str, ...] = DEFAULT_KNOWLEDGE_ROOTS
    reserved_filenames: tuple[str, ...] = DEFAULT_RESERVED_FILENAMES
    generated_begin: str = "<!-- BEGIN PARADIGMA AUTO-INDEX -->"
    generated_end: str = "<!-- END PARADIGMA AUTO-INDEX -->"
    runtime_root_name: str = "memory-bank/runtime"
    logs_root_name: str = "memory-bank/logs"
    template_root_name: str = "memory-bank-template"
    machine_index_name: str = DEFAULT_MACHINE_INDEX_PATH
    memory_root_name: str = DEFAULT_MEMORY_ROOT
    catalog_name: str = DEFAULT_CATALOG_PATH
    raw: dict[str, FlatValue] = field(default_factory=dict, repr=False)

    @property
    def knowledge_roots(self) -> tuple[Path, ...]:
        return tuple(
            (self.repository_root / name).resolve()
            for name in self.knowledge_root_names
        )

    @property
    def machine_index_path(self) -> Path:
        return (self.repository_root / self.machine_index_name).resolve()

    @property
    def memory_root(self) -> Path:
        return (self.repository_root / self.memory_root_name).resolve()

    @property
    def catalog_path(self) -> Path:
        return (self.repository_root / self.catalog_name).resolve()

    def validate(self) -> tuple[Diagnostic, ...]:
        diagnostics: list[Diagnostic] = []
        source = str(self.config_path)
        required = {
            "config_schema_version": self.config_schema_version,
            "okf_version": self.okf_version,
            "installed_distribution_version": self.installed_distribution_version,
        }
        for field_name, value in required.items():
            if not value:
                diagnostics.append(
                    Diagnostic(
                        "PD_CONFIG_REQUIRED_FIELD",
                        f"missing required config field `{field_name}`",
                        source,
                    )
                )
        if not self.knowledge_root_names:
            diagnostics.append(
                Diagnostic(
                    "PD_CONFIG_KNOWLEDGE_ROOTS_EMPTY",
                    "knowledge_roots must contain at least one path",
                    source,
                )
            )
        if not self.generated_begin or not self.generated_end:
            diagnostics.append(
                Diagnostic(
                    "PD_CONFIG_MARKER_EMPTY",
                    "generated index markers must be non-empty",
                    source,
                )
            )
        elif self.generated_begin == self.generated_end:
            diagnostics.append(
                Diagnostic(
                    "PD_CONFIG_MARKERS_EQUAL",
                    "generated index begin and end markers must differ",
                    source,
                )
            )
        cache_root = (self.repository_root / ".paradigma" / "cache").resolve()
        try:
            self.machine_index_path.relative_to(cache_root)
        except ValueError:
            diagnostics.append(
                Diagnostic(
                    "PD_CONFIG_CACHE_PATH_INVALID",
                    "machine_index_path must stay inside .paradigma/cache/",
                    source,
                )
            )
        try:
            self.catalog_path.relative_to(cache_root)
        except ValueError:
            diagnostics.append(
                Diagnostic(
                    "PD_CONFIG_CATALOG_PATH_INVALID",
                    "catalog_path must stay inside .paradigma/cache/",
                    source,
                )
            )
        try:
            self.memory_root.relative_to(self.repository_root)
        except ValueError:
            diagnostics.append(
                Diagnostic(
                    "PD_CONFIG_MEMORY_ROOT_INVALID",
                    "memory_root must stay inside the repository",
                    source,
                )
            )
        else:
            try:
                self.memory_root.relative_to(cache_root)
            except ValueError:
                pass
            else:
                diagnostics.append(
                    Diagnostic(
                        "PD_CONFIG_MEMORY_ROOT_INVALID",
                        "memory_root must not be inside disposable .paradigma/cache/",
                        source,
                    )
                )
        for name, path in zip(self.knowledge_root_names, self.knowledge_roots):
            try:
                path.relative_to(self.repository_root)
            except ValueError:
                diagnostics.append(
                    Diagnostic(
                        "PD_CONFIG_PATH_OUTSIDE_REPOSITORY",
                        f"knowledge root is outside repository: {name}",
                        source,
                        severity=Severity.ERROR,
                    )
                )
        return tuple(diagnostics)


def load_config(repository_root: Path) -> ParadigmaConfig:
    root = repository_root.resolve()
    path = root / ".paradigma" / "config.yaml"
    try:
        raw = load_flat_yaml_file(path)
    except ParseFailure as error:
        raise ConfigFailure(error.diagnostic) from error
    config = ParadigmaConfig(
        repository_root=root,
        config_path=path,
        config_schema_version=_get_scalar(raw, "config_schema_version"),
        okf_version=_get_scalar(raw, "okf_version"),
        installed_distribution_version=_get_scalar(
            raw, "installed_distribution_version"
        ),
        knowledge_root_names=_get_list(raw, "knowledge_roots")
        or DEFAULT_KNOWLEDGE_ROOTS,
        reserved_filenames=_get_list(raw, "reserved_filenames")
        or DEFAULT_RESERVED_FILENAMES,
        generated_begin=_get_scalar(
            raw,
            "generated_markers.begin",
            "<!-- BEGIN PARADIGMA AUTO-INDEX -->",
        ),
        generated_end=_get_scalar(
            raw,
            "generated_markers.end",
            "<!-- END PARADIGMA AUTO-INDEX -->",
        ),
        runtime_root_name=_get_scalar(raw, "runtime_root", "memory-bank/runtime"),
        logs_root_name=_get_scalar(raw, "logs_root", "memory-bank/logs"),
        template_root_name=_get_scalar(raw, "template_root", "memory-bank-template"),
        machine_index_name=_get_scalar(
            raw, "machine_index_path", DEFAULT_MACHINE_INDEX_PATH
        ),
        memory_root_name=_get_scalar(raw, "memory_root", DEFAULT_MEMORY_ROOT),
        catalog_name=_get_scalar(raw, "catalog_path", DEFAULT_CATALOG_PATH),
        raw=raw,
    )
    return config


def require_valid_config(repository_root: Path) -> ParadigmaConfig:
    config = load_config(repository_root)
    diagnostics = config.validate()
    if diagnostics:
        raise ConfigFailure(diagnostics[0])
    return config
