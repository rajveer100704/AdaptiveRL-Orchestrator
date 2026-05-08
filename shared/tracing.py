from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.propagate import set_global_textmap
from opentelemetry.propagators.b3 import B3MultiFormat
import os

def setup_tracing(service_name: str):
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    
    # Send to Jaeger OTLP collector (default port 4317)
    otlp_exporter = OTLPSpanExporter(endpoint="http://jaeger:4317", insecure=True)
    processor = BatchSpanProcessor(otlp_exporter)
    provider.add_span_processor(processor)
    
    trace.set_tracer_provider(provider)
    
    # Use B3 propagation for multi-hop async tracing
    set_global_textmap(B3MultiFormat())
    
    return trace.get_tracer(service_name)

tracer = None
def get_tracer(service_name: str):
    global tracer
    if tracer is None:
        tracer = setup_tracing(service_name)
    return tracer
