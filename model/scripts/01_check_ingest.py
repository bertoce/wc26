"""Smoke-test the historical results ingest.

Run from the repo root:
    .venv/bin/python model/scripts/01_check_ingest.py
"""

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env.local")

from wc26.ingest import load_results  # noqa: E402  (load_dotenv must come first)


def main() -> None:
    print("Loading historical results...")
    df = load_results()
    print(f"  {len(df):,} matches loaded")
    print(f"  date range: {df.date.min().date()} → {df.date.max().date()}")
    print(f"  teams: {len(set(df.home_team) | set(df.away_team)):,}")
    print(f"  tournaments: {df.tournament.nunique()}")
    print()
    print("Top tournaments by match count:")
    print(df.tournament.value_counts().head(10).to_string())


if __name__ == "__main__":
    main()
