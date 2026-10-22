"""Optional The Odds API v4 adapter. No credentials, no quotes; no fabricated prices."""
from datetime import datetime, timezone
import requests
import pandas as pd

BASE = "https://api.the-odds-api.com/v4"
DEFAULT_MARKETS = "player_goal_scorer_anytime"

class OddsFeedError(RuntimeError):
    pass

def fetch_odds(api_key, *, regions="us", markets=DEFAULT_MARKETS, timeout=12, session=None):
    """Fetch available NHL event-level player props, retaining source event IDs and timestamps.

    Provider coverage depends on subscription, region, market availability, and supported bookmakers.
    """
    if not api_key or not str(api_key).strip():
        raise OddsFeedError("No API key configured. Add ODDS_API_KEY to Streamlit secrets or upload CSV.")
    if not markets or any(not m.replace('_','').isalnum() for m in markets.split(',')):
        raise OddsFeedError("Invalid markets configuration")
    s = session or requests.Session()
    def get(path, params):
        try:
            response = s.get(BASE+path,params={**params,"apiKey":api_key},timeout=timeout)
            if response.status_code != 200:
                if response.status_code in (401,403):
                    raise OddsFeedError("Odds provider rejected credentials or market access (401/403).")
                if response.status_code == 429:
                    raise OddsFeedError("Odds provider rate limit or quota reached (429).")
                raise OddsFeedError(f"Odds provider returned HTTP {response.status_code}.")
            return response.json()
        except requests.RequestException as exc:
            raise OddsFeedError("Could not reach odds provider.") from exc
    events=get('/sports/icehockey_nhl/events',{})
    if not isinstance(events,list): raise OddsFeedError('Invalid event list from provider')
    rows=[]; warnings=[]
    for event in events:
        eid=event.get('id')
        if not eid: continue
        try:
            data=get(f'/sports/icehockey_nhl/events/{eid}/odds',{'regions':regions,'markets':markets,'oddsFormat':'american','dateFormat':'iso'})
        except OddsFeedError as exc:
            warnings.append(f"Event {eid}: {exc}")
            continue
        for book in data.get('bookmakers',[]):
            for market in book.get('markets',[]):
                for outcome in market.get('outcomes',[]):
                    player=str(outcome.get('description') or '').strip()
                    if not player: continue # exclude team odds and unidentifiable props
                    selection=str(outcome.get('name') or '').strip()
                    price=outcome.get('price')
                    if not selection or not isinstance(price,(int,float)) or price==0: continue
                    updated=market.get('last_update') or book.get('last_update')
                    if not updated: continue
                    rows.append({'event_id':str(eid),'player':player,'team':'',
                        'market':str(market.get('key','')),'selection':selection,
                        'line':str(outcome.get('point')) if outcome.get('point') is not None else '',
                        'sportsbook':str(book.get('title') or book.get('key') or ''),
                        'american_odds':int(price),'updated_at':updated,
                        'home_team':str(data.get('home_team','')),'away_team':str(data.get('away_team','')),
                        'commence_time':str(data.get('commence_time','')),'source':'The Odds API'})
    columns=['event_id','player','team','market','selection','line','sportsbook','american_odds','updated_at','home_team','away_team','commence_time','source']
    return pd.DataFrame(rows,columns=columns),warnings
