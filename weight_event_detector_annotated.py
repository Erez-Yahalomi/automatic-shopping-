#!/usr/bin/env python3
# Explanation: This shebang lets Unix-like systems run this file with Python 3 when the file is executable.

"""Detect sustained weight changes in smart-shelf measurement files.

Each input CSV file must contain the columns ``time_seconds`` and ``weights``.
The public function ``detect_weight_change`` accepts one file path and returns
``[(weight_change_in_grams, change_time_in_seconds), ...]``.

A positive change means that weight was added to the shelf. A negative change
means that weight was removed from the shelf.
"""
# Explanation: This module documentation explains the input format, the main function, and the meaning of positive and negative changes.

from __future__ import annotations
# Explanation: This postpones evaluation of type annotations, making modern type hints work consistently.

import argparse
# Explanation: argparse reads command-line options such as --plot.
import csv
# Explanation: csv reads the input measurement files safely.
import math
# Explanation: math provides isfinite(), which detects invalid numbers such as NaN and infinity.
import statistics
# Explanation: statistics provides median(), which is robust against occasional unusual readings.
from collections.abc import Iterable, Sequence
# Explanation: These type names describe collections accepted by helper functions.
from dataclasses import dataclass
# Explanation: dataclass automatically creates simple constructor and comparison methods for data-holder classes.
from pathlib import Path
# Explanation: Path represents file and folder paths in a platform-independent way.

try:
    # Explanation: Plotting is optional, so the program tries to import matplotlib first.
    import matplotlib.pyplot as pyplot
    # Explanation: pyplot is matplotlib's interface for creating the required graph.
except ImportError:
    # Explanation: This block runs only when matplotlib is not installed.
    pyplot = None
    # Explanation: None records that plot generation is unavailable, while detection can still run.


@dataclass(frozen=True)
# Explanation: dataclass creates a lightweight data class; frozen=True prevents accidental changes after creation.
class Measurement:
    # Explanation: This class groups one timestamp and one measured shelf weight.
    """One measurement reported by the shelf scale."""
    # Explanation: This documentation string describes the purpose of the class.

    time_seconds: float
    # Explanation: This field stores the time of the sample in seconds as a decimal number.
    weight_grams: float
    # Explanation: This field stores the shelf weight of the sample in grams as a decimal number.


@dataclass(frozen=True)
# Explanation: The parameter object is immutable so one run cannot accidentally alter another run's settings.
class DetectionParameters:
    # Explanation: This class collects every tuneable detection setting in one clearly named place.
    """Parameters controlling the balance between sensitivity and robustness.

    The defaults are intentionally expressed in seconds and grams instead of
    sample counts. Therefore, the detector continues to work when the sampling
    interval changes slightly between input files.
    """
    # Explanation: The documentation explains why physical units are preferable to fixed numbers of samples.

    initial_baseline_duration_seconds: float = 0.15
    # Explanation: The first 0.15 seconds of data define the initial stable shelf weight.
    confirmation_duration_seconds: float = 0.15
    # Explanation: A candidate change must remain settled for roughly 0.15 seconds before confirmation.
    required_confirmation_fraction: float = 0.95
    # Explanation: Sampling is discrete, so 95% of the requested duration is accepted instead of requiring an impossible exact boundary.
    minimum_activity_threshold_grams: float = 5.0
    # Explanation: A reading must deviate by at least 5 g before it can begin an event candidate.
    minimum_change_threshold_grams: float = 5.0
    # Explanation: A final difference smaller than 5 g is ignored as normal small-scale variation.
    minimum_stability_tolerance_grams: float = 2.5
    # Explanation: A settled window may vary by at least this much because real scales are not perfectly still.


@dataclass(frozen=True)
# Explanation: Each detected event is an immutable record containing its amount and start time.
class DetectionResult:
    # Explanation: This class holds the detailed form of one confirmed change.
    """A confirmed weight change and the time at which the activity began."""
    # Explanation: The event time is when activity started, not when the scale finally settled.

    weight_change_grams: float
    # Explanation: This signed value is positive for an addition and negative for a removal.
    change_time_seconds: float
    # Explanation: This value records the first significant departure from the old resting level.


def read_measurements(csv_path: str | Path) -> list[Measurement]:
    # Explanation: This function receives a text or Path filename and returns a list of validated Measurement objects.
    """Read and validate a shelf-measurement CSV file.

    The function rejects missing columns, non-numeric values, non-finite values,
    and time values that do not increase. Early validation makes later detection
    logic simpler and provides useful error messages to the caller.
    """
    # Explanation: Validation happens at the beginning so later functions can safely assume the input has the expected shape.

    input_path = Path(csv_path)
    # Explanation: Convert either a string or an existing Path object into one Path object.

    if not input_path.is_file():
        # Explanation: Check that the supplied path exists and is a normal file before trying to open it.
        raise FileNotFoundError(f"Input file does not exist: {input_path}")
        # Explanation: Stop immediately with a clear error message when the input file cannot be found.

    measurements: list[Measurement] = []
    # Explanation: Start an empty list; valid rows will be converted into Measurement objects and added here.

    with input_path.open(mode="r", encoding="utf-8", newline="") as input_file:
        # Explanation: Open the CSV for reading; the with statement closes it automatically, even if an error occurs.
        reader = csv.DictReader(input_file)
        # Explanation: DictReader reads each CSV row as a dictionary whose keys come from the header row.
        required_columns = {"time_seconds", "weights"}
        # Explanation: This set lists exactly the two column names required by the task.

        if reader.fieldnames is None or not required_columns.issubset(reader.fieldnames):
            # Explanation: Reject a file with no header or with either required column missing.
            raise ValueError(
                # Explanation: Begin a readable error message for an invalid CSV structure.
                "The CSV file must contain the columns 'time_seconds' and 'weights'."
                # Explanation: State exactly which column names are required.
            )
            # Explanation: End the ValueError call and stop processing this invalid file.

        for row_number, row in enumerate(reader, start=2):
            # Explanation: Read one data row at a time; start numbering at 2 because CSV row 1 is the header.
            try:
                # Explanation: Conversion can fail, so keep the two float conversions inside a try block.
                time_seconds = float(row["time_seconds"])
                # Explanation: Read the time cell and convert its text to a floating-point number.
                weight_grams = float(row["weights"])
                # Explanation: Read the weight cell and convert its text to a floating-point number.
            except (TypeError, ValueError) as error:
                # Explanation: Handle missing cells, non-text cells, or text that cannot become a float.
                raise ValueError(
                    # Explanation: Begin an error that identifies the bad data row.
                    f"Row {row_number} contains a non-numeric time or weight value."
                    # Explanation: Include the actual row number to make fixing the CSV easier.
                ) from error
                # Explanation: Preserve the original conversion error as additional debugging information.

            if not math.isfinite(time_seconds) or not math.isfinite(weight_grams):
                # Explanation: Reject special float values such as NaN, positive infinity, and negative infinity.
                raise ValueError(
                    # Explanation: Begin a message describing the invalid numerical value.
                    f"Row {row_number} contains a non-finite time or weight value."
                    # Explanation: Include the faulty row number.
                )
                # Explanation: Stop because non-finite numbers would break comparisons and calculations.

            if measurements and time_seconds <= measurements[-1].time_seconds:
                # Explanation: If an earlier sample exists, require the new timestamp to be strictly later than the previous timestamp.
                raise ValueError(
                    # Explanation: Begin an error message for incorrect time ordering.
                    "The time_seconds column must be strictly increasing. "
                    # Explanation: Explain the general timestamp requirement.
                    f"Row {row_number} violates this requirement."
                    # Explanation: Identify the row that breaks the requirement.
                )
                # Explanation: Stop because event timing is unreliable when time does not move forward.

            measurements.append(
                # Explanation: Add one validated record to the measurements list.
                Measurement(time_seconds=time_seconds, weight_grams=weight_grams)
                # Explanation: Create the immutable Measurement object from the converted values.
            )
            # Explanation: Finish appending the object to the list.

    if len(measurements) < 2:
        # Explanation: At least two measurements are needed to calculate a difference and detect a change.
        raise ValueError("At least two measurements are required for event detection.")
        # Explanation: Explain why a tiny input file is not valid for this algorithm.

    return measurements
    # Explanation: Give the caller the complete, validated list of measurements.


# Algorithm explanation — Median estimation:
# Collect the weights in the selected time window, sort them conceptually,
# and choose the middle value. A median reduces the influence of short spikes.
def median_weight(measurements: Iterable[Measurement]) -> float:
    # Explanation: This helper returns the median weight from any iterable of Measurement objects.
    """Return the median weight for a non-empty sequence of measurements."""
    # Explanation: A median is the middle value after sorting and is robust against unusual spikes.

    weights: list[float] = []
    # Explanation: Create an empty list that will hold only the numeric weight values.

    for measurement in measurements:
        # Explanation: Visit every Measurement object supplied by the caller.
        weights.append(measurement.weight_grams)
        # Explanation: Extract its weight field and add it to the list of numeric values.

    if not weights:
        # Explanation: An empty list has no median, so check this case explicitly.
        raise ValueError("Cannot calculate a median from an empty measurement set.")
        # Explanation: Stop with a clear message rather than producing a less helpful library error.

    return statistics.median(weights)
    # Explanation: Calculate and return the middle weight value.


# Algorithm explanation — Sliding confirmation window:
# During activity, keep only samples from the latest confirmation duration.
# As each new sample arrives, the window moves forward in time and older
# samples leave it. This tests the most recent physical behavior of the shelf.
def measurements_in_recent_duration(
    measurements: Sequence[Measurement], duration_seconds: float
) -> list[Measurement]:
    # Explanation: This function keeps only measurements from a recent time window ending at the latest sample.
    """Return the tail of measurements that lies within a time duration.

    The final measurement is used as the reference point. A duration-based
    window is more robust than a fixed number of samples because input files may
    have slightly different sampling frequencies.
    """
    # Explanation: The time window uses seconds, not a fixed number of rows, so small sampling-rate changes do not change its meaning.

    if not measurements:
        # Explanation: There is no latest timestamp if the input sequence is empty.
        return []
        # Explanation: Return an empty list because there are no recent measurements to select.

    final_time = measurements[-1].time_seconds
    # Explanation: The last record is the newest record, so its time is the end of the desired window.
    earliest_time = final_time - duration_seconds
    # Explanation: Subtract the requested duration to calculate the first acceptable timestamp.

    recent_measurements: list[Measurement] = []
    # Explanation: Create a list for the samples that fall inside the recent window.

    for measurement in measurements:
        # Explanation: Examine each available measurement in time order.
        if measurement.time_seconds >= earliest_time:
            # Explanation: Keep the measurement if its time is inside or exactly on the window boundary.
            recent_measurements.append(measurement)
            # Explanation: Add the accepted measurement to the output list.

    return recent_measurements
    # Explanation: Return the selected recent samples.


# Algorithm explanation — Sensor-noise estimation:
# Compare each reading with the immediately previous reading. Take the median
# of those absolute differences to represent normal short-term sensor jitter.
# A few large movement samples should not dominate this typical-noise value.
def estimate_sensor_noise_grams(measurements: Sequence[Measurement]) -> float:
    # Explanation: This function estimates normal short-term measurement variation in grams.
    """Estimate short-term sensor variation using consecutive differences.

    Most consecutive values are collected while the shelf is not being touched.
    The median absolute difference is therefore resistant to the small number of
    large movement spikes produced during a pickup or return action.
    """
    # Explanation: The method uses the median of adjacent changes, so a few large handling transitions do not dominate the estimate.

    absolute_differences: list[float] = []
    # Explanation: Create a list for the non-negative weight differences between adjacent samples.

    for index in range(1, len(measurements)):
        # Explanation: Start at index 1 so that every current measurement has a previous measurement at index - 1.
        previous_measurement = measurements[index - 1]
        # Explanation: Read the measurement immediately before the current one.
        current_measurement = measurements[index]
        # Explanation: Read the measurement currently being compared.
        difference_grams = abs(
            # Explanation: abs() removes direction because noise size matters, not whether the scale moved up or down.
            current_measurement.weight_grams - previous_measurement.weight_grams
            # Explanation: Subtract two neighboring weights to find the single-sample change.
        )
        # Explanation: Finish the absolute-difference calculation.
        absolute_differences.append(difference_grams)
        # Explanation: Save this adjacent difference for the final median calculation.

    return statistics.median(absolute_differences)
    # Explanation: Return the typical adjacent difference as the noise estimate.


# Algorithm explanation — Adaptive thresholds:
# Convert the measured noise into three rules: when activity starts, when a
# final change is large enough to report, and how much variation is allowed
# inside a stable window. Use minimum floors so thresholds cannot become zero.
def calculate_thresholds(
    sensor_noise_grams: float, parameters: DetectionParameters
) -> tuple[float, float, float]:
    # Explanation: This function converts the measured noise into three practical detection limits.
    """Create activity, change, and stability thresholds from measured noise."""
    # Explanation: The returned values control when activity begins, when a result is emitted, and when a window is settled.

    activity_threshold_grams = max(
        # Explanation: Choose the larger of the fixed minimum and the noise-based value.
        parameters.minimum_activity_threshold_grams,
        # Explanation: Never allow the activity threshold to be lower than the explicitly chosen minimum.
        12.0 * sensor_noise_grams,
        # Explanation: In a noisier signal, require a deviation twelve times typical adjacent noise before activity starts.
    )
    # Explanation: Store the final activity threshold.
    change_threshold_grams = max(
        # Explanation: Again choose the larger of a fixed lower bound and a noise-based lower bound.
        parameters.minimum_change_threshold_grams,
        # Explanation: Prevent tiny net changes from being reported as events.
        12.0 * sensor_noise_grams,
        # Explanation: In noisy data, require a larger final change before reporting it.
    )
    # Explanation: Store the final change-reporting threshold.
    stability_tolerance_grams = max(
        # Explanation: Choose an allowed stable-level deviation based on both a minimum and observed noise.
        parameters.minimum_stability_tolerance_grams,
        # Explanation: Allow at least the specified number of grams of normal variation.
        6.0 * sensor_noise_grams,
        # Explanation: When sensor noise is larger, allow six times that typical noise in the stability tolerance.
    )
    # Explanation: Store the final stability tolerance.

    return (
        # Explanation: Begin the tuple of three calculated thresholds.
        activity_threshold_grams,
        # Explanation: First returned value: deviation required to start an event candidate.
        change_threshold_grams,
        # Explanation: Second returned value: net change required to report an event.
        stability_tolerance_grams,
        # Explanation: Third returned value: permitted deviation while treating a window as settled.
    )
    # Explanation: Return all three values in the documented order.


# Algorithm explanation — Stability decision:
# A candidate window is stable when its highest weight minus its lowest weight
# is small enough. This accepts normal sensor oscillation but rejects a window
# that still contains a large movement transition.
def is_stable(
    measurements: Sequence[Measurement], stability_tolerance_grams: float
) -> bool:
    # Explanation: This function decides whether the recent measurements look like a settled shelf level.
    """Return whether a time window is a quiet, settled weight plateau.

    Small scales naturally oscillate around a fixed load. Requiring every value
    to lie inside a very narrow band would incorrectly label this normal sensor
    movement as activity. Instead, this function accepts a window when its full
    peak-to-peak range is no greater than twice the allowed deviation. A real
    pickup or return transition changes far more than this within the same short
    time interval.
    """
    # Explanation: A plateau may contain small fluctuations, but a real transition has a much larger maximum-minus-minimum range.

    if not measurements:
        # Explanation: An empty time window cannot demonstrate that the shelf is stable.
        return False
        # Explanation: Return False immediately for this invalid or incomplete case.

    weights: list[float] = []
    # Explanation: Create a list containing only the numeric weights from this time window.

    for measurement in measurements:
        # Explanation: Visit every sample in the candidate stable window.
        weights.append(measurement.weight_grams)
        # Explanation: Copy the sample's weight into the simpler numeric list.

    peak_to_peak_variation_grams = max(weights) - min(weights)
    # Explanation: Compute the full observed range: largest weight minus smallest weight.
    allowed_peak_to_peak_variation_grams = 2.0 * stability_tolerance_grams
    # Explanation: Allow two tolerance distances because the signal can be tolerance above and tolerance below its center.

    return peak_to_peak_variation_grams <= allowed_peak_to_peak_variation_grams
    # Explanation: The window is stable only when its observed range is not larger than the allowed range.


# Algorithm explanation — Initial baseline:
# Use the first 0.15 seconds as the starting observation window. The median of
# that window becomes the first resting shelf weight used for comparisons.
def choose_initial_baseline(
    measurements: Sequence[Measurement], parameters: DetectionParameters
) -> float:
    # Explanation: This function estimates the shelf's first resting weight before the first customer action.
    """Estimate the shelf's initial resting weight from the first quiet window."""
    # Explanation: The detector compares later readings with this baseline until it confirms a new resting level.

    starting_time = measurements[0].time_seconds
    # Explanation: The first sample gives the beginning of the initial baseline window.
    initial_window: list[Measurement] = []
    # Explanation: Create a list to hold samples that occur at the beginning of the recording.
    final_initial_window_time = (
        # Explanation: Begin a grouped expression for the end of the initial baseline period.
        starting_time + parameters.initial_baseline_duration_seconds
        # Explanation: Add 0.15 seconds, by default, to the starting time.
    )
    # Explanation: Finish and save the last timestamp that belongs to the initial window.

    for measurement in measurements:
        # Explanation: Examine each measurement to determine whether it belongs to the initial baseline period.
        if measurement.time_seconds <= final_initial_window_time:
            # Explanation: Select samples at or before the calculated final baseline time.
            initial_window.append(measurement)
            # Explanation: Add the selected sample to the initial window.

    return median_weight(initial_window)
    # Explanation: Use the median initial weight as the robust initial resting baseline.


# Algorithm explanation — Main event detector:
# Process measurements in chronological order using two states. In Stable mode,
# look for a threshold crossing. In Activity mode, collect a recent window,
# wait for enough elapsed time, confirm stability, calculate the new median,
# compare old and new levels, optionally emit one event, then reset the state.
def detect_weight_change_details(
    measurements: Sequence[Measurement],
    parameters: DetectionParameters | None = None,
) -> list[DetectionResult]:
    # Explanation: This is the main algorithm; it receives measurements and produces detailed event records.
    """Detect sustained shelf-weight changes with a two-state algorithm.

    The detector starts in a *stable* state. When a reading deviates enough from
    the known resting weight, it stores that first time as the event time and
    changes to an *activity in progress* state. It does not immediately report
    the change because a hand or moving product can create a temporary spike.
    Once a new level stays stable for the confirmation duration, the median of
    that stable level is compared with the old resting weight and one event is
    emitted. This reports the event as early as the data allows while avoiding
    false events caused by the transient spike itself.
    """
    # Explanation: The two states are represented below by the boolean activity_in_progress: False means stable and True means activity is being checked.

    if parameters is None:
        # Explanation: Allow callers to omit settings and still receive the documented default settings.
        parameters = DetectionParameters()
        # Explanation: Construct a fresh default parameter object.

    if len(measurements) < 2:
        # Explanation: Double-check that enough data exists because this function can also be called directly.
        raise ValueError("At least two measurements are required for event detection.")
        # Explanation: Stop before calculations that require adjacent or time-windowed samples.

    sensor_noise_grams = estimate_sensor_noise_grams(measurements)
    # Explanation: Calculate the typical short-term change in this recording.
    (
        # Explanation: Begin unpacking the three threshold values returned by calculate_thresholds().
        activity_threshold_grams,
        # Explanation: This variable receives the threshold for beginning an event candidate.
        change_threshold_grams,
        # Explanation: This variable receives the threshold for emitting a final event.
        stability_tolerance_grams,
        # Explanation: This variable receives the allowed normal movement in a settled window.
    ) = calculate_thresholds(sensor_noise_grams, parameters)
    # Explanation: Calculate all three thresholds using the data's noise level and the configured minimum values.

    # Algorithm step — Establish the first reference level before scanning.
    # Later readings are compared with this resting weight.
    resting_weight_grams = choose_initial_baseline(measurements, parameters)
    # Explanation: Set the initial stable shelf level from the beginning of the recording.
    events: list[DetectionResult] = []
    # Explanation: Create an empty list; each confirmed event will be appended here.
    activity_in_progress = False
    # Explanation: Start in the stable state because the algorithm has not yet observed a significant deviation.
    event_start_time_seconds: float | None = None
    # Explanation: There is no event start time yet, so use None until an event candidate begins.
    activity_measurements: list[Measurement] = []
    # Explanation: This list will hold only the latest samples while an event candidate is being confirmed.

    for measurement in measurements:
        # Explanation: Process the complete recording one measurement at a time, in chronological order.
        # Algorithm state 1 — Stable shelf:
        # Trust the current baseline and check whether this reading is far enough
        # away to indicate the beginning of a possible physical action.
        if not activity_in_progress:
            # Explanation: In the stable state, look only for the first large deviation from the known resting level.
            deviation_from_resting_weight = abs(
                # Explanation: abs() measures the size of the change regardless of whether weight increased or decreased.
                measurement.weight_grams - resting_weight_grams
                # Explanation: Subtract the current resting weight from the new raw scale reading.
            )
            # Explanation: Finish calculating the non-negative deviation from the stable baseline.

            if deviation_from_resting_weight >= activity_threshold_grams:
                # Explanation: A sufficiently large deviation means the user may be removing or adding an item.
                activity_in_progress = True
                # Explanation: Switch the algorithm from the stable state to the candidate-confirmation state.
                event_start_time_seconds = measurement.time_seconds
                # Explanation: Save the first threshold-crossing time so the returned event time is early.
                activity_measurements = [measurement]
                # Explanation: Start the candidate's measurement window with the current threshold-crossing sample.

            continue
            # Explanation: In either stable-state case, move to the next raw measurement; confirmation logic runs only after activity has started.

        # Algorithm state 2 — Activity in progress:
        # Do not report the first spike. Add readings to a rolling window and
        # wait until the shelf has stayed at a new level long enough.
        activity_measurements.append(measurement)
        # Explanation: Add the newest sample to the candidate event window.
        activity_measurements = measurements_in_recent_duration(
            # Explanation: Replace the candidate list with only its newest time-window portion.
            activity_measurements,
            # Explanation: Supply the samples collected since the candidate began.
            parameters.confirmation_duration_seconds,
            # Explanation: Keep only samples from the most recent confirmation duration.
        )
        # Explanation: Storing only recent values keeps memory use small during a long recording.
        recent_measurements = activity_measurements
        # Explanation: This clearer name emphasizes that these samples form the current confirmation window.

        observed_confirmation_duration_seconds = (
            # Explanation: Begin calculating how much time the current window actually spans.
            recent_measurements[-1].time_seconds - recent_measurements[0].time_seconds
            # Explanation: Subtract the first selected time from the most recent selected time.
        )
        # Explanation: Save the measured duration of the current confirmation window.
        required_confirmation_duration_seconds = (
            # Explanation: Begin calculating the slightly relaxed minimum required duration.
            parameters.confirmation_duration_seconds
            # Explanation: Use the requested confirmation duration, normally 0.15 seconds.
            * parameters.required_confirmation_fraction
            # Explanation: Multiply by 0.95 so discrete timestamp spacing does not block an otherwise complete window.
        )
        # Explanation: Save the duration that is long enough to test for stability.
        has_confirmation_duration = (
            # Explanation: Begin the boolean comparison that decides whether enough time has passed.
            observed_confirmation_duration_seconds
            # Explanation: Use the time span that is actually present in the recent window.
            >= required_confirmation_duration_seconds
            # Explanation: Require it to be at least the relaxed required duration.
        )
        # Explanation: Store True or False in a clearly named variable.

        # Algorithm gate 1 — Duration confirmation:
        # A window that is too short cannot prove that the shelf has settled.
        if not has_confirmation_duration:
            # Explanation: A short window cannot yet prove that the scale has settled.
            continue
            # Explanation: Wait for more samples and then test again.

        # Algorithm gate 2 — Stability confirmation:
        # If the recent window is still moving too much, keep waiting and do not
        # calculate a new baseline yet.
        if not is_stable(recent_measurements, stability_tolerance_grams):
            # Explanation: Reject a window whose weights still vary too widely, because the physical action is still in progress.
            continue
            # Explanation: Wait for the next sample instead of creating a false event from a transient spike.

        # Algorithm step — Estimate the new settled level:
        # The median of the confirmed stable window is the new shelf weight.
        new_resting_weight_grams = median_weight(recent_measurements)
        # Explanation: The median of the settled window estimates the new stable shelf load.
        weight_change_grams = new_resting_weight_grams - resting_weight_grams
        # Explanation: Subtract old stable level from new stable level; this creates the signed net change.

        # Algorithm step — Decide whether the net change is meaningful:
        # A stable but very small difference is treated as drift or disturbance,
        # not as a user event.
        if abs(weight_change_grams) >= change_threshold_grams:
            # Explanation: Report the candidate only if its final net size is larger than normal noise.
            events.append(
                # Explanation: Add one complete event record to the output list.
                DetectionResult(
                    # Explanation: Create the event object that will store the final amount and the earlier start time.
                    weight_change_grams=weight_change_grams,
                    # Explanation: Store the signed difference between new and old stable shelf levels.
                    change_time_seconds=event_start_time_seconds,
                    # Explanation: Store the first significant-deviation time, not the later confirmation time.
                )
                # Explanation: Finish creating the DetectionResult object.
            )
            # Explanation: Finish appending the confirmed event.

        # Algorithm step — Re-anchor the detector:
        # Whether or not an event was reported, the confirmed stable level becomes
        # the baseline used to detect the next event.
        resting_weight_grams = new_resting_weight_grams
        # Explanation: Whether or not the net change was large enough to report, use the settled level as the next baseline.
        activity_in_progress = False
        # Explanation: Return to the stable state and begin looking for a later independent event.
        event_start_time_seconds = None
        # Explanation: Clear the old event time because no candidate is currently active.
        activity_measurements = []
        # Explanation: Clear the old confirmation samples so they do not affect the next candidate.

    return events
    # Explanation: Return every confirmed detailed event after all measurements have been processed.


def detect_weight_change(csv_path: str | Path) -> list[tuple[float, float]]:
    # Explanation: This is the simple public function required by the task: it receives one file path and returns simple tuples.
    """Return ``(weight_change_grams, change_time_seconds)`` for one CSV file.

    This is the concise function required by the task. Values are rounded only
    in this public result so the internal calculations retain full precision.
    """
    # Explanation: Internal work keeps precise numbers; only the user-facing result is rounded for readability.

    measurements = read_measurements(csv_path)
    # Explanation: Load and validate the file before running the detection algorithm.
    detailed_events = detect_weight_change_details(measurements)
    # Explanation: Run the main algorithm and receive detailed DetectionResult objects.

    public_events: list[tuple[float, float]] = []
    # Explanation: Create the final list of ordinary `(change, time)` tuples expected by the task.

    for event in detailed_events:
        # Explanation: Convert each detailed object into a simple rounded tuple.
        rounded_event = (
            # Explanation: Begin the two-value tuple for one public event.
            round(event.weight_change_grams, 2),
            # Explanation: Round the weight change to two decimal places.
            round(event.change_time_seconds, 3),
            # Explanation: Round the event time to three decimal places.
        )
        # Explanation: Finish creating the rounded tuple.
        public_events.append(rounded_event)
        # Explanation: Add the rounded tuple to the public output list.

    return public_events
    # Explanation: Give the caller the requested list of `(weight_change, change_time)` pairs.


def write_detection_results(
    output_path: str | Path,
    input_path: str | Path,
    events: Sequence[tuple[float, float]],
) -> None:
    # Explanation: This function saves the numerical detection results as plain text.
    """Write detected weight changes and event times to a text file."""
    # Explanation: A text file is easy to open, archive, or import into another program.

    output_file = Path(output_path)
    # Explanation: Convert the requested output filename into a platform-independent Path object.
    output_file.parent.mkdir(parents=True, exist_ok=True)
    # Explanation: Create the output folder if it does not already exist.

    with output_file.open(mode="w", encoding="utf-8") as results_file:
        # Explanation: Open the text file for writing and replace an older result from the same run.
        results_file.write(f"Input file: {Path(input_path).name}\n")
        # Explanation: Record which CSV file produced these numerical results.
        results_file.write(f"Number of detected events: {len(events)}\n\n")
        # Explanation: State how many events were found before listing their details.

        if not events:
            results_file.write("No weight events were detected.\n")
            # Explanation: Make an empty result explicit and easy for a person to understand.

        for event_number, (weight_change_grams, change_time_seconds) in enumerate(events, start=1):
            # Explanation: Number each event so the text file is easy to read.
            if weight_change_grams < 0:
                change_description = "Weight removed from the shelf"
                # Explanation: A negative change means the shelf lost weight.
            else:
                change_description = "Weight added to or returned to the shelf"
                # Explanation: A positive change means the shelf gained weight.

            results_file.write(f"Event {event_number}:\n")
            # Explanation: Start a clearly labeled section for this detected event.
            results_file.write(f"  Weight change: {weight_change_grams:+.2f} grams\n")
            # Explanation: Write the signed weight difference with two decimal places.
            results_file.write(f"  Event time: {change_time_seconds:.3f} seconds\n")
            # Explanation: Write the event-start time with three decimal places.
            results_file.write(f"  Meaning: {change_description}\n\n")
            # Explanation: Describe the direction of the change and separate events visually.



def create_plot(
    measurements: Sequence[Measurement],
    events: Sequence[DetectionResult],
    output_path: str | Path,
) -> None:
    # Explanation: This optional function draws the raw weight curve and marks detected event times.
    """Create a plain plot of weight over time with event labels beneath it."""
    # Explanation: The chart is intentionally simple to satisfy the task's plain-text plotting requirement.

    if pyplot is None:
        # Explanation: Plot creation is impossible if the optional plotting library was not imported.
        raise RuntimeError(
            # Explanation: Begin a clear error message explaining how to proceed.
            "Plot creation requires matplotlib. Install it or run without --plot."
            # Explanation: Tell the user either to install matplotlib or omit the plotting option.
        )
        # Explanation: Stop instead of causing an unclear attribute error later.

    output_file = Path(output_path)
    # Explanation: Convert the requested output location into a Path object.
    output_file.parent.mkdir(parents=True, exist_ok=True)
    # Explanation: Create the output folder and any missing parent folders; do nothing if it already exists.

    figure, axis = pyplot.subplots(figsize=(10, 5.5))
    # Explanation: Create one matplotlib figure and one coordinate system, with a readable size in inches.
    times: list[float] = []
    # Explanation: Create a list for x-axis time values.
    weights: list[float] = []
    # Explanation: Create a list for y-axis weight values.

    for measurement in measurements:
        # Explanation: Visit every raw measurement so the complete signal can be plotted.
        times.append(measurement.time_seconds)
        # Explanation: Add the measurement timestamp to the x-axis list.
        weights.append(measurement.weight_grams)
        # Explanation: Add the measurement weight to the y-axis list.

    axis.plot(times, weights, color="#1f5a7a", linewidth=1.2, label="Measured weight")
    # Explanation: Draw the raw weight-vs-time line with a readable color and line width.
    axis.set_xlabel("Time (seconds)")
    # Explanation: Label the horizontal axis so the reader knows time is measured in seconds.
    axis.set_ylabel("Weight (grams)")
    # Explanation: Label the vertical axis so the reader knows weight is measured in grams.
    axis.set_title("Smart Shelf Weight Measurements")
    # Explanation: Add a descriptive title above the graph.
    axis.grid(True, alpha=0.3)
    # Explanation: Draw a faint grid to make approximate values easier to read.

    for event in events:
        # Explanation: Add one vertical marker for each detected event.
        axis.axvline(
            # Explanation: Begin drawing a vertical line at the event time.
            event.change_time_seconds,
            # Explanation: Use the event's stored start time as the x-coordinate.
            color="#b33a3a",
            # Explanation: Use a contrasting red-brown color for event markers.
            linestyle="--",
            # Explanation: Use a dashed line so the marker is distinguishable from the raw signal line.
            linewidth=1.0,
            # Explanation: Use a normal line width for the marker.
            alpha=0.8,
            # Explanation: Make the marker slightly transparent so it does not hide the data curve.
        )
        # Explanation: Finish drawing the event marker.

    if events:
        # Explanation: Use a detailed label only when at least one event was detected.
        event_text = "Detected weight changes: " + "; ".join(
            # Explanation: Start a readable sentence and join individual event descriptions using semicolons.
            f"{event.weight_change_grams:+.2f} g at {event.change_time_seconds:.3f} s"
            # Explanation: Format each event with an explicit sign, two decimal grams, and three decimal seconds.
            for event in events
            # Explanation: Repeat the formatting expression once for every event in the event list.
        )
        # Explanation: Finish building the one-line event summary.
    else:
        # Explanation: Use this alternative text when the detector found no events.
        event_text = "Detected weight changes: none"
        # Explanation: Provide an explicit, understandable result instead of leaving the graph unlabelled.

    figure.text(0.5, 0.02, event_text, ha="center", va="bottom", fontsize=9)
    # Explanation: Place the event summary near the lower centre of the figure, below the main graph area.
    figure.subplots_adjust(bottom=0.20)
    # Explanation: Reserve extra space at the bottom so the event summary is not clipped.
    figure.savefig(output_file, dpi=160, bbox_inches="tight")
    # Explanation: Save the figure as an image with readable resolution and a tight bounding box.
    pyplot.close(figure)
    # Explanation: Release plotting resources after saving, which matters when processing many files.


def process_file(input_path: Path, output_directory: Path, create_plots: bool) -> None:
    # Explanation: This command-line helper processes one file, prints its events, and optionally creates its plot.
    """Detect events for one file, print them, and optionally save its plot."""
    # Explanation: It reuses the validated reader and detailed detection function.

    measurements = read_measurements(input_path)
    # Explanation: Read and validate the selected input file.
    detailed_events = detect_weight_change_details(measurements)
    # Explanation: Detect events while retaining the detailed objects required for plot markers.
    public_events: list[tuple[float, float]] = []
    # Explanation: Create a list for the short, rounded form printed to the terminal.

    for event in detailed_events:
        # Explanation: Convert each detailed event into its public tuple form.
        rounded_event = (
            # Explanation: Begin the two-value tuple to be printed.
            round(event.weight_change_grams, 2),
            # Explanation: Round the signed weight amount to two decimal places.
            round(event.change_time_seconds, 3),
            # Explanation: Round the event time to three decimal places.
        )
        # Explanation: Finish creating the rounded display tuple.
        public_events.append(rounded_event)
        # Explanation: Add the display tuple to the list printed below.

    print(f"{input_path.name}: {public_events}")
    # Explanation: Print the filename and its detected public events for the command-line user.

    results_path = output_directory / f"{input_path.stem}_events.txt"
    # Explanation: Create a text filename such as results/50_gr_events.txt.
    write_detection_results(results_path, input_path, public_events)
    # Explanation: Save the numerical results even when plot generation is not requested.
    print(f"  Numerical results saved to: {results_path}")
    # Explanation: Tell the user where the text result file was created.

    if create_plots:
        # Explanation: Create a graph only when the caller supplied the --plot option.
        plot_path = output_directory / f"{input_path.stem}_events.png"
        # Explanation: Build a filename such as results/50_gr_events.png from the input file's stem.
        create_plot(measurements, detailed_events, plot_path)
        # Explanation: Draw and save the graph using raw measurements and detailed event times.
        print(f"  Plot saved to: {plot_path}")
        # Explanation: Tell the user exactly where the saved image can be found.


def parse_command_line_arguments() -> argparse.Namespace:
    # Explanation: This function defines and reads the options accepted when the file is run from a terminal.
    """Read file paths and output options from the command line."""
    # Explanation: The returned Namespace object stores the values typed by the user.

    parser = argparse.ArgumentParser(
        # Explanation: Create the command-line parser object.
        description="Detect sustained weight changes in smart-shelf CSV files."
        # Explanation: This description appears in the automatically generated help message.
    )
    # Explanation: Finish constructing the parser.
    parser.add_argument(
        # Explanation: Begin defining the required positional input-files argument.
        "input_files",
        # Explanation: Store the supplied file paths in the arguments.input_files attribute.
        nargs="+",
        # Explanation: Require one or more input files rather than exactly one file.
        type=Path,
        # Explanation: Convert each typed path string into a Path object automatically.
        help="One or more CSV files with time_seconds and weights columns.",
        # Explanation: Show this guidance when the user runs the program with --help.
    )
    # Explanation: Finish defining the input-files argument.
    parser.add_argument(
        # Explanation: Begin defining an optional folder for saved plot images.
        "--output-directory",
        # Explanation: This named option is written as --output-directory on the command line.
        type=Path,
        # Explanation: Convert the chosen directory string into a Path object.
        default=Path("results"),
        # Explanation: Use a folder named results when the user does not provide this option.
        help="Directory for generated plots. Default: results",
        # Explanation: Explain the option in the help message.
    )
    # Explanation: Finish defining the output-directory option.
    parser.add_argument(
        # Explanation: Begin defining the optional boolean plotting flag.
        "--plot",
        # Explanation: The flag is enabled when the user writes --plot.
        action="store_true",
        # Explanation: Store True when --plot appears; otherwise store False.
        help="Save one simple weight-versus-time plot for each input file.",
        # Explanation: Describe the plotting effect in the help message.
    )
    # Explanation: Finish defining the plot option.

    return parser.parse_args()
    # Explanation: Read the user's command-line text and return the resulting Namespace object.


def main() -> None:
    # Explanation: main() coordinates command-line parsing and processing of every requested file.
    """Run the command-line program."""
    # Explanation: This documentation string describes the entry point's purpose.

    arguments = parse_command_line_arguments()
    # Explanation: Read the user's input filenames and optional flags into one Namespace object.

    for input_path in arguments.input_files:
        # Explanation: Process every supplied CSV file one at a time.
        process_file(
            # Explanation: Begin the call that processes one input file.
            input_path=input_path,
            # Explanation: Pass the current CSV path by its descriptive parameter name.
            output_directory=arguments.output_directory,
            # Explanation: Pass the selected or default folder for output plots.
            create_plots=arguments.plot,
            # Explanation: Pass True or False depending on whether the user requested --plot.
        )
        # Explanation: Finish processing the current file before the loop moves to the next one.


if __name__ == "__main__":
    # Explanation: This condition is true only when the file is run directly, not when another file imports it.
    main()
    # Explanation: Start the command-line program.
