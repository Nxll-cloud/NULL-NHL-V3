"""V6.0: 'The List' - user-supplied static reference material (Best Bets to Score method).
Not an automated picking system, not a validated model, no live data or API calls."""
import html, re

CAPTION = 'User-provided method and historical example'

SOURCE = r'''THE LIST
How we build the nightly "Best bets to score" list, from the full slate to a ranked 7 and a 3-leg card. The method went 5 for 7 on November 6. Here's every step, so you can run it yourself.
Player selection: Nyah's method
Game environment + list format: our layer
Data: PropFinder

CREDIT WHERE IT'S DUE
The heart of this method is Nyah's. She came up with occurrence counting: you look across every PropFinder filter view and back the player who keeps showing up. That's step 4, along with her rules on time on ice, shots, position groups and when to switch to shots. Everything else (the game-environment ranking, the goalie layer, the line layer and the list format) is built on top of her work. Steps tagged NYAH are hers.

THE PROCESS, TOP TO FINISH
Run it in this order. The early steps decide which games to attack and what bet type to use. Only then do you pick players.

1 RANK THE GAME ENVIRONMENTS (OUR LAYER)
Before looking at a single player, sort the slate by which games should have goals. Check each team's offense against the defense it faces.
Goals for vs. goals against. Team goals scored per game against the opponent's goals allowed per game, over the last 5 and last 10. When they disagree, trust L10.
Team defense comes first. Use shots allowed per game and high-danger chances allowed. A good goalie still leaks behind a bad team, so this is the main signal for how a team is really playing.
Where: PropFinder → Cheatsheets → Team Stats (range Season / L5 / L10; Team Stats tab = scored, Opponent Stats tab = allowed). Defense table on Goalscorer Matchups (GA/G, SA/G, iSCF ranks). Early in the season L10 is empty until teams have 10 games, so use Season.

2 LAYER THE GOALIE ON TOP (OUR LAYER)
The goalie adjusts the read from step 1; he doesn't replace it. Use rates, not raw save counts: SV%, high-danger SV% and GSAx per game, over L5 / L10 / H2H. The goalie matters most when a backup starts.
Confirm the starter. "Expected" can flip to someone else. If no starter is confirmed, open the goalie picker and check each candidate's "Last Played".
Tiny sample? If the starter has only 2–3 games, don't overreact. Lean on team defense and use team SV% as the fallback.
Then the grid tells you the bet type for each team:
DEFENSE IT FACES | GOALIE IT FACES | PLAY
Bad D | Weak goalie | GOALS
Bad D | Hot goalie | SHOTS (volume is still there)
Good D | Weak goalie | HIGH-TOI PLAYERS ONLY
Good D | Hot goalie | SKIP THE TEAM
On Goalscorer Matchups, the first Defense block and goalie belong to the away team. The home skaters listed under it are the ones attacking it.

3 CUT GAMES WITH AN EASY-LOOKING DEFENSE (NYAH)
Rate defenses on their last 5 games first.
If a game's defense shows green across the board, skip it. Nyah calls that a "lighter path to victory": it looks too easy, and those spots don't hold up.
Look at goal attempts, not just goals. A player creating chances is due even if the goals haven't come yet.

4 OCCURRENCE COUNTING: FIND WHO KEEPS SHOWING UP (NYAH)
This is the core of player selection. For each game you're still playing, open the goalscorer leaderboard and cycle it through every filter view. Note who lands in the top 5 of each one.
VIEW | WHAT IT TELLS YOU
2025 season | Track record. Lean on it hardest in the first ~2 weeks, when 2026 is a thin sample.
2026 season | This year's role and form.
L10 | Medium-term form.
L5 | Who's hot right now.
H2H | Graded above every other view. How he does against this opponent.
The player who appears in the most views is the pick, even if he wouldn't pass the eye test on his own.
"Off the strength of him appearing those multiple times, I probably would have." – Nyah
Where: PropFinder → NHL Cheat Sheets → Goalscorer Matchups.

5 FILTER ON TOI, SHOTS AND POSITION (NYAH)
Time on ice and shots are the two main metrics. High TOI is the filter for longshots, because a player can't score from the bench.
Find which position group (C / RW / LW) is generating shots against that defense, and play into it.
Skip defensemen. They're longshots.
If the matchup cells are yellow or red (tough goalie or defense), switch that player from goals → shots.
Skip goalie props entirely.

6 CHECK THE 5-ON-5 LINE (OUR LAYER)
A scorer on a line that's getting caved in has a lower ceiling. Check his unit's possession and chance numbers over the last 5 games: CF%, xGF% and GF%. Prefer players whose line is controlling play.
Where: Line Combinations (per-unit CF / xGF / GF%, L5). Check the depth chart for PP1/PP2 as well.

7 PRICE IT: CONVERT ODDS TO A CHANCE (OUR LAYER)
Turn every price into the chance the book is implying. That tells you what you're paying for each pick.
Minus odds: chance = odds ÷ (odds + 100) e.g. −125 → 125 ÷ 225 = 56%
Plus odds: chance = 100 ÷ (odds + 100) e.g. +205 → 100 ÷ 305 = 33%
Odds can show N/A early in the day, so don't filter players out on odds. Price them once the lines post.

8 BUILD THE LIST (OUR FORMAT)
Rank 5–8 players in a table with these columns, every time:
# · Player (TEAM) · Price · Chance · Goals this season / last 10 · Goalie he faces + SV%
Under the table, add three short notes:
Best game environment: the game where both teams face a weak goalie, with any extra names from that game and their prices.
Fade: teams facing a hot goalie (give his SV% and record).
Check before betting: any goalie who is only "expected", not confirmed, and which picks depend on him.

9 BUILD THE 3-LEG CARD (OUR FORMAT)
Pick 3 legs from the list, each in a different game and each facing a weak goalie.
Check the games before you post it. On November 6 the list called Kaprizov / Farabee / Sennecke "all different games", but Farabee (CGY) and Sennecke (ANA) were playing each other. That's a same-game parlay, which many books block or reprice.

10 GRADE IT AND LOG IT (OUR LAYER)
After the games, mark each pick ✅ or ❌. Grade the notes too: did the best-environment game go over, did the fade hold, did the card cash? Log everything. One night is mostly variance, so only change the weights once a real log backs it up.
"Stick with your process." – Nyah

EXAMPLE: NOVEMBER 6 SLATE
5/7 picks scored
+$6.85 on $7 flat ($1 each)
# | PLAYER | PRICE | CHANCE | GOALS SEASON / L10 | GOALIE FACED | RESULT
1 | Kirill Kaprizov MIN | −125 | 56% | 11 in 17 / 7 | Askarov .887 | ✅ 1st
2 | Joel Farabee CGY | +205 | 33% | 5 in 16 / 5 | Dostal .872 | ✅ 1st
3 | Cutter Gauthier ANA | +140 | 42% | 5 in 15 / 4 | Wolf .870 | ✅ 3rd
4 | Beckett Sennecke ANA | +190 | 34% | 8 in 16 / 5 | Wolf .870 | ❌
5 | Tage Thompson BUF | +115 | 46% | 7 in 15 / 4 | Greaves .883 | ❌
6 | Jack Quinn BUF | +200 | 33% | 7 in 15 / 5 | Greaves .883 | ✅ 1st
7 | Kent Johnson CBJ | +260 | 28% | 6 in 14 / 4 | Luukkonen .874 | ✅ 1st

✅ Best environment, CGY vs ANA: 8 total goals, the highest-scoring game of the night. Leo Carlsson (+210) scored too; Granlund (+290) didn't.
✅ Fade San Jose vs Wallstedt (.920): held to 1 goal. That 1 was Celebrini's, though.
❌ The card as posted (Kaprizov / Farabee / Sennecke) lost on Sennecke. It also had two legs from the same game.
✅ A clean 3-game card (Kaprizov / Farabee / Kent Johnson) would have paid about +1880.

LESSONS FROM THE LOG
OCT 21 · 0 FOR 6
The game reads were right (weak goalies leaked), but the goals came from depth players and from alternates we had ranked lower. Zegras was 2-for-3 in H2H and got demoted for weak 2026 numbers.
Takeaway: respect the H2H weight, like Nyah says. In weak-goalie spots, add a high-shot L2/L3 or PP2 longshot instead of stacking three top-liners.

NOV 6 · 5 FOR 7
The full process, end to end. Ranking game environments first put us in the right games, and every pick but two faced a goalie under .890.
Takeaway: trust the order of the steps. Pick games first, then players. And check that card legs are really in different games.

One great night and one bad one are both small samples. Keep a log and judge the method over weeks, not slates. Bet what you can afford to lose.

Player-selection method (occurrence counting, TOI / shots, position and goal → shot rules) by Nyah. Game-environment, goalie, line and list-format layers built on top of it.
All data from PropFinder. Results checked against official NHL box scores.'''

STYLE = '''<style>
.tl60{border:1px solid rgba(0,229,255,.28);border-radius:16px;padding:18px clamp(12px,3vw,24px);margin:14px 0 22px;
background:linear-gradient(160deg,rgba(0,229,255,.06),rgba(155,92,255,.08));box-shadow:0 0 24px rgba(155,92,255,.12);max-width:100%;overflow-wrap:anywhere;box-sizing:border-box}
.tl60 .tl60-cap{font-size:.78rem;letter-spacing:.08em;text-transform:uppercase;color:#b9a3ff;margin:0 0 8px}
.tl60 h3.tl60-sec{font-size:1rem;letter-spacing:.12em;color:#00e5ff;margin:20px 0 6px;text-shadow:0 0 10px rgba(0,229,255,.35)}
.tl60 h3.tl60-sec:first-of-type{font-size:1.35rem;margin-top:4px}
.tl60 h4.tl60-step{font-size:.95rem;color:#c9b6ff;margin:18px 0 6px;letter-spacing:.05em}
.tl60 p{margin:4px 0;line-height:1.5}
.tl60 blockquote{margin:8px 0;padding:6px 12px;border-left:3px solid #9b5cff;color:#e6dcff;font-style:italic}
.tl60 .tl60-wrap{overflow-x:auto;-webkit-overflow-scrolling:touch;max-width:100%;margin:8px 0;border-radius:10px;border:1px solid rgba(155,92,255,.3)}
.tl60 table{border-collapse:collapse;width:100%;min-width:max-content;font-size:.88rem}
.tl60 th{background:rgba(0,229,255,.12);color:#00e5ff;text-align:left;padding:8px 10px;font-size:.74rem;letter-spacing:.06em;white-space:nowrap}
.tl60 td{padding:7px 10px;border-top:1px solid rgba(155,92,255,.2);white-space:nowrap}
.tl60 tbody tr:nth-child(even) td{background:rgba(155,92,255,.06)}
@media (max-width:420px){.tl60{padding:14px 10px}.tl60 table{font-size:.8rem}.tl60 th,.tl60 td{padding:6px 8px}}
</style>'''

_STEP = re.compile(r'^\d+ [A-Z]')

def _is_heading(line):
    letters = [c for c in line if c.isalpha()]
    return bool(letters) and line.upper() == line and '|' not in line and len(line) < 60

def blocks():
    """Yield (kind, payload) in source order. Kinds: sec, step, quote, p, table."""
    lines = SOURCE.split('\n'); i = 0
    while i < len(lines):
        ln = lines[i]
        if not ln.strip(): i += 1; continue
        if ' | ' in ln:
            rows = []
            while i < len(lines) and ' | ' in lines[i]:
                rows.append(lines[i].split(' | ')); i += 1
            yield 'table', rows; continue
        if _STEP.match(ln) and _is_heading(ln): yield 'step', ln
        elif _is_heading(ln): yield 'sec', ln
        elif ln.startswith('"'): yield 'quote', ln
        else: yield 'p', ln
        i += 1

def render_html():
    e = html.escape; out = [STYLE, '<section class="tl60" aria-label="The List — Best Bets to Score Method">',
                            f'<div class="tl60-cap">{e(CAPTION)}</div>']
    for kind, val in blocks():
        if kind == 'table':
            head, body = val[0], val[1:]
            out.append('<div class="tl60-wrap"><table><thead><tr>' + ''.join(f'<th scope="col">{e(c)}</th>' for c in head)
                       + '</tr></thead><tbody>' + ''.join('<tr>' + ''.join(f'<td>{e(c)}</td>' for c in r) + '</tr>' for r in body)
                       + '</tbody></table></div>')
        elif kind == 'sec': out.append(f'<h3 class="tl60-sec">{e(val)}</h3>')
        elif kind == 'step': out.append(f'<h4 class="tl60-step">{e(val)}</h4>')
        elif kind == 'quote': out.append(f'<blockquote>{e(val)}</blockquote>')
        else: out.append(f'<p>{e(val)}</p>')
    out.append('</section>')
    return ''.join(out)

def render(st):
    st.subheader('📝 The List — Best Bets to Score Method')
    st.markdown(render_html(), unsafe_allow_html=True)
