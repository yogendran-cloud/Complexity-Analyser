# Complexity Analyzer

An empirical Python library for measuring the runtime and peak traced memory
usage of a **trusted callable** across integer input sizes. It reports repeated
measurements and compares runtime patterns to common growth classes. The
runtime growth label is a heuristic, not a proof of theoretical Big-O; memory
is reported as peak traced bytes, not as a separate asymptotic space-class
estimate.

## Install

Python 3.10 or newer is required. The core library uses only the Python
standard library; installing it does not install Streamlit.
The package declares Python 3.10–3.14 classifiers and a minimum version of
Python 3.10. Local release validation was performed on Python 3.14.3. GitHub
Actions CI passed the complete Windows, Ubuntu, and macOS matrix for Python
3.10–3.14 on commit
[`27ad258`](https://github.com/yogendran-cloud/Complexity-Analyser/commit/27ad2586f8cfd585cf769362d8c59c25ef1f0d06).

Project repository: <https://github.com/yogendran-cloud/Complexity-Analyser>.

```sh
python -m pip install complexity-analyzer-empirical
```

The PyPI distribution is named `complexity-analyzer-empirical`; the Python
import module is `complexity_analyzer_empirical`. This module name is distinct
from the `complexity_analyzer` module installed by a separate PyPI distribution
named `complexity-analyzer`, avoiding their previous top-level module collision.

To install the optional dashboard dependency as well:

```sh
python -m pip install "complexity-analyzer-empirical[dashboard]"
```

For local development, install the project and dashboard extra with
`python -m pip install -e ".[dashboard]"`. The `dashboard.py` and
`sample_algorithms.py` modules remain included in the distribution; Streamlit
is only needed to import/run the dashboard.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for the
full license text and copyright notice.

## Streamlit dashboard

After installing the dashboard extra, launch the interactive dashboard from the
project folder:

```sh
python -m streamlit run dashboard.py
```

The dashboard exposes only the bundled trusted sample algorithms. Select a
sample, set increasing comma-separated input sizes and trial count, then choose
**Run analysis**. Form submission prevents benchmarks from rerunning on ordinary
page refreshes; results are kept in the session until another analysis is
submitted. Input caps are specific to each sample, especially the quadratic
and exponential examples, to keep runs bounded. Results include the empirical
estimate and evidence status, measurements, trial details, and CSV/SVG download
buttons. It does not accept or execute user-supplied Python code.

The public API is `complexity(my_function, sizes=..., trials=...)`; it can be
called from any Python project using a callable you trust.

## Quick start

Keep your function in Python code you trust, then pass it directly:

```python
from complexity_analyzer_empirical import complexity


def sum_values(size: int) -> int:
    return sum(range(size))


report = complexity(sum_values, sizes=(100, 500, 1_000, 2_000), trials=5)
print(report.format_report())
report.save_csv("measurements.csv")
report.save_plot("measurements.svg")
```

The core test suite does not require Streamlit:

```sh
python -m unittest -v test_analyzer
```

The separate dashboard tests need the optional extra. Install it and run both
suites with:

```sh
python -m pip install ".[dashboard]"
python -m unittest -v test_analyzer test_dashboard
```

The report contains median execution time in seconds, median peak traced
memory in bytes, and the likely growth class. The CSV export can be opened in a
spreadsheet; the SVG plot can be opened in a browser or vector graphics editor.
CSV rows include the estimate, classification status, and explanatory note;
the SVG chart displays the estimate and status so tentative and inconclusive
results remain visibly qualified outside the text report.
The default sizes are `(2, 4, 8, 12, 16)`: a bounded range with an 8x span,
chosen to provide more growth information than the old 4-to-20 range without
using huge inputs by default. For a particular algorithm, choose a more useful
range explicitly. For example, exponential work should use small sizes such as
`(4, 6, 8, 10, 12)`; an expensive quadratic or input-allocating function may
also need smaller values.

## Included sample algorithms

The `sample_algorithms.py` module provides `constant`, `logarithmic`, `linear`,
`linearithmic`, `quadratic`, and `exponential` for experiments. For example:

```python
from complexity_analyzer_empirical import complexity
from sample_algorithms import linear

report = complexity(linear, sizes=(100, 500, 1_000, 2_000), trials=3)
print(report.format_report())
```

Use small sizes for `exponential` (for example, 4 through 16).

For a repeated, non-asserting benchmark sanity check across the bundled
algorithms, run `python benchmark_sanity.py`. It prints the estimates and
statuses from three independent analyses per algorithm. The output is
diagnostic only: it deliberately does not make tests pass or fail based on
wall-clock classifications.

## Measurement details and limitations

- A callable is invoked once per size as an untimed warm-up. By default, each
	timing trial repeats it until at least 2 ms has elapsed, checking the timer
	every 25 calls and stopping at 100,000 calls. Pass `repetitions=...` to request
	an exact number of timed calls per trial (from 1 to 100,000). The trial's
	elapsed duration is divided by the actual call count; raw durations and counts
	are retained in each measurement and exported to CSV.
- Functions must accept one integer size and be safe to invoke repeatedly.
	Warm-up, timing, and memory passes all execute user code; state changes,
	caching, random behavior, external I/O, or other side effects can distort
	results. Do not benchmark functions that must run only once or have unsafe
	consequences. Analyzed code must not start or stop global `tracemalloc`.
- Runtime calls are timed with `tracemalloc` off; a separate call per trial
	measures peak traced memory. This avoids memory tracing changing the runtime
	measurement. Reported time and memory are medians; time variability is shown
	as median absolute deviation (MAD). `tracemalloc` measures Python-traced
	peak allocations, not total process memory and not a direct proof of
	auxiliary-space complexity.
- Very short explicit-repetition runs may be dominated by timer resolution and
	benchmark-loop overhead. Such reports are downgraded to **tentative** when a
	timed trial finishes before the 2 ms target; inspect raw trial data or use
	more repetitions. The adaptive default reduces this issue but cannot remove
	Python call and loop overhead completely.
- Machine load, interpreter behavior, input ranges, caching, garbage
	collection, and function side effects can affect results. Small inputs or
	noisy measurements may lead to a misleading classification. Increase sizes
	and trials and inspect the measurements rather than relying only on the label.
- Candidate estimates are limited to O(1), O(log n), O(n), O(n log n), O(n^2),
  and O(2^n); real algorithms may not match these shapes.
- This library accepts an already-created Python callable. It does not parse,
	evaluate, or execute source code supplied as text. Only analyze code you
	trust; measuring a callable still runs that callable.
- The analyzer requires `tracemalloc` not to be active before analysis so it
	does not interfere with an existing tracing session.

## Reading the classification status

- **plausible** means one supported model has a reasonable fit, low observed
	trial variation, a clear lead over the next-best model, enough sizes/trials,
	and remains the best fit when any one size is omitted. This is a qualified
	empirical estimate, not a formal probability or proof of theoretical Big-O.
- **tentative** means a best-fit estimate is available, but the tested range
	was narrow, there were too few raw trials, the fit error is noticeable, or
	the winner changes when an input size is omitted.
- **inconclusive** means variability was high or the measurements did not
	closely follow a supported pattern, one point is a strong outlier, or the
	best and next-best models fit too similarly on the supplied sizes. The report
	still shows its best-fit estimate for exploration. The existing
	`reliable_complexity` property is retained for compatibility and returns a
	value only for a **plausible** result; its name does not imply certainty.

The rules are applied in this order. Let relative noise be the largest
	per-size `time_mad_seconds / median_time_seconds`; fit error and model gaps are
	measured in log-time units, so exponentiating an error gives a multiplicative
	time factor:

1. **Inconclusive** if relative noise is over 0.35, the largest absolute
	log-residual is over `log(3)` (a greater than 3x miss at one size), the
	blended median/mean absolute residual is over `log(1.5)`, or the second-best
	model's error lead is no larger than `max(0.02, log1p(relative_noise))`.
2. **Tentative** if the size span is under 8x, fewer than four sizes are
	available, fewer than three requested or retained raw trials are available,
	relative noise exceeds 0.20, median fit error exceeds `log(1.25)`, fewer than
	five sizes are available for leave-one-out checking, or omitting any one size
	changes the winner.
3. **Plausible** otherwise: all prior checks pass and the same model wins every
	leave-one-size-out fit.

These cutoffs are conservative engineering guardrails, not statistically
	calibrated confidence levels. In particular, the model-gap comparison uses
	per-size median absolute deviation as a rough noise scale rather than a formal
	confidence interval. A **plausible** status should therefore be read as
	“the measurements support this candidate under these checks,” not as a
	probability or theoretical guarantee.

For example, a short linear loop can initially look linearithmic when overhead
is large relative to the work. The analyzer now times code without memory
tracing and uses a fixed-shape curve fit, but small ranges and environment noise
can still blur nearby classes.

## Estimator audit notes

The estimator compares `log(time)` to `log(candidate growth)` and fits only a
	constant scale factor per candidate. All candidates therefore have the same
	number of fitted parameters. It uses a median-based scale and a blend of
	median and mean absolute log residuals: the median reduces sensitivity to an
	outlier, while the mean keeps a bad point from disappearing completely.
	Close model fits are inconclusive; a single large residual is also checked.
	For a plausible label, the same candidate must win after each input size is
	removed in turn. These checks are safeguards, not formal statistical
	confidence intervals, and nearby models can remain indistinguishable on a
	particular finite range.

The timer now runs with tracing disabled because `tracemalloc` can add
	per-allocation overhead and distort runtime growth. A separate invocation is
	used for memory each trial. The untimed warm-up is retained to reduce one-time
	startup effects; the callable therefore needs to be repeatable and safe to
	invoke multiple times. A single test environment's sample classifications
	are demonstrations, not guarantees for other machines or input ranges.

## Troubleshooting

- **`ModuleNotFoundError: complexity_analyzer_empirical`:** install into the same Python
	interpreter that runs your script (`python -m pip install
	complexity-analyzer-empirical`). Check `python -m pip show
	complexity-analyzer-empirical` and avoid naming your own script
	`complexity_analyzer_empirical.py`.
- **`ModuleNotFoundError: streamlit`:** the dashboard is optional; install
	`complexity-analyzer-empirical[dashboard]` to use it. The core import does
	not need Streamlit.
- **`AnalysisError` says tracing is already active:** stop the caller's
	`tracemalloc` session before calling `complexity()`; the analyzer refuses to
	take over global tracing state.
- **Unexpected or inconclusive growth estimate:** use more widely spaced and
	larger safe inputs, increase the trial count, inspect the raw measurements,
	and account for function side effects and machine load. The result remains
	empirical and limited to the listed candidate models.

## Build and publish to PyPI

The distribution name is `complexity-analyzer-empirical`; import it as
`complexity_analyzer_empirical`. Check the name on PyPI immediately before publishing,
because name availability can change. Review the license, package metadata,
version, and built artifact contents before publishing.

From the project root, build and validate the artifacts locally:

```powershell
py -m pip install --upgrade build twine
py -m build
py -m twine check dist/*
```

For an upload, create a narrowly scoped PyPI API token on the PyPI website, keep
it private, and do not paste it into a command or commit it to source control.
Set Twine's username and let it prompt securely for the token:

```powershell
$env:TWINE_USERNAME = "__token__"
py -m twine upload --repository pypi dist/*
Remove-Item Env:\TWINE_USERNAME
```

At Twine's password prompt, enter the API token (PyPI tokens begin with
`pypi-`). Review the project name and artifacts before confirming an upload.
For automated releases, prefer PyPI Trusted Publishing with an identity-based
CI workflow instead of storing a long-lived token. These are instructions only:
this project setup does not publish or upload anything automatically.
