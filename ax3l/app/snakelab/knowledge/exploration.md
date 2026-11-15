# Exploration

Ordinary epsilon is the chance of a random action. The initial value and
per-episode decay multiplier are chosen together. A larger decay multiplier
keeps random exploration active longer. The minimum is fixed at zero.

Safe detours (EpsilonNice) are required after ordinary epsilon ends. The start
chance applies per eligible move and must be above zero and at most 10% (0.1).
Each detour lasts between 1 and 50 moves.
Detours begin on the next move and reset at episode boundaries. Safety covers
immediate collisions; a detour can still enter a trap.

Exact exploration counts and termination outcomes accompany saved run analyses.
They are observations, not proof that exploration caused a score pattern.

- [Choosing one setting](/selection)
- [Reference index](/)
