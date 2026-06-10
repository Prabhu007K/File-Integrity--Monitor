"""File Integrity Monitor — http://localhost:5004"""
import hashlib
import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path

from flask import Flask, render_template, request, jsonify

APP_DIR = os.path.dirname(os.path.abspath(__file__))
BASELINE_FILE = os.path.join(APP_DIR, "baseline.json")
HISTORY_FILE = os.path.join(APP_DIR, "baseline_history.json")
DEMO_DIR = os.path.join(APP_DIR, "watch_demo")

monitor_state = {
    "active": False,
    "path": None,
    "interval": 5,
    "alerts": [],
    "alerted_keys": set(),
    "last_check": None,
    "thread": None,
}


def sha256_file(filepath):
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def hash_directory(dir_path):
    baseline = {}
    root = Path(dir_path)
    if not root.is_dir():
        raise ValueError("Path is not a directory")
    for fp in root.rglob("*"):
        if fp.is_file():
            rel = str(fp.relative_to(root)).replace("\\", "/")
            try:
                baseline[rel] = {
                    "hash": sha256_file(fp),
                    "size": fp.stat().st_size,
                    "modified": fp.stat().st_mtime,
                }
            except OSError:
                continue
    return baseline


def load_baseline():
    if os.path.exists(BASELINE_FILE):
        with open(BASELINE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_baseline(data):
    with open(BASELINE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_history(entries):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(entries[-20:], f, indent=2)


def push_baseline_history(baseline, label="snapshot"):
    entries = load_history()
    entries.append({
        "label": label,
        "path": baseline.get("path"),
        "created": baseline.get("created"),
        "file_count": len(baseline.get("files", {})),
        "files": baseline.get("files", {}),
    })
    save_history(entries)


def alert_key(alert_type, path):
    return f"{alert_type}:{path}"


def add_alert(alert_type, path, detail="", hash_before=None, hash_after=None):
    key = alert_key(alert_type, path)
    if key in monitor_state["alerted_keys"]:
        return False

    now = datetime.now()
    alert = {
        "type": alert_type,
        "path": path,
        "detail": detail,
        "time": now.isoformat(),
        "time_display": now.strftime("%Y-%m-%d %H:%M:%S"),
        "hash_before": hash_before,
        "hash_after": hash_after,
    }
    monitor_state["alerted_keys"].add(key)
    monitor_state["alerts"].insert(0, alert)
    monitor_state["alerts"] = monitor_state["alerts"][:100]
    return True


def clear_alerts():
    monitor_state["alerts"] = []
    monitor_state["alerted_keys"] = set()


def compare_baselines(old, new):
    old_files = set(old.get("files", {}).keys())
    new_files = set(new.get("files", {}).keys())

    for f in new_files - old_files:
        add_alert("CREATED", f, "New file detected", hash_after=new["files"][f]["hash"])
    for f in old_files - new_files:
        add_alert("DELETED", f, "File removed", hash_before=old["files"][f]["hash"])
    for f in old_files & new_files:
        oh, nh = old["files"][f]["hash"], new["files"][f]["hash"]
        if oh != nh:
            add_alert("MODIFIED", f, "SHA-256 hash changed", hash_before=oh, hash_after=nh)


def compute_integrity(baseline, current_files):
    if not baseline.get("files"):
        return {"score": 100, "total": 0, "ok": 0, "changed": 0, "missing": 0, "extra": 0}

    old_files = set(baseline["files"].keys())
    new_files = set(current_files.keys())
    ok = sum(
        1 for f in old_files & new_files
        if baseline["files"][f]["hash"] == current_files[f]["hash"]
    )
    missing = len(old_files - new_files)
    extra = len(new_files - old_files)
    modified = sum(
        1 for f in old_files & new_files
        if baseline["files"][f]["hash"] != current_files[f]["hash"]
    )
    total = len(old_files)
    changed = missing + modified + extra
    score = round((ok / total) * 100) if total else 100

    return {
        "score": max(0, score),
        "total": total,
        "ok": ok,
        "changed": changed,
        "missing": missing,
        "extra": extra,
        "modified": modified,
    }


def build_file_tree(baseline, current_files):
    tree = []
    all_paths = sorted(set(baseline.get("files", {}).keys()) | set(current_files.keys()))
    for rel in all_paths:
        in_base = rel in baseline.get("files", {})
        on_disk = rel in current_files
        if in_base and on_disk:
            bh = baseline["files"][rel]["hash"]
            ch = current_files[rel]["hash"]
            status = "ok" if bh == ch else "modified"
            tree.append({
                "path": rel,
                "status": status,
                "hash": ch,
                "baseline_hash": bh,
                "size": current_files[rel]["size"],
            })
        elif in_base and not on_disk:
            tree.append({
                "path": rel,
                "status": "deleted",
                "hash": None,
                "baseline_hash": baseline["files"][rel]["hash"],
                "size": baseline["files"][rel]["size"],
            })
        else:
            tree.append({
                "path": rel,
                "status": "created",
                "hash": current_files[rel]["hash"],
                "baseline_hash": None,
                "size": current_files[rel]["size"],
            })
    return tree


def ensure_demo_folder():
    os.makedirs(DEMO_DIR, exist_ok=True)
    sample = os.path.join(DEMO_DIR, "sample.txt")
    readme = os.path.join(DEMO_DIR, "notes.txt")
    if not os.path.exists(sample):
        with open(sample, "w", encoding="utf-8") as f:
            f.write("Hello from FIM demo — edit this line to trigger a MODIFIED alert.\n")
    if not os.path.exists(readme):
        with open(readme, "w", encoding="utf-8") as f:
            f.write("This folder is watched by the File Integrity Monitor.\n")
    return DEMO_DIR


def monitor_loop():
    while monitor_state["active"]:
        try:
            current_files = hash_directory(monitor_state["path"])
            baseline = load_baseline()
            if baseline.get("path") == monitor_state["path"] and baseline.get("files"):
                compare_baselines(baseline, {"files": current_files})
            monitor_state["last_check"] = datetime.now().isoformat()
        except Exception as e:
            add_alert("ERROR", monitor_state["path"] or "?", str(e))
        time.sleep(monitor_state["interval"])


def create_app():
    app = Flask(__name__)

    @app.route("/")
    def about():
        return render_template("about.html")

    @app.route("/monitor")
    def monitor_page():
        return render_template("monitor.html")

    @app.route("/api/demo/path")
    def demo_path():
        path = ensure_demo_folder()
        return jsonify({"path": path})

    @app.route("/api/demo/create", methods=["POST"])
    def demo_create():
        path = ensure_demo_folder()
        return jsonify({
            "success": True,
            "path": path,
            "message": "Demo folder ready with sample.txt and notes.txt",
        })

    @app.route("/api/status")
    def status():
        baseline = load_baseline()
        path = baseline.get("path") or monitor_state.get("path")
        current_files = {}
        if path and os.path.isdir(path):
            try:
                current_files = hash_directory(path)
            except ValueError:
                pass

        integrity = compute_integrity(baseline, current_files)
        return jsonify({
            "monitoring": monitor_state["active"],
            "watch_path": monitor_state["path"] or path,
            "file_count": len(baseline.get("files", {})),
            "baseline_created": baseline.get("created"),
            "last_check": monitor_state["last_check"],
            "alert_count": len(monitor_state["alerts"]),
            "integrity": integrity,
            "files": build_file_tree(baseline, current_files),
        })

    @app.route("/api/baseline/history")
    def baseline_history():
        hist = load_history()
        summary = [{
            "label": h.get("label"),
            "path": h.get("path"),
            "created": h.get("created"),
            "file_count": h.get("file_count"),
        } for h in reversed(hist)]
        current = load_baseline()
        if current.get("created"):
            summary.insert(0, {
                "label": "current",
                "path": current.get("path"),
                "created": current.get("created"),
                "file_count": len(current.get("files", {})),
            })
        return jsonify({"history": summary[:10]})

    @app.route("/api/baseline", methods=["GET"])
    def get_baseline():
        data = load_baseline()
        return jsonify({
            "baseline": data,
            "file_count": len(data.get("files", {})),
            "monitoring": monitor_state["active"],
            "watch_path": monitor_state["path"],
        })

    @app.route("/api/baseline", methods=["POST"])
    def create_baseline():
        data = request.get_json() or {}
        path = (data.get("path") or "").strip()
        if not path or not os.path.isdir(path):
            return jsonify({"error": "Valid directory path required"}), 400
        try:
            old = load_baseline()
            if old.get("files"):
                push_baseline_history(old, "before rebaseline")
            baseline = {
                "path": path,
                "created": datetime.now().isoformat(),
                "files": hash_directory(path),
            }
            save_baseline(baseline)
            push_baseline_history(baseline, "baseline created")
            clear_alerts()
            integrity = compute_integrity(baseline, baseline["files"])
            return jsonify({
                "success": True,
                "file_count": len(baseline["files"]),
                "path": path,
                "integrity": integrity,
            })
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    @app.route("/api/baseline/update", methods=["POST"])
    def update_baseline():
        """Accept current disk state as new trusted baseline."""
        baseline = load_baseline()
        path = baseline.get("path")
        if not path or not os.path.isdir(path):
            return jsonify({"error": "No baseline path set"}), 400
        push_baseline_history(baseline, "before accept changes")
        new_files = hash_directory(path)
        new_baseline = {
            "path": path,
            "created": datetime.now().isoformat(),
            "files": new_files,
        }
        save_baseline(new_baseline)
        push_baseline_history(new_baseline, "changes accepted")
        clear_alerts()
        return jsonify({
            "success": True,
            "file_count": len(new_files),
            "integrity": compute_integrity(new_baseline, new_files),
        })

    @app.route("/api/monitor/start", methods=["POST"])
    def start_monitor():
        data = request.get_json() or {}
        path = (data.get("path") or "").strip()
        interval = int(data.get("interval", 5))
        baseline = load_baseline()
        if not path:
            path = baseline.get("path")
        if not path or not os.path.isdir(path):
            return jsonify({"error": "Set a valid watch directory first"}), 400
        if monitor_state["active"]:
            return jsonify({"error": "Monitor already running"}), 400

        monitor_state["active"] = True
        monitor_state["path"] = path
        monitor_state["interval"] = max(2, min(interval, 60))
        t = threading.Thread(target=monitor_loop, daemon=True)
        monitor_state["thread"] = t
        t.start()
        return jsonify({
            "success": True,
            "path": path,
            "interval": monitor_state["interval"],
        })

    @app.route("/api/monitor/stop", methods=["POST"])
    def stop_monitor():
        monitor_state["active"] = False
        return jsonify({"success": True})

    @app.route("/api/alerts")
    def get_alerts():
        return jsonify({
            "alerts": monitor_state["alerts"],
            "active": monitor_state["active"],
            "last_check": monitor_state["last_check"],
        })

    @app.route("/api/scan-now", methods=["POST"])
    def scan_now():
        baseline = load_baseline()
        path = baseline.get("path")
        if not path:
            return jsonify({"error": "No baseline set"}), 400
        current_files = hash_directory(path)
        compare_baselines(baseline, {"files": current_files})
        return jsonify({"alerts": monitor_state["alerts"][:20]})

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5004))
    print(f"File Integrity Monitor -> http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
