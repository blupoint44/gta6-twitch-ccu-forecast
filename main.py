"""Launch-day Twitch audience forecaster (gta6-twitch-ccu-forecast-01).

The idea: hour 1 of a big game launch mostly fixes the *scale* of the day,
while the *shape* of the remaining 23 hours is a property of big launches in
general. So this program measures the shape from the case's own comparables.
For every past launch in the case it forms, for each hour h of that launch's
release day, the log ratio

    r = ln(viewers in hour h / viewers in hour 1),

pools those ratios across launches, and reads the five scored quantiles
straight off the pooled empirical distribution of each hour. Each hour's
deviations from its own median are widened by a fixed factor (SPREAD_BOOST)
that a leave-one-out backtest over the kit's historical launches selected.
The case's hour-1 print then rescales the shape back into viewers.

Why empirical quantiles rather than a fitted normal: the cross-launch ratio
distribution is skewed (a launch whose first hour was quiet can multiply
several-fold by prime time, while a front-loaded one only fades), and the
contest scores a pinball loss on the log scale, which prices the quantiles
themselves. In the same backtest the empirical profile beat a normal fit of
the same ratios, and both beat the flat persistence forecast.

Runs offline, standard library only, deterministic: the same case always
produces the same forecast file.
"""

import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

# Widening applied to each hour's empirical deviations from its median.
# Chosen by leave-one-out backtests over the historical launches shipped in
# the kit's practice cases (the loss curve is flat between 1.0 and 1.1).
SPREAD_BOOST = 1.05

# Below this many ratio samples an hour is not trusted on its own.
MIN_SAMPLES = 5

# Standard-normal quantiles, used only by the no-comparables fallback.
NORMAL_Z = {0.05: -1.645, 0.25: -0.674, 0.5: 0.0, 0.75: 0.674, 0.95: 1.645}
FALLBACK_SIGMA = 0.20

MAX_VIEWERS = 1e9


def parse_instant(text):
    """Parse an ISO-8601 UTC timestamp into epoch seconds (float)."""
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    moment = datetime.fromisoformat(text)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.timestamp()


def empirical_quantile(sorted_values, tau):
    """Quantile of a sample by linear interpolation between order statistics."""
    n = len(sorted_values)
    if n == 1:
        return sorted_values[0]
    position = tau * (n - 1)
    lower = int(math.floor(position))
    upper = min(lower + 1, n - 1)
    fraction = position - lower
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * fraction


def release_day_ratios(comparable):
    """Map hour -> ln(viewers_h / viewers_1) for one comparable launch's day.

    Hours are counted from the comparable's own day_start; only hours with a
    positive count take part, and hour 1 must exist for the launch to count.
    """
    try:
        start = parse_instant(comparable["day_start"])
    except (KeyError, TypeError, ValueError):
        return {}
    by_hour = {}
    for point in comparable.get("hourly") or []:
        viewers = point.get("viewers")
        if viewers is None:
            continue
        try:
            offset = parse_instant(point["from"]) - start
        except (KeyError, TypeError, ValueError):
            continue
        if 0 <= offset < 24 * 3600:
            by_hour[int(offset // 3600) + 1] = viewers
    first = by_hour.get(1)
    if not first or first <= 0:
        return {}
    return {
        hour: math.log(viewers / first)
        for hour, viewers in by_hour.items()
        if hour >= 2 and viewers > 0
    }


def build_profiles(comparables):
    """Per-hour pooled log-ratio samples, plus one global sample of them all."""
    per_hour = {hour: [] for hour in range(2, 25)}
    pooled = []
    for comparable in comparables:
        for hour, ratio in release_day_ratios(comparable).items():
            per_hour[hour].append(ratio)
            pooled.append(ratio)
    for samples in per_hour.values():
        samples.sort()
    pooled.sort()
    return per_hour, pooled


def hour_log_quantiles(hour, levels, per_hour, pooled):
    """The five log-ratio quantiles for one hour, as offsets from ln(p1)."""
    samples = per_hour.get(hour) or []
    if len(samples) >= MIN_SAMPLES:
        median = empirical_quantile(samples, 0.5)
        return [
            median + SPREAD_BOOST * (empirical_quantile(samples, tau) - median)
            for tau in levels
        ]
    if pooled:
        # Sparse hour: keep its own centre if it has one, borrow the shape of
        # every ratio pooled together for the spread around that centre.
        centre = empirical_quantile(samples, 0.5) if samples else empirical_quantile(pooled, 0.5)
        pooled_median = empirical_quantile(pooled, 0.5)
        return [
            centre + SPREAD_BOOST * (empirical_quantile(pooled, tau) - pooled_median)
            for tau in levels
        ]
    return None


def round_half_up_2dp(value):
    return math.floor(value * 100 + 0.5) / 100


def clean_row(values):
    """Round, clamp into the allowed range and force non-decreasing order."""
    row = []
    for value in values:
        value = round_half_up_2dp(min(max(value, 0.01), MAX_VIEWERS))
        if row and value < row[-1]:
            value = row[-1]
        row.append(value)
    return row


def first_hour_print(case):
    """Hour 1's print from the case's known rows, with sane fallbacks."""
    for row in case.get("known") or []:
        if row.get("hour") == 1 and row.get("viewers") is not None:
            return max(1.0, float(row["viewers"]))
    history = case.get("history_hourly") or case.get("history") or []
    seen = [p["viewers"] for p in history if p.get("viewers")]
    return max(1.0, float(seen[-1])) if seen else 1.0


def forecast_case(case):
    levels = [float(tau) for tau in case["levels"]]
    p1 = first_hour_print(case)
    per_hour, pooled = build_profiles(case.get("comparables") or [])
    rows = []
    for target in sorted(case["forecast"], key=lambda r: r["hour"]):
        hour = int(target["hour"])
        offsets = hour_log_quantiles(hour, levels, per_hour, pooled)
        if offsets is None:
            # No comparables at all: hold hour 1's level, with a spread that
            # widens like a random walk's. Insurance only; real cases ship
            # with comparables.
            sigma = FALLBACK_SIGMA * math.sqrt(hour - 1)
            offsets = [NORMAL_Z.get(tau, 0.0) * sigma for tau in levels]
        rows.append({"hour": hour, "q": clean_row([p1 * math.exp(o) for o in offsets])})
    return {"hours": rows}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        result = forecast_case(case)
        payload = json.dumps(result, separators=(",", ":")) + "\n"
        (OUTPUT_DIR / (path.stem + ".out")).write_text(payload, encoding="utf-8")


if __name__ == "__main__":
    main()
