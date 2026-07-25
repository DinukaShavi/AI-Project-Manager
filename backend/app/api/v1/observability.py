from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
from app.core.observability import get_observability_manager

router = APIRouter(prefix="/observability", tags=["Observability & Distributed Tracing"])

class InjectSpanRequest(BaseModel):
    name: str # e.g. api_latency_ms, tool_call_latency_ms, llm_latency_ms
    duration_ms: float
    correlation_id: Optional[str] = None
    attributes: Optional[Dict[str, Any]] = None

@router.get("/traces")
async def export_open_telemetry_traces():
    """Export collected OpenTelemetry JSON span trace records for Jaeger / Zipkin."""
    obs = get_observability_manager()
    traces = obs.export_traces()
    return {
        "total_traces": len(traces),
        "spans": traces
    }

@router.get("/metrics")
async def export_prometheus_metrics():
    """Export aggregated telemetry metrics summary for Prometheus scraping endpoints."""
    obs = get_observability_manager()
    return obs.get_metrics_summary()

@router.post("/spans", status_code=status.HTTP_201_CREATED)
async def inject_custom_span(payload: InjectSpanRequest):
    """Inject a custom span trace into the observability engine."""
    obs = get_observability_manager()
    ctx = obs.create_trace_context(correlation_id=payload.correlation_id)
    span = obs.start_span(name=payload.name, trace_context=ctx, attributes=payload.attributes)
    
    # Simulate duration
    import time
    span.start_time = time.time() - (payload.duration_ms / 1000.0)
    completed_span = obs.end_span(span, status_code="OK")

    return {
        "message": "Span recorded successfully.",
        "traceparent": completed_span.trace_context.traceparent,
        "tracestate": completed_span.trace_context.tracestate,
        "correlation_id": completed_span.trace_context.correlation_id,
        "duration_ms": completed_span.duration_ms
    }
