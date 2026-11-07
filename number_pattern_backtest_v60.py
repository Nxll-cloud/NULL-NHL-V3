"""Saved historical audit presentation only. No API fetches, backtest execution or live selection changes."""
from pathlib import Path
from html import escape
import json

SUMMARY = Path(__file__).resolve().parent / 'backtests' / 'number_patterns_2026-11-07_summary.json'
STYLE = '''<style>
.npaudit{min-width:0;max-width:100%;box-sizing:border-box;overflow-wrap:anywhere}
.npaudit h3,.npaudit h4{color:#c9b6ff}.npaudit .npaudit-scroll{max-width:100%;overflow-x:auto;-webkit-overflow-scrolling:touch}
.npaudit table{border-collapse:collapse;width:100%;min-width:760px;font-size:.82rem}
.npaudit td,.npaudit th{padding:8px;text-align:left;vertical-align:top;border-bottom:1px solid rgba(155,92,255,.22)}
.npaudit th{color:#c9b6ff}.npaudit p,.npaudit li{font-size:.86rem;line-height:1.5}
.npaudit .npaudit-warning{padding:10px;border-left:3px solid #9b5cff;background:rgba(155,92,255,.07)}
.npaudit a{color:#8ed5ff}.npaudit code{overflow-wrap:anywhere;white-space:normal}
@media(max-width:420px){.npaudit td,.npaudit th{padding:6px}}
</style>'''


def load_summary(path=None):
    data = json.loads(Path(path or SUMMARY).read_text(encoding='utf-8'))
    if data.get('schema_version') != 1 or data.get('historical_audit_not_live_forecast') is not True:
        raise ValueError('Unsupported saved audit summary')
    return data


def _e(v):
    return escape(str(v))


def _pct(v):
    return f'{100*v:.2f}%' if v is not None else 'Not testable'


def _ci(values, percent=False):
    if not values:
        return 'Not available'
    return ('[' + ', '.join(f'{100*v:+.2f}' if percent else f'{v:.3f}' for v in values) + ']' + (' pp' if percent else ''))


def _table(headers, rows):
    return ('<div class="npaudit-scroll" tabindex="0" role="region" aria-label="Saved historical audit table"><table><thead><tr>'
            + ''.join(f'<th scope="col">{_e(h)}</th>' for h in headers) + '</tr></thead><tbody>'
            + ''.join('<tr>' + ''.join(f'<td>{_e(v)}</td>' for v in row) + '</tr>' for row in rows) + '</tbody></table></div>')


def section_html(data=None):
    d = data if data is not None else load_summary()
    c, controls = d['coverage'], d['controls']
    core = d['core']
    primary = core[0]
    out = [STYLE, '<section class="npaudit" aria-label="Historical number-pattern audit">',
           '<h3>Number-pattern historical audit</h3>', f'<p>Saved results · as of {_e(d["as_of"])} · 2024–25 and 2025–26 regular seasons</p>',
           f'<p><strong>{_e(d["verdict"])}</strong></p>',
           f'<p>{c["games"]:,} final games · {c["dates"]:,} dates · {c["skater_appearances"]:,} dressed-skater appearances. '
           'Zero-goal appearances are included; goalies are excluded from skater denominators. OT goals count; shootout deciding goals do not.</p>',
           f'<p>Primary date cohort: {_pct(primary["scoring_hit_rate"])} scored versus {_pct(primary["control_scoring_hit_rate"])} in controls '
           f'({primary["scorers"]:,} scorers / {primary["skater_appearances"]:,} appearances; {primary["games"]} games across {primary["dates"]} dates).</p>',
           '<p class="npaudit-warning">The later group <b>4, 10, 0, 9, 3, 6</b> and '
           '<b>Possible date mapping: October 9th, 36.</b> were <b>not tested</b> as a group or mapping. '
           'This saved audit does not validate today’s optional player-row overlay; no meaning or year is inferred for 36.</p>',
           '<p>Core date rule: <code>' + _e(d['core_formula']) + '</code>. It returns only 1–9; values above 9 cannot match. '
           'The primary core exposure is root 9, not 91–93 or 19. '
           + _e(d['undefined_literal']) + '</p>',
           '<h4>Core date cohorts · observational, not frozen model picks</h4>']
    rows = [[r['group'], f'{r["games"]} / {r["dates"]}', f'{r["scorers"]:,} / {r["skater_appearances"]:,}',
             _pct(r['scoring_hit_rate']), _pct(r['control_scoring_hit_rate']),
             f'{r["goals_per_game"]:.3f} · {_ci(r["goals_per_game_95ci"])}', f'{r["control_goals_per_game"]:.3f}',
             f'{r["goals_permutation_p"]:.4f}'] for r in core]
    out.append(_table(['Group', 'Games / dates', 'Scorers / appearances', 'Scoring hit rate', 'Control rate',
                       'Goals/game · 95% date-cluster CI', 'Control goals/game', 'Date-permutation p'], rows))
    out.append('<p>Zero core exposures (not 0% accuracy): ' + _e('; '.join(d['zero_core_exposure_groups'])) + '.</p>')
    out.append('<p>' + _e(d['date_only_win_warning']) + '</p>')
    out.append('<details><summary>Methods, uncertainty, separate alignment arms &amp; sources</summary>')
    out.append(f'<p>Controls: {controls["repetitions"]:,} seeded equal-size samples without replacement within '
               f'{_e(controls["strata"])}; {controls["bootstrap_repetitions"]:,} bootstrap replicates; '
               f'{controls["date_label_permutations"]:,} date-label permutations. '
               'Control values are repeated-sample means, not independent experimental replications. '
               + _e(controls['dependence']) + '.</p>')
    out.append('<p>Player/name alignment is a separate English-root/day arm, using all dressed skaters on core dates, '
               'not historical Form ranks or TOP PICK reconstructions. Equal-size nonmatching player controls come from the same games. '
               'The intervals below are differences from controls, not confidence intervals around the raw hit rate.</p>')
    rows = []
    for r in core:
        p = r['player_day_match']
        rows.append([r['group'], f'{p["matched_scorers"]} / {p["matched_appearances"]}', _pct(p['hit_rate']),
                     _pct(p['repeated_control_mean_hit_rate']), _ci(r['player_day_match_crossed_cluster_ci'], True)])
    out.append(_table(['Player alignment', 'Scorers / appearances', 'Hit rate', 'Same-game control rate',
                       'Difference · 95% crossed date/player CI'], rows))
    rows = []
    for r in core:
        t = r['unique_team_alignment']
        lo, hi = t['hit_rate_95ci']
        rows.append([r['group'], f'{t["wins"]} / {t["games"]}', _pct(t['hit_rate']),
                     f'{_pct(lo)}–{_pct(hi)}', f'{t["both_aligned_excluded"]} / {t["neither_aligned_excluded"]}',
                     f'{t["p_date_cluster_signflip"]:.4f}'])
    out.append('<p>Unique-team alignment is descriptive: only one team matches the existing team/day cipher test. '
               'Both/neither matches are excluded. Team strength remains a confounder; this is not a winner model.</p>')
    out.append(_table(['Team alignment', 'Wins / games', 'Win rate', '95% date-cluster CI', 'Both / neither excluded',
                       'Date-label p'], rows))
    out.append('<h4>Expanded date matches · exploratory only, not the app’s scoring rule</h4>'
               '<p>Separate month/day-of-month/unreduced digit-sum/root expansion. Undefined 2-21 is not expanded. '
               'Insufficient unmatched season/month controls remain not testable; no replacement or relaxed fallback.</p>')
    rows = []
    for r in d['expanded_exploratory']:
        ctl = r['control']
        rows.append([r['group'], f'{r["games"]} / {r["dates"]}', _pct(r['scoring_hit_rate']),
                     _pct(ctl['skater_goal_hit_rate']) if ctl else 'Not testable',
                     f'{r["goals_per_game"]:.3f}', f'{r["p"]:.4f}' if r['p'] is not None else 'Not testable'])
    out.append(_table(['Expanded group', 'Games / dates', 'Scoring hit rate', 'Control rate', 'Goals/game', 'Permutation p'], rows))
    mult = d['multiplicity']
    out.append(f'<p>{mult["planned_testable_comparisons"]} planned testable comparisons; smallest unadjusted p '
               f'{mult["smallest_unadjusted_p"]:.3f}; smallest Holm-adjusted p {mult["smallest_holm_p"]:.3f}. '
               'No reliable edge. Overlapping cohorts are not independent. Historical pattern provenance and player usage '
               'can be confounded; this is not a prospective betting test and has no odds/ROI analysis.</p>')
    out.append(f'<p>Seeds: {d["primary_seed"]}, {d["robustness_seed"]}. '
               f'{c["goalie_goals_not_in_skater_table"]} official goalie goals are included only in game totals; '
               f'{c["shootouts"]} shootout deciding goals excluded. '
               f'{c["goals_exceed_shots_rows_retained"]} official goals-over-shots rows retained after the saved audit’s boxscore checks.</p>')
    out.append('<p>Official data sources: ' + ' · '.join(f'<a href="{_e(s["url"])}">{_e(s["name"])}</a>' for s in d['sources']) + '.</p>')
    out.append('<p>Saved audit traceability: results SHA-256 <code>' + _e(d['traceability']['results_json_sha256'])
               + '</code>; source manifest SHA-256 <code>' + _e(d['traceability']['source_manifest_sha256']) + '</code>. '
               'Only the compact summary is bundled here; no raw dataset, recomputation or runtime source fetch.</p>')
    out.append('</details></section>')
    return ''.join(out)


def render(st):
    import v55_ui as v5
    with st.expander('Historical number-pattern audit · 2024–25 & 2025–26', expanded=False):
        try:
            v5.html_block(st, section_html(), extra_class='v58-num')
        except (OSError, ValueError, KeyError, TypeError):
            st.caption('Saved historical audit unavailable. No live calculation or source fetch was attempted.')
