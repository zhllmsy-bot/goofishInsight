from __future__ import annotations

import sys
from pathlib import Path


def _prepend_if_present(path: Path, package_name: str) -> None:
    if not (path / package_name).exists():
        return
    path_text = str(path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)


def ensure_analyzer_src_on_path() -> None:
    apps_dir = Path(__file__).resolve().parents[3]
    repo_root = apps_dir.parent
    analyzer_src = apps_dir / "analyzer" / "src"
    schema_src = repo_root / "packages" / "schema" / "src"
    _prepend_if_present(analyzer_src, "goofish_analyzer")
    _prepend_if_present(schema_src, "goofish_schema")
