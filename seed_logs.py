#!/usr/bin/env python3
"""Seed ChronoPulse with 4 client projects and 14 realistic work sessions.

Usage:
    python3 seed_logs.py            # seed only when the database is empty
    python3 seed_logs.py --reset    # wipe demo data and seed again
"""

from __future__ import annotations

import argparse
from contextlib import closing
from datetime import date, datetime, timedelta

from app import db, init_db

PROJECTS = [
    ("AeroCast Weather API", "AeroCast Labs", 1850.0, "#38BDF8"),
    ("FishWorld UI", "FishWorld Studio", 1450.0, "#14B8A6"),
    ("CyberRecon Audit", "Nexus Security", 2200.0, "#F59E0B"),
    ("MentorBridge Auth", "MentorBridge Inc.", 1600.0, "#A78BFA"),
]

# day offset from Monday, start time, minutes, project index, task, billable
SESSIONS = [
    (0, "09:30", 150, 0, "Designed /forecast/hourly API contract + rate-limit middleware", 1),
    (0, "12:15", 75, 1, "Rebuilt dashboard sidebar + frosted glass card system", 1),
    (0, "14:30", 120, 2, "Automated Nmap port-scan pipeline & JSON report parser", 1),
    (1, "10:00", 180, 0, "Implemented Redis cache layer for geolocation lookups", 1),
    (1, "13:45", 90, 3, "OAuth2 login flow + JWT refresh-token rotation", 1),
    (1, "16:15", 60, 1, "Fixed mobile navigation overlap at 375px breakpoint", 1),
    (2, "09:45", 210, 2, "Built CVSS v3.1 vulnerability scoring logic", 1),
    (2, "14:00", 105, 0, "Dockerised forecast worker with health checks", 1),
    (3, "10:30", 120, 3, "Role-based access control for mentor sessions", 1),
    (3, "13:00", 90, 1, "Shipped dark-mode design tokens & chart palette", 1),
    (4, "09:15", 165, 0, "Load-tested 10k req/min with Locust + Grafana", 1),
    (4, "13:30", 120, 2, "Client audit report review & remediation notes", 1),
    (5, "11:00", 75, 3, "Weekly backlog grooming + internal engineering docs", 0),
    (5, "12:30", 60, 1, "Polished onboarding micro-interactions", 1),
]


def seed(reset: bool = False) -> None:
    init_db()
    with closing(db()) as conn:
        existing = conn.execute("SELECT COUNT(*) FROM time_logs").fetchone()[0]
        if existing and not reset:
            print(f"ChronoPulse already has {existing} time logs. Use --reset to reseed.")
            return

        if reset:
            conn.execute("DELETE FROM time_logs")
            conn.execute("DELETE FROM projects")
            conn.execute(
                "DELETE FROM sqlite_sequence WHERE name IN ('projects', 'time_logs')"
            )

        rates: dict[int, float] = {}
        project_ids: list[int] = []
        for name, client, rate, color in PROJECTS:
            cur = conn.execute(
                "INSERT INTO projects (name, client_name, hourly_rate, color_tag) VALUES (?, ?, ?, ?)",
                (name, client, rate, color),
            )
            project_ids.append(cur.lastrowid)
            rates[cur.lastrowid] = rate

        monday = date.today() - timedelta(days=date.today().weekday())
        total_seconds = 0
        for day_offset, start, minutes, pidx, task, billable in SESSIONS:
            log_date = monday + timedelta(days=day_offset)
            start_dt = datetime.strptime(start, "%H:%M")
            end_dt = start_dt + timedelta(minutes=minutes)
            seconds = minutes * 60
            earnings = round(seconds / 3600 * rates[project_ids[pidx]], 2) if billable else 0.0
            total_seconds += seconds
            conn.execute(
                """
                INSERT INTO time_logs
                    (project_id, task_description, log_date, start_time, end_time,
                     duration_seconds, billable, earnings)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_ids[pidx],
                    task,
                    log_date.isoformat(),
                    start_dt.strftime("%H:%M"),
                    end_dt.strftime("%H:%M"),
                    seconds,
                    billable,
                    earnings,
                ),
            )

        conn.commit()

    print(f"Seeded {len(PROJECTS)} projects and {len(SESSIONS)} sessions.")
    print(f"Week of {monday.isoformat()} | {total_seconds / 3600:.2f} hours logged.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed ChronoPulse demo data")
    parser.add_argument("--reset", action="store_true", help="Replace existing demo data")
    args = parser.parse_args()
    seed(args.reset)
