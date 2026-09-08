from typing import Any

from .entity_metrics import rate


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * q
    lower = int(index)
    return ordered[lower] + (ordered[min(lower + 1, len(ordered) - 1)] - ordered[lower]) * (
        index - lower
    )


def operational(events: list[dict[str, Any]]) -> dict[str, Any]:
    fresh = [e for e in events if not e["cache_hit"]]
    latencies = [e["latency_seconds"] for e in fresh]
    attempts = sum(e["attempts"] for e in fresh)
    return {
        "logical_calls_n": len(events),
        "uncached_logical_calls_n": len(fresh),
        "api_requests_n": sum(e["attempts"] for e in fresh if e["provider"] != "mock"),
        "mock_invocations_n": sum(e["attempts"] for e in fresh if e["provider"] == "mock"),
        "cache_hit_rate": rate(len(events) - len(fresh), len(events)),
        "mean_latency_seconds": rate(sum(latencies), len(latencies)),
        "p50_latency_seconds": {"value": percentile(latencies, 0.5), "n": len(latencies)},
        "p95_latency_seconds": {"value": percentile(latencies, 0.95), "n": len(latencies)},
        "input_tokens": {"total": sum(e["input_tokens"] for e in fresh), "n": len(fresh)},
        "output_tokens": {"total": sum(e["output_tokens"] for e in fresh), "n": len(fresh)},
        "estimated_usd": {"total": sum(e["estimated_usd"] for e in fresh), "n": len(fresh)},
        "reserved_usd": {"total": sum(e.get("reserved_usd", 0) for e in fresh), "n": len(fresh)},
        "unknown_usage_calls": sum(not e["usage_known"] for e in fresh),
        "retry_rate": rate(sum(e["retries"] for e in fresh), attempts),
        "failure_rate": rate(sum(e["failure"] is not None for e in fresh), len(fresh)),
        "valid_json_rate": rate(sum(e.get("json_valid", False) for e in fresh), len(fresh)),
        "schema_valid_rate": rate(sum(e["schema_valid"] for e in fresh), len(fresh)),
    }
