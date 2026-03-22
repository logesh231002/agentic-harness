"""Tests for the Mermaid diagram generator."""

from __future__ import annotations

from pathlib import Path

from src.modules.context.diagram import (
    DiagramConfig,
    ModuleDependency,
    build_dependency_graph,
    generate_mermaid,
    parse_imports,
    write_diagram,
)


def _write_py(directory: Path, name: str, content: str) -> Path:
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


class TestParseImports:
    def test_extracts_from_import(self, tmp_path: Path) -> None:
        f = _write_py(tmp_path, "mod.py", "from src.config.schema import AppConfig\n")

        result = parse_imports(f, tmp_path)

        assert result == ["src.config.schema"]

    def test_extracts_plain_import(self, tmp_path: Path) -> None:
        f = _write_py(tmp_path, "mod.py", "import src.modules.context\n")

        result = parse_imports(f, tmp_path)

        assert result == ["src.modules.context"]

    def test_ignores_stdlib_imports(self, tmp_path: Path) -> None:
        f = _write_py(tmp_path, "mod.py", "import os\nfrom pathlib import Path\n")

        result = parse_imports(f, tmp_path)

        assert result == []

    def test_ignores_third_party_imports(self, tmp_path: Path) -> None:
        f = _write_py(tmp_path, "mod.py", "import yaml\nfrom pydantic import BaseModel\n")

        result = parse_imports(f, tmp_path)

        assert result == []


class TestBuildDependencyGraph:
    def test_builds_graph_from_files(self, tmp_path: Path) -> None:
        src = tmp_path / "src" / "modules" / "context"
        src.mkdir(parents=True)
        _write_py(src, "alpha.py", "from src.config.schema import AppConfig\n")
        _write_py(src, "beta.py", "from src.modules.routing import route\n")

        config = DiagramConfig(scan_dirs=["src"], extensions=[".py"])
        result = build_dependency_graph(tmp_path, config)

        sources = {d.source for d in result}
        targets = {d.target for d in result}
        assert "src.modules.context" in sources
        assert "src.config" in targets or "src.config.schema" in targets
        assert "src.modules.routing" in targets

    def test_deduplicates_edges(self, tmp_path: Path) -> None:
        src = tmp_path / "src" / "modules" / "context"
        src.mkdir(parents=True)
        _write_py(src, "a.py", "from src.config.schema import AppConfig\n")
        _write_py(src, "b.py", "from src.config.schema import AppConfig\n")

        config = DiagramConfig(scan_dirs=["src"], extensions=[".py"])
        result = build_dependency_graph(tmp_path, config)

        edges = [(d.source, d.target) for d in result]
        assert len(edges) == len(set(edges))

    def test_handles_circular_imports(self, tmp_path: Path) -> None:
        pkg_a = tmp_path / "src" / "modules" / "alpha"
        pkg_b = tmp_path / "src" / "modules" / "beta"
        pkg_a.mkdir(parents=True)
        pkg_b.mkdir(parents=True)
        _write_py(pkg_a, "mod.py", "from src.modules.beta import something\n")
        _write_py(pkg_b, "mod.py", "from src.modules.alpha import something\n")

        config = DiagramConfig(scan_dirs=["src"], extensions=[".py"])
        result = build_dependency_graph(tmp_path, config)

        edge_set = {(d.source, d.target) for d in result}
        assert ("src.modules.alpha", "src.modules.beta") in edge_set
        assert ("src.modules.beta", "src.modules.alpha") in edge_set


class TestGenerateMermaid:
    def test_produces_valid_mermaid_syntax(self) -> None:
        deps = [ModuleDependency(source="src.config", target="src.modules.context")]

        result = generate_mermaid(deps)

        assert result.startswith("graph TD")
        assert "-->" in result

    def test_empty_dependencies_produces_empty_graph(self) -> None:
        result = generate_mermaid([])

        assert result.strip() == "graph TD"


class TestWriteDiagram:
    def test_writes_file_to_output_path(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        _write_py(src, "main.py", "import os\n")
        output = tmp_path / "out" / "arch.mmd"

        config = DiagramConfig(scan_dirs=["src"], extensions=[".py"], output_path=Path("out/arch.mmd"))
        result = write_diagram(tmp_path, config)

        assert result == output
        assert output.exists()
        content = output.read_text(encoding="utf-8")
        assert content.startswith("graph TD")

    def test_overwrites_existing_file(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        _write_py(src, "main.py", "import os\n")
        output_path = Path("out/arch.mmd")
        config = DiagramConfig(scan_dirs=["src"], extensions=[".py"], output_path=output_path)

        write_diagram(tmp_path, config)
        write_diagram(tmp_path, config)

        output = tmp_path / output_path
        assert output.exists()
        files = list((tmp_path / "out").iterdir())
        assert len(files) == 1
