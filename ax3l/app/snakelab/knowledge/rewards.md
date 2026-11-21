# Rewards

Distance shaping uses Manhattan progress toward food. Choose closer-to-food
reward and farther-from-food penalty together from the supplied domains.
Their sum must be non-positive.

Choose empty space reward (-2 to +2), snake collision reward (-20 to 0), or
wall collision reward (-20 to 0) separately. Positive empty rewards can favor
survival without food. Food stays +10; the move-limit penalty stays -10.
Judge rewards by food scores, not total reward or loss scale.

- [Choosing one setting](/selection)
- [Reference index](/)
