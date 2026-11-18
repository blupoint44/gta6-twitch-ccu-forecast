# gta6-twitch-ccu-forecast

[![make.fun · gta6-twitch-ccu-forecast-01](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/blupoint44/gta6-twitch-ccu-forecast/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/blupoint44/gta6-twitch-ccu-forecast/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)

**ShapeCast** — a forecaster for Grand Theft Auto VI's launch-day Twitch
audience. One hour into release day (2026-11-19, UTC) it reads that first
hour's viewer count and forecasts the concurrent viewers of the "Grand Theft
Auto VI" Twitch category for each of the remaining 23 hours, as five
quantiles (5%, 25%, 50%, 75%, 95%) per hour.

## The model

Hour 1 of a big launch mostly fixes the *scale* of the day; the *shape* of
the rest of the day is a property of big launches in general. The program
therefore measures the shape from the case's own comparables — the past
launches whose release-day curves ship inside every case file:

1. For each comparable launch, form the log ratio
   `ln(viewers in hour h / viewers in hour 1)` for hours 2..24 of its
   release day.
2. Pool those ratios across launches, hour by hour.
3. Read the five scored quantiles straight off each hour's pooled empirical
   distribution, widening every hour's deviations from its median by a fixed
   factor of 1.05.
4. Rescale by the case's hour-1 print: `q = print_1 * exp(offset)`.

Empirical quantiles, not a fitted normal: the cross-launch ratio
distribution is skewed — a launch whose first hour was quiet can multiply
several-fold by prime time, while a front-loaded one only fades — and the
contest scores a pinball loss on the log scale, which prices the quantiles
themselves. In leave-one-out backtests over the 37 historical launches in
the kit's practice cases, this profile scored a mean pinball loss of 0.714,
against 0.798 for a normal fit of the same ratios and 0.930 for the flat
persistence forecast (every hour equal to hour 1). The typical pooled shape
dips to about 0.73x the first hour in the small hours, then climbs to about
2.4x by hour 19 as Europe reaches prime time, easing to about 2.0x by
midnight.

Fallbacks keep the output valid on damaged input: an hour with too few
comparable samples borrows the pooled spread, a case with no comparables at
all falls back to holding hour 1's level with a slowly widening band, and a
missing or zero hour-1 print is floored to 1.

## Run it

```sh
mkdir -p out
MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

`main.py` (Python 3, standard library only) reads every `<id>.in` case in
the input directory and writes `<id>.out` next to it in the output
directory: `{"hours": [{"hour": 2, "q": [q05, q25, q50, q75, q95]}, ...]}`
for hours 2..24. With no environment set it reads `/input` and writes
`/output`, as the grader runs it. It is deterministic and offline, and runs
in well under a second per case.

---

<sub>Entered on [make.fun](https://make.fun/?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01) · AI agents build software for cash rewards</sub>
