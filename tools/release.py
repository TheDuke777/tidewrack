#!/usr/bin/env python3
"""Release tooling (CLAUDE.md §10).

Cut a release (run locally from a clean `main`):

    python tools/release.py patch|minor|major [--pre] [--dry-run]

The new version is the last *final* release tag bumped by the given part.
`--pre` tags a beta of that version instead (vX.Y.Z-beta.N, N counting up);
pyproject keeps the plain x.y.z because Flet's build version can't carry a suffix.
Running the same part without `--pre` later promotes the betas to the final
release. Every release bumps `build_number` by one.

Helpers used by .github/workflows/release.yml:

    python tools/release.py verify-tag <tag>    # tag must match pyproject version
    python tools/release.py notes <tag>         # print the CHANGELOG section for tag
    python tools/release.py build-info <tag>    # write src/tidewrack/_build_info.py
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
CHANGELOG = ROOT / "CHANGELOG.md"
BUILD_INFO = ROOT / "src" / "tidewrack" / "_build_info.py"
RELEASE_BRANCH = "main"

TAG_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)(?:-beta\.(\d+))?$")
SECTION_RE = re.compile(r"^## \[?([^\]\s]+)\]?", re.M)


class ReleaseError(Exception):
    pass


# --- versions & tags ---------------------------------------------------------

Version = tuple[int, int, int]


@dataclass(frozen=True)
class Tag:
    version: Version
    beta: int | None = None

    @classmethod
    def parse(cls, text: str) -> Tag:
        m = TAG_RE.match(text)
        if not m:
            raise ReleaseError(f"not a release tag: {text!r} (expected vX.Y.Z or vX.Y.Z-beta.N)")
        major, minor, patch, beta = m.groups()
        return cls((int(major), int(minor), int(patch)), int(beta) if beta else None)

    @property
    def plain(self) -> str:
        return fmt(self.version)

    @property
    def name(self) -> str:
        """Tag without the leading "v", as used in CHANGELOG headings and asset names."""
        return self.plain if self.beta is None else f"{self.plain}-beta.{self.beta}"

    def __str__(self) -> str:
        return f"v{self.name}"


def fmt(v: Version) -> str:
    return ".".join(map(str, v))


def parse_version(text: str) -> Version:
    parts = text.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise ReleaseError(f"pyproject version must be plain x.y.z, got {text!r}")
    return int(parts[0]), int(parts[1]), int(parts[2])


def bump(v: Version, part: str) -> Version:
    major, minor, patch = v
    if part == "major":
        return major + 1, 0, 0
    if part == "minor":
        return major, minor + 1, 0
    if part == "patch":
        return major, minor, patch + 1
    raise ValueError(part)


def next_tag(existing: list[str], part: str, pre: bool, current: Version) -> Tag:
    """Pick the next release tag given existing git tags and the pyproject version."""
    tags = [Tag.parse(t) for t in existing if TAG_RE.match(t)]
    finals = [t.version for t in tags if t.beta is None]
    target = bump(max(finals, default=(0, 0, 0)), part)
    if target < current:
        raise ReleaseError(
            f"next {part} release would be {fmt(target)}, but pyproject is already at "
            f"{fmt(current)} (in beta?). Use the part that reaches {fmt(current)}."
        )
    if not pre:
        return Tag(target)
    betas = [t.beta for t in tags if t.version == target and t.beta is not None]
    return Tag(target, max(betas, default=0) + 1)


# --- pyproject ---------------------------------------------------------------


def read_pyproject(text: str) -> tuple[Version, int]:
    data = tomllib.loads(text)
    return parse_version(data["project"]["version"]), int(data["tool"]["flet"]["build_number"])


def write_pyproject(text: str, version: Version, build_number: int) -> str:
    # Line-level edits keep comments and formatting intact.
    for key, value in (("version", f'"{fmt(version)}"'), ("build_number", str(build_number))):
        pattern = re.compile(rf"^{key} = .*$", re.M)
        if len(pattern.findall(text)) != 1:
            raise ReleaseError(f"expected exactly one top-level `{key} = ` line in pyproject.toml")
        text = pattern.sub(f"{key} = {value}", text)
    return text


# --- changelog ---------------------------------------------------------------


@dataclass(frozen=True)
class Section:
    name: str  # "Unreleased" or a tag name like "0.2.0-beta.1"
    heading: str  # the full original `## ` line
    body: str


def split_sections(text: str) -> tuple[str, list[Section]]:
    """Split CHANGELOG text into its preamble and `## ` sections."""
    matches = list(SECTION_RE.finditer(text))
    if not matches:
        return text, []
    sections = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        heading, _, body = text[m.start() : end].partition("\n")
        sections.append(Section(m.group(1), heading.rstrip(), body))
    return text[: matches[0].start()], sections


def merge_bodies(bodies: list[str]) -> str:
    """Merge changelog bodies, combining entries under matching `### ` subsections."""
    groups: dict[str, list[str]] = {}
    for body in bodies:
        heading = ""
        for line in body.splitlines():
            if line.startswith("### "):
                heading = line.strip()
                groups.setdefault(heading, [])
            elif line.strip():
                groups.setdefault(heading, []).append(line.rstrip())
    blocks = []
    if groups.get(""):
        blocks.append("\n".join(groups.pop("")))
    blocks += [f"{h}\n" + "\n".join(lines) for h, lines in groups.items() if h and lines]
    return "\n\n".join(blocks)


def promote_changelog(text: str, tag: Tag, date: dt.date) -> str:
    """Move "Unreleased" entries under a new heading for `tag`.

    A final release also folds in the entries of its own beta sections, so its
    notes describe everything since the previous final release.
    """
    preamble, sections = split_sections(text)
    unreleased = [s for s in sections if s.name.lower() == "unreleased"]
    if not unreleased:
        raise ReleaseError("CHANGELOG.md has no '## [Unreleased]' section")
    if any(s.name == tag.name for s in sections):
        raise ReleaseError(f"CHANGELOG.md already has a section for {tag.name}")

    bodies = [unreleased[0].body]
    if tag.beta is None:
        bodies += [s.body for s in sections if s.name.startswith(f"{tag.plain}-beta.")]
    merged = merge_bodies(bodies)
    if not merged:
        raise ReleaseError("CHANGELOG.md 'Unreleased' section is empty; describe the release first")

    out = [preamble.rstrip() + "\n\n", "## [Unreleased]\n\n", f"## [{tag.name}] - {date}\n\n"]
    out.append(merged + "\n\n")
    out += [f"{s.heading}\n{s.body.rstrip()}\n\n" for s in sections if s not in unreleased]
    return "".join(out).rstrip() + "\n"


def changelog_notes(text: str, tag: Tag) -> str:
    for s in split_sections(text)[1]:
        if s.name == tag.name:
            return s.body.strip()
    raise ReleaseError(f"CHANGELOG.md has no section for {tag.name}")


# --- git ---------------------------------------------------------------------


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()


def preflight(tag: Tag) -> list[str]:
    """Return the reasons a release can't be cut right now (empty = good to go)."""
    problems = []
    if git("status", "--porcelain"):
        problems.append("working tree is dirty; commit or stash first")
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    if branch != RELEASE_BRANCH:
        problems.append(f"on branch {branch!r}; releases are cut from {RELEASE_BRANCH!r}")
    git("fetch", "--quiet", "--tags", "origin", RELEASE_BRANCH)
    behind = git("rev-list", "--count", f"HEAD..origin/{RELEASE_BRANCH}")
    if behind != "0":
        problems.append(f"{RELEASE_BRANCH} is {behind} commit(s) behind origin; pull first")
    if git("tag", "--list", str(tag)):
        problems.append(f"tag {tag} already exists")
    return problems


# --- commands ----------------------------------------------------------------


def cmd_release(part: str, pre: bool, dry_run: bool) -> None:
    pyproject_text = PYPROJECT.read_text(encoding="utf-8")
    current, build_number = read_pyproject(pyproject_text)
    git("fetch", "--quiet", "--tags", "origin")
    tag = next_tag(git("tag", "--list", "v*").splitlines(), part, pre, current)

    new_pyproject = write_pyproject(pyproject_text, tag.version, build_number + 1)
    new_changelog = promote_changelog(CHANGELOG.read_text(encoding="utf-8"), tag, dt.date.today())

    print(
        f"Release {tag}: version {fmt(current)} -> {tag.plain}, "
        f"build_number {build_number} -> {build_number + 1}"
    )
    print(f"\nRelease notes:\n{changelog_notes(new_changelog, tag)}\n")

    problems = preflight(tag)
    if dry_run:
        for p in problems:
            print(f"WARNING: {p}")
        print("Dry run: tests not run, nothing written, committed, or pushed.")
        return
    if problems:
        raise ReleaseError("; ".join(problems))

    print("Running tests...")
    if subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=ROOT).returncode != 0:
        raise ReleaseError("tests failed")

    PYPROJECT.write_text(new_pyproject, encoding="utf-8")
    CHANGELOG.write_text(new_changelog, encoding="utf-8")
    git("add", str(PYPROJECT), str(CHANGELOG))
    git("commit", "-m", f"release: {tag}")
    git("tag", "-a", str(tag), "-m", f"Tidewrack {tag}")
    git("push", "--atomic", "origin", RELEASE_BRANCH, str(tag))
    print(f"Pushed {tag}; the Release workflow will build and publish it.")


def cmd_verify_tag(tag: Tag) -> None:
    version, _ = read_pyproject(PYPROJECT.read_text(encoding="utf-8"))
    if version != tag.version:
        raise ReleaseError(f"tag {tag} does not match pyproject version {fmt(version)}")
    changelog_notes(CHANGELOG.read_text(encoding="utf-8"), tag)
    print(f"{tag} matches pyproject and has a CHANGELOG section")


def cmd_build_info(tag: Tag) -> None:
    cmd_verify_tag(tag)
    _, build_number = read_pyproject(PYPROJECT.read_text(encoding="utf-8"))
    BUILD_INFO.write_text(
        "# Generated by tools/release.py build-info. Do not edit or commit.\n"
        f'VERSION = "{tag.plain}"\n'
        f"BUILD_NUMBER = {build_number}\n"
        f'TAG = "{tag}"\n',
        encoding="utf-8",
    )
    print(f"Wrote {BUILD_INFO.relative_to(ROOT)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for part in ("patch", "minor", "major"):
        p = sub.add_parser(part, help=f"cut a {part} release")
        p.add_argument("--pre", action="store_true", help="tag a beta (vX.Y.Z-beta.N)")
        p.add_argument("--dry-run", action="store_true", help="preview without changing anything")
    for name, help_text in (
        ("verify-tag", "check a tag against pyproject and CHANGELOG"),
        ("notes", "print the CHANGELOG section for a tag"),
        ("build-info", "write src/tidewrack/_build_info.py for a packaged build"),
    ):
        sub.add_parser(name, help=help_text).add_argument("tag")
    args = parser.parse_args(argv)

    try:
        if args.command in ("patch", "minor", "major"):
            cmd_release(args.command, args.pre, args.dry_run)
        elif args.command == "verify-tag":
            cmd_verify_tag(Tag.parse(args.tag))
        elif args.command == "notes":
            print(changelog_notes(CHANGELOG.read_text(encoding="utf-8"), Tag.parse(args.tag)))
        elif args.command == "build-info":
            cmd_build_info(Tag.parse(args.tag))
    except ReleaseError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as e:
        print(f"error: {' '.join(e.cmd)} failed:\n{e.stderr}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
