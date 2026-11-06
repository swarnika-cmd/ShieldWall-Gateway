"""Create a project and print its API key (shown ONCE, only the hash is stored).

Usage (inside the api container):
    python scripts/create_project.py --name my-app --budget-usd 25
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg  # noqa: E402

import db  # noqa: E402
from auth import generate_api_key, hash_api_key  # noqa: E402


def create_project(name: str, budget_usd: float) -> str:
    key = generate_api_key()
    with db.sync_connect() as conn:
        db.apply_schema_sync(conn)
        with conn.transaction():
            conn.execute(
                "INSERT INTO projects (name, api_key_hash, monthly_budget_usd) VALUES (%s, %s, %s)",
                (name, hash_api_key(key), budget_usd),
            )
    return key


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--name", required=True, help="unique project name (max 64 chars)")
    parser.add_argument("--budget-usd", type=float, required=True, help="monthly budget in USD")
    parser.add_argument("--quiet", action="store_true", help="print only the key (for scripts)")
    args = parser.parse_args()

    try:
        key = create_project(args.name, args.budget_usd)
    except psycopg.errors.UniqueViolation:
        print(f"error: a project named '{args.name}' already exists", file=sys.stderr)
        return 1

    if args.quiet:
        print(key)
    else:
        print(f"Created project '{args.name}' with a monthly budget of ${args.budget_usd:.2f}.")
        print("API key (store it now, it cannot be shown again):")
        print(key)
    return 0


if __name__ == "__main__":
    sys.exit(main())
