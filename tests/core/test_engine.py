from dataclasses import dataclass

import pytest

from tidewrack.core.engine.ecs import World
from tidewrack.core.engine.events import Event, EventBus

# --- ECS -----------------------------------------------------------------------


@dataclass
class Pos:
    x: int


@dataclass
class Tag:
    pass


def test_query_returns_matching_entities_in_creation_order():
    world = World()
    a = world.create(Pos(1), Tag())
    world.create(Pos(2))
    c = world.create(Tag(), Pos(3))
    assert [e for e, _ in world.query(Pos, Tag)] == [a, c]
    assert [p.x for _, (p,) in world.query(Pos)] == [1, 2, 3]


def test_add_replaces_and_remove_detaches():
    world = World()
    e = world.create(Pos(1))
    world.add(e, Pos(5))
    assert world.get(e, Pos).x == 5
    assert world.remove(e, Pos).x == 5
    assert world.try_get(e, Pos) is None
    with pytest.raises(KeyError, match="no Pos"):
        world.get(e, Pos)


def test_destroy_and_ids_never_reused():
    world = World()
    a = world.create()
    world.destroy(a)
    assert not world.exists(a)
    assert world.create() != a


def test_single():
    world = World()
    e = world.create(Tag())
    assert world.single(Tag)[0] == e
    world.create(Tag())
    with pytest.raises(LookupError):
        world.single(Tag)


# --- event bus -----------------------------------------------------------------


@dataclass(frozen=True)
class Ping(Event):
    n: int


@dataclass(frozen=True)
class Pong(Event):
    n: int


def test_emit_queues_until_flush():
    bus, seen = EventBus(), []
    bus.subscribe(Ping, seen.append)
    bus.emit(Ping(1))
    assert seen == []
    assert bus.flush() == [Ping(1)]
    assert seen == [Ping(1)]


def test_handlers_emitting_are_delivered_fifo_without_reentry():
    bus, order = EventBus(), []

    def on_ping(e):
        order.append(f"ping{e.n}")
        bus.emit(Pong(e.n))

    bus.subscribe(Ping, on_ping)
    bus.subscribe(Pong, lambda e: order.append(f"pong{e.n}"))
    bus.emit(Ping(1))
    bus.emit(Ping(2))
    bus.flush()
    assert order == ["ping1", "ping2", "pong1", "pong2"]


def test_base_class_subscription_and_unsubscribe():
    bus, everything = EventBus(), []
    unsubscribe = bus.subscribe(Event, everything.append)
    bus.emit(Ping(1))
    bus.emit(Pong(2))
    bus.flush()
    unsubscribe()
    bus.emit(Ping(3))
    bus.flush()
    assert everything == [Ping(1), Pong(2)]


def test_runaway_handlers_are_stopped():
    bus = EventBus()
    bus.subscribe(Ping, lambda e: bus.emit(Ping(e.n + 1)))
    bus.emit(Ping(0))
    with pytest.raises(RuntimeError, match="limit"):
        bus.flush()
