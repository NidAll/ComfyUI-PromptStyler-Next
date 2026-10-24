# Security boundaries

Style packs are untrusted data, not executable plugins. Runtime validation rejects
unknown fields, duplicate keys, excessive size/depth, non-finite numeric inputs and
unsafe preview references. It does not execute code, fetch remote resources or
serve paths supplied by packs. Trusted Python adapters run as ordinary host code
and must be reviewed separately.

The HTTP sidecar is a local service, limited to loopback with strict Host/Origin
checks and bounded input. Mount its Node bridge behind HEISS's existing request
and access guards. This is not a multi-tenant or internet-facing deployment.
Prompt payloads are not logged or persisted by the engine/service; favorites are
browser-local UI state. An embedding host may have its own prompt-history policy.

For a vulnerability report, privately contact the repository maintainer through
the repository's available security reporting channel. Do not include credentials,
private prompts or exploit payloads in public issues. No reporting endpoint or
response-time commitment is invented by this document.
