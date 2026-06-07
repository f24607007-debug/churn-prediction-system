import time

from backend.chatbot.services.faq_matcher import get_response_for_intent

def test_faq_lookup_performance():
    """Benchmarks 1000 FAQ lookups to ensure that the caching is active and fast."""
    start_time = time.perf_counter()
    
    # Run lookup 1000 times
    for _ in range(1000):
        res = get_response_for_intent("refund_policy")
        assert res == "You can request a refund within 30 days."

    duration = time.perf_counter() - start_time
    print(f"\n1000 FAQ lookups completed in: {duration:.6f} seconds")
    
    # 1000 cached in-memory reads should easily execute in under 0.1 seconds
    assert duration < 0.1, f"FAQ lookups took too long: {duration:.4f}s (potential cache miss)"
