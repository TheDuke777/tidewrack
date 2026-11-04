from tidewrack.services.settings import Settings, SettingsStore


def test_round_trip(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    store.save(Settings(log_visible=False, log_share=0.25))
    assert store.load() == Settings(log_visible=False, log_share=0.25)


def test_missing_or_broken_file_means_defaults(tmp_path):
    path = tmp_path / "settings.json"
    assert SettingsStore(path).load() == Settings()
    path.write_text("{not json")
    assert SettingsStore(path).load() == Settings()
    path.write_text('{"log_share": 7}')
    assert SettingsStore(path).load() == Settings()


def test_unknown_keys_from_newer_apps_are_ignored(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"log_visible": false, "theme": "dark"}')
    assert SettingsStore(path).load() == Settings(log_visible=False)
