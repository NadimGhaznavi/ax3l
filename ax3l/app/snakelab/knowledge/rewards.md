# Rewards

Distance shaping uses Manhattan progress toward food. Choose closer-to-food
reward and farther-from-food penalty together from the supplied domains.
Their sum must be non-positive to avoid rewarding loops.

Food reward and collision/move-limit penalties are fixed by Ax3l. Episode score
counts food eaten; training reward and training loss are separate diagnostics.
Changing rewards can change the scale of Smooth L1 loss without improving
episode scores.

- [Choosing one setting](/selection)
- [Reference index](/)
