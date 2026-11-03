"""Pure game logic (CLAUDE.md §2, §11).

Nothing under ``core`` may import UI or services code, touch files, the network,
the clock, or ``random`` — tests/core/test_purity.py enforces this. All
randomness goes through :mod:`tidewrack.core.rng`.
"""
