"""The game's only source of randomness (CLAUDE.md §11).

A self-contained xoshiro256** generator rather than :mod:`random`: Python's
``random`` helpers (``choice``, ``shuffle``, ``randrange``…) have changed between
versions, and CI tests on a different Python than the APK bundles. Owning the
algorithm keeps "same seed + same generator version = same world" true
everywhere. State is plain ints, so it saves to JSON.
"""

from __future__ import annotations

import hashlib
from collections.abc import MutableSequence, Sequence
from typing import TypeVar

T = TypeVar("T")

MASK64 = (1 << 64) - 1


def _rotl(x: int, k: int) -> int:
    return ((x << k) | (x >> (64 - k))) & MASK64


def splitmix64(x: int) -> tuple[int, int]:
    """One splitmix64 step: returns (output, next state). Used to expand seeds."""
    x = (x + 0x9E3779B97F4A7C15) & MASK64
    z = x
    z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
    z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & MASK64
    return z ^ (z >> 31), x


class Rng:
    """Seeded random stream. Create one per game; :meth:`derive` makes substreams."""

    def __init__(self, seed: int) -> None:
        self.seed = seed & MASK64
        state, x = [], self.seed
        for _ in range(4):
            out, x = splitmix64(x)
            state.append(out)
        self._s = state

    # --- persistence -------------------------------------------------------------

    def get_state(self) -> dict:
        return {"seed": self.seed, "s": list(self._s)}

    @classmethod
    def from_state(cls, state: dict) -> Rng:
        rng = cls(state["seed"])
        s = [int(v) & MASK64 for v in state["s"]]
        if len(s) != 4 or not any(s):
            raise ValueError("invalid RNG state")
        rng._s = s
        return rng

    def derive(self, label: str) -> Rng:
        """Independent substream named `label`, seeded from this stream's *seed*.

        Draws from one subsystem (say, ambient flavour) then never shift another's
        (say, loot), and deriving doesn't consume from this stream.
        """
        digest = hashlib.blake2b(f"{self.seed}:{label}".encode(), digest_size=8).digest()
        return Rng(int.from_bytes(digest, "little"))

    # --- core generator ----------------------------------------------------------

    def next_u64(self) -> int:
        s0, s1, s2, s3 = self._s
        result = (_rotl((s1 * 5) & MASK64, 7) * 9) & MASK64
        t = (s1 << 17) & MASK64
        s2 ^= s0
        s3 ^= s1
        s1 ^= s2
        s0 ^= s3
        s2 ^= t
        s3 = _rotl(s3, 45)
        self._s = [s0, s1, s2, s3]
        return result

    # --- helpers -----------------------------------------------------------------

    def below(self, n: int) -> int:
        """Uniform int in [0, n), without modulo bias."""
        if n <= 0:
            raise ValueError("n must be positive")
        limit = ((1 << 64) // n) * n
        while True:
            r = self.next_u64()
            if r < limit:
                return r % n

    def randint(self, a: int, b: int) -> int:
        """Uniform int in [a, b], inclusive."""
        if b < a:
            raise ValueError("empty range")
        return a + self.below(b - a + 1)

    def random(self) -> float:
        """Uniform float in [0, 1)."""
        return (self.next_u64() >> 11) * (1.0 / (1 << 53))

    def chance(self, p: float) -> bool:
        return self.random() < p

    def choice(self, seq: Sequence[T]) -> T:
        if not seq:
            raise IndexError("choice from empty sequence")
        return seq[self.below(len(seq))]

    def weighted_choice(self, items: Sequence[T], weights: Sequence[float]) -> T:
        if len(items) != len(weights) or not items:
            raise ValueError("items and weights must be non-empty and the same length")
        total = sum(weights)
        if total <= 0 or any(w < 0 for w in weights):
            raise ValueError("weights must be non-negative with a positive total")
        r = self.random() * total
        for item, w in zip(items, weights, strict=True):
            r -= w
            if r < 0:
                return item
        return items[-1]  # float rounding fallback

    def shuffle(self, seq: MutableSequence) -> None:
        """Fisher–Yates, in place."""
        for i in range(len(seq) - 1, 0, -1):
            j = self.below(i + 1)
            seq[i], seq[j] = seq[j], seq[i]
