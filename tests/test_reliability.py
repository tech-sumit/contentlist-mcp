from contentlist_mcp.reliability import CircuitBreaker, RateLimiter, guarded_call


def test_rate_limiter_allows_burst_then_blocks():
    rl = RateLimiter(rate_per_min=60, burst=3)
    # Same instant: only `burst` requests get through before the bucket empties.
    allowed = [rl.allow("client-a", now=100.0) for _ in range(5)]
    assert allowed == [True, True, True, False, False]


def test_rate_limiter_is_per_client():
    rl = RateLimiter(rate_per_min=60, burst=1)
    assert rl.allow("a", now=0.0) is True
    assert rl.allow("a", now=0.0) is False
    assert rl.allow("b", now=0.0) is True  # different client, own bucket


def test_rate_limiter_refills_over_time():
    rl = RateLimiter(rate_per_min=60, burst=1)  # 1 token/sec
    assert rl.allow("a", now=0.0) is True
    assert rl.allow("a", now=0.5) is False
    assert rl.allow("a", now=1.1) is True  # ~1s later, refilled


def test_circuit_breaker_trips_after_threshold():
    cb = CircuitBreaker("x", fail_threshold=2, reset_seconds=30.0)
    assert cb.allows(now=0.0) is True
    cb.record_failure(now=0.0)
    assert cb.allows(now=0.0) is True  # 1 failure < threshold
    cb.record_failure(now=0.0)
    assert cb.allows(now=1.0) is False  # tripped open


def test_circuit_breaker_half_open_after_cooldown_then_closes_on_success():
    cb = CircuitBreaker("x", fail_threshold=1, reset_seconds=10.0)
    cb.record_failure(now=0.0)
    assert cb.allows(now=5.0) is False   # still cooling down
    assert cb.allows(now=10.0) is True   # half-open probe allowed
    cb.record_success()
    assert cb.allows(now=10.0) is True   # closed again


async def test_guarded_call_returns_empty_and_trips_on_failure():
    cb = CircuitBreaker("x", fail_threshold=1, reset_seconds=30.0)

    async def boom():
        raise RuntimeError("backend down")

    out = await guarded_call(cb, lambda: boom())
    assert out == []
    assert cb.allows() is False  # one failure tripped it (threshold=1)


async def test_guarded_call_skips_when_open():
    cb = CircuitBreaker("x", fail_threshold=1, reset_seconds=30.0)
    cb.record_failure()
    called = False

    async def backend():
        nonlocal called
        called = True
        return [1, 2, 3]

    out = await guarded_call(cb, lambda: backend())
    assert out == []
    assert called is False  # breaker open → backend never invoked


async def test_guarded_call_passes_through_on_success():
    cb = CircuitBreaker("x", fail_threshold=2, reset_seconds=30.0)

    async def backend():
        return ["a"]

    assert await guarded_call(cb, lambda: backend()) == ["a"]
