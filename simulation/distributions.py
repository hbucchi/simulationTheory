"""Per-agent random values for the game rules.

A "spread" is either a plain number (every agent gets exactly that) or a dict:

    {"dist": "uniform", "min": a, "max": b}
    {"dist": "normal",  "min": a, "max": b, "mean": m, "std": s}
    {"dist": "skewed",  "min": a, "max": b, "mean": m, "std": s, "skew": k}

"normal" is a Gaussian; "skewed" is a skew-normal with the same mean and std,
leaning right for k > 0 and left for k < 0 (k = 0 is the plain Gaussian).
Draws outside [min, max] are re-drawn (a truncated distribution), so min and
max are hard limits.
"""

import math

DISTRIBUTIONS = ("uniform", "normal", "skewed")
MAX_SKEW = 20
_REDRAWS = 100


def normalize(spec, name, low, high, whole=False):
    """Validate a spread from JSON. Returns a number or a clean dict. Raises ValueError."""
    if not isinstance(spec, dict):
        return _number(spec, name, low, high, whole)
    dist = spec.get("dist")
    if dist not in DISTRIBUTIONS:
        raise ValueError(f"{name}.dist must be one of {', '.join(DISTRIBUTIONS)}")
    allowed = {"dist", "min", "max"} | ({"mean", "std"} if dist != "uniform" else set()) | (
        {"skew"} if dist == "skewed" else set())
    extra = set(spec) - allowed
    if extra:
        raise ValueError(f"{name}: unexpected {', '.join(sorted(extra))} for a {dist} distribution")
    out = {"dist": dist,
           "min": _number(spec.get("min"), f"{name}.min", low, high, whole),
           "max": _number(spec.get("max"), f"{name}.max", low, high, whole)}
    if out["min"] > out["max"]:
        raise ValueError(f"{name}: min can't be larger than max")
    if dist != "uniform":
        out["mean"] = _number(spec.get("mean"), f"{name}.mean", out["min"], out["max"])
        out["std"] = _number(spec.get("std"), f"{name}.std", 0, 1e12)
    if dist == "skewed":
        out["skew"] = _number(spec.get("skew", 0), f"{name}.skew", -MAX_SKEW, MAX_SKEW)
    return out


def sample(spec, rng, whole=False):
    """Draw one value for one agent."""
    if not isinstance(spec, dict):
        return spec
    low, high = spec["min"], spec["max"]
    if spec["dist"] == "uniform":
        value = rng.uniform(low, high)
    else:
        draw = (lambda: _skew_normal(rng, spec["skew"])) if spec["dist"] == "skewed" else (lambda: rng.gauss(0, 1))
        value = None
        for _ in range(_REDRAWS):
            candidate = spec["mean"] + spec["std"] * draw()
            if low <= candidate <= high:
                value = candidate
                break
        if value is None:  # std is tiny compared with the gap to the limits: fall back to clamping
            value = min(max(spec["mean"], low), high)
    if whole:
        return int(min(max(round(value), math.ceil(low)), math.floor(high)))
    return value


def mean(spec):
    """Approximate average value (ignores truncation). Used for previews."""
    if not isinstance(spec, dict):
        return spec
    return (spec["min"] + spec["max"]) / 2 if spec["dist"] == "uniform" else spec["mean"]


def _skew_normal(rng, alpha):
    """Skew-normal draw, rescaled to mean 0 and std 1 so the spread's mean/std mean what they say."""
    delta = alpha / math.sqrt(1 + alpha * alpha)
    u0, v = rng.gauss(0, 1), rng.gauss(0, 1)
    u1 = delta * u0 + math.sqrt(1 - delta * delta) * v
    z = u1 if u0 >= 0 else -u1
    m = delta * math.sqrt(2 / math.pi)
    return (z - m) / math.sqrt(1 - m * m)


def _number(value, name, low, high, whole=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    if not low <= value <= high:
        raise ValueError(f"{name} must be between {low:g} and {high:g}")
    if whole:
        if value != int(value):
            raise ValueError(f"{name} must be a whole number")
        return int(value)
    return float(value)
