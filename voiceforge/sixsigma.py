"""
VoiceForge - Six Sigma math.

DPMO, process sigma, I-MR control limits, and Cp/Cpk capability.
No dependencies; statistics.NormalDist handles the inverse normal.
"""

import statistics
from statistics import NormalDist

OPPORTUNITIES_PER_UNIT = 6  # D1..D6 defect types from analysis.defects()
D2_CONSTANT = 1.128  # for moving ranges of size 2


def dpmo(defect_count, unit_count, opportunities=OPPORTUNITIES_PER_UNIT):
    if unit_count <= 0:
        return None
    return round(defect_count / (unit_count * opportunities) * 1_000_000, 1)


def sigma_level(dpmo_value):
    """Process sigma with the classic 1.5 sigma shift."""
    if dpmo_value is None:
        return None
    p = min(max(dpmo_value / 1_000_000, 1e-12), 1 - 1e-12)
    return round(NormalDist().inv_cdf(1 - p) + 1.5, 2)


def yield_pct(defective_units, unit_count):
    if not unit_count:
        return None
    return round((1 - defective_units / unit_count) * 100, 1)


def imr_limits(values):
    """Individuals + moving range chart limits. Returns dict."""
    vals = [v for v in values if v is not None]
    if len(vals) < 2:
        return None
    center = statistics.fmean(vals)
    mr = [abs(vals[i] - vals[i - 1]) for i in range(1, len(vals))]
    mr_bar = statistics.fmean(mr)
    sigma = mr_bar / D2_CONSTANT
    return {
        "center": round(center, 3),
        "mr_bar": round(mr_bar, 3),
        "sigma_hat": round(sigma, 3),
        "ucl": round(center + 3 * sigma, 3),
        "lcl": round(center - 3 * sigma, 3),
        "n": len(vals),
    }


def capability(values, lsl, usl):
    vals = [v for v in values if v is not None]
    if len(vals) < 3:
        return None
    mu = statistics.fmean(vals)
    sd = statistics.stdev(vals)
    if sd == 0:
        return {"cp": None, "cpk": None, "mean": mu, "sd": 0.0}
    return {
        "cp": round((usl - lsl) / (6 * sd), 2),
        "cpk": round(min(usl - mu, mu - lsl) / (3 * sd), 2),
        "mean": round(mu, 3),
        "sd": round(sd, 3),
        "lsl": lsl,
        "usl": usl,
    }


def pareto(records):
    """Defect counts by code, largest first."""
    counts = {}
    for r in records:
        for code in r.get("defects", []):
            counts[code] = counts.get(code, 0) + 1
    return sorted(cohort_items(counts), key=lambda kv: -kv[1])


def cohort_items(d):
    return list(d.items())


def summarize(records, field=None):
    """Six Sigma summary for a set of generation records."""
    total = len(records)
    defect_total = sum(len(r.get("defects", [])) for r in records)
    defective_units = sum(1 for r in records if r.get("defects"))
    d = dpmo(defect_total, total)
    latencies = [r.get("latency_s") for r in records if r.get("latency_s") is not None]
    rates = [r.get("metrics", {}).get("sec_per_100chars") for r in records]
    rates = [r for r in rates if r is not None]
    return {
        "units": total,
        "defect_opportunities": total * OPPORTUNITIES_PER_UNIT,
        "defects": defect_total,
        "defective_units": defective_units,
        "dpmo": d,
        "sigma": sigma_level(d),
        "yield_pct": yield_pct(defective_units, total),
        "pareto": pareto(records),
        "rate_chart": imr_limits(rates),
        "rate_capability": capability(rates, 3.0, 14.0) if rates else None,
        "latency_p50": round(statistics.median(latencies), 2) if latencies else None,
        "latency_p95": round(sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)], 2) if latencies else None,
    }
