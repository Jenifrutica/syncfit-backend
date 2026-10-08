import pytest

from app.analytics.phase_graph import PhaseGraph, PhaseNode


def build_cycle() -> PhaseGraph:
    graph = PhaseGraph("day")
    graph.add_phase(PhaseNode("MENSTRUAL", 1, 5, "RECOVERY"))
    graph.add_phase(PhaseNode("FOLLICULAR", 6, 8, "STRENGTH"))
    graph.add_phase(PhaseNode("OVULATORY", 14, 3, "LOW_IMPACT"))
    graph.add_phase(PhaseNode("LUTEAL", 17, 12, "ENDURANCE"))
    graph.connect("MENSTRUAL", "FOLLICULAR")
    graph.connect("FOLLICULAR", "OVULATORY")
    graph.connect("OVULATORY", "LUTEAL")
    graph.connect("LUTEAL", "MENSTRUAL", restarts_cycle=True)
    graph.set_first("MENSTRUAL")
    return graph


def test_walk_follows_the_cycle_once():
    phases = [node.phase for node in build_cycle().walk()]
    assert phases == ["MENSTRUAL", "FOLLICULAR", "OVULATORY", "LUTEAL"]


def test_cycle_length_is_sum_of_phases():
    assert build_cycle().cycle_length() == 28


@pytest.mark.parametrize(
    "day, phase",
    [(1, "MENSTRUAL"), (5, "MENSTRUAL"), (6, "FOLLICULAR"), (15, "OVULATORY"), (28, "LUTEAL"), (30, "MENSTRUAL")],
)
def test_phase_for_day(day, phase):
    assert build_cycle().phase_for_day(day).phase == phase


def test_walk_without_first_phase_fails():
    graph = PhaseGraph("day")
    graph.add_phase(PhaseNode("MENSTRUAL", 1, 5, "RECOVERY"))
    with pytest.raises(ValueError):
        list(graph.walk())


def test_set_first_with_unknown_phase_fails():
    with pytest.raises(ValueError):
        PhaseGraph("day").set_first("LUTEAL")


def test_cycle_without_restart_edge_is_detected():
    graph = PhaseGraph("day")
    graph.add_phase(PhaseNode("A", 1, 2, "X"))
    graph.add_phase(PhaseNode("B", 3, 2, "X"))
    graph.connect("A", "B")
    graph.connect("B", "A")
    graph.set_first("A")
    with pytest.raises(ValueError):
        list(graph.walk())
