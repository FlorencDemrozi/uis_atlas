# Deploying the weekly update on a UiS server

`pipeline/run_weekly.py` does the whole update in one command: collectors (Scopus,
UiS employee directory, RCN calls), processing (`run_all.py`) and the website build.
This page sets it up as a weekly scheduled job on a Windows server at UiS.

## What a weekly run does

1. **Scopus**: after the first full search, each run searches only the last
   `config.SCOPUS_REFRESH_YEARS` (2) calendar years again. New papers are added,
   citation counts of recent papers are updated, and older papers are kept. Detail
   lookups (departments) run only for authors who still need them. A typical run
   uses a few hundred API requests, well within the weekly quota.
2. **Employee directory and RCN calls** are collected again.
3. **Processing**: profiles, summaries (Anthropic API, only for changed researchers),
   embeddings, public export, funding matching.
4. **Website** build to `web/dist/`.
5. **Publishing** (only with `--publish`): the licence guard (`tests/test_policy.py`)
   runs, then `data/public/` alone is committed and pushed. The GitHub Pages
   workflow then redeploys the site.

If a collector fails (e.g. Scopus 401/403 or quota), the previous data is used and
the problem is listed at the end. If a processing stage fails, the run stops and
nothing is built or published. All output goes to `logs/weekly-<date>.log` (local
only, last 26 runs kept).

## Server requirements

- Windows server **on the UiS network** (Elsevier recognises the IP range), or an
  institutional token (`SCOPUS_INSTTOKEN`) from the UiS Library.
- Outbound HTTPS to: `api.elsevier.com`, `api.anthropic.com`, `www.uis.no`,
  `www.forskningsradet.no`, `huggingface.co` (first download of the embedding
  model), `github.com` (only with `--publish`), `registry.npmjs.org` (`npm ci`).
- Python 3.12, Node.js 22, Git.
- A service account to run the job. Keep the files on a local disk, **not**
  OneDrive or a synced folder.
- Disk: about 1 GB (raw Scopus data, model cache, `node_modules`).

## One-time setup

```powershell
# 1. Code (outside any synced folder)
git clone https://github.com/FlorencDemrozi/uis_atlas.git D:\uis_atlas
cd D:\uis_atlas

# 2. Python environment (outside the repo) and web dependencies
py -3.12 -m venv C:\python-envs\.atlas
C:\python-envs\.atlas\Scripts\python.exe -m pip install -r requirements.txt
cd web; npm ci; cd ..

# 3. Secrets: fill in SCOPUS_API_KEY, ANTHROPIC_API_KEY, ATLAS_FUNDING_PASSWORD,
#    ATLAS_FIRST_YEAR (same value as on your laptop), SCOPUS_INSTTOKEN if needed
Copy-Item .env.example .env
notepad .env
```

4. **Copy the existing data** from your laptop, so the first run does not repeat
   the full Scopus download: `data\raw\` and `data\interim\` into the same folders on
   the server. These contain licensed data and personal data: copy them over a UiS
   network share or encrypted storage, never via e-mail or public cloud storage.
   Make sure the `.env` file on the server allows read access for the service
   account only.

5. **Test run by hand** and read the log:

   ```powershell
   C:\python-envs\.atlas\Scripts\python.exe pipeline\run_weekly.py
   ```

## Publishing the result: choose one

**A. Push to GitHub Pages (current site).** Give the server push access to the
repository with a deploy key (*Settings → Deploy keys → Allow write access*), stored
in the service account's `~/.ssh`. Set the remote to SSH
(`git remote set-url origin git@github.com:FlorencDemrozi/uis_atlas.git`) and set
`git config user.name` / `user.email` for the server. Add `--publish` to the
scheduled command. Each run then pulls the latest code (`git pull --ff-only`) and
pushes only `data/public/`. Do not edit files on the server by hand; if the pull
cannot fast-forward, the run stops.

**B. Serve from a UiS web server.** Leave out `--publish` and point IIS (or nginx)
at `D:\uis_atlas\web\dist`, or add a step that copies that folder to the web server.
The build replaces `web/dist/` in a few seconds, so a visitor may very rarely see
an incomplete page during the run.

## Schedule (Windows Task Scheduler)

Every Saturday at 01:00, as the service account, whether or not anyone is logged on:

```powershell
schtasks /Create /TN "UiS Atlas weekly" /SC WEEKLY /D SAT /ST 01:00 /RU "UIS\svc-atlas" /RP * `
  /TR "C:\python-envs\.atlas\Scripts\python.exe D:\uis_atlas\pipeline\run_weekly.py --publish"
```

Leave out `--publish` for option B. `/RP *` asks for the account password once.
Check the result in Task Scheduler (*Last Run Result* 0 = success) and in `logs\`.
Run it now to test: `schtasks /Run /TN "UiS Atlas weekly"`.

Linux cron alternative: `0 1 * * 6 cd /srv/uis_atlas && /path/to/python pipeline/run_weekly.py --publish`.

## Maintenance

- **New code**: with option A the server pulls before each run. With option B, run
  `git pull` (and `npm ci` if `web/package-lock.json` changed) on the server.
- **Scopus quota or access errors** are in the log; the site keeps the last data.
  Run `pipeline\collect_scopus.py` by hand later. It resumes where it stopped.
- **Full re-collection** (e.g. a new `ATLAS_FIRST_YEAR`): change it in `.env`; the
  next run searches the whole range again.
