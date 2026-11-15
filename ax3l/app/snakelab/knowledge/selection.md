# Choosing one setting

Goal: improve the high score over 500 episodes. Choose only the assigned
setting or pair, using the rules in your submission tool. Read data_tool /draft
for current choices, then / for runs. Keeping a value unchanged is allowed.
Data values are JSON; null means unrecorded. Navigation pages link to the
requested settings, scores, activity, endings, and observations.

Latest is feedback from the last completed run, even if unsuccessful. Golden
is the current-seed baseline. Best is historical context; different
seeds are not controlled comparisons. Observed patterns suggest hypotheses,
not proof that an individual setting caused a result.

Call the assigned submission tool once your choice is ready, then stop. It
saves the choice; Ax3l runs one simulation after every setting has been chosen.
The final complete configuration must differ from previous configurations.

Example: for learning rate, submit_single_value(value=0.0021) saves
only that value. For a pair, use submit_pair_values(value_1=..., value_2=...).
Choose values from the supplied domain; examples are not recommendations.

- [Model and inputs](/model)
- [Exploration](/exploration)
- [Rewards](/rewards)
- [Reference index](/)
