"""Optional, noisy benchmark checks for the bundled example algorithms.

Run with ``python benchmark_sanity.py``. This script prints repeated empirical
estimates but intentionally does not assert a particular class: benchmark
results vary with Python version, hardware, and system load.
"""

from collections import Counter

from complexity_analyzer_empirical import complexity
from sample_algorithms import (
    constant,
    exponential,
    linear,
    linearithmic,
    logarithmic,
    quadratic,
)


BENCHMARKS = (
    ("constant", constant, (8, 16, 32, 64, 128)),
    ("logarithmic", logarithmic, (16, 64, 256, 1024, 4096)),
    ("linear", linear, (1_000, 2_000, 4_000, 8_000, 16_000)),
    ("linearithmic", linearithmic, (128, 256, 512, 1_024, 2_048)),
    ("quadratic", quadratic, (20, 40, 80, 160, 320)),
    # Exponential inputs are intentionally small to keep the run bounded.
    ("exponential", exponential, (4, 6, 8, 10, 12)),
)


RUNS_PER_ALGORITHM = 3
TRIALS_PER_RUN = 5


def main() -> None:
    for name, function, sizes in BENCHMARKS:
        results = []
        for _ in range(RUNS_PER_ALGORITHM):
            report = complexity(function, sizes=sizes, trials=TRIALS_PER_RUN)
            results.append((report.estimated_complexity, report.classification_status))
        counts = Counter(results)
        print(f"{name} on sizes {sizes}")
        for (estimate, status), count in sorted(counts.items()):
            print(f"  {estimate} ({status}): {count}/{RUNS_PER_ALGORITHM} runs")


if __name__ == "__main__":
    main()
