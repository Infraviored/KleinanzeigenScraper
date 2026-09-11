#!/usr/bin/env python3
import sqlite3
import os
import sys

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scraper"
    ),
)
import db_schema  # noqa: E402
import json


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db_path = db_schema.default_path()
    progress_path = os.path.join(base_dir, "data", "scraper_progress.json")
    log_path = os.path.join(base_dir, "data", "scraper.log")

    print("========================================")
    print("      Kleinanzeigen Scraper Reset Tool  ")
    print("========================================")

    if not os.path.exists(db_path):
        print(f"Database not found at: {db_path}")
        return

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Count current listings
        cursor.execute("SELECT COUNT(*) FROM listings")
        count = cursor.fetchone()[0]

        print(f"Found {count} listings in the database.")

        if count > 0:
            # Delete listings
            cursor.execute("DELETE FROM listings")
            conn.commit()
            print(f"Successfully deleted {count} listings.")
        else:
            print("No listings found to clear.")

        conn.close()

        # Reset scraper_progress.json
        if os.path.exists(progress_path):
            with open(progress_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "active": False,
                        "progress": {
                            "phase": "idle",
                            "current": 0,
                            "total": 0,
                            "status": "Scraper is idle.",
                        },
                    },
                    f,
                    indent=2,
                )
            print("Successfully reset scraper_progress.json state.")

        # Truncate scraper.log if exists
        if os.path.exists(log_path):
            with open(log_path, "w", encoding="utf-8") as f:
                f.write("")
            print("Successfully truncated scraper.log file.")

        print("\nReset process completed successfully.")
        print(
            "Campaigns, search targets, knowledge profiles, and cookies remain untouched."
        )
        print("========================================")

    except Exception as e:
        print(f"Error occurred during reset: {str(e)}")


if __name__ == "__main__":
    main()
