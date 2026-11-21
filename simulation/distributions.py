"""Per-agent values for the game rules.

A "spread" is either a plain number (every agent gets exactly that) or a dict:

    {"dist": "uniform", "min": a, "max": b}
        anywhere between a and b.
    {"dist": "normal", "mean": m, "std": s, "limit": k, "skew": a}
        Gaussian with mean m and standard deviation s, cut off at m ± k·s
        (values outside are re-drawn). skew 0 = symmetric; > 0 leans right
        (most agents low, a few high); < 0 leans left. mean/std stay as given.
    {"dist": "tiered", "average": A, "tiers": [{"agents": 1, "share": 50}, ...]}
        Splits a total of A × (number of agents) between groups of agents:
        the first 1% of agents hold 50% of it, and so on. Tier percentages
        each add up to 100. Agents in the same tier get equal amounts.

Values are also kept inside the field's own limits (e.g. never below 0).
"""

import math

DISTRIBUTIONS = ("uniform", "normal", "tiered")
MAX_SKEW = 20
MAX_TIERS = 10
_REDRAWS = 100


def normalize(spec, name, low, high, whole=False, tiered=False):
    """Validate a spread from JSON. Returns a number or a clean dict. Raises ValueError.

    ``tiered`` says whether this field may use the tiered distribution (only
    amounts that can be shared out, like inventory and money).
    """
    if not isinstance(spec, dict):
        return _number(spec, name, low, high, whole)
    dist = spec.get("dist")
    allowed_dists = DISTRIBUTIONS if tiered else ("uniform", "normal")
    if dist not in allowed_dists:
        raise ValueError(f"{name}.dist must be one of {', '.join(allowed_dists)}")
    keys = {"uniform": {"min", "max"}, "normal": {"mean", "std", "limit", "skew"},
            "tiered": {"average", "tiers"}}[dist]
    extra = set(spec) - keys - {"dist"}
    if extra:
        raise ValueError(f"{name}: unexpected {', '.join(sorted(extra))} for a {dist} distribution")

    if dist == "uniform":
        out = {"dist": dist, "min": _number(spec.get("min"), f"{name}.min", low, high, whole),
               "max": _number(spec.get("max"), f"{name}.max", low, high, whole)}
        if out["min"] > out["max"]:
            raise ValueError(f"{name}: min can't be larger than max")
        return out
    if dist == "normal":
        return {"dist": dist,
                "mean": _number(spec.get("mean"), f"{name}.mean", low, high),
                "std": _number(spec.get("std"), f"{name}.std", 0, 1e12),
                "limit": _number(spec.get("limit", 3), f"{name}.limit", 0.1, 10),
                "skew": _number(spec.get("skew", 0), f"{name}.skew", -MAX_SKEW, MAX_SKEW)}

    tiers = spec.get("tiers")
    if not isinstance(tiers, list) or not 1 <= len(tiers) <= MAX_TIERS:
        raise ValueError(f"{name}.tiers must be a list of 1-{MAX_TIERS} tiers")
    clean = []
    for i, tier in enumerate(tiers, 1):
        if not isinstance(tier, dict) or set(tier) != {"agents", "share"}:
            raise ValueError(f"{name}: tier {i} needs 'agents' and 'share' percentages")
        clean.append({"agents": _number(tier["agents"], f"{name} tier {i} agents %", 0.001, 100),
                      "share": _number(tier["share"], f"{name} tier {i} share %", 0, 100)})
    for key, label in (("agents", "agent"), ("share", "share")):
        total = sum(t[key] for t in clean)
        if abs(total - 100) > 0.01:
            raise ValueError(f"{name}: tier {label} percentages add up to {total:g}, not 100")
    return {"dist": dist, "average": _number(spec.get("average"), f"{name}.average", low, high),
            "tiers": clean}


def bounds(spec, low=-math.inf, high=math.inf):
    """The range values can fall in, intersected with the field's limits."""
    if spec["dist"] == "uniform":
        return spec["min"], spec["max"]
    if spec["dist"] == "normal":
        reach = spec["limit"] * spec["std"]
        return max(low, spec["mean"] - reach), min(high, spec["mean"] + reach)
    amounts = [tier_amount(spec, t) for t in spec["tiers"]]
    return min(amounts), max(amounts)


def tier_amount(spec, tier):
    """What one agent in ``tier`` gets: average × share% / agents%."""
    return spec["average"] * tier["share"] / tier["agents"]


def sample(spec, rng, whole=False, low=-math.inf, high=math.inf):
    """Draw one value for one agent (independently of the others)."""
    if not isinstance(spec, dict):
        return spec
    if spec["dist"] == "uniform":
        value = rng.uniform(spec["min"], spec["max"])
    elif spec["dist"] == "normal":
        value = _normal(spec, rng, low, high)
    else:  # tiered: an agent lands in a tier with probability agents%
        tier = rng.choices(spec["tiers"], weights=[t["agents"] for t in spec["tiers"]])[0]
        value = tier_amount(spec, tier)
    value = min(max(value, low), high)
    return int(round(value)) if whole else value


def allocate(spec, n, rng, whole=False, low=-math.inf, high=math.inf):
    """Values for n agents created together.

    Tiered spreads are shared out exactly (the top tier really holds its share
    of the total); everything else is n independent draws.
    """
    if not isinstance(spec, dict) or spec["dist"] != "tiered":
        return [sample(spec, rng, whole, low, high) for _ in range(n)]
    counts = _tier_counts([t["agents"] for t in spec["tiers"]], n)
    shares = [t["share"] for t in spec["tiers"]]
    # A tier with no agents (too few agents to fill it) hands its share to the next tier.
    for i, count in enumerate(counts):
        if count == 0 and shares[i]:
            j = next((k for k in range(i + 1, len(counts)) if counts[k]), None)
            j = j if j is not None else max(k for k in range(len(counts)) if counts[k])
            shares[j] += shares[i]
            shares[i] = 0
    total = spec["average"] * n
    values = []
    for count, share in zip(counts, shares):
        if count:
            values += _split(total * share / 100, count, whole)
    rng.shuffle(values)  # who ends up rich is random
    return values


def mean(spec):
    """Approximate average value (ignores cut-offs). Used for previews."""
    if not isinstance(spec, dict):
        return spec
    if spec["dist"] == "uniform":
        return (spec["min"] + spec["max"]) / 2
    return spec["average"] if spec["dist"] == "tiered" else spec["mean"]


def _tier_counts(percents, n):
    """Agents per tier: largest-remainder rounding of n × percent, and every
    tier gets at least one agent while there are enough agents to go round."""
    exact = [n * p / 100 for p in percents]
    counts = [math.floor(e) for e in exact]
    for i in sorted(range(len(exact)), key=lambda i: exact[i] - counts[i], reverse=True)[:n - sum(counts)]:
        counts[i] += 1
    for i in range(len(counts)):
        if counts[i] == 0 and n >= len(counts):
            donor = max(range(len(counts)), key=lambda k: counts[k])
            counts[donor] -= 1
            counts[i] += 1
    return counts


def _split(amount, count, whole):
    """Split ``amount`` equally between ``count`` agents (whole units: exact total)."""
    if not whole:
        return [amount / count] * count
    total = int(round(amount))
    base, extra = divmod(total, count)
    return [base + 1] * extra + [base] * (count - extra)


def _normal(spec, rng, low, high):
    lo, hi = bounds(spec, low, high)
    if spec["std"] == 0 or lo >= hi:
        return min(max(spec["mean"], lo), hi)
    draw = (lambda: _skew_normal(rng, spec["skew"])) if spec["skew"] else (lambda: rng.gauss(0, 1))
    for _ in range(_REDRAWS):
        value = spec["mean"] + spec["std"] * draw()
        if lo <= value <= hi:
            return value
    return min(max(spec["mean"], lo), hi)


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
