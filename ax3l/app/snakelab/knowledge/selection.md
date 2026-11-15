# Choosing one setting

Goal: improve the high score over 500 episodes. Choose only the assigned
parameter or pair, using the domain in the task prompt. Consider settings
already chosen in this draft. Keeping a setting unchanged is allowed.

Latest is feedback from the last completed run, even if unsuccessful. Golden
is the current-seed baseline. All-time best is historical context; different
seeds are not controlled comparisons. Observed patterns suggest hypotheses,
not proof that an individual setting caused a result.

Call the assigned submission tool once your choice is ready, then stop. It
saves the choice; Ax3l runs one simulation after every setting has been chosen.
The final complete configuration must differ from previous configurations.

Example: if assigned learning_rate, submit_single_value(value=0.0021) saves
only that value. For a pair, use submit_pair_values(value_1=..., value_2=...).
Choose values from the supplied domain; examples are not recommendations.

- [Model and inputs](/model)
- [Exploration](/exploration)
- [Rewards](/rewards)
- [Reference index](/)
