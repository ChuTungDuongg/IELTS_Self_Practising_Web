"""Closed workload profiles. High is a planning envelope, never executable locally."""

import math

from benchmarks.load.safety import SafetyError

PROFILES = {
    "smoke": {"ramp": 5, "steady": 70, "drain": 10, "users": 5},
    "ramp": {"ramp": 60, "steady": 180, "drain": 30, "users": 10},
    "burst": {"ramp": 2, "steady": 45, "drain": 15, "users": 10},
    "soak": {"ramp": 30, "steady": 1800, "drain": 30, "users": 5},
    "high": {
        "ramp": 900,
        "steady": 1800,
        "drain": 300,
        "users": 5000,
        "design_only": True,
    },
}


def configured_profile(name, environment):
    result = dict(PROFILES[name])
    for field in ("ramp", "steady", "drain"):
        value = float(environment.get(f"LOAD_{field.upper()}_SECONDS", result[field]))
        if not math.isfinite(value) or not 1 <= value <= 7200:
            raise SafetyError("PROFILE_DURATION_INVALID")
        result[field] = value
    think = float(environment.get("LOAD_THINK_SCALE", "1"))
    rate = float(environment.get("LOAD_MAX_RPS_PER_USER", "0"))
    if not math.isfinite(think) or not 1 <= think <= 1000:
        raise SafetyError("THINK_SCALE_INVALID")
    if not math.isfinite(rate) or not 0 <= rate <= 100:
        raise SafetyError("RATE_CAP_INVALID")
    return dict(result, think_scale=think, max_rps_per_user=rate)
