from hiver_agent.escalate.rules import decide_escalation
from hiver_agent.schemas import IntentPrediction


def test_security_always_escalates():
    pred = IntentPrediction(intent="privacy_security", confidence=0.99, method="test")
    d = decide_escalation("My iPhone was stolen", pred)
    assert d.action == "escalate"
    assert d.rules_fired


def test_low_confidence_escalates():
    pred = IntentPrediction(intent="how_to", confidence=0.1, method="test")
    d = decide_escalation("maybe something about settings", pred)
    assert d.action == "escalate"
    assert any("low_confidence" in r for r in d.rules_fired)


def test_auto_handle_clear_howto():
    pred = IntentPrediction(intent="how_to", confidence=0.9, method="test")
    d = decide_escalation("How do I set up Focus modes on iPhone?", pred)
    assert d.action == "auto_handle"


def test_billing_refund_escalates():
    pred = IntentPrediction(intent="billing_subscription", confidence=0.8, method="test")
    d = decide_escalation("I need a refund for an unauthorized charge", pred)
    assert d.action == "escalate"
