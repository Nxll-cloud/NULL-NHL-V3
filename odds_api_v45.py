"""Optional The Odds API v4 adapter. No credentials, no quotes; no fabricated prices."""
from datetime import datetime, timezone
import math
import requests
import pandas as pd

BASE = "https://api.the-odds-api.com/v4"
DEFAULT_MARKETS = "player_goal_scorer_anytime"

class OddsFeedError(RuntimeError):
    def __init__(self, message, code='unavailable', status=None):
        super().__init__(message)
        self.code, self.safe_message, self.status = code, message, status or {}


def _items(value):
    """Provider lists may be missing or null; only dict entries are usable."""
    return [v for v in value if isinstance(v,dict)] if isinstance(value,list) else []

def _valid_price(price):
    """American prices must be finite numbers outside (-100, 100); booleans are rejected."""
    if isinstance(price,bool) or not isinstance(price,(int,float)): return False
    if not math.isfinite(price): return False
    return price>=100 or price<=-100

def fetch_odds(api_key, *, regions="us", markets=DEFAULT_MARKETS, timeout=12, session=None, keep_event=None, event_cache=None):
    """Fetch available NHL event-level player props, retaining source event IDs and timestamps.

    Provider coverage depends on subscription, region, market availability, and supported bookmakers.
    keep_event(event) -> bool (V6.0, optional): skip events before their odds call (saves credits).
    """
    if api_key is not None and not isinstance(api_key,str):
        raise OddsFeedError("ODDS_API_KEY must be a string in top-level Streamlit secrets.", code="configuration")
    if not api_key or not str(api_key).strip():
        raise OddsFeedError("No API key configured. Add ODDS_API_KEY to Streamlit secrets or upload CSV.", code="missing_key")
    if not markets or any(not m.replace('_','').isalnum() for m in markets.split(',')):
        raise OddsFeedError("Invalid markets configuration")
    s = session or requests.Session()
    def get(path, params):
        try:
            response = s.get(BASE+path,params={**params,"apiKey":api_key},timeout=timeout)
            if response.status_code != 200:
                if response.status_code in (401,403):
                    raise OddsFeedError("Odds provider rejected credentials or market access (401/403).", code="auth")
                if response.status_code == 429:
                    raise OddsFeedError("Odds provider rate limit or quota reached (429).", code="quota")
                raise OddsFeedError(f"Odds provider returned HTTP {response.status_code}.", code="unavailable")
            try:
                return response.json()
            except ValueError as exc:  # V5.3: malformed provider JSON is a feed error, not a crash
                raise OddsFeedError("Odds provider returned malformed JSON.", code="malformed") from exc
        except requests.Timeout as exc:
            raise OddsFeedError("Odds provider request timed out.", code="timeout") from exc
        except requests.RequestException as exc:
            raise OddsFeedError("Could not reach odds provider.", code="network") from exc
    events=get('/sports/icehockey_nhl/events',{})
    if not isinstance(events,list): raise OddsFeedError('Invalid event list from provider', code='malformed')
    rows=[]; warnings=[]; issues={}; attempted=0; failed=0; event_requests=0
    fetched_at=datetime.now(timezone.utc).isoformat()
    for event in events:
        if not isinstance(event,dict) or not isinstance(event.get('id'),str) or not event['id'].strip():
            failed+=1; issues['malformed']=issues.get('malformed',0)+1
            continue
        eid=event['id']
        if keep_event is not None and not keep_event(event): continue
        attempted+=1
        try:
            def load_event():
                nonlocal event_requests
                event_requests+=1
                return get(f'/sports/icehockey_nhl/events/{eid}/odds',{'regions':regions,'markets':markets,'oddsFormat':'american','dateFormat':'iso'})
            data=event_cache(eid,load_event) if event_cache else load_event()
        except OddsFeedError as exc:
            warnings.append(f"Event {eid}: {exc.safe_message}")
            failed+=1; issues[exc.code]=issues.get(exc.code,0)+1
            continue
        if not isinstance(data,dict):
            warnings.append(f"Event {eid}: invalid odds payload")
            failed+=1; issues['malformed']=issues.get('malformed',0)+1
            continue
        for book in _items(data.get('bookmakers')):
            for market in _items(book.get('markets')):
                for outcome in _items(market.get('outcomes')):
                    player=str(outcome.get('description') or '').strip()
                    if not player: continue # exclude team odds and unidentifiable props
                    selection=str(outcome.get('name') or '').strip()
                    price=outcome.get('price')
                    if not selection or not _valid_price(price): continue
                    updated=market.get('last_update') or book.get('last_update')
                    if not updated: continue
                    rows.append({'event_id':str(eid),'player':player,'team':'',
                        'market':str(market.get('key','')),'selection':selection,
                        'line':str(outcome.get('point')) if outcome.get('point') is not None else '',
                        'sportsbook':str(book.get('title') or book.get('key') or ''),
                        'american_odds':int(price),'updated_at':updated,
                        'home_team':str(data.get('home_team') or event.get('home_team') or ''),'away_team':str(data.get('away_team') or event.get('away_team') or ''),
                        'commence_time':str(data.get('commence_time') or event.get('commence_time') or ''),'source':'The Odds API'})
    columns=['event_id','player','team','market','selection','line','sportsbook','american_odds','updated_at','home_team','away_team','commence_time','source']
    frame=pd.DataFrame(rows,columns=columns)
    frame.attrs['feed_status']={'state':'partial' if failed else 'ok' if rows else 'empty',
        'provider':'The Odds API','events':len(events),'attempted_events':attempted,'failed_events':failed,'event_requests':event_requests,
        'issues':issues,'quotes':len(rows),'fetched_at':fetched_at}
    return frame,warnings
