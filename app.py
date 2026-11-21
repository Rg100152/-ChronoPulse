#!/usr/bin/env python3
"""ChronoPulse - Precision Work-Hour Tracker & Timesheet Studio.

A lightweight, production-ready Flask application that turns live stopwatch
sessions and manual work logs into clean, client-ready timesheets.

Developed by Raj Gautam - https://github.com/Rg100152
"""

from __future__ import annotations

import csv
import io
import os
import re
import sqlite3
from contextlib import closing
from datetime import date, datetime, timedelta

from flask import (
    Flask,
    Response,
    jsonify,
    render_template,
    request,
    send_from_directory,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database", "chronopulse.db")

app = Flask(__name__)

DEVELOPER = {
    "name": "Raj Gautam",
    "email": "graj13099@gmail.com",
    "phone": "+91 9555785729",
    "instagram": "@linuxuser.raj",
    "instagram_url": "https://instagram.com/linuxuser.raj",
    "github": "https://github.com/Rg100152",
    "role": "Lead Developer & Full-Stack Engineer",
}


# --------------------------------------------------------------------------- #
# Database helpers
# --------------------------------------------------------------------------- #
def db() -> sqlite3.Connection:
    """Open a SQLite connection with row access by column name."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Create the database file and tables if they do not exist yet."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with closing(db()) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                name         TEXT NOT NULL UNIQUE,
                client_name  TEXT NOT NULL,
                hourly_rate  REAL NOT NULL DEFAULT 0,
                color_tag    TEXT NOT NULL DEFAULT '#F59E0B',
                created_at   TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS time_logs (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id        INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                task_description  TEXT NOT NULL,
                log_date          TEXT NOT NULL,
                start_time        TEXT,
                end_time          TEXT,
                duration_seconds  INTEGER NOT NULL,
                billable          INTEGER NOT NULL DEFAULT 1,
                earnings          REAL NOT NULL DEFAULT 0,
                created_at        TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_logs_date ON time_logs(log_date);
            CREATE INDEX IF NOT EXISTS idx_logs_project ON time_logs(project_id);
            """
        )
        conn.commit()


def week_bounds(ref: date | None = None) -> tuple[date, date]:
    """Return Monday and Sunday of the week containing ``ref``."""
    ref = ref or date.today()
    monday = ref - timedelta(days=ref.weekday())
    return monday, monday + timedelta(days=6)


def parse_range(args) -> tuple[date, date]:
    """Parse from/to filters with a sensible current-week default."""
    monday, sunday = week_bounds()
    try:
        start = date.fromisoformat(args.get("from") or args.get("from_date") or monday.isoformat())
    except ValueError:
        start = monday
    try:
        end = date.fromisoformat(args.get("to") or args.get("to_date") or sunday.isoformat())
    except ValueError:
        end = sunday
    if start > end:
        start, end = end, start
    return start, end


def get_projects(conn: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM projects ORDER BY id")]


def get_logs(
    conn: sqlite3.Connection,
    start: date,
    end: date,
    project_id: int = 0,
    billable: str = "all",
) -> list[dict]:
    sql = """
        SELECT l.*, p.name AS project_name, p.client_name,
               p.hourly_rate, p.color_tag
        FROM time_logs l
        JOIN projects p ON p.id = l.project_id
        WHERE l.log_date BETWEEN ? AND ?
    """
    params: list = [start.isoformat(), end.isoformat()]
    if project_id:
        sql += " AND l.project_id = ?"
        params.append(project_id)
    if billable == "billable":
        sql += " AND l.billable = 1"
    elif billable == "non-billable":
        sql += " AND l.billable = 0"
    sql += " ORDER BY l.log_date DESC, l.start_time DESC, l.id DESC"

    rows = []
    for row in conn.execute(sql, params):
        item = dict(row)
        item["hours"] = round(item["duration_seconds"] / 3600, 2)
        rows.append(item)
    return rows


def dashboard_payload(conn: sqlite3.Connection | None = None) -> dict:
    """Build every value rendered by the dashboard and /api/dashboard."""
    own_connection = conn is None
    conn = conn or db()
    try:
        today = date.today()
        monday, sunday = week_bounds(today)
        projects = get_projects(conn)
        week_logs = get_logs(conn, monday, sunday)
        today_logs = [r for r in week_logs if r["log_date"] == today.isoformat()]

        week_seconds = sum(r["duration_seconds"] for r in week_logs)
        today_seconds = sum(r["duration_seconds"] for r in today_logs)
        billable_amount = round(sum(r["earnings"] for r in week_logs if r["billable"]), 2)

        per_project: dict[int, int] = {}
        for log in week_logs:
            per_project[log["project_id"]] = per_project.get(log["project_id"], 0) + log["duration_seconds"]
        top_name, top_seconds = "No data yet", 0
        if per_project:
            top_id, top_seconds = max(per_project.items(), key=lambda kv: kv[1])
            top_name = next((p["name"] for p in projects if p["id"] == top_id), "No data yet")

        chart = []
        for offset in range(7):
            day = monday + timedelta(days=offset)
            day_logs = [r for r in week_logs if r["log_date"] == day.isoformat()]
            seconds = sum(r["duration_seconds"] for r in day_logs)
            chart.append(
                {
                    "date": day.isoformat(),
                    "day": day.strftime("%a"),
                    "day_num": day.day,
                    "hours": round(seconds / 3600, 2),
                    "earnings": round(sum(r["earnings"] for r in day_logs), 2),
                    "is_today": day == today,
                    "heat": min(4, int(seconds // 7200) + 1) if seconds else 0,
                }
            )

        recent = get_logs(conn, monday - timedelta(days=60), sunday)[:8]

        return {
            "projects": projects,
            "stats": {
                "today_hours": round(today_seconds / 3600, 2),
                "week_hours": round(week_seconds / 3600, 2),
                "billable_amount": billable_amount,
                "top_project": top_name,
                "top_project_hours": round(top_seconds / 3600, 2),
                "sessions": len(week_logs),
            },
            "chart": chart,
            "recent_logs": recent,
            "generated_at": datetime.now().strftime("%d %b %Y, %I:%M %p"),
        }
    finally:
        if own_connection:
            conn.close()


# --------------------------------------------------------------------------- #
# Global template context
# --------------------------------------------------------------------------- #
@app.context_processor
def inject_globals() -> dict:
    return {"dev": DEVELOPER, "app_name": "ChronoPulse"}


# --------------------------------------------------------------------------- #
# Pages
# --------------------------------------------------------------------------- #
@app.get("/")
def index():
    with closing(db()) as conn:
        payload = dashboard_payload(conn)
    return render_template("index.html", **payload)


@app.get("/timesheet")
@app.get("/timesheet/print")
def timesheet():
    print_mode = request.path.endswith("/print")
    start, end = parse_range(request.args)
    try:
        project_id = int(request.args.get("project") or request.args.get("project_id") or 0)
    except ValueError:
        project_id = 0
    billable = request.args.get("billable", "all")
    if billable not in ("all", "billable", "non-billable"):
        billable = "all"

    with closing(db()) as conn:
        projects = get_projects(conn)
        logs = get_logs(conn, start, end, project_id, billable)

    total_seconds = sum(r["duration_seconds"] for r in logs)
    billable_logs = [r for r in logs if r["billable"]]
    total_earnings = round(sum(r["earnings"] for r in billable_logs), 2)
    clients = sorted({r["client_name"] for r in logs})

    query = {
        "from": start.isoformat(),
        "to": end.isoformat(),
        "project": project_id,
        "billable": billable,
    }
    return render_template(
        "timesheet.html",
        projects=projects,
        logs=logs,
        query=query,
        clients=clients,
        total_hours=round(total_seconds / 3600, 2),
        total_earnings=total_earnings,
        session_count=len(logs),
        avg_hourly=round(total_earnings / (total_seconds / 3600), 2) if total_seconds else 0,
        print_mode=print_mode,
        issued_on=date.today().isoformat(),
        invoice_no="CP-" + start.strftime("%Y%m%d") + "-" + end.strftime("%Y%m%d"),
    )


@app.get("/favicon.svg")
def favicon():
    return send_from_directory(
        os.path.join(BASE_DIR, "static", "assets"), "logo-chronopulse.svg"
    )


@app.get("/health")
def health():
    with closing(db()) as conn:
        projects = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        logs = conn.execute("SELECT COUNT(*) FROM time_logs").fetchone()[0]
    return jsonify({"status": "ok", "projects": projects, "logs": logs})


# --------------------------------------------------------------------------- #
# JSON APIs
# --------------------------------------------------------------------------- #
@app.get("/api/dashboard")
def api_dashboard():
    with closing(db()) as conn:
        return jsonify(dashboard_payload(conn))


@app.get("/api/projects")
def api_projects():
    with closing(db()) as conn:
        return jsonify({"projects": get_projects(conn)})


@app.post("/api/projects")
def api_add_project():
    data = request.get_json(silent=True) or {}
    name = str(data.get("name") or "").strip()
    client = str(data.get("client_name") or "").strip()
    try:
        rate = round(float(data.get("hourly_rate") or 0), 2)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Invalid hourly rate."}), 400
    color = str(data.get("color_tag") or "#F59E0B")
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", color):
        color = "#F59E0B"
    if not name or not client or rate < 0:
        return jsonify({"ok": False, "error": "name, client_name and a valid rate are required."}), 400

    with closing(db()) as conn:
        try:
            cur = conn.execute(
                "INSERT INTO projects (name, client_name, hourly_rate, color_tag) VALUES (?, ?, ?, ?)",
                (name, client, rate, color),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            return jsonify({"ok": False, "error": "A project with that name already exists."}), 409
        project = dict(conn.execute("SELECT * FROM projects WHERE id = ?", (cur.lastrowid,)).fetchone())
    return jsonify({"ok": True, "project": project}), 201


@app.post("/api/log")
def api_add_log():
    data = request.get_json(silent=True) or {}
    try:
        project_id = int(data.get("project_id") or 0)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Invalid project."}), 400

    task = str(data.get("task_description") or "").strip() or "Untitled work session"
    log_date = str(data.get("log_date") or date.today().isoformat())
    try:
        date.fromisoformat(log_date)
    except ValueError:
        return jsonify({"ok": False, "error": "Invalid date. Use YYYY-MM-DD."}), 400

    start_time = str(data.get("start_time") or "").strip() or None
    end_time = str(data.get("end_time") or "").strip() or None
    duration = data.get("duration_seconds")

    try:
        if duration in (None, ""):
            hours = float(data.get("hours") or 0)
            if hours <= 0 and start_time and end_time:
                fmt = "%H:%M:%S" if ":" in start_time and start_time.count(":") == 2 else "%H:%M"
                delta = datetime.strptime(end_time, fmt) - datetime.strptime(start_time, fmt)
                hours = delta.total_seconds() / 3600
            duration = int(round(hours * 3600))
        else:
            duration = int(float(duration))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Invalid duration."}), 400

    if duration <= 0:
        return jsonify({"ok": False, "error": "Duration must be greater than zero."}), 400

    billable_raw = str(data.get("billable", "1")).lower()
    billable = 1 if billable_raw in ("1", "true", "yes", "on") else 0

    with closing(db()) as conn:
        project = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not project:
            return jsonify({"ok": False, "error": "Project not found."}), 404
        earnings = round(duration / 3600 * project["hourly_rate"], 2) if billable else 0.0
        cur = conn.execute(
            """
            INSERT INTO time_logs
                (project_id, task_description, log_date, start_time, end_time,
                 duration_seconds, billable, earnings)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (project_id, task[:240], log_date, start_time, end_time, duration, billable, earnings),
        )
        conn.commit()
        row = dict(
            conn.execute(
                """
                SELECT l.*, p.name AS project_name, p.client_name, p.color_tag
                FROM time_logs l JOIN projects p ON p.id = l.project_id
                WHERE l.id = ?
                """,
                (cur.lastrowid,),
            ).fetchone()
        )
    return jsonify({"ok": True, "log": row, "earnings": earnings}), 201


@app.delete("/api/log/<int:log_id>")
def api_delete_log(log_id: int):
    with closing(db()) as conn:
        cur = conn.execute("DELETE FROM time_logs WHERE id = ?", (log_id,))
        conn.commit()
    if cur.rowcount == 0:
        return jsonify({"ok": False, "error": "Log not found."}), 404
    return jsonify({"ok": True, "deleted": log_id})


# --------------------------------------------------------------------------- #
# CSV export
# --------------------------------------------------------------------------- #
@app.get("/api/export/csv")
def export_csv():
    start, end = parse_range(request.args)
    try:
        project_id = int(request.args.get("project") or request.args.get("project_id") or 0)
    except ValueError:
        project_id = 0
    billable = request.args.get("billable", "all")
    if billable not in ("all", "billable", "non-billable"):
        billable = "all"

    with closing(db()) as conn:
        logs = get_logs(conn, start, end, project_id, billable)

    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(
        ["Date", "Project", "Client", "Task Description", "Start", "End",
         "Hours", "Billable", "Rate", "Earnings (INR)"]
    )
    for log in logs:
        writer.writerow(
            [
                log["log_date"],
                log["project_name"],
                log["client_name"],
                log["task_description"],
                log["start_time"] or "",
                log["end_time"] or "",
                f'{log["duration_seconds"] / 3600:.2f}',
                "Yes" if log["billable"] else "No",
                f'{log["hourly_rate"]:.2f}',
                f'{log["earnings"]:.2f}',
            ]
        )
    total_seconds = sum(r["duration_seconds"] for r in logs)
    total_earnings = sum(r["earnings"] for r in logs)
    writer.writerow([])
    writer.writerow(
        ["TOTAL", f"{len(logs)} sessions", "", "", "", "",
         f"{total_seconds / 3600:.2f}", "", "", f"{total_earnings:.2f}"]
    )
    writer.writerow(["Generated by ChronoPulse - Raj Gautam", "", "", "", "", "", "", "", "", ""])

    filename = f"ChronoPulse_Timesheet_{start.isoformat()}_{end.isoformat()}.csv"
    response = Response("\ufeff" + output.getvalue(), mimetype="text/csv; charset=utf-8")
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


# --------------------------------------------------------------------------- #
# Boot
# --------------------------------------------------------------------------- #
init_db()

if __name__ == "__main__":
    print("\n  ChronoPulse is running  ->  http://127.0.0.1:5000")
    print("  Precision Work-Hour Tracker by Raj Gautam\n")
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", 5000)),
        debug=os.environ.get("FLASK_DEBUG") == "1",
    )
