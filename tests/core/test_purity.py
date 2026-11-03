"""Import-lint for core purity (CLAUDE.md §2, §11).

core/ must run unchanged on Android, desktop and (maybe) Pyodide, and must be
deterministic: no UI or services imports, no file/network/process I/O, no clock,
no system randomness. Everything in src/ gets its randomness from core.rng.
"""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
CORE = SRC / "tidewrack" / "core"

FORBIDDEN_MODULES = {
    # UI and app layers
    "flet", "tidewrack.ui", "tidewrack.services", "tidewrack.version",
    # file, OS, process and network I/O
    "os", "io", "sys", "pathlib", "shutil", "glob", "tempfile", "fileinput",
    "subprocess", "multiprocessing", "threading", "asyncio", "signal",
    "socket", "ssl", "http", "urllib", "ftplib", "smtplib", "requests", "httpx",
    "sqlite3", "shelve", "dbm", "pickle", "marshal", "importlib", "ctypes",
    "logging", "webbrowser", "platform",
    # nondeterminism
    "random", "secrets", "time", "uuid",
}  # fmt: skip
FORBIDDEN_CALLS = {"open", "print", "input", "exec", "eval", "compile", "__import__", "breakpoint"}


def _module_name(path: Path, src: Path) -> str:
    rel = path.relative_to(src).with_suffix("")
    parts = rel.parts[:-1] if rel.name == "__init__" else rel.parts
    return ".".join(parts)


def _imports(path: Path, src: Path = SRC) -> list[tuple[int, str]]:
    """(line, absolute module name) for every import in `path`."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    module_name = _module_name(path, src)
    package = module_name if path.name == "__init__.py" else module_name.rpartition(".")[0]
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [(node.lineno, alias.name) for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.split(".")
                base = base[: len(base) - (node.level - 1)]
                module = ".".join(base + ([node.module] if node.module else []))
            else:
                module = node.module or ""
            found.append((node.lineno, module))
            # `from tidewrack import ui` imports a forbidden submodule too.
            found += [(node.lineno, f"{module}.{alias.name}") for alias in node.names]
    return found


def _forbidden(module: str, banned: set[str]) -> bool:
    return any(module == b or module.startswith(b + ".") for b in banned)


def test_core_imports_are_pure():
    problems = []
    for path in sorted(CORE.rglob("*.py")):
        for line, module in _imports(path):
            if _forbidden(module, FORBIDDEN_MODULES):
                problems.append(f"{path.relative_to(SRC)}:{line} imports {module}")
    assert not problems, "core/ must stay pure:\n" + "\n".join(problems)


def test_core_makes_no_io_calls():
    problems = []
    for path in sorted(CORE.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in FORBIDDEN_CALLS
            ):
                problems.append(f"{path.relative_to(SRC)}:{node.lineno} calls {node.func.id}()")
    assert not problems, "core/ must not do I/O:\n" + "\n".join(problems)


def test_nothing_uses_the_random_module():
    problems = [
        f"{path.relative_to(SRC)}:{line}"
        for path in sorted(SRC.rglob("*.py"))
        for line, module in _imports(path)
        if _forbidden(module, {"random"})
    ]
    assert not problems, "use tidewrack.core.rng instead of random:\n" + "\n".join(problems)


def test_lint_catches_violations(tmp_path):
    """The checks above would be useless if they silently matched nothing."""
    bad = tmp_path / "tidewrack" / "core" / "bad.py"
    bad.parent.mkdir(parents=True)
    bad.write_text("import os\nfrom ..ui import screens\nfrom random import choice\n")
    modules = {m for _, m in _imports(bad, src=tmp_path)}
    assert {"os", "tidewrack.ui", "tidewrack.ui.screens", "random"} <= modules
    assert _forbidden("tidewrack.ui.screens", FORBIDDEN_MODULES)
    assert not _forbidden("tidewrack.core.rng", FORBIDDEN_MODULES)
