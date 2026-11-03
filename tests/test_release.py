import datetime as dt

import pytest
from release import (
    ReleaseError,
    Tag,
    changelog_notes,
    next_tag,
    promote_changelog,
    read_pyproject,
    write_pyproject,
)

DATE = dt.date(2026, 11, 2)


# --- next_tag ------------------------------------------------------------------


def test_first_release():
    assert str(next_tag([], "patch", pre=False, current=(0, 0, 0))) == "v0.0.1"


def test_bumps_from_last_final():
    tags = ["v0.0.1", "v0.1.0", "v0.0.2"]
    assert str(next_tag(tags, "patch", False, (0, 1, 0))) == "v0.1.1"
    assert str(next_tag(tags, "minor", False, (0, 1, 0))) == "v0.2.0"
    assert str(next_tag(tags, "major", False, (0, 1, 0))) == "v1.0.0"


def test_betas_count_up_then_promote():
    tags = ["v0.1.0"]
    assert str(next_tag(tags, "minor", True, (0, 1, 0))) == "v0.2.0-beta.1"
    tags.append("v0.2.0-beta.1")
    assert str(next_tag(tags, "minor", True, (0, 2, 0))) == "v0.2.0-beta.2"
    tags.append("v0.2.0-beta.2")
    assert str(next_tag(tags, "minor", False, (0, 2, 0))) == "v0.2.0"


def test_refuses_to_go_below_version_in_beta():
    with pytest.raises(ReleaseError, match="in beta"):
        next_tag(["v0.1.0", "v0.2.0-beta.1"], "patch", False, (0, 2, 0))


def test_ignores_unrelated_tags():
    assert str(next_tag(["latest", "v1.2"], "patch", False, (0, 0, 0))) == "v0.0.1"


def test_tag_parse_rejects_garbage():
    for bad in ("0.1.0", "v0.1", "v0.1.0-rc.1", "v0.1.0-beta"):
        with pytest.raises(ReleaseError):
            Tag.parse(bad)


# --- pyproject -----------------------------------------------------------------

PYPROJECT = """\
[project]
name = "tidewrack"
# keep me
version = "0.1.0"

[tool.ruff]
target-version = "py312"

[tool.flet]
build_number = 4
"""


def test_pyproject_round_trip_keeps_comments():
    out = write_pyproject(PYPROJECT, (0, 2, 0), 5)
    assert read_pyproject(out) == ((0, 2, 0), 5)
    assert "# keep me" in out
    assert 'target-version = "py312"' in out


def test_pyproject_rejects_ambiguous_keys():
    with pytest.raises(ReleaseError):
        write_pyproject(PYPROJECT + 'version = "9.9.9"\n', (0, 2, 0), 5)


# --- changelog -----------------------------------------------------------------

CHANGELOG = """\
# Changelog

Intro text.

## [Unreleased]

### Added
- Pets.

### Fixed
- Crash on load.

## [0.1.0] - 2026-10-01

### Added
- Map.
"""


def test_promote_moves_unreleased_and_keeps_history():
    out = promote_changelog(CHANGELOG, Tag.parse("v0.2.0"), DATE)
    assert out.index("## [Unreleased]") < out.index("## [0.2.0] - 2026-11-02")
    assert "## [0.1.0] - 2026-10-01" in out
    assert "Intro text." in out
    assert changelog_notes(out, Tag.parse("v0.2.0")) == (
        "### Added\n- Pets.\n\n### Fixed\n- Crash on load."
    )
    assert changelog_notes(out, Tag.parse("v0.1.0")) == "### Added\n- Map."


def test_promote_leaves_unreleased_empty():
    out = promote_changelog(CHANGELOG, Tag.parse("v0.2.0"), DATE)
    with pytest.raises(ReleaseError, match="empty"):
        promote_changelog(out, Tag.parse("v0.2.1"), DATE)


def test_final_release_folds_in_beta_notes():
    beta = promote_changelog(CHANGELOG, Tag.parse("v0.2.0-beta.1"), DATE)
    beta = beta.replace("## [Unreleased]\n", "## [Unreleased]\n\n### Added\n- Cooking.\n")
    final = promote_changelog(beta, Tag.parse("v0.2.0"), DATE)
    assert changelog_notes(final, Tag.parse("v0.2.0")) == (
        "### Added\n- Cooking.\n- Pets.\n\n### Fixed\n- Crash on load."
    )
    assert "## [0.2.0-beta.1] - 2026-11-02" in final


def test_final_after_betas_needs_no_new_entries():
    beta = promote_changelog(CHANGELOG, Tag.parse("v0.2.0-beta.1"), DATE)
    final = promote_changelog(beta, Tag.parse("v0.2.0"), DATE)
    assert "- Pets." in changelog_notes(final, Tag.parse("v0.2.0"))


def test_promote_rejects_duplicate_section():
    with pytest.raises(ReleaseError, match="already"):
        promote_changelog(CHANGELOG, Tag.parse("v0.1.0"), DATE)
