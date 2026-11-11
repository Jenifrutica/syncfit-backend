from app.services.ordering import _local_order


def entry(name, groups=None, compound=None, pattern=None, impact="MEDIUM", role="MAIN", blocked=False):
    item = {
        "exercise_original": name,
        "role": role,
        "impact": impact,
        "muscle_groups": groups or ["GLUTES"],
        "blocked": blocked,
    }
    if compound is not None:
        item["compound"] = compound
    if pattern is not None:
        item["movement_pattern"] = pattern
    return item


def names(entries):
    return [e["exercise_original"] for e in entries]


def test_fallback_orders_compound_unilateral_accessory():
    entries = [
        entry("curl", groups=["BICEPS"], compound=False),
        entry("bulgarian", groups=["QUADS", "GLUTES"], compound=True, pattern="lunge"),
        entry("squat", groups=["QUADS", "GLUTES", "CORE"], compound=True, pattern="squat"),
        entry("lateral-raise", groups=["SHOULDERS"], compound=False),
    ]
    assert names(_local_order(entries)) == ["squat", "bulgarian", "curl", "lateral-raise"]


def test_fallback_activation_first_and_blocked_last():
    entries = [
        entry("blocked-squat", groups=["QUADS", "GLUTES", "CORE"], blocked=True),
        entry("activation", role="ACTIVATION", groups=["GLUTES"], compound=False),
        entry("main", groups=["QUADS", "GLUTES", "CORE"], compound=True),
    ]
    assert names(_local_order(entries)) == ["activation", "main", "blocked-squat"]


def test_fallback_low_impact_first_in_ovulatory():
    entries = [
        entry("jumps", impact="HIGH", groups=["QUADS", "GLUTES"], compound=True, pattern="plyometric"),
        entry("goblet", impact="LOW", groups=["QUADS", "GLUTES"], compound=True, pattern="squat"),
    ]
    assert names(_local_order(entries, "OVULATORY")) == ["goblet", "jumps"]
