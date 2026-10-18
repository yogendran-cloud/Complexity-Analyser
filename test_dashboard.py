"""Tests for dashboard-only behavior; requires the dashboard extra."""

import unittest

from complexity_analyzer import ComplexityReport, Measurement
from dashboard import _has_traced_memory, _runtime_display_scale


class DashboardTests(unittest.TestCase):
    def test_runtime_display_converts_seconds_per_call_to_microseconds(self):
        # complexity() stores elapsed_seconds / actual_call_count in seconds.
        elapsed_seconds = 0.0006
        call_count = 3
        seconds_per_call = elapsed_seconds / call_count
        scale, unit = _runtime_display_scale(seconds_per_call)

        self.assertEqual(unit, "µs")
        self.assertAlmostEqual(seconds_per_call * scale, 200.0)

    def test_zero_traced_memory_is_not_presented_as_a_memory_curve(self):
        zero_report = ComplexityReport(
            (Measurement(8, 0.001, 0), Measurement(16, 0.002, 0)),
            "O(n)",
            3,
        )
        positive_report = ComplexityReport(
            (Measurement(8, 0.001, 1), Measurement(16, 0.002, 0)),
            "O(n)",
            3,
        )

        self.assertFalse(_has_traced_memory(zero_report))
        self.assertTrue(_has_traced_memory(positive_report))

    def test_raw_peak_memory_prevents_false_zero_empty_state(self):
        report = ComplexityReport(
            (
                Measurement(8, 0.001, 0, raw_trial_peak_memory_bytes=(0, 4, 0)),
                Measurement(16, 0.002, 0, raw_trial_peak_memory_bytes=(0, 8, 0)),
            ),
            "O(n)",
            3,
        )

        self.assertTrue(_has_traced_memory(report))


if __name__ == "__main__":
    unittest.main()
