"""What happens when a need goes unmet (rules.need_penalties_enabled).

Each need has a warning level (WARNING, 0.80) and a critical level (CRITICAL, 1.00):

    need      warning (>= 0.80)                   critical (>= 1.00)
    thirst    walks 30% slower                    death (world.check_death)
    hunger    labour capacity -30%                death
    sleep     labour capacity -30% (tired)        (agents rest from 0.5, see Rest)
    shelter   health grows twice as fast          sleep recovers 30% slower
    health    labour capacity -50% (sick days)    can't work; dies after HEALTH_DEATH_DAYS at 1.00
    energy    labour capacity -20%                shelter grows twice as fast (no heating)
    boredom   -                                   depression (Mood): slower, and labour -20%

Penalties only apply to needs that exist in the game (some good relieves them), so a game
without shelter goods doesn't punish everyone for a need nobody can meet. Lower labour
capacity is how lower productivity shows: a tired or sick worker delivers fewer units of
labour, so it earns less and its employer makes less.
"""
WARNING = 0.8
CRITICAL = 1.0
HEALTH_DEATH_DAYS = 30

LABOR_AT_WARNING = {"hunger": 0.7, "sleep": 0.7, "health": 0.5, "energy": 0.8}
DEPRESSED_LABOR = 0.8
THIRSTY_SPEED = 0.7
SLOW_SLEEP_RECOVERY = 0.7


def _on(rules, need):
    return rules.need_penalties_enabled and (need == "sleep" or need in rules.consumer_needs)


def labor_factor(agent, rules):
    """Share of its labour capacity the agent can still give."""
    if not rules.need_penalties_enabled:
        return 1.0
    if _on(rules, "health") and agent.health >= CRITICAL:
        return 0.0
    f = 1.0
    for need, factor in LABOR_AT_WARNING.items():
        if _on(rules, need) and getattr(agent, need) >= WARNING:
            f *= factor
    if agent.depressed:
        f *= DEPRESSED_LABOR
    return f


def speed_factor(agent, rules):
    return THIRSTY_SPEED if _on(rules, "thirst") and agent.thirst >= WARNING else 1.0


def growth_factor(agent, need, rules):
    """How much faster ``need`` grows because of another unmet need."""
    if need == "health" and _on(rules, "shelter") and agent.shelter >= WARNING:
        return 2.0
    if need == "shelter" and _on(rules, "energy") and agent.energy >= CRITICAL:
        return 2.0
    return 1.0


def sleep_recovery_factor(agent, rules):
    return SLOW_SLEEP_RECOVERY if _on(rules, "shelter") and agent.shelter >= CRITICAL else 1.0


def describe(agent, rules):
    """Penalties the agent suffers now, in words (for its card)."""
    out = []
    if not rules.need_penalties_enabled:
        return out
    if speed_factor(agent, rules) < 1:
        out.append("thirsty: walks 30% slower")
    for need, factor in LABOR_AT_WARNING.items():
        if _on(rules, need) and getattr(agent, need) >= WARNING and not (need == "health" and agent.health >= CRITICAL):
            out.append(f"{need}: labour -{round((1 - factor) * 100)}%")
    if _on(rules, "health") and agent.health >= CRITICAL:
        out.append(f"too sick to work ({agent.critical_health_days} of {HEALTH_DEATH_DAYS} days)")
    if growth_factor(agent, "health", rules) > 1:
        out.append("no shelter: health worsens twice as fast")
    if sleep_recovery_factor(agent, rules) < 1:
        out.append("no shelter: sleeps badly")
    if growth_factor(agent, "shelter", rules) > 1:
        out.append("no energy: shelter worsens twice as fast")
    if agent.depressed:
        out.append("depressed: labour -20%")
    return out
