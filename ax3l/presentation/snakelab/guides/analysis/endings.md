# Game-ending reasons

Three horizontal bars show snake collisions, wall collisions, and max moves,
in that order. Each bar uses all episodes in the run as its denominator. The
axis always runs from 0% to 100%. Zero-count reasons remain visible.

Labels show percentages rounded to the nearest whole percent and exact episode
counts. JSON retains the full measured precision. Board-filled and
unrecorded or other outcomes appear in a note when present. They remain in the
denominator, so the three bars need not add up to 100%.

This chart summarizes the whole run; it does not show when endings occurred.
Use it with food scores when choosing collision rewards. Fewer collisions
alone do not establish better food-finding performance; check whether more
episodes simply reached max moves.

- [Reward settings](/guides/rewards)
- [Chart interpretation](/guides/analysis/)
