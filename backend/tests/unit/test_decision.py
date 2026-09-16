from app.modules.access_control.service import GateDecisionService


def test_barrier_open_for_allow():
    assert GateDecisionService.barrier_action_for("ALLOW") == "OPEN"


def test_barrier_open_for_warning():
    assert GateDecisionService.barrier_action_for("ALLOW_WITH_WARNING") == "OPEN"


def test_barrier_open_for_offline_allow():
    assert GateDecisionService.barrier_action_for("OFFLINE_ALLOW") == "OPEN"


def test_barrier_closed_for_deny():
    assert GateDecisionService.barrier_action_for("DENY") == "KEEP_CLOSED"


def test_barrier_closed_for_unknown():
    assert GateDecisionService.barrier_action_for("UNKNOWN_PLATE") == "KEEP_CLOSED"


def test_barrier_closed_for_approval():
    assert GateDecisionService.barrier_action_for("REQUIRE_OPERATOR_APPROVAL") == "KEEP_CLOSED"