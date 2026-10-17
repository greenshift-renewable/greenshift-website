#!/usr/bin/env python3
"""
Show the enquiries saved by the website, straight from the database file.

    python view_enquiries.py                    -> print them on screen
    python view_enquiries.py --csv leads.csv    -> save them as a spreadsheet file

Times are shown in UTC (Nigeria is UTC+1, so add one hour).
Run it from the same folder as server.py.
"""
import csv
import sys

import server


def main():
    server.load_env(server.BASE_DIR / ".env")
    server.init_db()
    rows = server.list_enquiries()

    if len(sys.argv) >= 3 and sys.argv[1] == "--csv":
        with open(sys.argv[2], "w", newline="", encoding="utf-8-sig") as fh:  # utf-8-sig opens cleanly in Excel
            writer = csv.writer(fh)
            writer.writerow(["id", "received (UTC)", "name", "phone", "email", "type", "message"])
            for r in rows:
                writer.writerow([r["id"], r["created_at"], r["name"], r["phone"], r["email"], r["type"], r["message"]])
        print("Saved %d enquiries to %s" % (len(rows), sys.argv[2]))
        return

    if not rows:
        print("No enquiries saved yet.")
        return
    print("%d enquiries (newest first)\n" % len(rows))
    for r in rows:
        print("#%s  %s (UTC)" % (r["id"], r["created_at"]))
        print("  Name:    %s" % r["name"])
        print("  Phone:   %s" % r["phone"])
        print("  Email:   %s" % (r["email"] or "-"))
        print("  Type:    %s" % r["type"])
        print("  Details: %s" % ((r["message"] or "-").replace("\n", "\n           ")))
        print()


if __name__ == "__main__":
    main()
