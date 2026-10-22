import unittest
from rankings import rank_players

class RankingTests(unittest.TestCase):
    def test_excludes_insufficient_and_flagged(self):
        def row(name, gp=5, status="Historical log available"):
            return dict(Player=name, Team="ANA", Position="C", GP=gp, Goals=2, Shots=15,
                        **{"GP L5": 5, "Goals L5": 2, "Shots L5": 15,
                           "GP L10": 5, "Goals L10": 2, "Shots L10": 15,
                           "Data status": status})
        result = rank_players([row("ok"), row("low", gp=1), row("bad", status="Needs review")])
        self.assertEqual([x["Player"] for x in result], ["ok"])

if __name__ == "__main__":
    unittest.main()
