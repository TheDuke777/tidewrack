"""Content validation: every bundled file must load (CLAUDE.md §14 step 2), and
the loader must reject the mistakes content authors are likely to make."""

import copy
import json

import pytest

from tidewrack.core.data.loader import ContentError, content_hash, load_content
from tidewrack.services.content import CONTENT_ROOT, read_content_files

BUNDLED = read_content_files()


def test_bundled_content_is_valid():
    content = load_content(BUNDLED)  # raises ContentError listing every problem
    assert "dungeon.first_descent" in content.dungeons
    assert len(content.dungeon("dungeon.first_descent").nodes) == 7


def test_content_lives_where_flet_bundles_it():
    # flet build only packages src/ ([tool.flet.app] path).
    assert CONTENT_ROOT.parent.name == "src" and CONTENT_ROOT.is_dir()


def test_content_hash_is_stable_and_sensitive():
    assert content_hash(BUNDLED) == content_hash(dict(reversed(BUNDLED.items())))
    changed = dict(
        BUNDLED, **{"dungeons/first_descent.json": BUNDLED["dungeons/first_descent.json"] + " "}
    )
    assert content_hash(changed) != content_hash(BUNDLED)


# --- rejections ------------------------------------------------------------------

DUNGEON = json.loads(BUNDLED["dungeons/first_descent.json"])


def _problems(files: dict[str, str]) -> list[str]:
    with pytest.raises(ContentError) as e:
        load_content(files)
    return e.value.problems


def _dungeon_problems(mutate) -> list[str]:
    data = copy.deepcopy(DUNGEON)
    mutate(data)
    return _problems({"dungeons/first_descent.json": json.dumps(data)})


def test_rejects_unknown_keys():
    problems = _dungeon_problems(lambda d: d["nodes"][0].update(descripton="typo"))
    assert any("nodes.0.descripton" in p and "Extra inputs" in p for p in problems)


def test_rejects_missing_fields():
    problems = _dungeon_problems(lambda d: d["nodes"][0].pop("name"))
    assert any("nodes.0.name" in p and "required" in p for p in problems)


def test_rejects_dangling_exit():
    problems = _dungeon_problems(lambda d: d["nodes"][0]["exits"][0].update(to="nowhere"))
    assert any("unknown node 'nowhere'" in p for p in problems)


def test_rejects_unreachable_node():
    def strand_shrine(d):
        stair = next(n for n in d["nodes"] if n["id"] == "cliff_stair")
        stair["exits"] = [e for e in stair["exits"] if e["to"] != "tide_shrine"]

    assert any("tide_shrine: unreachable" in p for p in _dungeon_problems(strand_shrine))


def test_rejects_duplicate_node_ids():
    problems = _dungeon_problems(lambda d: d["nodes"].append(copy.deepcopy(d["nodes"][0])))
    assert any("duplicate node ids: wrack_cove" in p for p in problems)


def test_rejects_bad_ids():
    assert any(
        "nodes.0.id" in p
        for p in _dungeon_problems(lambda d: d["nodes"][0].update(id="Wrack Cove"))
    )
    assert any(
        p.startswith("dungeons/first_descent.json: id:")
        for p in _dungeon_problems(lambda d: d.update(id="first_descent"))
    )


def test_id_must_match_file_name():
    problems = _problems({"dungeons/other.json": BUNDLED["dungeons/first_descent.json"]})
    assert problems == [
        "dungeons/other.json: id is 'dungeon.first_descent' but this file must hold 'dungeon.other'"
    ]


def test_reports_every_problem_with_its_path():
    problems = _problems(
        {
            "dungeons/broken.json": "{not json",
            "monsters/rat.json": "{}",
            "dungeons/notes.txt": "",
            "dungeons/first_descent.json": BUNDLED["dungeons/first_descent.json"],
        }
    )
    assert [p.split(":")[0] for p in problems] == [
        "dungeons/broken.json",
        "dungeons/notes.txt",
        "monsters/rat.json",
    ]
