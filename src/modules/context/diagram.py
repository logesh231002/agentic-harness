"""Mermaid diagram generator: reads imports from source files and produces architecture diagrams."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path


class DiagramError(Exception):
    """Raised when diagram generation fails."""


@dataclass(frozen=True)
class DiagramConfig:
    scan_dirs: list[str] = field(default_factory=lambda: ["src"])
    extensions: list[str] = field(default_factory=lambda: [".py"])
    output_path: Path = Path(".claude/diagrams/architecture.mmd")


@dataclass(frozen=True)
class ModuleDependency:
    source: str
    target: str


def parse_imports(file_path: Path, project_root: Path) -> list[str]:
    """Extract project-internal import targets from a Python source file.

    Only imports whose top-level package starts with ``src.`` are returned.
    Each returned string is the full dotted module path (e.g. ``src.config.schema``).
    """
    try:
        source = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DiagramError(f"Cannot read {file_path}: {exc}") from exc

    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError as exc:
        raise DiagramError(f"Syntax error in {file_path}: {exc}") from exc

    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("src."):
                    modules.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None and node.module.startswith("src."):
                modules.append(node.module)
    return modules


def _module_to_package(module_name: str) -> str:
    """Simplify a dotted module path to its package level.

    ``src.modules.context.scoped_rules`` becomes ``src.modules.context``.
    Modules with fewer than three dots are returned as-is.
    """
    parts = module_name.split(".")
    if len(parts) > 3:
        return ".".join(parts[:3])
    return module_name


def _file_to_package(file_path: Path, project_root: Path) -> str:
    """Convert a file path to its package-level dotted module name."""
    relative = file_path.relative_to(project_root)
    parts = list(relative.with_suffix("").parts)
    module_name = ".".join(parts)
    return _module_to_package(module_name)


def build_dependency_graph(project_root: Path, config: DiagramConfig) -> list[ModuleDependency]:
    """Scan source files and build a deduplicated list of package-level dependencies."""
    seen: set[tuple[str, str]] = set()
    dependencies: list[ModuleDependency] = []

    for scan_dir in config.scan_dirs:
        root_dir = project_root / scan_dir
        if not root_dir.is_dir():
            continue
        for ext in config.extensions:
            for file_path in sorted(root_dir.rglob(f"*{ext}")):
                source_pkg = _file_to_package(file_path, project_root)
                imports = parse_imports(file_path, project_root)
                for imp in imports:
                    target_pkg = _module_to_package(imp)
                    if source_pkg == target_pkg:
                        continue
                    edge = (source_pkg, target_pkg)
                    if edge not in seen:
                        seen.add(edge)
                        dependencies.append(ModuleDependency(source=source_pkg, target=target_pkg))

    return dependencies


def generate_mermaid(dependencies: list[ModuleDependency]) -> str:
    """Produce a Mermaid ``graph TD`` diagram from dependency edges."""
    lines: list[str] = ["graph TD"]
    for dep in dependencies:
        lines.append(f"    {dep.source} --> {dep.target}")
    return "\n".join(lines) + "\n"


def write_diagram(project_root: Path, config: DiagramConfig | None = None) -> Path:
    """Build the dependency graph, generate Mermaid output, and write to disk.

    Creates parent directories if needed.  Overwrites any existing file at
    the configured output path.  Returns the absolute path of the written file.
    """
    cfg = config if config is not None else DiagramConfig()
    dependencies = build_dependency_graph(project_root, cfg)
    mermaid = generate_mermaid(dependencies)

    output = project_root / cfg.output_path
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(mermaid, encoding="utf-8")
    return output
