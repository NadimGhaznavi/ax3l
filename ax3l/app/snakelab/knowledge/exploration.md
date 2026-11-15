# Exploration

Ordinary epsilon is the chance of a random action. The initial value and
per-episode decay multiplier are chosen together. A larger decay multiplier
keeps random exploration active longer. The minimum is fixed at zero.

EpsilonNice is required after ordinary epsilon ends. Its probability controls
the chance per eligible move of starting a safe detour on the next move; steps
controls its duration. Detours reset at episode boundaries. Safety covers
immediate collisions; a detour can still enter a trap.

Exact exploration counts and termination outcomes accompany saved run analyses.
They are observations, not proof that exploration caused a score pattern.

- [Choosing one setting](/selection)
- [Reference index](/)
