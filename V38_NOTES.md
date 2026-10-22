# NULL NHL V3.8

Adds pre-slate regular-season opponent history and season-goal milestone evidence from NHL game logs, alongside existing V3.7 featured storyline selection.

Steps: Rank Entire Slate -> Fetch NHL player biographies and arenas -> Fetch opponent history and milestone evidence. The top card updates when evidence is loaded. Start with 50 players, then increase coverage as needed. Data is cached within the Python app process.

Opponent-history flag: at least 2 prior meetings against tonight's opponent AND at least 2 total goals in those meetings, in the current NHL season. Season milestone flag: 1 goal away from 10/20/30/40/50/60 season goals. These are descriptive criteria, not validated predictive effects. Data strictly before the slate date. The dashboard never infers former-team, revenge, injuries, career milestones or news. Some NHL API records may lack opponentAbbrev and are excluded; no historical cross-season records are used. Source URLs link to NHL API player game logs.

Run tests: python -m unittest discover -p 'test_*.py' -q
