"""Read-only pooled accuracy for retained production logs; never a forecast/backfill runner.
Different targets stay separate. Shared views/aliases are not extra models.
"""
from html import escape
from pathlib import Path
from datetime import date
import math

import accuracy_v58 as acc
import gematria_log_v59 as gem

# Research Statistical is NP/Form; EdgeLab/Edge Flags/top-threat are views of Model, not extra forecasts.
LABELS = {
    'model': 'Model · anytime goal', 'np': 'NP / Form · Research Statistical',
    'blend': 'Blend · experimental', 'books': 'Books', 'firstgoal': 'First Goal',
    'gematria': 'Gematria matches · research signals', 'nextgoal': 'Live Next Goal',
    'winprob': 'Game winner', 'storyline': 'Research Storylines', 'overlap': 'Research Overlap',
    'sleepers': 'Research Statistical Sleepers', 'thelist': 'The List / Nyah · reference only',
}
CAPTION = ('Correct ÷ all completed tracked predictions, pooled across nights (not an average of nightly rates). '
           'Model/NP/Blend/Books: frozen top-10 anytime scorers; First Goal: one favourite per game; '
           'Gematria: all unique matched players, not a predictive model. Targets differ, so rates are not like-for-like.')
SCOPE = ('Available saved history only, including already-saved rebuilt nights; not lifetime accuracy. '
         'Blend, Books, First Goal and Gematria logs retain 90 days; slate snapshots retain 60 days. '
         'Model accuracy logs have no scheduled pruning. Missing/pending/void results are excluded. '
         'Research Statistical shares NP; threat badges, EdgeLab and Edge Flags share Model. '
         'Cards, goalie/shot statistics and offline audit backtests are not independent production model histories.')
UNTRACKED = ('Live next-goal events, game-winner forecasts and the Research Storylines/Overlap/Sleepers lists '
             'have no independently saved graded selection history here. The List is reference material; '
             'its pasted November 6 example is not a tracked log.')


def _records(records, today):
    """One usable record/date. Duplicates cannot inflate totals; last graded version wins."""
    out = {}
    for r in records or []:
        day = r.get('day')
        try:
            date.fromisoformat(day)
        except (ValueError, TypeError):
            continue
        res = r.get('results')
        if (day > today or r.get('demo') or r.get('final') is False or not isinstance(res, dict) or not res
                or res.get('complete') is False or res.get('status') in ('pending', 'void', 'push', 'missing', 'unknown')):
            continue
        out[day] = r
    return out


def _ids(values):
    ids = []
    for v in values or []:
        try:
            if isinstance(v, bool) or int(v) <= 0:
                continue
            pid = str(int(v))
        except (TypeError, ValueError, OverflowError):
            continue
        if pid not in ids:
            ids.append(pid)
    return ids


def _pairs(ids, res):
    """Use saved identities/outcomes, never rerank today's data. No missing scorer list = no grades."""
    if not isinstance(res.get('scorers'), list):
        return []
    scorers = _ids(s[0] if isinstance(s, (list, tuple)) else s for s in res['scorers'])
    excluded = {str(p) for key in ('voided_players', 'pending_players', 'missing_players') for p in res.get(key, [])}
    statuses = res.get('statuses') or {}
    return [(pid, pid in scorers) for pid in _ids(ids) if pid not in excluded
            and statuses.get(pid, 'graded') not in ('pending', 'void', 'push', 'missing', 'unknown')]


def _add(totals, model, day, pairs):
    if not pairs:
        return
    t = totals[model]
    # Single model/day adapter only; schema IDs already deduplicated inside pairs.
    if day in t['days']:
        return
    t['days'].append(day)
    t['correct'] += sum(bool(hit) for _, hit in pairs)
    t['predictions'] += len(pairs)


def aggregate(acc_entries=(), blend_records=(), books_records=(), firstgoal_records=(), gematria_records=(), today=None, *, model_top_ids):
    """Public logs only. The tab injects its existing frozen model-ID reader; no blend-engine import here.
    No private stake ledgers, uploads, demos or offline backtest examples.
    """
    today = today or acc.eastern_today().isoformat()
    out = {key: {'key': key, 'label': label, 'correct': 0, 'predictions': 0, 'days': []} for key, label in LABELS.items()}
    accs, blends = _records(acc_entries, today), _records(blend_records, today)
    # Model/NP use their own saved accuracy entries; existing blend's frozen/rebuilt ID lists cover missing dates.
    # Never limit this to pm.TREND_N or to dates with a blend/books log.
    for day in sorted(set(accs) | set(blends)):
        e, b = accs.get(day), blends.get(day)
        for model in ('model', 'np'):
            pairs = []
            if e:
                if model == 'model' and e.get('players'):
                    ids = model_top_ids(e['players'])
                elif model == 'np':
                    ids = acc.np_top_ids(e)
                else:
                    ids = None
                pairs = _pairs(ids, e['results'])
                # Old compacted entries may lack complete IDs. Existing grading summary is authoritative.
                # Only use it when no recoverable frozen IDs exist, not for void/pending-filtered selections.
                summary = e.get('summary') or {}
                hk, nk = ('top_hits', 'top_n') if model == 'model' else ('np_top_hits', 'np_top_n')
                h, n = summary.get(hk), summary.get(nk)
                if (ids is None and isinstance(h, int) and isinstance(n, int) and 0 <= h <= n and n > 0 and isinstance(e['results'].get('scorers'), list)
                        and not any(e['results'].get(k) for k in ('statuses', 'voided_players', 'pending_players', 'missing_players'))):
                    pairs = [(str(i), i < h) for i in range(n)]
            if not pairs and b and not e:
                pairs = _pairs(b.get(model + '_top'), b['results'])
            # NP missing in an otherwise valid old accuracy entry can use that date's saved blend NP IDs.
            if not pairs and model == 'np' and b and e and not acc.np_top_ids(e) and not (e.get('summary') or {}).get('np_top_n'):
                pairs = _pairs(b.get('np_top'), b['results'])
            _add(out, model, day, pairs)
        if b:
            _add(out, 'blend', day, _pairs([p[0] for p in b.get('top') or []], b['results']))
    for day, b in _records(books_records, today).items():
        _add(out, 'books', day, _pairs([p[0] for p in b.get('top') or []], b['results']))
    for day, r in _records(firstgoal_records, today).items():
        res, pairs = r['results'], []
        # Same definition as firstgoal_v60.score: that game's frozen favourite scored first.
        for game, fav in (r.get('favs') or {}).items():
            if (game not in (res.get('firsts') or {}) or game in res.get('voided_games', [])
                    or (res.get('statuses') or {}).get(game) in ('pending', 'void', 'push', 'missing', 'unknown')):
                continue
            ids = _ids([fav[0]])
            if ids:
                # Explicit final no-goal None is a miss under the existing first-goal definition, not absent data.
                pairs.append((game, str(res['firsts'][game]) == ids[0]))
        _add(out, 'firstgoal', day, pairs)
    for day, r in _records(gematria_records, today).items():
        res, pairs, seen = r['results'], [], set()
        if not res.get('complete') or r.get('no_games'):
            continue
        post = set(res.get('postponed') or [])
        for m in r.get('matched') or []:
            ids = _ids([m.get('pid')]); pid = ids[0] if ids else None
            key = pid
            count = (res.get('scored') or {}).get(pid)
            if (not pid or not m.get('match') or m.get('game') in post or key in seen
                    or not isinstance(count, (int, float)) or not math.isfinite(count) or count < 0):
                continue
            seen.add(key)
            pairs.append((key, count > 0))
        _add(out, 'gematria', day, pairs)
    for t in out.values():
        t['accuracy'] = t['correct'] / t['predictions'] if t['predictions'] else None
        t['days'].sort()
    return list(out.values())


def gematria_records(root=None):
    """Existing validated reader; absence is a genuine untracked state, never a fetch/backfill."""
    root = Path(root or gem.ROOT)
    return [r for r in (gem.load(p.stem, root) for p in sorted(root.glob('????-??-??.json'))) if r]


def log_signature():
    """Additional short-cache invalidation, shared core-log signature stays unchanged."""
    import firstgoal_v60 as fg
    out = []
    for root in (gem.ROOT, fg.ROOT):
        for p in sorted(root.glob('????-??-??.json')):
            try:
                out.append((str(p), p.stat().st_mtime_ns))
            except OSError:
                pass
    return tuple(out)


CSS = '''<style>
.oa60{box-sizing:border-box;min-width:0;max-width:100%;border:1px solid rgba(0,229,255,.28);border-radius:14px;padding:14px;margin:14px 0;overflow-wrap:anywhere}
.oa60 h3{color:var(--neon,#00e5ff);margin:0 0 8px}.oa60 .oa60-wrap{max-width:100%;overflow-x:auto}
.oa60 table{width:100%;border-collapse:collapse;font-size:.9rem}.oa60 th,.oa60 td{text-align:left;padding:8px;border-bottom:1px solid rgba(155,92,255,.22);vertical-align:top}
.oa60 .oa60-caption{font-size:.82rem;line-height:1.45;margin:8px 0}.oa60 td:last-child{font-variant-numeric:tabular-nums}
@media(max-width:420px){.oa60{padding:10px}.oa60 th,.oa60 td{padding:6px;font-size:.8rem}}
</style>'''


def section_html(rows):
    body = []
    for r in rows:
        value = 'Not tracked yet' if r['accuracy'] is None else f"{100*r['accuracy']:.1f}% across {r['predictions']:,} predictions"
        body.append(f'<tr><th scope="row">{escape(r["label"])}</th><td>{escape(value)}</td></tr>')
    return (CSS + '<section class="oa60" aria-label="Overall model accuracy"><h3>Overall model accuracy · tracked history</h3>'
            + f'<p class="oa60-caption">{escape(CAPTION)}</p>'
            + '<div class="oa60-wrap"><table><thead><tr><th scope="col">Model / research system</th><th scope="col">Cumulative accuracy</th></tr></thead><tbody>'
            + ''.join(body) + '</tbody></table></div>'
            + f'<details><summary>History scope &amp; system coverage</summary><p class="oa60-caption">{escape(SCOPE)}</p>'
            + f'<p class="oa60-caption">{escape(UNTRACKED)}</p></details></section>')
