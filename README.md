# File Integrity Monitor (FIM)

A Flask security tool that builds SHA-256 baselines for a folder, detects unauthorized file changes, and alerts once per event with timestamps. Includes an informative about page, live dashboard, guided 8-step demo, and integrity scoring.

## Live Demo

<!-- Deploy on Render — NOT Netlify/GitHub Pages -->
`https://file-integrity-monitor-ejg3.onrender.com`

## Can this deploy on Netlify?

**No.** This is a **Python Flask app** that reads and hashes files on the server filesystem. **Netlify** and **GitHub Pages** only host static sites. Use **[Render](https://render.com)** or **[Railway](https://railway.app)**.

> **Best experience:** run locally so the guided demo can watch the included `watch_demo` folder on your machine. Cloud deploy works for the UI and about page; file monitoring on Render uses the server’s disk (resets on free-tier restarts).

## Features

### About page (`/`)
- What FIM is and why SHA-256 is used
- Animated flow diagram (File → Hash → Baseline → Compare → Alert)
- Before/after edit mockup
- Link to **guided demo**

### Monitor dashboard (`/monitor`)
- **Guided 8-step activity** — create demo folder, copy path, baseline, monitor, edit file, alert, export, accept change
- **Live dashboard** — files watched, integrity %, status, last scan, alert count
- **SHA-256 baseline** — snapshot of every file in a directory
- **Continuous monitoring** — configurable interval (2–60 sec)
- **One alert per change** — no repeated spam; timestamp on each event
- **Hash diff** — before/after hashes on MODIFIED alerts
- **File tree** — status per file (ok / modified / deleted / created)
- **Integrity score** — percentage ring when files drift from baseline
- **Alert timeline** — CREATED / MODIFIED / DELETED with animations
- **Update baseline** — accept legitimate changes
- **Export CSV** — download alert report
- **Baseline history** — snapshot log in sidebar
- **Demo folder** — one-click `watch_demo` setup with sample files

## Tech Stack

- Python 3, Flask
- SHA-256 (`hashlib`)
- HTML, CSS, JavaScript

## Project Structure

```
├── app.py
├── run.py
├── requirements.txt
├── start.bat
├── watch_demo/          # sample files for guided demo
├── templates/
│   ├── about.html
│   └── monitor.html
├── static/
│   ├── css/style.css
│   ├── css/about.css
│   └── js/app.js
├── description.txt
└── README.md
```

## Run Locally (recommended)

```bash
pip install -r requirements.txt
python run.py
```

- **http://localhost:5004** — about / introduction
- **http://localhost:5004/monitor** — dashboard + guided demo

Or double-click `start.bat` on Windows.

### Quick guided demo

1. Open **http://localhost:5004/monitor**
2. Click **Create / reset demo folder**
3. Click **Create baseline**
4. Click **Start monitoring**
5. Edit `watch_demo/sample.txt` in Notepad and save
6. See one **MODIFIED** alert with timestamp and hash diff

## Deploy on Render (free)

1. Push this folder to a GitHub repository.
2. [Render](https://render.com) → **New → Web Service** → connect repo.
3. Settings:

| Setting | Value |
|---------|--------|
| **Build command** | `pip install -r requirements.txt` |
| **Start command** | `gunicorn app:app --bind 0.0.0.0:$PORT` |
| **Instance** | Free |

4. Deploy and paste your URL into this README under **Live Demo**.

## Deploy on Railway

Same as Render — connect repo, build with `pip install -r requirements.txt`, start with `gunicorn app:app --bind 0.0.0.0:$PORT`.

## GitHub upload checklist

1. Create repo (e.g. `file-integrity-monitor`).
2. Upload project contents (not the parent `Cyber_Sec` folder).
3. Add `description.txt` text to the repo **Description** field.
4. Optionally add a `.gitignore` excluding `baseline.json` and `baseline_history.json` if you don’t want local scan data in git.
