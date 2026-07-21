# oracle/envoy — circuit breaker as resource manager

Source: Envoy source (resource_manager_impl.h, outlier_detection_impl.cc), protobuf defs
Date pulled: 2026-07-20

## Critical Finding: Not a State Machine

Envoy's circuit breaker IS NOT a state machine. No closed/open/half-open. No cooldown.
It's atomic counters with fail-fast semantics.

## How It Works

```
forall request r, forall resource t in {connections, pendingRequests, requests, retries}:
  canCreate(t) := atomically_read(count(t)) < max(t)
  if canCreate: admit, increment count
  else: reject immediately, 503, overflow_stat++
  
dec(t, amount): decrement count when request completes
  ASSERT(count >= amount) in debug builds (prevents counter underflow)
```

## Key Properties

1. **Approximate, not exact.** Atomics without cross-thread locks. Counters can briefly exceed max.
   Tradeoff: throughput over strict invariant enforcement.

2. **Per-priority isolation.** DEFAULT and HIGH have independent resource budgets.
   High-priority traffic never consumes Default's budget.

3. **Fail-fast.** No queue behind the breaker. No wait. No backoff. Rejected = 503 now.
   "It's nearly always better to fail quickly and apply back pressure downstream."

4. **Retry budget IS dynamic.** `max_retries = max(budget_percent * active_requests, min_retry_concurrency)`.
   Default: 20% budget_percent, floor 3. Prevents retry amplification.

5. **Orthogonal to health checking.** Circuit breaker and outlier detection share NO code paths.
   Independent layers: breaker protects cluster from overload, outlier detector ejects sick hosts.

## Our orbit circuitbreaker vs Envoy

| | orbit circuitbreaker | Envoy circuit breaker |
|---|---|---|
| Model | State machine (Hystrix) | Resource manager (counters) |
| State | Closed/Open/HalfOpen | No state, count vs max per request |
| Recovery | Timer + HalfOpen probe | Count decrements when request completes |
| Error tracking | RecordFailure counts errors | Not tracked (health = outlier detection) |
| Precision | Exact (mutex-protected) | Approximate (atomics, no lock) |
| Retry budget | Max 3 attempts per task | Dynamic % of active requests |

## What To Adopt

1. **Retry budget as % of active requests** — our dispatch has max 3 but no global cap
2. **Per-priority isolation** — HIGH and DEFAULT should have independent token pools
3. **Fail-fast overflow counters** — `upstream_rq_overflow` metrics that actually move