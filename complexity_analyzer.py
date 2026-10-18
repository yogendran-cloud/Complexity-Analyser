"""Empirical runtime and memory analysis for trusted Python callables."""

from __future__ import annotations

import csv
import math
import statistics
import time
import tracemalloc
from dataclasses import dataclass
from typing import Callable, Sequence
from xml.sax.saxutils import escape

_MIN_TRIAL_SECONDS = 0.002
_CALLS_PER_TIMING_CHECK = 25
_MAX_CALLS_PER_TRIAL = 100_000
_DEFAULT_SIZES = (2, 4, 8, 12, 16)


class AnalysisError(RuntimeError):
	"""Raised when a callable fails during a measurement."""


@dataclass(frozen=True)
class Measurement:
	"""Median measurements collected for one input size."""

	input_size: int
	median_time_seconds: float
	median_peak_memory_bytes: int
	time_mad_seconds: float = 0.0
	raw_trial_times_seconds: tuple[float, ...] = ()
	raw_trial_elapsed_seconds: tuple[float, ...] = ()
	raw_trial_call_counts: tuple[int, ...] = ()
	raw_trial_peak_memory_bytes: tuple[int, ...] = ()


@dataclass(frozen=True)
class ComplexityReport:
	"""Results and a heuristic complexity estimate for a callable."""

	measurements: tuple[Measurement, ...]
	estimated_complexity: str
	trials: int
	classification_status: str = "inconclusive"
	classification_note: str = ""

	@property
	def reliable_complexity(self) -> str | None:
		"""Compatibility alias for the plausible empirical estimate, not proof."""
		if self.classification_status == "plausible":
			return self.estimated_complexity
		return None

	def format_report(self) -> str:
		"""Return a readable text report."""
		lines = [
			"Complexity Analyzer report",
			"size | median time (s) | time MAD (s) | median peak traced memory (bytes)",
			"-----|-----------------|--------------|-------------------------------",
		]
		lines.extend(
			f"{item.input_size:>4} | {item.median_time_seconds:.8f} | "
			f"{item.time_mad_seconds:.8f} | "
			f"{item.median_peak_memory_bytes:>10}"
			for item in self.measurements
		)
		lines.extend(
			[
				f"Estimated growth: {self.estimated_complexity}",
				f"Classification status: {self.classification_status}",
				(
					f"Plausible empirical estimate: {self.reliable_complexity}"
					if self.reliable_complexity is not None
					else "Plausible empirical estimate: none"
				),
				self.classification_note,
				"Empirical measurements do not prove theoretical Big-O.",
			]
		)
		return "\n".join(lines)

	def save_csv(self, path: str) -> None:
		"""Save the measurements as a CSV file."""
		with open(path, "w", newline="", encoding="utf-8") as csv_file:
			writer = csv.writer(csv_file)
			writer.writerow(
				[
					"input_size",
					"median_time_seconds",
					"time_mad_seconds",
					"median_peak_memory_bytes",
					"raw_trial_times_seconds",
					"raw_trial_elapsed_seconds",
					"raw_trial_call_counts",
					"raw_trial_peak_memory_bytes",
					"estimated_complexity",
					"classification_status",
					"classification_note",
				]
			)
			writer.writerows(
				(
					item.input_size,
					item.median_time_seconds,
					item.time_mad_seconds,
					item.median_peak_memory_bytes,
					";".join(map(str, item.raw_trial_times_seconds)),
					";".join(map(str, item.raw_trial_elapsed_seconds)),
					";".join(map(str, item.raw_trial_call_counts)),
					";".join(map(str, item.raw_trial_peak_memory_bytes)),
					self.estimated_complexity,
					self.classification_status,
					self.classification_note,
				)
				for item in self.measurements
			)

	def save_plot(self, path: str) -> None:
		"""Save a dependency-free SVG plot of time and peak traced memory."""
		width, panel_height, margin = 760, 230, 76
		height = panel_height * 2 + 70
		plot_width = width - margin - 24
		count = len(self.measurements)
		x_positions = [
			margin + (plot_width * index / max(count - 1, 1))
			for index in range(count)
		]

		def render_panel(
			title: str,
			values: Sequence[float],
			y_offset: int,
			color: str,
			unit: str,
		) -> str:
			max_value = max(max(values, default=0), 1e-12)
			top = y_offset + 34
			bottom = y_offset + panel_height - 34
			points = [
				(
					x_positions[index],
					bottom - (value / max_value) * (bottom - top),
				)
				for index, value in enumerate(values)
			]
			polyline = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
			fragments = [
				f'<text x="{margin}" y="{y_offset + 18}" class="title">{title}</text>',
				f'<line x1="{margin}" y1="{bottom}" x2="{width - 24}" y2="{bottom}" class="axis"/>',
				f'<polyline points="{polyline}" fill="none" stroke="{color}" stroke-width="3"/>',
			]
			for index, (x, y) in enumerate(points):
				fragments.append(
					f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{color}"/>'
				)
				fragments.append(
					f'<text x="{x:.1f}" y="{bottom + 18}" text-anchor="middle" class="label">'
					f'{self.measurements[index].input_size}</text>'
				)
			fragments.append(
				f'<text x="{margin}" y="{top - 8}" class="label">{max_value:.4g} {unit}</text>'
			)
			return "\n".join(fragments)

		time_values = [item.median_time_seconds for item in self.measurements]
		memory_values = [item.median_peak_memory_bytes for item in self.measurements]
		svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<style>text {{ font-family: sans-serif; fill: #243047; }} .title {{ font-size: 16px; font-weight: bold; }} .label {{ font-size: 11px; }} .axis {{ stroke: #9aa6b2; stroke-width: 1; }}</style>
<rect width="100%" height="100%" fill="white"/>
<text x="{margin}" y="28" class="title">Complexity Analyzer measurements</text>
<text x="{margin}" y="44" class="label">Estimated {escape(self.estimated_complexity)} | status: {escape(self.classification_status)}</text>
{render_panel('Median time (seconds)', time_values, 42, '#2563eb', 's')}
{render_panel('Median peak traced memory (bytes)', memory_values, panel_height + 48, '#0f9d72', 'bytes')}
</svg>
'''
		with open(path, "w", encoding="utf-8") as svg_file:
			svg_file.write(svg)


def _log_growth_value(model: str, size: int) -> float:
	"""Return the logarithm of a representative growth function."""
	if model == "O(1)":
		return 0.0
	if model == "O(log n)":
		return math.log(math.log(max(size, 2)))
	if model == "O(n)":
		return math.log(size)
	if model == "O(n log n)":
		return math.log(size) + math.log(math.log(max(size, 2)))
	if model == "O(n^2)":
		return 2 * math.log(size)
	return float(size) * math.log(2)  # log(2ⁿ), without exponent overflow


def _validate_measurements(measurements: Sequence[Measurement]) -> None:
	if len(measurements) < 2:
		raise ValueError("at least two measurements are required")
	previous_size = 0
	for item in measurements:
		if not isinstance(item, Measurement):
			raise ValueError("all values must be Measurement instances")
		if (
			not isinstance(item.input_size, int)
			or isinstance(item.input_size, bool)
			or item.input_size <= previous_size
		):
			raise ValueError("measurement sizes must be positive and strictly increasing")
		if any(
			isinstance(value, bool) or not isinstance(value, (int, float))
			for value in (item.median_time_seconds, item.time_mad_seconds)
		):
			raise ValueError("measurement times and variability must be numeric")
		if (
			not math.isfinite(item.median_time_seconds)
			or item.median_time_seconds <= 0
			or not math.isfinite(item.time_mad_seconds)
			or item.time_mad_seconds < 0
		):
			raise ValueError("measurement times and variability must be finite and valid")
		if (
			not isinstance(item.median_peak_memory_bytes, int)
			or isinstance(item.median_peak_memory_bytes, bool)
			or item.median_peak_memory_bytes < 0
		):
			raise ValueError("peak memory measurements cannot be negative")
		previous_size = item.input_size


def _fit_models(
	measurements: Sequence[Measurement],
) -> tuple[tuple[float, float, str], ...]:
	"""Fit all models in log space; return (robust error, max error, label).

	For a candidate ``f(n)``, the model is ``time = scale * f(n)``. Taking
	logs gives ``log(time) = log(scale) + log(f(n))``. The log-scale is fitted
	with the median residual, which is less sensitive to one unusual input than
	least squares. Every model fits the same one parameter (the scale).
	"""
	candidates = ("O(1)", "O(log n)", "O(n)", "O(n log n)", "O(n^2)", "O(2^n)")
	log_times = [math.log(item.median_time_seconds) for item in measurements]
	fits = []
	for model in candidates:
		features = [_log_growth_value(model, item.input_size) for item in measurements]
		log_scale = statistics.median(
			observed - expected for observed, expected in zip(log_times, features)
		)
		residuals = [
			abs(observed - (log_scale + expected))
			for observed, expected in zip(log_times, features)
		]
		# Blend median and mean absolute error: the median limits outlier influence,
		# while the mean ensures one outlier cannot disappear from model quality.
		error = 0.75 * statistics.median(residuals) + 0.25 * statistics.fmean(residuals)
		fits.append((error, max(residuals), model))
	return tuple(sorted(fits))


def _classify_complexity(
	measurements: Sequence[Measurement], trials: int = 3
) -> tuple[str, str, str]:
	"""Return the best estimate, evidence status, and a plain-language note.

	``plausible`` means the data supports one candidate under this comparison;
	``tentative`` means the best candidate is useful but evidence is incomplete;
	``inconclusive`` means candidates/noise do not permit a meaningful choice.
	These are empirical evidence labels, not formal confidence intervals.
	"""
	_validate_measurements(measurements)
	if not isinstance(trials, int) or isinstance(trials, bool) or trials < 1:
		raise ValueError("trials must be a positive integer")
	fits = _fit_models(measurements)
	best_error, largest_residual, best_model = fits[0]
	second_error = fits[1][0]
	relative_noise = max(
		item.time_mad_seconds / item.median_time_seconds for item in measurements
	)
	noise_in_log_units = math.log1p(relative_noise)
	input_span = measurements[-1].input_size / measurements[0].input_size
	median_error_factor = math.exp(best_error)
	worst_error_factor = math.exp(largest_residual)
	model_gap = second_error - best_error

	# A >35% median trial deviation is too noisy for the current summary to
	# separate growth. A >=3x miss at even one size is a strong outlier/poor fit.
	if relative_noise > 0.35 or worst_error_factor > 3.0:
		return best_model, "inconclusive", (
			"Timing variability or an outlying size is too large for a useful model choice."
		)
	if median_error_factor > 1.5:
		return best_model, "inconclusive", (
			"No supported growth curve stays within a typical 50% multiplicative fit error."
		)

	# Nearby candidate curves can be effectively indistinguishable on the chosen
	# sizes. Require their fit gap to exceed both a small numeric floor and the
	# observed relative timing noise; otherwise do not report a winning class.
	minimum_gap = max(0.02, noise_in_log_units)
	if model_gap <= minimum_gap:
		return best_model, "inconclusive", (
			"The best and next-best growth models are ambiguous: they fit too similarly for these input sizes."
		)
	if input_span < 8 or len(measurements) < 4:
		return best_model, "tentative", (
			"A best-fit estimate is available, but the size range or number of sizes is too small."
		)
	if trials < 3 or any(len(item.raw_trial_times_seconds) < 3 for item in measurements):
		return best_model, "tentative", (
			"A best-fit estimate is available, but repeated raw trials are insufficient to assess stability."
		)
	if relative_noise > 0.20 or median_error_factor > 1.25:
		return best_model, "tentative", (
			"The fit or trial variability leaves meaningful uncertainty in the estimate."
		)

	# Leave-one-size-out checks test whether one chosen point alone determines
	# the winner. Require the same candidate to win every reduced fit.
	if len(measurements) < 5:
		return best_model, "tentative", (
			"At least five input sizes are needed to check whether the estimate survives removing one size."
		)
	leave_one_out_winners = []
	for omitted in range(len(measurements)):
		reduced = measurements[:omitted] + measurements[omitted + 1 :]
		leave_one_out_winners.append(_fit_models(reduced)[0][2])
	if any(model != best_model for model in leave_one_out_winners):
		return best_model, "tentative", (
			"The winning model changes when one input size is omitted, so the result is sensitive to the sample."
		)

	return best_model, "plausible", (
		"One supported shape fits consistently across sizes and repeated trials; this is still empirical evidence, not proof."
	)


def _estimate_complexity(measurements: Sequence[Measurement]) -> str:
	"""Return the best-fit estimate without making a reliability claim."""
	return _classify_complexity(measurements)[0]


def complexity(
	function: Callable[[int], object],
	sizes: Sequence[int] = _DEFAULT_SIZES,
	trials: int = 3,
	repetitions: int | None = None,
) -> ComplexityReport:
	"""Measure a trusted function called as ``function(size)``.

	The function is warmed up once at each size. By default each timing trial
	repeats calls until at least 2 ms has elapsed, checking the timer every 25
	calls and stopping at 100,000 calls. Set ``repetitions`` to a positive
	integer to run exactly that many timed calls per trial instead. Timed calls
	run without memory tracing; memory is measured in separate invocations.
	Functions should be safe to call repeatedly and should not change global
	tracemalloc state. Very short fixed-repetition samples are flagged as
	tentative because timer and harness overhead may dominate.
	"""
	if not callable(function):
		raise TypeError("function must be callable")
	if not isinstance(trials, int) or isinstance(trials, bool) or trials < 1:
		raise ValueError("trials must be a positive integer")
	if repetitions is not None and (
		not isinstance(repetitions, int)
		or isinstance(repetitions, bool)
		or not 1 <= repetitions <= _MAX_CALLS_PER_TRIAL
	):
		raise ValueError(
			f"repetitions must be an integer from 1 to {_MAX_CALLS_PER_TRIAL}"
	)
	try:
		sizes = tuple(sizes)
	except TypeError as error:
		raise ValueError("sizes must be an iterable of positive integers") from error
	if len(sizes) < 2:
		raise ValueError("sizes must contain at least two input sizes")
	if any(not isinstance(size, int) or isinstance(size, bool) or size < 1 for size in sizes):
		raise ValueError("sizes must contain positive integers")
	if any(left >= right for left, right in zip(sizes, sizes[1:])):
		raise ValueError("sizes must be strictly increasing")
	if tracemalloc.is_tracing():
		raise AnalysisError(
			"tracemalloc is already active; stop it before running an analysis"
		)

	measurements = []
	for size in sizes:
		warmup_started_tracing = False
		try:
			function(size)
		except Exception as error:
			if tracemalloc.is_tracing():
				tracemalloc.stop()
			raise AnalysisError(
				f"Function failed during warm-up for input size {size}: {error}"
			) from error
		finally:
			if tracemalloc.is_tracing():
				tracemalloc.stop()
				warmup_started_tracing = True
		if warmup_started_tracing:
			raise AnalysisError(
				"Analyzed function changed tracemalloc state during warm-up; "
				"functions must not start tracing"
			)

		elapsed_times = []
		trial_elapsed_times = []
		trial_call_counts = []
		peak_memory = []
		for trial in range(1, trials + 1):
			timing_started_tracing = False
			try:
				try:
					started = time.perf_counter()
					calls = 0
					if repetitions is not None:
						for _ in range(repetitions):
							function(size)
							calls += 1
					else:
						while calls < _MAX_CALLS_PER_TRIAL:
							for _ in range(
								min(_CALLS_PER_TIMING_CHECK, _MAX_CALLS_PER_TRIAL - calls)
							):
								function(size)
								calls += 1
							if time.perf_counter() - started >= _MIN_TRIAL_SECONDS:
								break
					elapsed = time.perf_counter() - started
					elapsed_times.append(elapsed / calls)
					trial_elapsed_times.append(elapsed)
					trial_call_counts.append(calls)
				finally:
					if tracemalloc.is_tracing():
						tracemalloc.stop()
						timing_started_tracing = True
			except Exception as error:
				raise AnalysisError(
					f"Function failed for input size {size} on trial {trial}: {error}"
				) from error
			if timing_started_tracing:
				raise AnalysisError(
					"Analyzed function changed tracemalloc state during timing; "
					"functions must not start tracing"
				)

		# Measure memory after timing trials so tracing never interrupts a timed
		# sequence or changes its cache/state characteristics between trials.
		for trial in range(1, trials + 1):
			try:
				tracemalloc.start()
				function(size)
				_, peak = tracemalloc.get_traced_memory()
				peak_memory.append(peak)
			except Exception as error:
				raise AnalysisError(
					f"Memory measurement failed for input size {size} on trial {trial}: {error}"
				) from error
			finally:
				if tracemalloc.is_tracing():
					tracemalloc.stop()

		median_time = statistics.median(elapsed_times)
		measurements.append(
			Measurement(
				input_size=size,
				median_time_seconds=median_time,
				median_peak_memory_bytes=int(statistics.median(peak_memory)),
				time_mad_seconds=statistics.median(
					abs(value - median_time) for value in elapsed_times
				),
				raw_trial_times_seconds=tuple(elapsed_times),
				raw_trial_elapsed_seconds=tuple(trial_elapsed_times),
				raw_trial_call_counts=tuple(trial_call_counts),
				raw_trial_peak_memory_bytes=tuple(peak_memory),
			)
		)

	result = tuple(measurements)
	estimate, status, note = _classify_complexity(result, trials)
	if any(
		elapsed < _MIN_TRIAL_SECONDS
		for item in result
		for elapsed in item.raw_trial_elapsed_seconds
	):
		if status == "plausible":
			status = "tentative"
		note = (
			note + " At least one timing trial was shorter than the minimum target; "
			"timer and harness overhead may dominate."
		)
	return ComplexityReport(result, estimate, trials, status, note)


__all__ = ["AnalysisError", "ComplexityReport", "Measurement", "complexity"]
