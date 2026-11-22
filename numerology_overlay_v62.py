"""EdgeLab numerology overlay (t234): display/filter only, never an input to the anytime-goal %.

Reuses the Numbers tab's own matching code, nothing re-implemented:
  * gematria  - player_targets_v49.slate_targets (same rows as By Game / Player Targets / gem_match_v58):
                D = name's English digit equals the universal day, A = arena match, T = team-name match
  * pattern   - daily_patterns_v60.matches against the slate date's pattern (saved registry entry, else auto-computed):
                English root, full English total or raw jersey number equals one of the day's numbers
  * lifepath  - lifepath_v61.hits: a step of the birthdate Life Path chain is one of the day's numbers
Snapshots without Jersey / Birth date columns get the same render-time roster fallbacks the Numbers tab uses.
"""
import html

FAMILIES = (('gem', 'Gematria (D / A / T)'), ('pattern', 'Daily pattern numbers'), ('lp', 'Life Path'))
DEFAULT_FAMILIES = ('gem',)   # the narrow, original Numbers matches; pattern / Life Path each match ~half the slate
TOGGLE_KEY = 'v62_ag_num_overlay:{day}'
TIGHT_KEY = 'v62_ag_num_tight:{day}'
FAMILY_KEY = 'v62_ag_num_fam:{day}'
CAPTION = ('Numerology overlay: display and filter only. It never changes the anytime-goal % or the order; '
           'the tighter list just hides engine picks with no match in the families picked. Same matching as the Numbers tab.')


def _pid(v):
    try:
        return str(int(float(v)))
    except (TypeError, ValueError):
        return ''


def matches(rankings, games, day, registry=()):
    """-> {pid: {'gem': [labels], 'pattern': [labels], 'lp': [labels]}} for every ranked player on the slate. Never raises."""
    try:
        import pandas as pd
        import daily_patterns_v60 as dp
        import lifepath_v61 as lp
        from gematria_log_v59 import team_names
        from numerology_v48 import analyze_game, universal_day
        from player_targets_v49 import slate_targets
        frame = rankings if isinstance(rankings, pd.DataFrame) else pd.DataFrame(list(rankings or []))
        if frame.empty or not games:
            return {}
        names = team_names()
        analyses = [analyze_game(g, day, names) for g in games if isinstance(g, dict)]
        entry = dp.entry_for(str(day), registry or ())
        uday = universal_day(day)
        out = {}
        for s in slate_targets(analyses, frame, day):
            arena = s['game'].get('arena_values') or {}
            for t in list(s.get('away_targets') or []) + list(s.get('home_targets') or []):
                pid = _pid(t.get('player_id'))
                if not pid or pid in out:
                    continue
                gem = ([f'D {uday}'] if t.get('day') else []) + \
                      ([f'A {arena.get("ordinal_root")}'] if t.get('arena_matches') else []) + \
                      ([f'T {t["values"]["ordinal_root"]}'] if t.get('team_matches') else [])
                pat = [why.replace('English root = ', 'Root ').replace('English total = ', 'Eng ').replace('Jersey #', '#')
                       for _e, why in dp.matches(t, [entry])]
                c = tuple(t.get('life_path') or ())
                hs = lp.hits(c, entry.get('numbers'))
                out[pid] = {'gem': gem, 'pattern': pat,
                            'lp': [f'LP {lp.text(c)}' + (f' via {hs[0]}' if hs and hs[0] != c[-1] else '')] if hs else [],
                            'lp_known': bool(c)}
        return out
    except Exception:
        return {}


def chips(m, families):
    """Flat chip labels for the picked families (each family's labels in order)."""
    return [x for f in families for x in (m or {}).get(f, [])]


def annotate(preds, nmap, families, tight=False):
    """Copy of the engine rows with 'num' chips; tight=True keeps only rows with >= 1 chip. Order and % unchanged."""
    out = []
    for i, r in enumerate(preds or [], 1):
        c = chips(nmap.get(_pid(r.get('pid'))), families)
        if tight and not c:
            continue
        out.append(dict(r, num=c, rank=r.get('rank', i)))
    return out


BACKTEST_NOTE = ('Walk-forward check, 19 saved nights (engine top-20 = 380 picks): engine picks with a gematria D/A/T match scored '
                 '31/114 (27%), daily-pattern match 41/156 (26%), Life Path match 51/179 (28%), any of the three 79/287 (28%), vs 109/380 '
                 '(29%) for the engine top-20 as a whole. No family produced a tighter list that scored more often, so '
                 'numerology stays out of the %.')


def empty_msg(families):
    fam = ' + '.join(lab for k, lab in FAMILIES if k in families)
    return (f'No engine pick still in play has a {fam} match tonight. Turn the tighter list off to see the full list.' if fam
            else 'Pick at least one numerology family, or turn the tighter list off.')


def summary_html(n_all, n_match, families, tight, entry_label, n_lp_missing=0):
    fam = ' + '.join(lab for k, lab in FAMILIES if k in families) or 'no family picked'
    txt = (f'Numerology overlay ON · {html.escape(fam)} vs {html.escape(entry_label)} · <b>{n_match}</b> of {n_all} engine picks match'
           + (' · tighter list shows only those' if tight else ''))
    if 'lp' in families and n_lp_missing:
        txt += f' · {n_lp_missing} without a birthdate (no Life Path)'
    return f'<p class="spn">{txt}. {html.escape(BACKTEST_NOTE)}</p>'
