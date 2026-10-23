"""Null's Playbook V5.6 · edgelab tab. Executed by tabs.run_tab() inside the app's namespace (split from app.py, unchanged logic)."""
# ============================================================ V5.5 EdgeLab
def _edgelab_conn():
    """Fresh connection per operation (Streamlit reruns on other threads); file sits next to the tracker DB."""
    import sqlite3
    _p=trk.db_path().parent/'edgelab.sqlite'
    _p.parent.mkdir(parents=True,exist_ok=True)
    return sqlite3.connect(str(_p),timeout=10)

edgelab.render_edgelab(quotes=_np_shared_clean,conn_factory=_edgelab_conn)
