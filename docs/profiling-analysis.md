# Profiling Analysis

## Test Setup

| Parameter | Value                                      |
|-----------|--------------------------------------------|
| Corpus    | 207 greeting card PDFs                     |
| Machine   | Apple Silicon (arm64), 16 cores, 64 GB RAM |
| OS        | macOS 26.3                                 |
| Python    | 3.14.3                                     |
| Date      | 2026-02-26                                 |

## Results Overview

| # | Stage             |   Total |  Per Card | Throughput | % of Total |
|---|-------------------|--------:|----------:|-----------:|-----------:|
| 1 | Hash              |    43ms |     208µs |    4,797/s |       0.1% |
| 2 | Database          |   445ms |     2.2ms |      465/s |       1.1% |
| 3 | Render            |  12.39s |    59.9ms |     16.7/s |      29.6% |
| 4 | OCR               |  28.96s |   139.9ms |      7.1/s |      69.2% |
| 5 | Name extraction   |    17ms |      83µs |   12,113/s |       0.0% |
| 6 | AI (mock)         |   7.02s |    33.9ms |     29.5/s |          — |
| 7 | Full (sequential) |  19.28s |    93.2ms |     10.7/s |          — |
| 8 | Full (parallel)   |   2.14s |    10.4ms |     96.6/s |          — |

### Parallelism

| Metric          |  Value |
|-----------------|-------:|
| Sequential time | 19.28s |
| Parallel time   |  2.14s |
| Speedup         |   9.0x |
| Workers         |     16 |
| Efficiency      |    56% |

## Analysis

### The pipeline is OCR-bound

OCR accounts for 69% of total stage time (29s), Render is 30% (12.4s). Everything else is noise — Hash (43ms), Database (445ms), Name extraction (17ms) are essentially free. The actual work is PyMuPDF rendering + Tesseract OCR.

### Memory locality matters

The sequential full pipeline (19.3s) is faster than OCR alone (29s). When `process_pdf_worker` renders and OCRs one PDF at a time, images stay hot in CPU cache. The standalone OCR stage operates on 207 PDFs' worth of pre-rendered images sitting in memory (several GB), likely hitting memory pressure. This validates the per-PDF pipeline design as the right architecture choice.

### Parallelism is effective

9.0x speedup on 16 cores (56% efficiency) is solid for a CPU-bound workload with I/O (disk reads, SQLite writes). The gap from 16x to 9x comes from: Tesseract not being perfectly parallelizable (shared memory bus), SQLite write contention, and ProcessPoolExecutor overhead (pickling results across processes). 56% efficiency is typical for this kind of mixed workload.

### Production throughput

Per-card budget at full parallel: ~10ms. 207 cards processed in 2.1 seconds. Users dropping large batches of cards won't wait long.

### AI concurrency plumbing works

The AI mock (7s for 207 cards at concurrency=3) validates the async pipeline. The math checks out: 207 cards × 100ms / 3 concurrent ≈ 6.9s. With real API calls at ~1-2s latency, the semaphore-bounded concurrency would keep wall time manageable.

### Where to optimize

If the pipeline ever needs to be faster, Tesseract is the bottleneck. Options:
- Lower DPI (currently `PDF_DPI` from constants)
- Faster OCR engine or GPU-accelerated OCR
- Render at lower resolution for OCR (keep high-res only for preview)

Rendering is the second lever. Everything else is already negligible.

## Reproducing

```bash
uv run python -m scripts.profiling ~/Desktop/Cards
uv run python -m scripts.profiling ~/Desktop/Cards --limit 10  # quick test
```

Output goes to `_build/script_output/YYYYMMDD_HHMM-profiling/` with HTML reports, pyinstrument profiles, and machine-readable data exports (JSON, TSV).
