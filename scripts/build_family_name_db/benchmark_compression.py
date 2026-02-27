"""Compression benchmark for the family name database.

Tests loading speed vs file size for raw TSV, gzip, lzma, bz2.
Run after Phase 1 generates the raw TSV.

Usage::

    uv run python -m scripts.build_family_name_db.benchmark_compression
"""

from __future__ import annotations

import bz2
import gzip
import lzma
import tempfile
import time
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import IO

TSV_PATH = Path(__file__).resolve().parent.parent.parent / "content" / "data" / "family_name_database.tsv"
ITERATIONS = 5


def _load_tsv(path: Path, open_fn: Callable[..., IO[str]]) -> int:
    """Load TSV entries using the given open function, return entry count."""
    count = 0
    with open_fn(path) as f:
        for line in f:
            if line.startswith("#"):
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 4:
                count += 1
    return count


def _benchmark(path: Path, loader: Callable[[Path], int]) -> tuple[float, int, int]:
    """Run benchmark: returns (median_ms, file_size_bytes, entry_count)."""
    file_size = path.stat().st_size
    times: list[float] = []
    count = 0

    for _i in range(ITERATIONS):
        start = time.perf_counter()
        count = loader(path)
        elapsed = (time.perf_counter() - start) * 1000
        times.append(elapsed)

    times.sort()
    median = times[len(times) // 2]
    return median, file_size, count


def main() -> None:
    if not TSV_PATH.exists():
        print(f"ERROR: {TSV_PATH} not found. Run the build script first.")
        print("  uv run python -m scripts.build_family_name_db")
        return

    print(f"Benchmarking compression formats ({ITERATIONS} iterations each)")
    print(f"Source: {TSV_PATH}")
    print(f"Source size: {TSV_PATH.stat().st_size / 1024 / 1024:.1f} MB")
    print()

    # Create compressed variants in temp dir
    raw_data = TSV_PATH.read_bytes()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # Raw TSV
        raw_path = tmp / "family_name_database.tsv"
        raw_path.write_bytes(raw_data)

        # gzip
        gz_path = tmp / "family_name_database.tsv.gz"
        with gzip.open(gz_path, "wb", compresslevel=9) as f:
            f.write(raw_data)

        # lzma
        xz_path = tmp / "family_name_database.tsv.xz"
        with lzma.open(xz_path, "wb", preset=9) as f:
            f.write(raw_data)

        # bz2
        bz2_path = tmp / "family_name_database.tsv.bz2"
        with bz2.open(bz2_path, "wb", compresslevel=9) as f:
            f.write(raw_data)

        print(f"{'Format':<10} {'Size':>10} {'Ratio':>8} {'Load (ms)':>10} {'Entries':>10}")
        print("-" * 55)

        results: list[tuple[str, float, int, int]] = []

        for name, path, open_fn in [
            ("Raw TSV", raw_path, lambda p: p.open(encoding="utf-8")),
            ("gzip", gz_path, lambda p: gzip.open(p, "rt", encoding="utf-8")),  # noqa: SIM115
            ("lzma", xz_path, lambda p: lzma.open(p, "rt", encoding="utf-8")),  # noqa: SIM115
            ("bz2", bz2_path, lambda p: bz2.open(p, "rt", encoding="utf-8")),  # noqa: SIM115
        ]:
            loader = partial(_load_tsv, open_fn=open_fn)
            median, size, count = _benchmark(path, loader)
            ratio = size / len(raw_data)
            results.append((name, median, size, count))
            print(f"{name:<10} {size / 1024:>8.0f} KB {ratio:>7.1%} {median:>9.1f}ms {count:>10,}")

        print()

        # Recommendation
        print("Decision criteria: Load time < 100ms, then smallest file.")
        fast_enough = [(n, t, s, c) for n, t, s, c in results if t < 100]
        if fast_enough:
            best = min(fast_enough, key=lambda x: x[2])
            print(f"Recommendation: {best[0]} ({best[2] / 1024:.0f} KB, {best[1]:.1f}ms)")
        else:
            print("WARNING: No format loads under 100ms!")
            best = min(results, key=lambda x: x[1])
            print(f"Fastest: {best[0]} ({best[1]:.1f}ms)")


if __name__ == "__main__":
    main()
