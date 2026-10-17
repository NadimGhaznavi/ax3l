"""Advance reporting's ordered round-robin count from projected completions."""


def completed_rounds(turns: list[dict], order_size: int, rounds: int = 0,
                     expected: int = 0) -> tuple[int, int]:
    for turn in turns:
        if not turn["first_completion"]:
            continue
        index = turn["parameter_index"]
        if index != expected:
            expected = 0
            if index != 0:
                continue
        expected += 1
        if expected == order_size:
            rounds += 1
            expected = 0
    return rounds, expected
