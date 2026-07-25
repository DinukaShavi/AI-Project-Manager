import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional

@dataclass
class TraceContext:
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    span_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tracestate: str = "congo=t61rcWkgMzE,rojo=00f067aa0ba902b7"

    @property
    def traceparent(self) -> str:
        """Construct W3C Traceparent Header (00-{trace_id}-{span_id}-01)."""
        return f"00-{self.trace_id.zfill(32)}-{self.span_id.zfill(16)}-01"

@dataclass
class Span:
    name: str
    trace_context: TraceContext
    attributes: Dict[str, Any] = field(default_factory=dict)
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    duration_ms: Optional[float] = None
    status_code: str = "UNSET"

class ObservabilityManager:
    """Enterprise OpenTelemetry Distributed Tracing & Telemetry Metrics Engine."""

    def __init__(self):
        self.spans: List[Span] = []
        self.metrics_store: List[Dict[str, Any]] = []

    def create_trace_context(self, correlation_id: Optional[str] = None) -> TraceContext:
        """Initialize or propagate a W3C trace context."""
        cid = correlation_id or str(uuid.uuid4())
        return TraceContext(correlation_id=cid)

    def start_span(
        self,
        name: str,
        trace_context: Optional[TraceContext] = None,
        attributes: Optional[Dict[str, Any]] = None
    ) -> Span:
        """Start a new telemetry trace span."""
        ctx = trace_context or self.create_trace_context()
        span = Span(
            name=name,
            trace_context=ctx,
            attributes=attributes or {},
            start_time=time.time()
        )
        return span

    def end_span(self, span: Span, status_code: str = "OK") -> Span:
        """Complete a span, compute latency duration in ms, and record for export."""
        span.end_time = time.time()
        span.duration_ms = round((span.end_time - span.start_time) * 1000.0, 3)
        span.status_code = status_code
        self.spans.append(span)

        # Store in metrics aggregator
        self.metrics_store.append({
            "metric_type": span.name, # api_latency_ms, tool_call_latency_ms, llm_latency_ms, workflow_duration_ms, agent_run_duration_ms
            "duration_ms": span.duration_ms,
            "correlation_id": span.trace_context.correlation_id,
            "timestamp": span.end_time
        })
        return span

    def export_traces(self) -> List[Dict[str, Any]]:
        """Export OTel-compliant JSON span traces for Jaeger / Zipkin collectors."""
        return [
            {
                "trace_id": s.trace_context.trace_id,
                "span_id": s.trace_context.span_id,
                "parent_span_id": None,
                "name": s.name,
                "traceparent": s.trace_context.traceparent,
                "tracestate": s.trace_context.tracestate,
                "correlation_id": s.trace_context.correlation_id,
                "start_time": s.start_time,
                "end_time": s.end_time,
                "duration_ms": s.duration_ms,
                "status_code": s.status_code,
                "attributes": s.attributes
            }
            for s in self.spans
        ]

    def get_metrics_summary(self) -> Dict[str, Any]:
        """Export aggregated telemetry latency metrics for Prometheus scraping."""
        categories = ["api_latency_ms", "tool_call_latency_ms", "llm_latency_ms", "workflow_duration_ms", "agent_run_duration_ms"]
        summary = {}

        for cat in categories:
            cat_samples = [m["duration_ms"] for m in self.metrics_store if m["metric_type"] == cat]
            if not cat_samples:
                summary[cat] = {"count": 0, "avg_ms": 0.0, "max_ms": 0.0, "p95_ms": 0.0}
            else:
                cat_samples.sort()
                p95_idx = int(len(cat_samples) * 0.95)
                summary[cat] = {
                    "count": len(cat_samples),
                    "avg_ms": round(sum(cat_samples) / len(cat_samples), 2),
                    "max_ms": round(max(cat_samples), 2),
                    "p95_ms": round(cat_samples[min(p95_idx, len(cat_samples) - 1)], 2)
                }

        return {
            "total_spans_recorded": len(self.spans),
            "telemetry_metrics": summary
        }


# Singleton Instance Manager
_observability_manager_instance: Optional[ObservabilityManager] = None

def get_observability_manager() -> ObservabilityManager:
    """Get global ObservabilityManager singleton instance."""
    global _observability_manager_instance
    if _observability_manager_instance is None:
        _observability_manager_instance = ObservabilityManager()
    return _observability_manager_instance
