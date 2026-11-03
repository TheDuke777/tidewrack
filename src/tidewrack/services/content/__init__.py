"""Reads the content files bundled with the app and hands them to the pure loader.

Content lives in ``src/content/`` so ``flet build`` packages it (it bundles only
``src/``). This is the only place that touches those files on disk.
"""

from __future__ import annotations

from pathlib import Path

from tidewrack.core.data.loader import Content, load_content

CONTENT_ROOT = Path(__file__).resolve().parents[3] / "content"


def read_content_files(root: Path = CONTENT_ROOT) -> dict[str, str]:
    """{relative posix path: text} for every non-hidden file under `root`."""
    return {
        path.relative_to(root).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(root.rglob("*"))
        if path.is_file() and not any(part.startswith(".") for part in path.relative_to(root).parts)
    }


def load_bundled_content() -> Content:
    return load_content(read_content_files())
