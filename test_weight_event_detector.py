"""Regression and edge-case tests for the smart-shelf detector."""

import csv
import os
import tempfile
import unittest
from pathlib import Path

from weight_event_detector_annotated import (
    Measurement,
    detect_weight_change,
    detect_weight_change_details,
    is_stable,
    median_weight,
    read_measurements,
)


INPUT_DIRECTORY = Path(__file__).resolve().parent / "data"


class WeightEventDetectorTests(unittest.TestCase):
    """Check normal behavior, edge cases, and validation behavior."""

    def test_each_recording_has_one_removal_and_one_addition(self) -> None:
        """Every provided file contains a removal followed by a return."""

        expected_changes_grams = {
            "50_gr.csv": 70.0,
            "500_gr.csv": 500.0,
            "1000_gr.csv": 1000.0,
        }

        for file_name, expected_change_grams in expected_changes_grams.items():
            with self.subTest(file_name=file_name):
                events = detect_weight_change(INPUT_DIRECTORY / file_name)

                self.assertEqual(len(events), 2)

                removal_change, removal_time = events[0]
                addition_change, addition_time = events[1]

                self.assertLess(removal_change, 0.0)
                self.assertGreater(addition_change, 0.0)
                self.assertLess(removal_time, addition_time)
                self.assertAlmostEqual(
                    abs(removal_change), expected_change_grams, delta=15.0
                )
                self.assertAlmostEqual(
                    addition_change, expected_change_grams, delta=15.0
                )

    def test_constant_weight_produces_no_events(self) -> None:
        """A quiet shelf must not create a false event."""

        measurements = [
            Measurement(time_seconds=index * 0.01, weight_grams=500.0)
            for index in range(100)
        ]

        events = detect_weight_change_details(measurements)

        self.assertEqual(events, [])

    def test_small_change_below_minimum_is_ignored(self) -> None:
        """A stable three-gram change must not be reported as an event."""

        measurements = [
            Measurement(time_seconds=index * 0.01, weight_grams=500.0)
            for index in range(20)
        ]
        measurements.extend(
            Measurement(time_seconds=index * 0.01, weight_grams=503.0)
            for index in range(20, 80)
        )

        events = detect_weight_change_details(measurements)

        self.assertEqual(events, [])

    def test_temporary_spike_returning_to_baseline_is_ignored(self) -> None:
        """A short disturbance that returns to the old level is not an event."""

        measurements = [
            Measurement(time_seconds=index * 0.01, weight_grams=500.0)
            for index in range(20)
        ]
        measurements.extend(
            Measurement(time_seconds=index * 0.01, weight_grams=550.0)
            for index in range(20, 25)
        )
        measurements.extend(
            Measurement(time_seconds=index * 0.01, weight_grams=500.0)
            for index in range(25, 100)
        )

        events = detect_weight_change_details(measurements)

        self.assertEqual(events, [])

    def test_single_removal_is_detected(self) -> None:
        """A sustained drop is reported as one negative event."""

        measurements = [
            Measurement(time_seconds=index * 0.01, weight_grams=500.0)
            for index in range(20)
        ]
        measurements.extend(
            Measurement(time_seconds=index * 0.01, weight_grams=0.0)
            for index in range(20, 80)
        )

        events = detect_weight_change_details(measurements)

        self.assertEqual(len(events), 1)
        self.assertLess(events[0].weight_change_grams, 0.0)
        self.assertAlmostEqual(
            events[0].weight_change_grams,
            -500.0,
            delta=15.0,
        )

    def test_single_addition_is_detected(self) -> None:
        """A sustained increase is reported as one positive event."""

        measurements = [
            Measurement(time_seconds=index * 0.01, weight_grams=0.0)
            for index in range(20)
        ]
        measurements.extend(
            Measurement(time_seconds=index * 0.01, weight_grams=500.0)
            for index in range(20, 80)
        )

        events = detect_weight_change_details(measurements)

        self.assertEqual(len(events), 1)
        self.assertGreater(events[0].weight_change_grams, 0.0)
        self.assertAlmostEqual(
            events[0].weight_change_grams,
            500.0,
            delta=15.0,
        )

    def test_empty_measurements_cannot_have_a_median(self) -> None:
        """An empty collection must be rejected by the median helper."""

        with self.assertRaises(ValueError):
            median_weight([])

    def test_too_few_measurements_are_rejected(self) -> None:
        """Event detection requires at least two measurements."""

        one_measurement = [Measurement(time_seconds=0.0, weight_grams=500.0)]

        with self.assertRaises(ValueError):
            detect_weight_change_details(one_measurement)

    def test_stability_check_accepts_quiet_window_and_rejects_moving_window(self) -> None:
        """The stability helper uses the full peak-to-peak weight range."""

        stable_measurements = [
            Measurement(time_seconds=0.00, weight_grams=500.0),
            Measurement(time_seconds=0.01, weight_grams=501.0),
            Measurement(time_seconds=0.02, weight_grams=500.5),
        ]
        unstable_measurements = [
            Measurement(time_seconds=0.00, weight_grams=500.0),
            Measurement(time_seconds=0.01, weight_grams=520.0),
            Measurement(time_seconds=0.02, weight_grams=480.0),
        ]

        self.assertTrue(is_stable(stable_measurements, 2.5))
        self.assertFalse(is_stable(unstable_measurements, 2.5))

    def test_missing_csv_columns_are_rejected(self) -> None:
        """A CSV without both required columns must fail validation."""

        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "missing_column.csv"
            csv_path.write_text("time_seconds,temperature\n0.0,20.0\n", encoding="utf-8")

            with self.assertRaises(ValueError):
                read_measurements(csv_path)

    def test_non_numeric_csv_value_is_rejected(self) -> None:
        """A text value in a numeric column must fail validation."""

        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "non_numeric.csv"
            csv_path.write_text(
                "time_seconds,weights\n0.0,500.0\n0.01,not-a-number\n",
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                read_measurements(csv_path)

    def test_non_finite_csv_value_is_rejected(self) -> None:
        """NaN and infinity must not enter the detection algorithm."""

        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "non_finite.csv"
            csv_path.write_text(
                "time_seconds,weights\n0.0,500.0\n0.01,nan\n",
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                read_measurements(csv_path)

    def test_non_increasing_time_is_rejected(self) -> None:
        """Repeated timestamps must fail because event order depends on time."""

        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "bad_time.csv"
            csv_path.write_text(
                "time_seconds,weights\n0.0,500.0\n0.01,500.0\n0.01,501.0\n",
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                read_measurements(csv_path)


def write_test_report(result: unittest.TestResult, output_path: str | Path) -> None:
    """Write a plain-language summary of the test run to a text file."""

    report_path = Path(output_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    with report_path.open(mode="w", encoding="utf-8") as report_file:
        report_file.write("SMART-SHELF WEIGHT DETECTOR TEST REPORT\n")
        report_file.write("=" * 42 + "\n\n")
        report_file.write(f"Tests executed: {result.testsRun}\n")
        report_file.write(
            f"Tests passed: {result.testsRun - len(result.failures) - len(result.errors)}\n"
        )
        report_file.write(f"Tests failed: {len(result.failures)}\n")
        report_file.write(f"Test errors: {len(result.errors)}\n")
        report_file.write(
            f"Overall result: {'PASS - all checks succeeded' if result.wasSuccessful() else 'FAIL - review the details below'}\n\n"
        )

        report_file.write("WHAT THE TESTS CHECK\n")
        report_file.write("- Supplied recordings detect the expected removal and addition.\n")
        report_file.write("- Quiet data and temporary spikes do not create false events.\n")
        report_file.write("- Real removals are negative and additions are positive.\n")
        report_file.write("- Small changes below the configured threshold are ignored.\n")
        report_file.write("- Invalid, incomplete, or incorrectly timed data is rejected.\n\n")

        if result.failures:
            report_file.write("FAILED TESTS\n")
            for test_case, traceback_text in result.failures:
                report_file.write(f"\n{test_case}\n{traceback_text}\n")

        if result.errors:
            report_file.write("TEST ERRORS\n")
            for test_case, traceback_text in result.errors:
                report_file.write(f"\n{test_case}\n{traceback_text}\n")

        if result.wasSuccessful():
            report_file.write("\nConclusion: The detector passed all implemented checks.\n")
        else:
            report_file.write(
                "\nConclusion: At least one check failed. Review the failed test details before relying on the results.\n"
            )


def run_test_suite() -> bool:
    """Run all tests, print details, and save the explained text report."""

    suite = unittest.defaultTestLoader.loadTestsFromModule(__import__(__name__))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    report_path = os.environ.get("TEST_REPORT_PATH", "test_results.txt")
    write_test_report(result, report_path)
    print(f"\nTest report saved to: {report_path}")
    return result.wasSuccessful()


if __name__ == "__main__":
    raise SystemExit(0 if run_test_suite() else 1)
