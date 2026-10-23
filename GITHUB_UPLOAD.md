# Uploading Null’s Playbook to GitHub (V5.5)

GitHub warns about files over **50 MB** and rejects files over **100 MB** (and web uploads over 25 MB per file).
The source tree is under 1 MB; anything large is local data, a build artefact or a video and must stay out.

## 1. Unzip
The release zip has its files at the **top level** (no wrapper folder, no nested zips):

    mkdir nulls-playbook && cd nulls-playbook
    unzip ../Nulls_Playbook_V5_5.zip

## 2a. Command line

    git init -b main
    python check_repo_size.py          # must end with "OK: no file over the fail limit."
    git add .
    git status                          # review: no data/, *.sqlite, *.zip, secrets, videos
    git commit -m "Null's Playbook V5.5"
    git remote add origin https://github.com/<you>/<repo>.git
    git push -u origin main

## 2b. GitHub Desktop
File → Add local repository → choose the unzipped folder → “create a repository” when asked →
check the Changes list (same rules as below) → Commit to main → Publish repository.

## 3. What NOT to commit (already in `.gitignore`)
* `venv/`, `.venv/`, `env/`, `__pycache__/`, `.pytest_cache/`
* `*.zip` (release zips), `data/` and every `*.sqlite*` (tracker + EdgeLab stores)
* `snapshots/*.json` (the GitHub workflow generates and force-adds them; `snapshots/.gitkeep` keeps the folder)
* `.streamlit/secrets.toml` — **never** commit `ODDS_API_KEY`; put it in Streamlit Cloud → App → Settings → Secrets.
  `SGO_API_KEY` (future) is read only from `st.secrets` as well.
* logs (`*.log`, `logs/`), screenshots (`playbook_screens/`), videos and GIFs (`*.mp4`, `*.gif`)

## 4. Check sizes before every push

    python check_repo_size.py              # top 15 files; warn > 50 MB; exit 1 on any file > 95 MB
    python check_repo_size.py --top 30 --fail-mb 90

It respects `.gitignore` (uses `git ls-files` inside a repo, a built-in matcher otherwise). The scheduled workflow
runs it before committing snapshots. Optional local hook:

    cp tools/pre-commit.sample .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit

## 5. Data that grows
* **Snapshots:** the workflow runs `python snapshot_store.py prune --keep-days 60`, which deletes only
  `snapshots/YYYY-MM-DD.json` files older than 60 days (preview with `--dry-run`). A missing snapshot just
  means the app computes that date live. Nothing else is ever deleted automatically.
* **Track Record:** the SQLite store is local and ignored. Export with *Export history (JSON)* or the new
  per-month export (*Month to export*) on the Track Record tab; each month imports back with *Import*.

## 6. Finding big files

    du -ah . | sort -rh | head -20                                   # working tree
    git rev-list --objects --all | git cat-file --batch-check='%(objecttype) %(objectname) %(objectsize) %(rest)' \
      | awk '/^blob/ {print $3, $4}' | sort -rn | head -20           # everything in history

## 7. A big file already got committed
Deleting it in a new commit is not enough — it stays in history and the push is still rejected.

    pip install git-filter-repo
    git filter-repo --path data/prediction_tracker_v54.sqlite --invert-paths     # or --strip-blobs-bigger-than 50M
    git remote add origin https://github.com/<you>/<repo>.git                    # filter-repo removes the remote
    git push --force -u origin main

(Force-pushing rewrites the remote history — make sure nobody else depends on it first.)

## 8. Git LFS
Only for **intentional** large datasets you really want versioned (`git lfs track "datasets/*.parquet"`).
Do not use LFS for the tracker DB, snapshots, zips or screenshots — keep those out of git.
