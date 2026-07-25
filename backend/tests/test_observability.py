import asyncio
import time
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.observability import (
    get_observability_manager,
    ObservabilityManager,
    TraceContext,
    Span
)

async def test_observability_flow():
    print("Initializing OpenTelemetry Distributed Tracing & Observability validation tests...")
    obs = get_observability_manager()

    # 1. Test Trace Context W3C Header Construction
    print("\nTest 1: Testing W3C traceparent (00-{trace_id}-{span_id}-01) & tracestate propagation...")
    ctx = obs.create_trace_context()
    assert ctx.traceparent.startswith("00-")
    assert len(ctx.traceparent.split("-")) == 4
    assert "congo=" in ctx.tracestate
    print(f"SUCCESS: Trace context generated (traceparent={ctx.traceparent}).")

    # 2. Test Span Tracing and Latency Duration Calculation
    print("\nTest 2: Testing span recording across telemetry latency categories...")
    span_api = obs.start_span("api_latency_ms", trace_context=ctx, attributes={"path": "/api/v1/projects"})
    time.sleep(0.01) # 10ms delay
    obs.end_span(span_api, status_code="OK")
    assert span_api.duration_ms is not None
    assert span_api.duration_ms >= 10.0

    span_tool = obs.start_span("tool_call_latency_ms", trace_context=ctx, attributes={"tool": "github_get_pr_diff"})
    time.sleep(0.015) # 15ms delay
    obs.end_span(span_tool, status_code="OK")

    span_llm = obs.start_span("llm_latency_ms", trace_context=ctx, attributes={"model": "claude-3-5-sonnet"})
    time.sleep(0.02) # 20ms delay
    obs.end_span(span_llm, status_code="OK")

    print("SUCCESS: Spans recorded and durations computed accurately.")

    # 3. Test Jaeger Traces & Prometheus Metrics Exports
    print("\nTest 3: Testing OTel trace export and Prometheus metrics summary...")
    traces = obs.export_traces()
    assert len(traces) >= 3
    assert "traceparent" in traces[0]

    metrics = obs.get_metrics_summary()
    assert metrics["total_spans_recorded"] >= 3
    assert "api_latency_ms" in metrics["telemetry_metrics"]
    assert "p95_ms" in metrics["telemetry_metrics"]["api_latency_ms"]
    print("SUCCESS: Jaeger trace export and Prometheus metrics summary verified.")

    # 4. Test REST API Endpoints
    print("\nTest 4: Testing Observability HTTP REST API endpoints...")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # POST /api/v1/observability/spans
        res_inj = await client.post(
            "/api/v1/observability/spans",
            json={
                "name": "workflow_duration_ms",
                "duration_ms": 125.5,
                "attributes": {"workflow_id": "wf-101"}
            }
        )
        assert res_inj.status_code == 201
        assert res_inj.json()["duration_ms"] == 125.5

        # GET /api/v1/observability/traces
        res_tr = await client.get("/api/v1/observability/traces")
        assert res_tr.status_code == 200
        assert res_tr.json()["total_traces"] >= 4

        # GET /api/v1/observability/metrics
        res_met = await client.get("/api/v1/observability/metrics")
        assert res_met.status_code == 200
        assert "workflow_duration_ms" in res_met.json()["telemetry_metrics"]
        print("SUCCESS: Observability REST API endpoints verified.")

    print("\nAll OpenTelemetry Distributed Tracing & Observability System tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_observability_flow())
