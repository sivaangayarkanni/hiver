from hiver_agent.classify.baselines import KeywordBaseline, MajorityBaseline
from hiver_agent.intents import INTENT_NAMES


def test_keyword_login():
    clf = KeywordBaseline().fit([], [])
    pred = clf.predict_one("I forgot my Apple ID password and can't sign in")
    assert pred.intent == "apple_id_login"
    assert pred.confidence > 0


def test_keyword_battery():
    clf = KeywordBaseline().fit([], [])
    pred = clf.predict_one("Battery draining super fast after update")
    assert pred.intent == "battery_performance"


def test_majority_fits():
    clf = MajorityBaseline().fit(
        ["a", "b", "c"],
        ["how_to", "how_to", "billing_subscription"],
    )
    pred = clf.predict_one("anything")
    assert pred.intent == "how_to"
    assert set(INTENT_NAMES).issuperset(pred.scores.keys())


def test_intent_names_count():
    assert 8 <= len(INTENT_NAMES) <= 12
