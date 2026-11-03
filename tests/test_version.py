from tidewrack.version import _PYPROJECT, BuildInfo, _from_pyproject, version_label


def test_reads_version_from_pyproject():
    info = _from_pyproject(_PYPROJECT)
    assert info.tag is None
    assert info.version.count(".") == 2
    assert info.build_number >= 0


def test_missing_pyproject_falls_back(tmp_path):
    assert _from_pyproject(tmp_path / "nope.toml") == BuildInfo("0.0.0", 0, None)


def test_label_for_release_build():
    assert version_label(BuildInfo("0.2.0", 7, "v0.2.0-beta.1")) == "v0.2.0-beta.1 (build 7)"


def test_label_for_source_run():
    assert version_label(BuildInfo("0.2.0", 7, None)) == "v0.2.0 (build 7, dev)"
