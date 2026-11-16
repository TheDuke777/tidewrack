"""Dotted borders between regions on the world map (after 8a beta 3)."""

from tidewrack.core.engine.components import Explorer
from tidewrack.core.engine.game import Game
from tidewrack.core.procgen.grid import grow_regions
from tidewrack.core.procgen.world_gen import OVERWORLD_SHAPE, generate_world
from tidewrack.core.rng import Rng
from tidewrack.core.world.borders import grid_side, region_borders
from tidewrack.services.content import load_bundled_content

CONTENT = load_bundled_content()
RECIPE = CONTENT.world("world.standard")


def _world(seed):
    return generate_world(seed, RECIPE, CONTENT.roomsets, CONTENT.regions)


def test_the_grid_size_is_recovered_from_saved_positions():
    # Worlds don't save their grid size; positions are (cell + 0.5 ± jitter) / side.
    for seed in range(60):
        world = _world(seed)
        layout = grow_regions(
            Rng(seed).derive("worldgen").derive("layout"),
            [p.locations for p in RECIPE.regions],
            OVERWORLD_SHAPE,
        )
        assert grid_side([loc.pos for loc in world.locations.values()]) == layout.side


def test_no_border_within_one_region():
    assert region_borders([(0.1, 0.1, 0), (0.6, 0.6, 0)], side=4) == ()


def test_a_border_runs_between_two_regions_along_cell_edges():
    # Two places in neighbouring cells of a 4×4 grid: one straight edge between them.
    assert region_borders([(0.1, 0.1, 0), (0.4, 0.1, 1)], side=4) == ((0.25, 0.0, 0.25, 0.5),)


def test_borders_are_merged_into_runs_and_on_cell_edges():
    world = _world(20261103)
    side = grid_side([loc.pos for loc in world.locations.values()])
    order = {r: i for i, r in enumerate(world.regions)}
    places = [(*loc.pos, order[loc.region]) for loc in world.locations.values()]
    segments = region_borders(places, side)
    assert segments
    for x1, y1, x2, y2 in segments:
        assert x1 == x2 or y1 == y2  # straight
        for v in (x1, y1, x2, y2):
            assert abs(v * side - round(v * side)) < 1e-9  # on the grid
    # Runs are merged: no two segments continue each other in a straight line.
    ends = {(s[2], s[3], s[0] == s[2]) for s in segments}
    assert not any((s[0], s[1], s[0] == s[2]) in ends for s in segments)


def test_the_world_map_draws_borders_only_between_regions_you_know():
    world = _world(20261103)
    game = Game(20261103, world)
    assert game.view().world_map.borders == ()  # only the coast is known

    explorer = game.world.get(game.player, Explorer)
    fens = [loc.id for loc in world.locations.values() if loc.region == "region.fens"]
    explorer.locations_discovered.update(fens)
    two = game.view().world_map.borders
    assert two

    explorer.locations_discovered.update(world.locations)
    assert len(game.view().world_map.borders) > len(two)
