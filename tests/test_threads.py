from hiver_agent.data.threads import build_threads, customer_message_text, resolution_text


def test_build_threads_orders_and_extracts():
    raw = [
        {
            "message_id": "2",
            "thread_id": "T1",
            "author": "AppleSupport",
            "role": "agent",
            "text": "Try resetting network settings.",
            "created_at": "2024-01-01T12:05:00Z",
            "intent": "connectivity",
        },
        {
            "message_id": "1",
            "thread_id": "T1",
            "author": "user1",
            "role": "customer",
            "text": "Wi-Fi keeps dropping on my iPhone.",
            "created_at": "2024-01-01T12:00:00Z",
            "intent": "connectivity",
        },
        {
            "message_id": "3",
            "thread_id": "T2",
            "author": "user2",
            "text": "How do I take a screenshot?",
            "created_at": "2024-01-01T13:00:00Z",
            "intent": "how_to",
        },
    ]
    threads = build_threads(raw)
    assert len(threads) == 2
    t1 = threads[0]
    assert t1.thread_id == "T1"
    assert t1.messages[0].message_id == "1"
    assert "Wi-Fi" in t1.customer_text
    assert "resetting" in t1.resolution_text
    assert t1.intent == "connectivity"


def test_customer_and_resolution_helpers():
    from hiver_agent.schemas import Message

    msgs = [
        Message(
            message_id="a",
            thread_id="t",
            author="u",
            role="customer",
            text="Hello",
            created_at="t0",
        ),
        Message(
            message_id="b",
            thread_id="t",
            author="AppleSupport",
            role="agent",
            text="Hi there",
            created_at="t1",
        ),
    ]
    assert customer_message_text(msgs) == "Hello"
    assert resolution_text(msgs) == "Hi there"
