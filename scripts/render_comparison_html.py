"""Render an offline interactive HTML report from comparison artifacts."""

from __future__ import annotations

import argparse
from pathlib import Path

from etf_backtesting.reports.html_report import render_comparison_html


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--comparison-dir",
        default="reports/backtests/latest",
        help="directory containing comparison.json and runs/",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="output HTML path (defaults to <comparison-dir>/comparison.html)",
    )
    args = parser.parse_args()
    path = render_comparison_html(
        Path(args.comparison_dir),
        Path(args.output) if args.output else None,
    )
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
