"""Read Snake Lab simulation data through AX3L's database manager."""

import json
from ax3l.app.snakelab.SingleParameters import SCHEMA, SINGLE_PARAMETERS
from ax3l.app.DbMgr import DbMgr


class SnakeLabDb:
    def __init__(self, db: DbMgr):
        self._db = db

    def get_num_sims(self) -> int:
        """Count all stored runs, including repeated configurations and all statuses."""
        return self._db.query("SELECT COUNT(*) AS num_sims FROM simulation_runs")[0]["num_sims"]

    def get_high_score(self) -> int | None:
        """Return the highest recorded score across all runs, or None before any score."""
        return self._db.query(
            "SELECT MAX(high_score) AS high_score FROM simulation_runs"
        )[0]["high_score"]

    def get_run_scores(self) -> list[int | None]:
        """Return every run's score in submission order, including unscored runs."""
        return [row["high_score"] for row in self._db.query(
            "SELECT high_score FROM simulation_runs ORDER BY id"
        )]

    def get_config(self, run_id: str) -> dict | None:
        rows = self._db.query(
            "SELECT config FROM simulation_runs WHERE run_id = %s", (run_id,)
        )
        return json.loads(rows[0]["config"]) if rows else None

    def is_config_unique(self, config: dict) -> bool:
        """Compare the full config across all runs, independent of JSON key order."""
        rows = self._db.query(
            "SELECT 1 FROM simulation_runs WHERE JSON_EQUALS(config, %s) LIMIT 1",
            (json.dumps(config, allow_nan=False),),
        )
        return not rows

    def get_run_result(self, run_id: str) -> dict | None:
        rows = self._db.query(
            "SELECT run_id, status, high_score, config FROM simulation_runs WHERE run_id = %s",
            (run_id,),
        )
        if not rows:
            return None
        result = rows[0]
        result["config"] = json.loads(result["config"])
        return result

    def get_learning_rate_history(self) -> list[dict]:
        rows = self._db.query("""
            SELECT run_id, status, high_score,
                   JSON_EXTRACT(config, '$.training.learning_rate') AS learning_rate
            FROM simulation_runs
            ORDER BY JSON_EXTRACT(config, '$.training.learning_rate') + 0, id
        """)
        for row in rows:
            row["learning_rate"] = json.loads(row["learning_rate"])
        return rows

    def get_episode_losses(self, run_id: str) -> list[tuple[int, float | None]]:
        """Read losses in episode order, preserving episodes with no training loss."""
        rows = self._db.query(
            "SELECT episode, loss FROM simulation_episodes WHERE run_id = %s ORDER BY episode",
            (run_id,),
        )
        return [(row["episode"], row["loss"]) for row in rows]

    def find_config_run(self, config: dict) -> str | None:
        rows = self._db.query("SELECT run_id FROM simulation_runs WHERE JSON_EQUALS(config, %s) ORDER BY id DESC LIMIT 1",
                              (json.dumps(config, allow_nan=False),))
        return rows[0]["run_id"] if rows else None

    def get_learning_rate_report(self, golden_run_id: str) -> list[dict]:
        return self.get_parameter_report(golden_run_id, "learning_rate")

    def get_epsilon_report(self, golden_run_id: str) -> list[dict]:
        """Group comparable epsilon pairs, including gaps in observed values."""
        rows = self._db.query("""
            SELECT r.status, r.high_score,
                   JSON_EXTRACT(r.config, '$.epsilon.initial') AS initial,
                   JSON_EXTRACT(r.config, '$.epsilon.decay') AS decay
            FROM simulation_runs r JOIN simulation_runs g ON g.run_id = %s
            WHERE JSON_EQUALS(
                JSON_REMOVE(r.config, '$.seed', '$.epsilon.initial', '$.epsilon.decay'),
                JSON_REMOVE(g.config, '$.seed', '$.epsilon.initial', '$.epsilon.decay'))
            ORDER BY JSON_EXTRACT(r.config, '$.epsilon.initial') + 0,
                     JSON_EXTRACT(r.config, '$.epsilon.decay') + 0, r.id
        """, (golden_run_id,))
        grouped = {}
        decays = set()
        for row in rows:
            initial = json.loads(row["initial"])
            decay = json.loads(row["decay"])
            decays.add(decay)
            scores = grouped.setdefault(initial, {}).setdefault(decay, [])
            if row["status"] == "completed" and row["high_score"] is not None:
                scores.append(row["high_score"])
        return [
            {"initial": initial, "pairs": [
                {"decay": decay, "scores": sorted(grouped[initial].get(decay, []))}
                for decay in sorted(decays)
            ]}
            for initial in sorted(grouped)
        ]

    def get_reward_report(self, golden_run_id: str) -> dict:
        """Return the full legal distance-reward grid across comparable seeds."""
        fields = SCHEMA["properties"]["game"]["properties"]["rewards"]["properties"]
        closer = fields["closer_to_food"]
        further = fields["further_from_food"]
        grid = {
            str(first): {str(second): []
                         for second in range(further["minimum"], further["maximum"] + 1)}
            for first in range(closer["minimum"], closer["maximum"] + 1)
        }
        rows = self._db.query("""
            SELECT r.status, r.high_score,
                   JSON_EXTRACT(r.config, '$.game.rewards.closer_to_food') AS closer_to_food,
                   JSON_EXTRACT(r.config, '$.game.rewards.further_from_food') AS further_from_food
            FROM simulation_runs r JOIN simulation_runs g ON g.run_id = %s
            WHERE JSON_EQUALS(
                JSON_REMOVE(r.config, '$.seed', '$.game.rewards.closer_to_food', '$.game.rewards.further_from_food'),
                JSON_REMOVE(g.config, '$.seed', '$.game.rewards.closer_to_food', '$.game.rewards.further_from_food'))
            ORDER BY r.id
        """, (golden_run_id,))
        for row in rows:
            first = json.loads(row["closer_to_food"])
            second = json.loads(row["further_from_food"])
            # Historical configurations outside today's legal grid have no cell.
            if first not in range(closer["minimum"], closer["maximum"] + 1) or second not in range(further["minimum"], further["maximum"] + 1):
                continue
            if row["status"] == "completed" and row["high_score"] is not None:
                grid[str(int(first))][str(int(second))].append(row["high_score"])
        for pairs in grid.values():
            for scores in pairs.values():
                scores.sort()
        return grid

    def get_parameter_report(self, golden_run_id: str, parameter: str) -> list[dict]:
        path, _ = SINGLE_PARAMETERS[parameter]
        json_path = "$." + ".".join(path)
        rows = self._db.query(f"""
            SELECT r.run_id, r.status, r.high_score,
                   JSON_EXTRACT(r.config, '{json_path}') AS {parameter},
                   JSON_EQUALS(JSON_EXTRACT(r.config, '$.seed'),
                               JSON_EXTRACT(g.config, '$.seed')) AS current_seed
            FROM simulation_runs r JOIN simulation_runs g ON g.run_id = %s
            WHERE JSON_EQUALS(JSON_REMOVE(r.config, '$.seed', '{json_path}'),
                              JSON_REMOVE(g.config, '$.seed', '{json_path}'))
            ORDER BY JSON_EXTRACT(r.config, '{json_path}') + 0, r.id
        """, (golden_run_id,))
        grouped = {}
        for row in rows:
            value = json.loads(row[parameter])
            entry = grouped.setdefault(value, {parameter: value, "results": [], "history": []})
            if row["current_seed"]:
                entry["results"].append({key: row[key] for key in ("run_id", "status", "high_score")})
            elif row["status"] == "completed" and row["high_score"] is not None:
                entry["history"].append(row["high_score"])
        for entry in grouped.values():
            entry["history"].sort()
        return list(grouped.values())
