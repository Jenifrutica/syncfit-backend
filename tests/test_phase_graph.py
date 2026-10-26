import pytest

from app.analytics.phase_graph import (
    PhaseGraph,
    PhaseNode,
    build_cycle_graph,
    build_gestation_graph,
)


def test_rejects_duplicate_phase_and_unknown_edges():
    graph = PhaseGraph("day")
    graph.add_phase(PhaseNode("A", 1, 3, "STRENGTH"))
    with pytest.raises(ValueError):
        graph.add_phase(PhaseNode("A", 4, 3, "STRENGTH"))
    with pytest.raises(ValueError):
        graph.connect("A", "B")


def test_each_phase_has_a_single_next_phase():
    graph = PhaseGraph("day")
    graph.add_phase(PhaseNode("A", 1, 3, "STRENGTH"))
    graph.add_phase(PhaseNode("B", 4, 3, "STRENGTH"))
    graph.add_phase(PhaseNode("C", 7, 3, "STRENGTH"))
    graph.connect("A", "B")
    with pytest.raises(ValueError):
        graph.connect("A", "C")


@pytest.mark.parametrize(
    "day, phase",
    [(1, "MENSTRUAL"), (5, "MENSTRUAL"), (6, "FOLLICULAR"), (13, "FOLLICULAR"),
     (14, "OVULATORY"), (16, "OVULATORY"), (17, "LUTEAL"), (28, "LUTEAL"), (40, "LUTEAL")],
)
def test_cycle_phase_for_day(day, phase):
    assert build_cycle_graph().phase_for(day).phase == phase


@pytest.mark.parametrize(
    "week, phase",
    [(1, "TRIMESTER_1"), (13, "TRIMESTER_1"), (14, "TRIMESTER_2"), (27, "TRIMESTER_2"),
     (28, "TRIMESTER_3"), (42, "TRIMESTER_3")],
)
def test_gestation_phase_for_week(week, phase):
    assert build_gestation_graph().phase_for(week).phase == phase


def test_phase_for_rejects_non_positive_position():
    with pytest.raises(ValueError):
        build_cycle_graph().phase_for(0)


def test_walk_follows_edges_once_around_the_cycle():
    assert list(build_cycle_graph().walk()) == ["MENSTRUAL", "FOLLICULAR", "OVULATORY", "LUTEAL"]
    assert list(build_cycle_graph().walk("OVULATORY")) == ["OVULATORY", "LUTEAL", "MENSTRUAL", "FOLLICULAR"]


def test_luteal_closes_the_cycle():
    transition = build_cycle_graph().next_phase("LUTEAL")
    assert transition.target == "MENSTRUAL" and transition.restarts_cycle


def test_gestation_ends_in_last_trimester():
    assert build_gestation_graph().next_phase("TRIMESTER_3") is None


def test_units_until_inside_the_same_cycle():
    graph = build_cycle_graph()
    assert graph.units_until(1, "OVULATORY") == 13
    assert graph.units_until(14, "OVULATORY") == 0
    assert graph.units_until(10, "LUTEAL") == 7


def test_units_until_wraps_into_the_next_cycle():
    graph = build_cycle_graph(28)
    assert graph.units_until(20, "MENSTRUAL") == 9
    assert graph.units_until(20, "OVULATORY") == 22


def test_units_until_unreachable_in_gestation():
    graph = build_gestation_graph()
    assert graph.units_until(5, "TRIMESTER_3") == 23
    with pytest.raises(ValueError):
        graph.units_until(30, "TRIMESTER_1")


def test_cycle_length_stretches_the_luteal_phase():
    assert build_cycle_graph(35).node("LUTEAL").length == 19
    assert build_cycle_graph(10).node("LUTEAL").length == 1
