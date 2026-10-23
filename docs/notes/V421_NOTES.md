# Null's Playbook V4.2.1 — KeyError hotfix

Fixes the pandas KeyError in `history_v386.merge_multi_history` when previous historical columns are already present after an earlier history merge. Historical columns are replaced without `_x`/`_y` suffixes; missing optional baseline columns are handled safely.

This is a crash fix. It does not implement deferred/background history fetching, so first-load latency may still be significant.

Test suite: 73 passed.
