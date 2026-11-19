from notifier.state import AccountState, load_state, prune_state, save_state


def test_missing_file_means_empty_state(tmp_path):
    assert load_state(tmp_path / "nope.json") == {}


def test_round_trip(tmp_path):
    path = tmp_path / "state.json"
    save_state(path, {"alice": AccountState("1", "99")})
    assert load_state(path) == {"alice": AccountState("1", "99")}


def test_save_creates_folder_and_leaves_no_temp_file(tmp_path):
    path = tmp_path / "sub" / "state.json"
    save_state(path, {})
    assert path.exists()
    assert not path.with_suffix(".json.tmp").exists()


def test_corrupt_file_is_moved_aside(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("{not json")
    assert load_state(path) == {}
    assert (tmp_path / "state.json.corrupt").exists()
    assert not path.exists()


def test_unknown_fields_are_ignored(tmp_path):
    path = tmp_path / "state.json"
    path.write_text('{"alice": {"user_id": "1", "last_seen_id": "5", "extra": true}}')
    assert load_state(path) == {"alice": AccountState("1", "5")}


def test_prune_removes_unlisted_accounts():
    state = {"alice": AccountState(), "old": AccountState()}
    prune_state(state, ("alice",))
    assert list(state) == ["alice"]
