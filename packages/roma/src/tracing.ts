/**
 * OpenTelemetry Tracing Setup for ROMA
 *
 * Configures distributed tracing and metrics export to Honeycomb
 */
import { NodeSDK } from '@opentelemetry/sdk-node';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http';
import { OTLPMetricExporter } from '@opentelemetry/exporter-metrics-otlp-http';
import { Resource } from '@opentelemetry/resources';
import { ATTR_SERVICE_NAME, ATTR_SERVICE_VERSION } from '@opentelemetry/semantic-conventions';
import { trace, metrics, Span, SpanStatusCode } from '@opentelemetry/api';

let sdk: NodeSDK | null = null;
let isInitialized = false;

/**
 * Initialize OpenTelemetry SDK with Honeycomb configuration
 */
export function initializeTracing(): void {
  if (isInitialized) {
    return;
  }

  const honeycombApiKey = process.env.HONEYCOMB_API_KEY;
  const honeycombDataset = process.env.HONEYCOMB_DATASET || 'roma';
  const serviceName = process.env.OTEL_SERVICE_NAME || 'roma-builder';
  const serviceVersion = process.env.OTEL_SERVICE_VERSION || '0.1.0';

  // If no Honeycomb API key, skip initialization (graceful degradation)
  if (!honeycombApiKey) {
    console.warn('[Tracing] HONEYCOMB_API_KEY not set. Tracing disabled.');
    isInitialized = true;
    return;
  }

  const resource = new Resource({
    [ATTR_SERVICE_NAME]: serviceName,
    [ATTR_SERVICE_VERSION]: serviceVersion,
  });

  const traceExporter = new OTLPTraceExporter({
    url: 'https://api.honeycomb.io/v1/traces',
    headers: {
      'x-honeycomb-team': honeycombApiKey,
      'x-honeycomb-dataset': honeycombDataset,
    },
  });

  const metricExporter = new OTLPMetricExporter({
    url: 'https://api.honeycomb.io/v1/metrics',
    headers: {
      'x-honeycomb-team': honeycombApiKey,
      'x-honeycomb-dataset': honeycombDataset,
    },
  });

  sdk = new NodeSDK({
    resource,
    traceExporter,
    metricReader: {
      exporter: metricExporter,
    } as any,
  });

  sdk.start();
  isInitialized = true;

  console.log(`[Tracing] OpenTelemetry initialized for Honeycomb (dataset: ${honeycombDataset})`);

  // Graceful shutdown on process exit
  process.on('SIGTERM', () => {
    sdk?.shutdown()
      .then(() => console.log('[Tracing] SDK shut down successfully'))
      .catch((error) => console.error('[Tracing] Error shutting down SDK', error));
  });
}

/**
 * Get the global tracer instance
 */
export function getTracer(name: string = 'roma-core') {
  return trace.getTracer(name);
}

/**
 * Get the global meter instance for metrics
 */
export function getMeter(name: string = 'roma-core') {
  return metrics.getMeter(name);
}

/**
 * Start a new span with common attributes
 */
export function startSpan(
  name: string,
  attributes: Record<string, string | number | boolean> = {}
): Span {
  const tracer = getTracer();
  return tracer.startSpan(name, {
    attributes,
  });
}

/**
 * Execute a function within a span, automatically handling errors and completion
 */
export async function withSpan<T>(
  name: string,
  attributes: Record<string, string | number | boolean>,
  fn: (span: Span) => Promise<T>
): Promise<T> {
  const span = startSpan(name, attributes);

  try {
    const result = await fn(span);
    span.setStatus({ code: SpanStatusCode.OK });
    return result;
  } catch (error) {
    span.setStatus({
      code: SpanStatusCode.ERROR,
      message: error instanceof Error ? error.message : String(error),
    });
    span.recordException(error as Error);
    throw error;
  } finally {
    span.end();
  }
}

/**
 * Shutdown the SDK (for testing or graceful shutdown)
 */
export async function shutdownTracing(): Promise<void> {
  if (sdk) {
    await sdk.shutdown();
    sdk = null;
    isInitialized = false;
  }
}
