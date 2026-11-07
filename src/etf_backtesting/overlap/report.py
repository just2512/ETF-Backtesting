"""CSV-ready pairwise overlap report builders."""

from __future__ import annotations

import csv
from collections.abc import Mapping, Sequence
from itertools import combinations
from pathlib import Path
from typing import Any

from etf_backtesting.overlap.calculations import constituent_jaccard, weighted_overlap


def build_pairwise_overlap_report(
    constituents_by_index: Mapping[str, set[str]],
    weights_by_index: Mapping[str, Mapping[str, float] | None],
) -> list[dict[str, Any]]:
    rows = []
    for index_a, index_b in combinations(sorted(constituents_by_index), 2):
        weight_a = weights_by_index.get(index_a)
        weight_b = weights_by_index.get(index_b)
        row: dict[str, Any] = {
            "index_a": index_a,
            "index_b": index_b,
            "constituent_jaccard": constituent_jaccard(
                constituents_by_index[index_a], constituents_by_index[index_b]
            ),
            "weighted_overlap": None,
            "weight_status": "MISSING",
            "weight_error": None,
        }
        if weight_a is not None and weight_b is not None:
            try:
                row["weighted_overlap"] = weighted_overlap(weight_a, weight_b)
                row["weight_status"] = "PASS"
            except ValueError as exc:
                row["weight_status"] = "REJECT"
                row["weight_error"] = str(exc)
        rows.append(row)
    return rows


def write_overlap_csv(rows: Sequence[Mapping[str, Any]], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "index_a", "index_b", "constituent_jaccard",
        "weighted_overlap", "weight_status", "weight_error",
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
