"""Tests for the initial Complexity Analyzer implementation."""

import csv
import math
import os
import tempfile
import tracemalloc
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch

from complexity_analyzer import (
	AnalysisError,
	ComplexityReport,
	Measurement,
	_classify_complexity,
	_estimate_complexity,
	complexity,
)
from sample_algorithms import (
	constant,
	linear,
	linearithmic,
	logarithmic,
	quadratic,
	exponential,
)


class ComplexityTests(unittest.TestCase):
	def test_reliable_complexity_is_only_set_for_plausible_status(self):
		plausible = ComplexityReport((), "O(n)", 3, "plausible", "empirical")
		tentative = ComplexityReport((), "O(n)", 3, "tentative", "uncertain")
		inconclusive = ComplexityReport((), "O(n)", 3, "inconclusive", "ambiguous")

		self.assertEqual(plausible.reliable_complexity, "O(n)")
		self.assertIsNone(tentative.reliable_complexity)
		self.assertIsNone(inconclusive.reliable_complexity)

	def test_sample_algorithms(self):
		self.assertEqual(constant(10), 1)
		self.assertEqual(logarithmic(16), 4)
		self.assertEqual(linear(5), 10)
		self.assertEqual(linearithmic(4), 8)
		self.assertEqual(quadratic(4), 4)
		self.assertEqual(exponential(5), 32)

	def test_collects_one_measurement_per_size(self):
		report = complexity(lambda n: sum(range(n)), sizes=(10, 20, 30), trials=2)

		self.assertEqual([item.input_size for item in report.measurements], [10, 20, 30])
		self.assertTrue(all(item.median_time_seconds >= 0 for item in report.measurements))
		self.assertTrue(all(item.median_peak_memory_bytes >= 0 for item in report.measurements))
		self.assertTrue(all(item.time_mad_seconds >= 0 for item in report.measurements))
		self.assertEqual(report.trials, 2)
		self.assertTrue(all(len(item.raw_trial_times_seconds) == 2 for item in report.measurements))
		self.assertTrue(all(len(item.raw_trial_elapsed_seconds) == 2 for item in report.measurements))
		self.assertTrue(all(len(item.raw_trial_peak_memory_bytes) == 2 for item in report.measurements))

	def test_fixed_repetitions_are_exact_and_raw_calls_are_retained(self):
		calls_by_size = {8: 0, 16: 0}

		def counted(size):
			calls_by_size[size] += 1

		report = complexity(
			counted, sizes=(8, 16), trials=2, repetitions=3
		)

		# One warm-up, three timed calls per trial, one memory call per trial.
		self.assertEqual(calls_by_size, {8: 9, 16: 9})
		self.assertEqual(report.measurements[0].raw_trial_call_counts, (3, 3))
		self.assertEqual(report.measurements[1].raw_trial_call_counts, (3, 3))

	def test_default_sizes_are_bounded_and_cover_eightfold_span(self):
		report = complexity(
			lambda _size: None, trials=1, repetitions=1
		)

		self.assertEqual(
			tuple(item.input_size for item in report.measurements),
			(2, 4, 8, 12, 16),
		)
		self.assertEqual(report.measurements[-1].input_size, 16)

	def test_short_fixed_repetition_is_not_marked_reliable(self):
		with patch(
			"complexity_analyzer.time.perf_counter",
			side_effect=(0.0, 0.0001, 1.0, 1.0001),
		):
			report = complexity(
				lambda _size: None,
				sizes=(8, 16),
				trials=1,
				repetitions=1,
			)

		self.assertEqual(report.classification_status, "tentative")
		self.assertIsNone(report.reliable_complexity)

	def test_estimates_constant_work(self):
		samples = tuple(
			Measurement(size, 0.001, 0) for size in (10, 20, 30, 40)
		)

		self.assertEqual(_estimate_complexity(samples), "O(1)")

	def test_linear_curve_is_not_penalized_as_linearithmic(self):
		samples = tuple(
			Measurement(
				size,
				0.00001 * size,
				0,
				0.0,
				raw_trial_times_seconds=(0.00001 * size,) * 5,
			)
			for size in (100, 500, 1000, 5000, 10000)
		)
		estimate, status, _ = _classify_complexity(samples, trials=5)

		self.assertEqual(estimate, "O(n)")
		self.assertEqual(status, "plausible")

	def test_rejects_invalid_sizes(self):
		with self.assertRaises(ValueError):
			complexity(lambda n: n, sizes=(3, 2))
		with self.assertRaises(ValueError):
			complexity(lambda n: n, sizes=(1, 1))
		with self.assertRaises(ValueError):
			complexity(lambda n: n, sizes=(True, 2))
		with self.assertRaises(ValueError):
			complexity(lambda n: n, sizes=(0, 2))
		with self.assertRaises(ValueError):
			complexity(lambda n: n, sizes=None)

	def test_wraps_callable_errors_and_stops_tracing(self):
		def broken(_n):
			raise RuntimeError("expected failure")

		with self.assertRaisesRegex(AnalysisError, "input size 4"):
			complexity(broken, sizes=(4, 8), trials=1)
		self.assertFalse(tracemalloc.is_tracing())

	def test_runtime_timer_does_not_run_with_memory_tracing(self):
		tracing_states = []

		def observe_tracing(_size):
			tracing_states.append(tracemalloc.is_tracing())

		with patch(
			"complexity_analyzer.time.perf_counter",
			side_effect=(0.0, 0.0001, 1.0, 1.0002),
		):
			report = complexity(
				observe_tracing,
				sizes=(8, 16),
				trials=1,
				repetitions=1,
			)

		self.assertIn(False, tracing_states)
		self.assertIn(True, tracing_states)
		self.assertEqual(report.classification_status, "tentative")
		self.assertIsNone(report.reliable_complexity)
		self.assertIn("Plausible empirical estimate: none", report.format_report())

	def test_peak_memory_records_temporary_allocations(self):
		report = complexity(lambda size: [0] * size, sizes=(100, 1000), trials=3)

		self.assertGreater(report.measurements[0].median_peak_memory_bytes, 0)
		self.assertGreater(
			report.measurements[1].median_peak_memory_bytes,
			report.measurements[0].median_peak_memory_bytes,
		)

	def test_failure_during_memory_measurement_stops_tracing(self):
		def fail_only_while_tracing(_size):
			if tracemalloc.is_tracing():
				raise RuntimeError("memory-pass failure")

		with self.assertRaisesRegex(AnalysisError, "Memory measurement failed"):
			complexity(fail_only_while_tracing, sizes=(8, 16), trials=1)
		self.assertFalse(tracemalloc.is_tracing())

	def test_failure_during_timing_stops_tracing_started_by_function(self):
		calls = 0

		def starts_tracing_then_fails(_size):
			nonlocal calls
			calls += 1
			if calls == 2:
				tracemalloc.start()
				raise RuntimeError("timing failure")

		with self.assertRaisesRegex(AnalysisError, "input size 8 on trial 1"):
			complexity(starts_tracing_then_fails, sizes=(8, 16), trials=1)
		self.assertFalse(tracemalloc.is_tracing())

	def test_estimates_known_synthetic_growth_patterns(self):
		cases = {
			"O(1)": lambda n: 1,
			"O(log n)": lambda n: math.log(n),
			"O(n)": lambda n: n,
			"O(n log n)": lambda n: n * math.log(n),
			"O(n^2)": lambda n: n**2,
			"O(2^n)": lambda n: 2**n,
		}
		sizes = (8, 16, 32, 64, 128, 256)
		for expected, growth in cases.items():
			with self.subTest(expected=expected):
				trial_times = tuple(
					(float(growth(size)) * 0.001,) * 5 for size in sizes
				)
				samples = tuple(
					Measurement(
						size,
						float(growth(size)) * 0.001,
						0,
						0.0,
						raw_trial_times_seconds=trial_values,
					)
					for size, trial_values in zip(sizes, trial_times)
				)
				estimate, status, _ = _classify_complexity(samples, trials=5)
				self.assertEqual(estimate, expected)
				self.assertEqual(status, "plausible")
				self.assertEqual(_estimate_complexity(samples), expected)

	def test_one_outlier_size_cannot_create_a_plausible_classification(self):
		sizes = (8, 16, 32, 64, 128, 256)
		times = (0.008, 0.016, 0.032, 0.064, 0.128, 1.0)
		samples = tuple(
			Measurement(size, seconds, 0, 0.0, (seconds,) * 5)
			for size, seconds in zip(sizes, times)
		)
		_, status, _ = _classify_complexity(samples, trials=5)

		self.assertEqual(status, "inconclusive")

	def test_missing_raw_trials_never_claims_plausibility(self):
		samples = tuple(
			Measurement(size, 0.001 * size, 0, 0.0)
			for size in (8, 16, 32, 64, 128)
		)
		_, status, _ = _classify_complexity(samples, trials=5)

		self.assertEqual(status, "tentative")

	def test_ambiguous_small_range_is_tentative(self):
		samples = tuple(
			Measurement(size, float(size), 0) for size in (10, 12, 14)
		)
		_, status, note = _classify_complexity(samples, trials=1)

		self.assertEqual(status, "tentative")
		self.assertTrue(note)

	def test_close_growth_models_are_reported_as_ambiguous(self):
		samples = tuple(
			Measurement(size, size * math.sqrt(math.log(size)), 0)
			for size in (8, 16, 32, 64, 128, 256, 512)
		)
		_, status, note = _classify_complexity(samples, trials=5)

		self.assertEqual(status, "inconclusive")
		self.assertIn("ambiguous", note)

	def test_inconsistent_measurements_are_inconclusive(self):
		samples = tuple(
			Measurement(size, seconds, 0)
			for size, seconds in zip(
				(8, 16, 32, 64, 128), (0.001, 0.02, 0.0011, 0.03, 0.0012)
			)
		)
		_, status, _ = _classify_complexity(samples, trials=5)

		self.assertEqual(status, "inconclusive")

	def test_high_trial_variation_is_inconclusive(self):
		samples = tuple(
			Measurement(size, 0.001 * size, 0, 0.0005 * size)
			for size in (8, 16, 32, 64, 128)
		)
		_, status, _ = _classify_complexity(samples, trials=5)

		self.assertEqual(status, "inconclusive")

	def test_malformed_estimator_measurements_are_rejected(self):
		with self.assertRaises(ValueError):
			_estimate_complexity(())
		with self.assertRaises(ValueError):
			_estimate_complexity(
				(Measurement(8, float("nan"), 0), Measurement(16, 1, 0))
			)
		with self.assertRaises(ValueError):
			_estimate_complexity((Measurement(8, 1, 0), Measurement(8, 2, 0)))
		with self.assertRaises(ValueError):
			_estimate_complexity((Measurement(8, "bad", 0), Measurement(16, 1, 0)))
		with self.assertRaises(ValueError):
			_estimate_complexity((Measurement(8, 1, -1), Measurement(16, 2, 0)))

	def test_exports_csv_and_svg(self):
		report = complexity(lambda n: sum(range(n)), sizes=(10, 20), trials=1)
		with tempfile.TemporaryDirectory() as folder:
			csv_path = os.path.join(folder, "report.csv")
			svg_path = os.path.join(folder, "plot.svg")
			report.save_csv(csv_path)
			report.save_plot(svg_path)

			with open(csv_path, newline="", encoding="utf-8") as csv_file:
				rows = list(csv.DictReader(csv_file))
			with open(svg_path, encoding="utf-8") as svg_file:
				svg = svg_file.read()

		self.assertEqual(len(rows), 2)
		self.assertEqual(rows[0]["estimated_complexity"], report.estimated_complexity)
		self.assertEqual(rows[0]["classification_status"], report.classification_status)
		self.assertTrue(rows[0]["classification_note"])
		self.assertIn("<svg", svg)
		self.assertIn("Median time", svg)
		self.assertIn("peak traced memory", svg)
		svg_root = ET.fromstring(svg)
		svg_text = " ".join(node.text or "" for node in svg_root.iter() if node.tag.endswith("text"))
		self.assertIn(report.estimated_complexity, svg_text)
		self.assertIn(report.classification_status, svg_text)

	def test_requires_positive_integer_trials(self):
		with self.assertRaises(ValueError):
			complexity(lambda n: n, sizes=(2, 4), trials=1.5)
		with self.assertRaises(ValueError):
			complexity(lambda n: n, sizes=(2, 4), trials=True)

	def test_rejects_invalid_repetitions(self):
		for repetitions in (0, -1, True, 1.5, 100_001):
			with self.subTest(repetitions=repetitions):
				with self.assertRaises(ValueError):
					complexity(
						lambda n: n,
						sizes=(2, 4),
						repetitions=repetitions,
					)


if __name__ == "__main__":
	unittest.main()
