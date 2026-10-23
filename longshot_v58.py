"""V5.8 Top Long Shot Candidate (Home): ONE slate skater with a lower model chance but strong upside signals.

Display only and price-free (no prices, implied probabilities or edge % are shown; an Edge Flags hit appears only as
an 'Edge flag' chip and only when real opening lines were loaded - DEMO lines never count).

Band (documented constants): model P(anytime goal) in [P_FLOOR, P_CAP] AND below the slate's top quartile
(< the 75th percentile of all candidate chances), so he is genuinely not a favourite but not noise either.
Excluded: finished games, already-scored players, players listed out (ESPN injuries), and the Top Four-Leg Parlay legs.
A candidate needs at least one upside signal. Score = model P x (1 + upside), upside =
  GEM_W x numerology threat score / 100 (numboard_v56: day/arena/team matches)
+ STORY_W per storyline tag (Revenge, Former, Hometown, VS team, Hot streak, Birthday, Milestone, 1st game), capped at STORY_CAP
+ JUMP_W per rank the player has climbed in his game's live next-goal order vs the pregame order (live games only), capped at JUMP_CAP ranks
+ EDGE_W when Edge Flags flags him against a real opening line.
Tie-break: score, then model P, then name, then player id (deterministic).

Audit P1.6: Home shows TWO separately labelled options via picks()/pair_html():
  * Model pick - in-band model P x (1 + next-goal jump + Edge flag); model signals only, no gematria/storyline input.
  * Gematria / Numbers pick - in-band, needs a gematria or storyline signal, ranked by model P x (1 + those signals);
    it is not a model pick and is never counted in a model hit rate.
pick() (the legacy single mixed pick) is kept for compatibility but no longer drives Home.
"""
import parlay_v58 as parlay

P_FLOOR, P_CAP, TOP_QUANTILE = 0.06, 0.20, 0.75
GEM_W, STORY_W, STORY_CAP, JUMP_W, JUMP_CAP, EDGE_W = 0.50, 0.15, 0.45, 0.05, 6, 0.10
STORY_TAGS = ('REVENGE', 'FORMER', 'HOMETOWN', 'VS TEAM', 'HOT STREAK', 'BDAY', 'MILESTONE', '1ST GAME')


def quantile(values, q):
    v = sorted(values)
    if not v:
        return None
    pos = (len(v) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (pos - lo)


def game_jumps(results):
    """{pid: ranks climbed} = pregame rank (by lam_game) - live next-goal rank, per live game."""
    out = {}
    for r in results or []:
        res = r['result']
        if res.get('phase') != 'live':
            continue
        players = res.get('players') or []
        pre = sorted(players, key=lambda p: (-(p.get('lam_game') or 0), p.get('name') or ''))
        pre_rank = {p['pid']: i for i, p in enumerate(pre, 1)}
        for i, p in enumerate(players, 1):      # players are already in live next-goal order
            out[p['pid']] = pre_rank.get(p['pid'], i) - i
    return out


def in_band(cands):
    cap = quantile([c['p'] for c in cands], TOP_QUANTILE)
    if cap is None:
        return []
    return [c for c in cands if P_FLOOR <= c['p'] <= P_CAP and c['p'] < cap]


def score(c, gem=None, stories=None, jumps=None, edge_ids=()):
    """(score, signals[(chip text, tone)], why) for one candidate."""
    sig, up, why = [], 0.0, []
    th = (gem or {}).get(c['pid']) or (gem or {}).get(str(c['pid']))
    if th and th.get('threat', 0) > 0:
        up += GEM_W * th['threat'] / 100
        kinds = [k for k in ('day', 'arena', 'team') if th.get(k)]
        sig.append((f'Gematria: {" + ".join(kinds)} match · {th["threat"]}', 'gem'))
        why.append(f'{" + ".join(kinds)} number match')
    tags = [t for t in (stories or {}).get(c['pid'], []) if t in STORY_TAGS]
    tags = list(dict.fromkeys(tags))
    if tags:
        up += min(STORY_CAP, STORY_W * len(tags))
        sig += [(f'Storyline: {t.title()}', 'gem') for t in tags[:3]]
        why.append(tags[0].lower() + ' storyline')
    j = (jumps or {}).get(c['pid'], 0)
    if j > 0:
        up += JUMP_W * min(j, JUMP_CAP)
        sig.append((f'Next-goal jump +{j} rank{"s" if j != 1 else ""}', 'hot'))
        why.append(f'climbing the live next-goal order (+{j})')
    if c['pid'] in set(edge_ids or ()):
        up += EDGE_W
        sig.append(('Edge flag', 'ok'))
        why.append('flagged on Edge Flags')
    return c['p'] * (1 + up), sig, why


def pick(cands, parlay_ids=(), gem=None, stories=None, jumps=None, edge_ids=()):
    """The single top long shot, or None. Each candidate dict gains 'ls_score', 'signals', 'why'."""
    taken = set(parlay_ids or ())
    best = []
    for c in in_band(cands):
        if c['pid'] in taken:
            continue
        s, sig, why = score(c, gem, stories, jumps, edge_ids)
        if not sig:
            continue
        best.append(dict(c, ls_score=s, signals=sig, why=why))
    best.sort(key=lambda c: (-c['ls_score'], -c['p'], c['name'], c['pid']))
    return best[0] if best else None


def model_score(c, jumps=None, edge_ids=()):
    """Model-only upside (next-goal jump + Edge flag); never gematria or storylines."""
    return score(c, None, None, jumps, edge_ids)


def numbers_score(c, gem=None, stories=None):
    """Gematria / storyline upside only (the Numbers lens)."""
    return score(c, gem, stories, None, ())


def picks(cands, parlay_ids=(), gem=None, stories=None, jumps=None, edge_ids=()):
    """{'model': candidate or None, 'numbers': candidate or None} - two separate options (audit P1.6).

    model: best in-band candidate by model_score (no signal required: the model's own long shot).
    numbers: best in-band candidate by numbers_score that HAS a gematria/storyline signal, a different player from the
    model pick. Each dict gains 'ls_score', 'signals', 'why' and 'lens' ('model' / 'numbers')."""
    taken = set(parlay_ids or ())
    band = [c for c in in_band(cands) if c['pid'] not in taken]
    key = lambda c: (-c['ls_score'], -c['p'], c['name'], c['pid'])
    m = []
    for c in band:
        s, sig, why = model_score(c, jumps, edge_ids)
        m.append(dict(c, ls_score=s, signals=sig, why=why or ['highest model chance in the long-shot band'], lens='model'))
    m.sort(key=key)
    model = m[0] if m else None
    n = []
    for c in band:
        if model is not None and c['pid'] == model['pid']:
            continue
        s, sig, why = numbers_score(c, gem, stories)
        if sig:
            n.append(dict(c, ls_score=s, signals=sig, why=why, lens='numbers'))
    n.sort(key=key)
    return {'model': model, 'numbers': n[0] if n else None}


def gem_threats(targets):
    """home_leaders_v52.all_targets -> {player_id str: {'threat', 'day', 'arena', 'team'}} via numboard_v56 (unchanged formula)."""
    import numboard_v56 as nb
    out = {}
    for m in targets or []:
        for side in ('away_targets', 'home_targets'):
            for t in m.get(side) or []:
                if t.get('player_id'):
                    out[str(t['player_id'])] = {'threat': nb.threat_score(t), 'day': bool(t.get('day')),
                                                'arena': bool(t.get('arena_matches')), 'team': bool(t.get('team_matches'))}
    return out


def section_html(c, scored=False, record=None):
    import position_badge_v59 as pb
    import scorers_tonight_v58 as sctn
    import v55_ui as v5
    import venue_v58 as vn
    head = ('<div class="sh"><h3>Top long shot candidate</h3><p>One skater outside the favourites (model chance '
            f'{P_FLOOR * 100:.0f}–{P_CAP * 100:.0f}%, below the slate’s top quartile) with the strongest upside signals · not a parlay leg</p></div>')
    if not c:
        return (f'<section class="sec nls">{head}<div class="npp-empty"><b>No qualifying long shot tonight</b><p>Nobody in the band has a gematria, storyline, '
                'live next-goal or Edge-flag signal yet (or rankings are not built for this slate).</p></div></section>')
    where = f'{v5.esc(c["team"])} {"vs" if c.get("home") else "@"} {v5.esc(c["opp"])}'
    when = v5.et_time(c.get('start')) if c.get('start') else ''
    why = 'Why: ' + '; '.join(c['why']) + f' - on top of a {c["p"] * 100:.1f}% model chance.'
    state = '<span class="npp-st s-hit">✓ Scored</span>' if scored else ''
    return (f'<section class="sec nls">{head}<article class="nls-card" style="{v5.team_vars(c["team"])}">{v5.logo(c["team"], "nls-lg")}'
            f'<div class="nls-id"><span class="kind">Long shot</span><b class="nls-name">{v5.esc(c["name"])}{pb.goalie_badge(pb.position_of(c))}{sctn.badge_for(record, c.get("pid"), c.get("name"))}</b><small>{where}{" · " + v5.esc(when) if when else ""}</small>{vn.tag(c.get("venue"))}'
            f'<p class="nls-why">{v5.esc(why)}</p><div class="cats">{v5.chips(c["signals"])}</div></div>'
            f'<div class="nls-p"><span class="lbl">Model chance</span><strong>{c["p"] * 100:.1f}%</strong>{state}</div></article></section>')


PAIR_LABELS = {'model': ('Model pick', 'Model long shot: model chance plus live next-goal / Edge-flag signals only.'),
               'numbers': ('Gematria / Numbers pick', 'Numbers lens (gematria + storylines). Not a model pick; never counted in model hit rates.')}


def _card(c, lens, scored, record):
    import position_badge_v59 as pb
    import scorers_tonight_v58 as sctn
    import v55_ui as v5
    import venue_v58 as vn
    label, note = PAIR_LABELS[lens]
    if not c:
        empty = ('No in-band candidate tonight.' if lens == 'model' else
                 'Nobody else in the band has a gematria or storyline signal tonight.')
        return (f'<article class="nls-card nls-{lens} empty"><div class="nls-id"><span class="kind">{v5.esc(label)}</span>'
                f'<p class="nls-why">{v5.esc(empty)}</p><small class="nls-note">{v5.esc(note)}</small></div></article>')
    where = f'{v5.esc(c["team"])} {"vs" if c.get("home") else "@"} {v5.esc(c["opp"])}'
    when = v5.et_time(c.get('start')) if c.get('start') else ''
    why = 'Why: ' + '; '.join(c['why']) + f' - on top of a {c["p"] * 100:.1f}% model chance.'
    state = '<span class="npp-st s-hit">✓ Scored</span>' if scored else ''
    return (f'<article class="nls-card nls-{lens}" style="{v5.team_vars(c["team"])}">{v5.logo(c["team"], "nls-lg")}'
            f'<div class="nls-id"><span class="kind">{v5.esc(label)}</span><b class="nls-name">{v5.esc(c["name"])}{pb.goalie_badge(pb.position_of(c))}{sctn.badge_for(record, c.get("pid"), c.get("name"))}</b><small>{where}{" · " + v5.esc(when) if when else ""}</small>{vn.tag(c.get("venue"))}'
            f'<p class="nls-why">{v5.esc(why)}</p><div class="cats">{v5.chips(c["signals"])}</div><small class="nls-note">{v5.esc(note)}</small></div>'
            f'<div class="nls-p"><span class="lbl">Model chance</span><strong>{c["p"] * 100:.1f}%</strong>{state}</div></article>')


def pair_html(pp, scored_ids=(), record=None):
    """Two labelled long-shot options (audit P1.6). pp = picks() output (or None when rankings are not built)."""
    head = ('<div class="sh"><h3>Top long shot candidates</h3><p>Two separate options outside the favourites (model chance '
            f'{P_FLOOR * 100:.0f}–{P_CAP * 100:.0f}%, below the slate’s top quartile) · not parlay legs · '
            'the Gematria / Numbers pick is not a model pick</p></div>')
    if not pp or not (pp.get('model') or pp.get('numbers')):
        return (f'<section class="sec nls">{head}<div class="npp-empty"><b>No qualifying long shot tonight</b><p>Nobody is in the long-shot band yet '
                '(or rankings are not built for this slate).</p></div></section>')
    sc = set(scored_ids or ())
    cards = ''.join(_card(pp.get(k), k, bool(pp.get(k) and pp[k]['pid'] in sc), record) for k in ('model', 'numbers'))
    return f'<section class="sec nls">{head}{cards}</section>'
