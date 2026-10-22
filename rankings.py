"""Transparent descriptive goal-scoring form rankings, not probabilities."""
def rank_players(rows, min_gp=3):
    ranked = []
    for r in rows:
        if r.get("Position") == "G" or r.get("Data status") == "Needs review":
            continue
        gp = r.get("GP") or 0
        if gp < min_gp:
            continue
        g5 = r.get("GP L5") or 0
        g10 = r.get("GP L10") or 0
        if not g5 or not g10:
            continue
        s5 = r["Shots L5"] / g5
        s10 = r["Shots L10"] / g10
        g_rate = r["Goals"] / gp
        g5_rate = r["Goals L5"] / g5
        index = round(40 * s5 / 4 + 25 * s10 / 4
                      + 20 * g_rate / .5 + 15 * g5_rate / .5, 1)
        ranked.append({
            "Player": r["Player"], "Player ID": r.get("id"), "Team": r["Team"],
            "Position": r["Position"], "Form Index": index,
            "Shots/G L5": round(s5, 2),
            "Shots/G L10": round(s10, 2),
            "Goals/G Prior": round(g_rate, 3),
            "Goals/G L5": round(g5_rate, 3),
            "Prior GP": gp,
            "Data status": r["Data status"],
        })
    ranked.sort(key=lambda x: (-x["Form Index"], -x["Shots/G L5"], x["Player"]))
    return ranked
