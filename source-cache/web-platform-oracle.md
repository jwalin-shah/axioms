# Web Platform Contracts Oracle

Source: HTTP/1.1 (RFC 7230-7235), HTTP/2 (RFC 7540), HTTP/3 (RFC 9114),
FastAPI documentation, MDN Web Docs, "High Performance Browser Networking" (Ilya Grigorik, O'Reilly 2013),
MCP Specification (Model Context Protocol, 2024-2025).

This is the web portion of Lens 3 (Platform Contracts) in the framework. Every web
framework — FastAPI, Express, Go net/http, Django, Rails — is a contract enforcement
engine. The HTTP spec, the browser, and the framework each enforce different parts of
the contract. Violating any layer = broken request, security hole, or degraded user
experience.

---

## 1. Request Lifecycle

**Principle:** Every HTTP request follows a fixed pipeline: receive, parse, route, handle,
respond. Each stage has a well-defined contract. The invariant is that every request
produces exactly one response, and every response is tied to exactly one request.

**Invariant:**
```
∀request R: ∃!response S such that:
  R enters server → parse → route → handle → S exits server
  S.status ∈ {1xx, 2xx, 3xx, 4xx, 5xx}
  S is sent exactly once, to the connection that carried R
```

**Contract details (per RFC 7230 Section 6, RFC 7231 Section 6):**

| Stage | Contract | Violation |
|---|---|---|
| **Receive** | Server reads request line (method, URI, version), headers (name: value), optional body (Content-Length or Transfer-Encoding: chunked) | Malformed request → 400 Bad Request. Chunked encoding error → 400. Header too large → 431 Request Header Fields Too Large. |
| **Parse** | Server validates HTTP version, method (allowed methods), URI (valid characters, max length), header field names (token), header values (field-content) | Invalid version → 505 HTTP Version Not Supported. Method not allowed → 405 Method Not Allowed. URI too long → 414 URI Too Long. |
| **Route** | Server maps URI + method to a handler. Exact match > prefix match > parameterized match > catch-all | No match → 404 Not Found. Ambiguous match → framework error (500). |
| **Handle** | Handler runs application logic. May read body, set headers, produce body. | Handler panics → 500 Internal Server Error. Handler writes headers twice → framework error. |
| **Respond** | Server sends status line, headers, optional body. May add headers (Date, Content-Length, Content-Type, Server). | Response sent to wrong connection → protocol violation. Response sent twice → broken pipe / write error. |

**Enforcement patterns:**

- **FastAPI/Python (Starlette):** The ASGI (Asynchronous Server Gateway Interface) spec enforces the lifecycle. The ASGI application receives `scope` (connection info), `receive` (event stream for request body), and `send` (callable for response). `send` must be called exactly once with a response event. FastAPI adds route-level validation via Pydantic models — malformed request bodies produce 422 Unprocessable Entity before the handler runs.

  ```python
  # ASGI contract: send is called exactly once
  async def app(scope, receive, send):
      # scope = {"method": "GET", "path": "/", ...}
      # body = await receive()  # bytes
      await send({"type": "http.response.start", "status": 200, "headers": [...]})
      await send({"type": "http.response.body", "body": b"..."})
  ```

- **Express/Node.js:** The Node.js HTTP server emits `request` events. Express wraps this in a middleware pipeline. The `res` object's `end()` must be called exactly once — calling it twice throws `ERR_STREAM_WRITE_AFTER_END`. Response headers are sent on first `write()` or `end()` — setting headers after that throws `ERR_HTTP_HEADERS_SENT`.

- **Go net/http:** The `http.Handler` interface is `ServeHTTP(w ResponseWriter, r *Request)`. Writing to `w` after the handler returns is a race condition. The `http.ResponseWriter`'s `WriteHeader()` must be called before `Write()` — calling it after `Write()` is silently ignored (first write implicitly sends 200).

**Inbox application:**
- FastAPI server: Starlette's ASGI lifecycle guarantees exactly-one-response. The handler must not call `send()` manually — FastAPI's route handler returns a Pydantic model, and the framework calls `send()`.
- Textual TUI: The TUI opens an HTTP connection to the server. The request lifecycle is the same, but the TUI must handle idle timeouts — a server that doesn't respond within the keep-alive timeout will close the connection, and the TUI must retry.
- MCP gateway: The gateway translates between JSON-RPC (MCP) and HTTP. An MCP `tools/call` request becomes an HTTP POST to the gateway. The gateway must produce exactly one JSON-RPC response per request.

---

## 2. Middleware Contracts

**Principle:** Middleware is a chain of functions that wrap the request handler. Each
middleware may inspect, modify, or reject the request. The invariant is the "next or
return" rule: every middleware must either call the next middleware (or handler) or
return a response. It must not do both, and it must not call next after sending
a response.

**Invariant:**
```
∀middleware M in chain C:
  M receives request R
  M must either:
    (a) call next(R) → M's post-processing receives the response
    (b) return response S directly (with status, headers, body)
  M must NOT:
    call next(R) after sending response S
    modify request after calling next(R)
    rely on ordering of middleware in the chain (unless documented)
```

**Middleware state machine (conceptual):**

```
                    ┌─────────────┐
                    │  Receive R  │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Process R  │──── Modify headers, authenticate, rate-limit
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
     ┌────────▼───┐  ┌────▼────┐  ┌────▼──────┐
     │ Call next  │  │ Return  │  │  Return   │
     │ (continue) │  │ 4xx/5xx │  │  3xx      │
     └────────┬───┘  └─────────┘  └───────────┘
              │
     ┌────────▼───┐
     │  Post-proc │── Modify response: add headers, log, wrap body
     └────────▲───┘
              │
     ┌────────┴───┐
     │  Send S    │
     └────────────┘
```

**Common middleware invariants:**

| Middleware | Invariant | Violation |
|---|---|---|
| **Auth** | ∀request R: if R lacks valid credentials, M returns 401 Unauthorized (or 403 Forbidden) and does NOT call next | Leaked authenticated endpoint |
| **Logging** | ∀request R: M logs (method, path, status, duration) after next returns. M must not block on logger. | Synchronous disk I/O in logging middleware blocks the event loop |
| **CORS** | ∀cross-origin R: M sets Access-Control-Allow-Origin before next, or returns 204 for preflight OPTIONS | Cross-origin requests fail without CORS headers |
| **Rate limit** | ∀R: if R's client exceeds limit, M returns 429 Retry-After and does NOT call next | Downstream handler runs on a request that should be rejected |
| **Error recovery** | ∀panic in handler or next: M catches it, returns 500, logs stack trace | Uncaught panic kills the process |
| **Request ID** | ∀R: M assigns unique ID (uuid, traceparent) before next, adds it to response headers | Two requests share the same ID, or ID is missing in logs |

**Enforcement patterns:**

- **FastAPI:** Middleware is an ASGI middleware: `@app.middleware("http")` wraps an `async def(request, call_next)`. The `call_next` returns a `Response`. The middleware must `await call_next(request)` exactly once. If the middleware returns early (e.g., 401), it must not call `call_next`. FastAPI's dependency injection system can also act as middleware — dependencies with `yield` run before and after the handler.

  ```python
  @app.middleware("http")
  async def auth_middleware(request: Request, call_next):
      token = request.headers.get("Authorization")
      if not token or not is_valid(token):
          return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
      response = await call_next(request)
      response.headers["X-Request-ID"] = str(uuid.uuid4())
      return response
  ```

- **Express:** Middleware is `(req, res, next)`. `next()` passes to the next middleware. `next(err)` skips to error middleware. Middleware must call `next()` or send a response — never both. Express has a special error-handling middleware signature: `(err, req, res, next)` — four parameters.

- **Go net/http:** There is no built-in middleware concept. The pattern is `func(next http.Handler) http.Handler` — a function that wraps a handler. The wrapping handler calls `next.ServeHTTP(w, r)` or writes its own response. Go's `http.ResponseWriter` is an interface — middleware can wrap it to intercept writes.

**Inbox application:**
- FastAPI server: CORS middleware for the Textual TUI client. `CORSMiddleware` from `starlette.middleware.cors` is the standard. Auth middleware for JWT token validation. Rate-limit middleware for the MCP gateway endpoints.
- MCP gateway: Request logging middleware that traces the MCP message ID through the system. Auth middleware that validates the MCP session token.
- Textual TUI: The TUI is the client, not the server. It doesn't run middleware, but it must handle the middleware's responses — 401 means re-auth, 429 means backoff, 3xx means follow redirect.

**btw-v1 application:**
- livelm API: CORS middleware for the browser client. The client is a web app, so preflight OPTIONS requests must be handled. Auth middleware for API key validation.

**Bridge application:**
- Gateway middleware: Request logging, rate limiting per client IP, auth token validation before forwarding to upstream services. The bridge gateway is the entry point for all external requests — middleware here is the enforcement boundary.

---

## 3. Async Event Loop

**Principle:** Python's `asyncio`, Node.js's libuv, and Go's goroutine scheduler are all
event-driven concurrency models. The invariant is: cooperative multitasking. A handler
must yield control back to the event loop during I/O. Blocking the event loop stalls
every other handler.

**Invariant:**
```
∀handler H:
  H must not block the event loop for more than ε (ε ≈ 1ms for interactive, 100ms for background)
  H must yield during I/O:
    Python: await asyncio.sleep(0), await asyncio.to_thread(blocking_fn)
    Node.js: await new Promise(setImmediate), worker_threads
    Go: runtime.Gosched() (but Go preempts automatically, so this is less critical)
  H must NOT use synchronous I/O in the event loop thread:
    Python: requests.get() instead of httpx.AsyncClient — BLOCKING
    Node.js: fs.readFileSync instead of fs.promises.readFile — BLOCKING
    Go: Not applicable — Go's net/http handlers already run in goroutines
```

**Event loop architectures:**

| System | Event loop | Preemption | Blocking detection |
|---|---|---|---|
| **Python asyncio** | Single-threaded, cooperative | No preemption — must `await` | `asyncio.timeout()` in 3.12+, debug mode logs slow callbacks |
| **Node.js libuv** | Single-threaded, cooperative + worker pool | No preemption for JS — must `await` | `--trace-event-categories` shows blocking, `process.blocked` events |
| **Go runtime** | M:N scheduler (goroutines on kernel threads) | Preemptive at function call edges | `runtime/pprof`, `net/http/pprof` goroutine profile shows stuck goroutines |
| **uvicorn/gunicorn** | Workers (multi-process), each with asyncio loop | Per worker: cooperative | Worker timeout → kill and restart |

**CPU-bound work handling:**

| Framework | Escaping the event loop | Pattern |
|---|---|---|
| **FastAPI** | `await asyncio.to_thread(cpu_bound_fn, arg)` | Runs in a thread pool, returns a coroutine |
| **Express** | `worker_threads` or `child_process` | Dedicated worker for CPU work, message passing |
| **Go** | Not needed — goroutines are preemptive | `go func()` runs concurrently, `runtime.GOMAXPROCS` controls parallelism |

**Invariant:**
```
∀CPU-bound operation O:
  runtime(O) > 10ms → O must run outside the event loop thread
  O must communicate result via a future/promise/channel, not shared state
  O must be cancellable via timeout/context
```

**Inbox application:**
- FastAPI server: All handlers are `async def`. Database queries use `asyncpg` or `databases` (async SQLAlchemy). HTTP calls to MCP upstream use `httpx.AsyncClient`. CPU-bound operations (e.g., JSON serialization of large payloads) use `await asyncio.to_thread()`.
- Textual TUI: Uses `httpx` for HTTP calls. The TUI's event loop is Textual's own async framework. HTTP calls must be `await`ed — blocking the TUI loop freezes the UI.
- MCP gateway: Each MCP request is an async handler. The gateway must not block on upstream MCP server calls — use `httpx.AsyncClient` with timeouts.

**btw-v1 application:**
- livelm API: Same pattern as FastAPI server. The livelm service may call an LLM provider — that's network I/O, so it's naturally async. But if the LLM provider's SDK is synchronous, it must be wrapped in `asyncio.to_thread()`.

---

## 4. Connection Lifecycle

**Principle:** HTTP connections are resources. They must be created, used, and
closed or returned to a pool. Leaked connections are resource leaks. The invariant
is: every connection either returns to the pool after use or is closed after an error.

**Invariant:**
```
∀connection C:
  C is created → used → (returned to pool ∨ closed after error)
  ¬∃C: C is created but never closed (leaked FD)
  ¬∃C: C is used after being returned to pool (use-after-free)
  timeout(C) → C is closed and removed from pool
```

**Connection states:**

```
                 ┌──────────────┐
                 │   Idle       │ ← Pooled, ready for reuse
                 └──────┬───────┘
                        │ request
                 ┌──────▼───────┐
                 │   Active     │ ← In use
                 └──────┬───────┘
                        │
              ┌─────────┼──────────┐
              │         │          │
       ┌──────▼──┐ ┌───▼───┐ ┌───▼──────┐
       │  Done   │ │Error  │ │ Timeout  │
       └────┬────┘ └───┬───┘ └────┬─────┘
            │          │          │
     ┌──────▼──────────▼──────────▼──────┐
     │   Return to pool or Close        │
     └───────────────────────────────────┘
```

**Keep-alive behavior (per HTTP/1.1 RFC 7230 Section 6.1):**

| Protocol | Multiplexing | Connection reuse | Limit |
|---|---|---|---|
| **HTTP/1.1** | No — one request at a time | Yes, via `Connection: keep-alive` (default) | Browser: 6-8 connections per origin |
| **HTTP/2** | Yes — multiple streams on one connection | Yes — single connection per origin | 100 concurrent streams per connection (recommended) |
| **HTTP/3** | Yes — QUIC streams | Yes — single connection, 0-RTT reconnect | Per-stream flow control |

**Connection pooling by framework:**

| Framework | Pool | Size | Idle timeout | Health check |
|---|---|---|---|---|
| **httpx** (Python) | `httpx.Client()` (connection pool built-in) | Default 10 | 5s default | On reuse |
| **aiohttp** (Python) | `TCPConnector` | Default 100, `limit=0` for unlimited | 30s default | Periodic |
| **Node.js http** | `http.Agent` | Default: Infinity (per origin) | `keepAliveMsecs: 1000` | None |
| **Go net/http** | `http.Transport` | `MaxIdleConnsPerHost: 2` | `IdleConnTimeout: 90s` | None (but `DialContext` handles errors) |

**Graceful shutdown (RFC 7230 Section 6.6):**

**Invariant:**
```
∀server shutdown:
  server stops accepting new connections
  server drains in-flight requests (waits for handlers to complete)
  server closes idle connections
  server closes listener
  ∀request R in-flight at shutdown: R is completed ∨ R is responded with 503 Service Unavailable
  timeout(T_drain) → remaining connections are force-closed
```

**Enforcement patterns:**

- **FastAPI/uvicorn:** `uvicorn --timeout-keep-alive 5` sets idle timeout. Graceful shutdown is handled by the ASGI server — `lifespan` events (`startup`/`shutdown`) allow the app to clean up resources.

- **Go net/http server:** `srv.Shutdown(ctx)` is the standard pattern. It waits for all active connections to complete, then closes. `srv.Close()` is the force-close. The `http.Server`'s `BaseContext` and `ConnContext` allow per-connection state.

- **Connection draining:** When the server receives a SIGTERM, it should:
  1. Set a health-check endpoint to return 503
  2. Stop accepting new connections (load balancer detects health check failure)
  3. Wait for in-flight requests to complete (with a timeout)
  4. Close idle connections
  5. Close the listener

**Inbox application:**
- FastAPI server: Use `httpx.AsyncClient` as a long-lived client for MCP upstream calls. Configure `limits=httpx.Limits(max_keepalive_connections=10, max_connections=20)`. Use `lifespan` events to create and close the client.
- Textual TUI: Use `httpx.Client()` (synchronous) or `httpx.AsyncClient()` (async). The TUI must close the client on shutdown. Use `with httpx.Client() as client:` context manager.
- MCP gateway: Connection pooling to upstream MCP servers. Each upstream server gets its own connection pool. The gateway must handle upstream server disconnection — treat it as an error and retry with backoff.

**btw-v1 application:**
- livelm API: Connection pooling to the LLM provider API. Use `httpx.AsyncClient` with `limits` and `timeout` configured. The LLM provider may have rate limits — the client must respect `Retry-After` headers and not retry blindly.

**Bridge application:**
- Gateway: Connection pooling to upstream services. Each upstream service gets its own pool. The gateway must drain connections on shutdown — the bridge is the entry point, and dropping in-flight requests means data loss.

---

## 5. Error Handling

**Principle:** Every HTTP response must communicate what went wrong. The status code
tells the category, the body tells the detail, and the headers tell the recovery
strategy. Structured errors are the contract between server and client.

**Invariant:**
```
∀error E:
  response.status ∈ {400, 401, 403, 404, 405, 409, 422, 429, 500, 502, 503, 504}
  response.body contains:
    type: string  (machine-readable error code, e.g., "rate_limit_exceeded")
    detail: string  (human-readable explanation)
    (optional) instance: string  (URI for this specific error occurrence)
  response.headers (when applicable):
    Retry-After: seconds  (for 429, 503)
    WWW-Authenticate: scheme  (for 401)
  client can parse the error and act on it without human interpretation
```

**Standard HTTP status codes for errors (RFC 7231, RFC 6585, RFC 7238):**

| Code | Name | When | Body | Retry |
|---|---|---|---|---|
| 400 | Bad Request | Malformed syntax, invalid Content-Type, missing required field | What field is invalid, what was expected | No — fix the request |
| 401 | Unauthorized | No valid credentials | Which auth scheme (Basic, Bearer, Digest) | No — provide credentials |
| 403 | Forbidden | Valid credentials, insufficient permissions | Which resource, what permission is needed | No — need different credentials |
| 404 | Not Found | Resource doesn't exist at this URI | Which resource type, what identifier | No — fix the URI |
| 405 | Method Not Allowed | URI exists but method is not supported | Which methods ARE allowed (`Allow` header) | No — use a different method |
| 409 | Conflict | Resource state conflicts (e.g., duplicate, version mismatch) | Which field conflicts, current vs. expected value | Maybe — retry with updated state |
| 422 | Unprocessable Entity | Request body is valid JSON but semantic validation fails (FastAPI's default for Pydantic validation errors) | Which field, what constraint was violated | No — fix the body |
| 429 | Too Many Requests | Rate limit exceeded | Which limit, when it resets (`Retry-After` header) | Yes — wait `Retry-After` seconds |
| 500 | Internal Server Error | Unhandled exception, unexpected state | No details in production (security) | Maybe — retry with backoff |
| 502 | Bad Gateway | Upstream server returned invalid response | Which upstream, what was received | Maybe — retry |
| 503 | Service Unavailable | Server is overloaded or down for maintenance | When to retry (`Retry-After` header) | Yes — wait `Retry-After` seconds |
| 504 | Gateway Timeout | Upstream server didn't respond in time | Which upstream, timeout duration | Maybe — retry with longer timeout |

**Error response schema (RFC 7807 Problem Details):**

```json
{
  "type": "https://example.com/errors/rate-limit-exceeded",
  "title": "Rate Limit Exceeded",
  "status": 429,
  "detail": "You have exceeded the rate limit of 100 requests per minute.",
  "instance": "/api/v1/chat/completions",
  "retry_after": 30
}
```

**Enforcement patterns:**

- **FastAPI:** `HTTPException` is the standard. FastAPI's exception handlers can be customized. Pydantic validation errors automatically produce 422 responses. Custom exception handlers for 429, 500, etc.

  ```python
  from fastapi import HTTPException, Request
  from fastapi.responses import JSONResponse

  @app.exception_handler(HTTPException)
  async def http_exception_handler(request: Request, exc: HTTPException):
      return JSONResponse(
          status_code=exc.status_code,
          content={
              "type": f"https://errors.inbox.app/{exc.status_code}",
              "detail": exc.detail,
              "instance": str(request.url),
          },
          headers=getattr(exc, "headers", None),
      )
  ```

- **Express:** Error-handling middleware with 4 parameters: `(err, req, res, next)`. Express's default error handler returns 500 with stack trace in development. Custom error classes with status codes.

- **Go net/http:** No built-in error handling. The pattern is to define an `ErrorResponse` struct and a `writeError` helper. The `http.Error` function writes a plain-text error — not structured. Custom middleware can wrap the `ResponseWriter` to intercept writes.

**Inbox application:**
- FastAPI server: Register exception handlers for all HTTP status codes. Use Problem Details (RFC 7807) format. The Textual TUI client must parse these structured errors.
- Textual TUI: Display errors to the user. A 401 means "re-authenticate." A 429 means "wait and retry." A 500 means "server is broken, try again later." The TUI must not crash on unexpected errors.
- MCP gateway: Map MCP error codes to HTTP status codes. MCP `-32603` (Internal error) → 500. MCP `-32601` (Method not found) → 404. MCP `-32602` (Invalid params) → 422.

**btw-v1 application:**
- livelm API: The LLM provider may return 429 or 503. The API must propagate these to the client or retry internally. If retrying, the API must apply backoff and jitter.

**Bridge application:**
- Gateway: All upstream errors must be mapped to consistent HTTP responses. The gateway must not leak internal error details to the client. The gateway must log the full error internally.

---

## 6. CORS and Same-Origin

**Principle:** The browser enforces the same-origin policy: a web page can only read
resources from the same origin (scheme + host + port). Cross-origin requests require
explicit server permission via CORS headers. Without CORS, the browser blocks the
response.

**Invariant:**
```
∀cross-origin HTTP request R from origin O_client to server S:
  S must respond with Access-Control-Allow-Origin header
    Value = O_client (for credentialed requests)
    Value = * (for public, non-credentialed requests)
  If R is a preflight OPTIONS request (for non-simple requests):
    S must respond with:
      Access-Control-Allow-Methods
      Access-Control-Allow-Headers
      Access-Control-Max-Age (optional, for caching)
  If R includes credentials (cookies, Authorization header):
    Access-Control-Allow-Origin must NOT be *
    Access-Control-Allow-Credentials: true
  If S does not set these headers:
    Browser blocks the response (JavaScript cannot read it)
    The request still reaches the server (it's not blocked at the network level)
```

**Same-origin definition (RFC 6454):**

| URL A | URL B | Same origin? | Reason |
|---|---|---|---|
| `https://example.com/page` | `https://example.com/api` | Yes | Same scheme, host, port |
| `https://example.com` | `http://example.com` | No | Different scheme |
| `https://example.com` | `https://api.example.com` | No | Different host |
| `https://example.com:443` | `https://example.com:8443` | No | Different port |
| `http://localhost:3000` | `http://127.0.0.1:3000` | No | Different host (DNS != IP) |

**Simple vs. preflight requests (Fetch spec):**

A request is "simple" (no preflight needed) if:
- Method is GET, HEAD, or POST
- Only CORS-safelisted headers: `Accept`, `Accept-Language`, `Content-Language`, `Content-Type` (only `application/x-www-form-urlencoded`, `multipart/form-data`, `text/plain`)
- No `ReadableStream` body

Everything else triggers a preflight OPTIONS request.

**CORS headers by role:**

| Header | Set by | Purpose | Example |
|---|---|---|---|
| `Access-Control-Allow-Origin` | Server | Which origin is allowed | `https://app.inbox.com` or `*` |
| `Access-Control-Allow-Methods` | Server (preflight) | Which HTTP methods are allowed | `GET, POST, PUT, DELETE` |
| `Access-Control-Allow-Headers` | Server (preflight) | Which custom headers are allowed | `Authorization, Content-Type, X-Request-ID` |
| `Access-Control-Allow-Credentials` | Server | Whether credentials are allowed | `true` |
| `Access-Control-Expose-Headers` | Server | Which headers the JS can read | `X-Request-ID, Retry-After` |
| `Access-Control-Max-Age` | Server | Cache the preflight result (seconds) | `86400` |
| `Access-Control-Request-Method` | Client (preflight) | Which method the actual request will use | `POST` |
| `Access-Control-Request-Headers` | Client (preflight) | Which headers the actual request will include | `authorization, content-type` |
| `Origin` | Client (every request) | Which origin initiated the request | `https://app.inbox.com` |

**Enforcement patterns:**

- **FastAPI:** `CORSMiddleware` from `starlette.middleware.cors`. Configure `allow_origins`, `allow_methods`, `allow_headers`, `allow_credentials`, `max_age`. The middleware intercepts OPTIONS requests and returns 204 with the appropriate headers.

  ```python
  app.add_middleware(
      CORSMiddleware,
      allow_origins=["https://app.inbox.com"],  # NOT "*" if credentials=True
      allow_credentials=True,
      allow_methods=["GET", "POST", "PUT", "DELETE"],
      allow_headers=["Authorization", "Content-Type"],
  )
  ```

- **Express:** `cors` npm package. Same configuration pattern.

- **Go net/http:** No built-in CORS middleware. The `rs/cors` library is the standard. Or implement manually: check `Origin` header, set `Access-Control-Allow-Origin`, handle OPTIONS.

**Inbox application:**
- FastAPI server: The Textual TUI connects from `localhost` or a specific origin. If the TUI is a web app served from a different origin, CORS must be configured. If the TUI is a desktop app (not browser), CORS doesn't apply — the app directly connects to the server.
- MCP gateway: The MCP gateway is a server-to-server interface — CORS doesn't apply. But if the gateway exposes a browser-facing endpoint, CORS must be configured.

**btw-v1 application:**
- livelm API: The browser client is a web app. CORS is critical. The client's origin is `https://app.btw.sh` (or similar). The API must allow this origin. Preflight requests must be handled for POST requests with `Authorization` headers.

---

## 7. Content Security Policy (CSP)

**Principle:** CSP is the browser's defense against XSS and data injection. It tells
the browser which sources of content are trusted. Any resource that doesn't match
a CSP directive is blocked. Violations are reported to the server.

**Invariant:**
```
∀resource load L from origin O:
  if L's type matches a CSP directive in the page's policy:
    O must match one of the allowed sources in that directive
    if O does not match: browser blocks L, sends CSP violation report to report-uri
  if L's type does not match any CSP directive:
    behavior depends on browser default (usually allowed, but unsafe)
  ∀inline script or style:
    'unsafe-inline' is set in the directive, OR
    nonce matches the server-generated nonce in the <script>/<style> tag, OR
    hash matches the script's content
```

**CSP directives (grouped by resource type):**

| Directive | Controls | Example |
|---|---|---|
| `default-src` | Fallback for all unlisted directives | `default-src 'self'` |
| `script-src` | JavaScript sources | `script-src 'self' https://cdn.example.com` |
| `style-src` | CSS sources | `style-src 'self' 'unsafe-inline'` |
| `img-src` | Image sources | `img-src 'self' data: https://*.example.com` |
| `connect-src` | XHR, fetch, WebSocket, EventSource | `connect-src 'self' https://api.inbox.com` |
| `font-src` | Font sources | `font-src 'self' https://fonts.gstatic.com` |
| `frame-src` | Iframe sources | `frame-src 'none'` |
| `media-src` | Audio/video sources | `media-src 'self'` |
| `object-src` | `<object>`, `<embed>`, `<applet>` | `object-src 'none'` (recommended) |
| `base-uri` | `<base>` tag URIs | `base-uri 'self'` |
| `form-action` | Form submission targets | `form-action 'self'` |
| `frame-ancestors` | Which origins can embed this page | `frame-ancestors 'none'` |
| `report-uri` / `report-to` | Where to send violation reports | `report-uri /csp-violation` |

**CSP sources (from most to least secure):**

| Source | Meaning | Risk |
|---|---|---|
| `'none'` | Nothing allowed | Safe but rarely useful |
| `'self'` | Same origin only | Safe — only the app's own resources |
| `https://*.example.com` | All subdomains, HTTPS only | Moderate — depends on subdomain security |
| `https://cdn.example.com` | Specific subdomain, HTTPS only | Safe — tightly scoped |
| `'nonce-abc123'` | Inline scripts with matching nonce | Safe — nonce is per-request, unguessable |
| `'sha256-...'` | Inline scripts with matching hash | Safe — hash is content-based, unguessable |
| `'unsafe-inline'` | Any inline script/style | UNSAFE — defeats XSS protection |
| `'unsafe-eval'` | `eval()`, `setTimeout(string)`, `Function()` | UNSAFE — allows arbitrary code execution |
| `*` | Any origin | UNSAFE — no restriction |
| `data:` | data: URIs | Moderate — can be used for injection |
| `blob:` | blob: URIs | Moderate — used for service workers |

**Strict CSP (nonce-based, recommended for SPAs):**

```
Content-Security-Policy:
  default-src 'self';
  script-src 'nonce-{random}' 'strict-dynamic';
  style-src 'self' 'unsafe-inline';
  img-src 'self' data:;
  connect-src 'self' https://api.inbox.com;
  base-uri 'self';
  form-action 'self';
  frame-ancestors 'none';
  report-uri /csp-violation;
```

**CSP violation report (sent to `report-uri`):**

```json
{
  "csp-report": {
    "document-uri": "https://app.inbox.com/chat",
    "referrer": "",
    "blocked-uri": "https://evil.com/script.js",
    "violated-directive": "script-src 'self'",
    "effective-directive": "script-src",
    "original-policy": "default-src 'self'; script-src 'self'; ...",
    "disposition": "enforce",
    "source-file": "https://app.inbox.com/chat",
    "line-number": 42,
    "column-number": 10,
    "status-code": 200
  }
}
```

**Enforcement patterns:**

- **FastAPI:** CSP is a response header. Set it in middleware or in the route handler. Use `Content-Security-Policy-Report-Only` for testing before enforcing.

  ```python
  @app.middleware("http")
  async def csp_middleware(request: Request, call_next):
      response = await call_next(request)
      response.headers["Content-Security-Policy"] = (
          "default-src 'self'; "
          "script-src 'self'; "
          "style-src 'self' 'unsafe-inline'; "
          "img-src 'self' data:; "
          "connect-src 'self'; "
          "report-uri /csp-violation;"
      )
      return response
  ```

- **Express:** `helmet` package sets CSP headers. `helmet.contentSecurityPolicy()` configures directives.

- **Go net/http:** Write CSP header in middleware or handler. The `github.com/unrolled/secure` package provides CSP configuration.

**Inbox application:**
- FastAPI server: If the server serves any HTML (admin panel, status page), CSP must be set. The Textual TUI is not a browser — CSP doesn't apply. But if the inbox project includes a web frontend, CSP is mandatory.
- CSP violation endpoint: `POST /csp-violation` that logs violations. Violations are XSS attempts — they must be alerted.

**btw-v1 application:**
- livelm API: If the API serves a web frontend, CSP is critical. The frontend makes `connect-src` requests to the API — the API's origin must be in `connect-src`. The frontend uses a framework (React/Vue) — use nonce-based or hash-based CSP for scripts.

---

## 8. Rate Limiting and Backpressure

**Principle:** Rate limiting protects the server from overload. Backpressure signals
the client to slow down. The invariant is that every client is limited to a maximum
request rate, and excess requests receive 429 with a Retry-After header.

**Invariant:**
```
∀client C:
  requests(C, window) ≤ rate_limit(window)
  excess requests → response 429 Too Many Requests
  Retry-After header in response: seconds until next allowed request
  server must not process the request (no side effects) if rate-limited
```

**Rate limiting algorithms:**

| Algorithm | Behavior | Best for | Trade-off |
|---|---|---|---|
| **Token bucket** | Tokens added at fixed rate, consumed per request. Burst up to bucket size. | General API rate limiting | Simple, allows bursts. Memory: 1 counter per client. |
| **Sliding window log** | Timestamped log per client. Requests older than window are expired. | Precise limits | Memory: O(N) per client (N = requests in window). |
| **Sliding window counter** | Approximate count using previous window + current window with weighted average. | High-traffic, distributed | Slightly imprecise (5-10% error). Memory: 2 counters per client. |
| **Fixed window counter** | Reset counter at window boundaries. | Simple, low-traffic | Burst at window boundary: 2x rate for a moment. |
| **GCRA (Generic Cell Rate Algorithm)** | Tracks when the next request is allowed. Used by rate-limiter-flexible. | Precise, memory-efficient | Slightly more complex. 1 counter per client. |

**Token bucket formalization:**

```
∀client C:
  bucket[C] = min(bucket[C] + refill_rate * Δt, bucket_size)
  ∀request R from C:
    if bucket[C] >= 1:
      bucket[C] -= 1
      process request
    else:
      return 429 Retry-After: (1 - bucket[C]) / refill_rate
```

**Backpressure patterns:**

| Pattern | Mechanism | When to use |
|---|---|---|
| **429 + Retry-After** | Client waits N seconds before retrying | Standard rate limiting |
| **Connection pooling** | Limited number of concurrent connections to upstream | Protecting upstream services |
| **Circuit breaker** | Fail fast when upstream is unhealthy | Preventing cascading failures |
| **Load shedding** | Randomly drop requests under extreme load | Preventing complete outage |
| **Queue with backpressure** | Bounded queue, producer blocks when full | Async processing pipelines |

**Enforcement patterns:**

- **FastAPI:** `slowapi` (built on top of Starlette's `BaseHTTPMiddleware`). Uses in-memory storage (default) or Redis for distributed rate limiting. Decorator: `@limiter.limit("100/minute")`.

  ```python
  from slowapi import Limiter, _rate_limit_exceeded_handler
  from slowapi.util import get_remote_address

  limiter = Limiter(key_func=get_remote_address)
  app.state.limiter = limiter
  app.add_exception_handler(429, _rate_limit_exceeded_handler)

  @app.get("/api/chat")
  @limiter.limit("100/minute")
  async def chat_endpoint(request: Request):
      ...
  ```

- **Express:** `express-rate-limit` package. Middleware that tracks request counts per IP. Configurable window, max, message, status code.

- **Go net/http:** `golang.org/x/time/rate` provides a token bucket implementation. `go.uber.org/ratelimit` provides a leaky bucket. The tokenrouter pattern in `pkg/tokenrouter` is the canonical orbit rate limiting implementation.

**Retry-After format (RFC 7231 Section 7.1.3):**

```
Retry-After: 120                    # seconds (integer)
Retry-After: Fri, 31 Dec 2021 23:59:59 GMT  # HTTP-date
```

**Inbox application:**
- FastAPI server: Rate limit the MCP gateway endpoints. The MCP upstream may have its own rate limits — the gateway must track downstream rate limits and apply backpressure to the client. Different rate limits for different endpoints: `/api/chat` (100/min), `/api/search` (30/min).
- Textual TUI: Must handle 429 responses. Parse `Retry-After` header. Wait before retrying. Display a "rate limited" message to the user.
- MCP gateway: Rate limit per MCP session. Track per-session request counts. Apply backpressure to the client when the upstream MCP server is rate-limited.

**btw-v1 application:**
- livelm API: The LLM provider has rate limits (tokens per minute, requests per minute). The API must track both. The tokenrouter pattern from `pkg/tokenrouter` is directly applicable.

**Bridge application:**
- Gateway: Rate limit per client IP, per API key, per endpoint. Use Redis for distributed rate limiting across bridge instances. The bridge gateway is the entry point — rate limiting here protects the entire system.

---

## 9. Idempotency

**Principle:** An idempotent operation produces the same result regardless of how
many times it is applied. PUT is idempotent by definition. POST is not. The
invariant distinguishes safe methods (read-only, no side effects) from idempotent
methods (same result every time) from non-idempotent methods (different result
each time).

**Invariant:**
```
∀method M in {GET, HEAD, OPTIONS, TRACE}:
  M is safe: f(x) has no side effects — multiple calls produce the same result,
  and no resources are modified

∀method M in {PUT, DELETE}:
  M is idempotent: f(x) = f(f(x)) — the first call creates/updates the resource,
  subsequent calls produce the same server state

∀method M in {POST, PATCH}:
  M is NOT idempotent by default:
    POST: f(x) creates a new resource — multiple calls create multiple resources
    PATCH: f(x) applies a partial update — multiple calls may produce different results
    (PATCH CAN be idempotent if the patch document is a merge patch, not a JSON patch)
```

**Idempotency key pattern (for POST endpoints that SHOULD be safe to retry):**

**Invariant:**
```
∀POST endpoint E with idempotency support:
  client sends Idempotency-Key header: unique UUID per operation
  server stores: (key, response, status) for T seconds (e.g., 24 hours)
  ∀request R with key K:
    if K is new: process R, store (K, response), return response
    if K is seen: return stored response (same status, same body) — do NOT process R
  ¬∃K: two different responses for the same K
  ¬∃K: K is accepted for a non-idempotent endpoint
```

**Enforcement patterns:**

- **FastAPI:** No built-in idempotency support. Implement as middleware. Store (key, response) in Redis with TTL. The middleware must be atomic — check-and-set to avoid race conditions.

  ```python
  @app.middleware("http")
  async def idempotency_middleware(request: Request, call_next):
      if request.method not in {"POST", "PATCH"}:
          return await call_next(request)
      key = request.headers.get("Idempotency-Key")
      if not key:
          return await call_next(request)
      # Check if key exists
      existing = await redis.get(f"idempotency:{key}")
      if existing:
          return JSONResponse(status_code=existing["status"], content=existing["body"])
      # Process and store
      response = await call_next(request)
      response_body = await response.body()
      await redis.setex(f"idempotency:{key}", 86400, {"status": response.status_code, "body": response_body})
      return response
  ```

- **Express:** `express-idempotency` package. Same pattern: Idempotency-Key header, Redis storage, TTL.

- **Go net/http:** Implement as middleware. Use sync.Map or Redis for key storage. The `http.Request`'s header access is straightforward.

**Inbox application:**
- FastAPI server: Idempotency support for chat message creation (POST /api/chat/messages). The Textual TUI sends an Idempotency-Key header to prevent duplicate messages on network retry. The server stores (key, response) for 24 hours.
- MCP gateway: MCP requests have a unique `id` field (JSON-RPC). The gateway can use the MCP message `id` as the idempotency key. If the gateway receives a duplicate MCP request (same `id`), it returns the cached response.

**btw-v1 application:**
- livelm API: LLM API calls are expensive. Idempotency keys prevent duplicate LLM calls on network retry. The client sends an Idempotency-Key header, the server deduplicates.

---

## 10. MCP Protocol (Model Context Protocol)

**Principle:** MCP is a JSON-RPC 2.0 based protocol for AI model context management.
The invariant is that every MCP message has a valid JSON-RPC 2.0 structure, and
every request produces exactly one response (or error).

**Invariant:**
```
∀MCP message M:
  M is valid JSON
  M has "jsonrpc": "2.0"
  If M is a request:
    M has "id": number | string
    M has "method": string
    M has "params": object | null (optional)
  If M is a response:
    M has "id": number | string (matching the request)
    M has "result": object | null  OR  M has "error": object
    M.error has "code": integer, "message": string, "data": any (optional)
  ¬∃M: M has both "result" and "error"
  ∀request R: ∃!response S such that S.id = R.id
```

**MCP core methods:**

| Method | Direction | Purpose | Params | Result |
|---|---|---|---|---|
| `tools/list` | Client → Server | List available tools | (none) | `{ tools: [{ name, description, inputSchema }] }` |
| `tools/call` | Client → Server | Execute a tool | `{ name, arguments }` | `{ content: [{ type, text }] }` |
| `resources/list` | Client → Server | List available resources | (none) | `{ resources: [{ uri, name, description }] }` |
| `resources/read` | Client → Server | Read a resource | `{ uri }` | `{ contents: [{ uri, text }] }` |
| `prompts/get` | Client → Server | Get a prompt template | `{ name, arguments }` | `{ messages: [{ role, content }] }` |
| `prompts/list` | Client → Server | List available prompts | (none) | `{ prompts: [{ name, description }] }` |
| `notifications/initialized` | Client → Server | Signal initialization complete | (none) | No response (notification) |

**MCP error codes (JSON-RPC standard + MCP extensions):**

| Code | Name | When |
|---|---|---|
| `-32700` | Parse Error | Invalid JSON |
| `-32600` | Invalid Request | Not a valid JSON-RPC request |
| `-32601` | Method not found | Unknown method |
| `-32602` | Invalid params | Parameters don't match schema |
| `-32603` | Internal error | Server-side error |
| `-32000` to `-32099` | Server error | MCP-specific errors |

**MCP transport layer:**

| Transport | Protocol | When to use | Notes |
|---|---|---|---|
| **stdio** | Child process stdin/stdout | Local server, tight integration | Server runs as subprocess. Messages are JSON-RPC on stdin/stdout, one per line. |
| **HTTP+SSE** | HTTP POST (client→server) + SSE (server→client) | Remote server, browser | Server sends events via SSE. Client sends POST requests. |
| **WebSocket** | Bidirectional WebSocket | Interactive, low-latency | Full duplex. Messages are JSON-RPC frames. |

**MCP session lifecycle:**

```
Client                          Server
  │                               │
  │── initialize(request) ──────→│  (protocol version, capabilities)
  │                               │
  │←── initialize(result) ───────│  (server info, capabilities)
  │                               │
  │── notifications/initialized ─→│  (no response — notification)
  │                               │
  │── tools/list ───────────────→│
  │←── tools/list(result) ───────│
  │                               │
  │── tools/call(request) ──────→│
  │←── tools/call(result) ───────│
  │                               │
  │          ...                  │
  │                               │
  │  (session ends)               │
```

**Enforcement patterns:**

- **FastAPI (MCP gateway):** The gateway accepts JSON-RPC messages over HTTP POST. Validate the JSON-RPC structure in middleware. Route to the appropriate MCP server based on the `method` field. Handle JSON-RPC batch requests (array of requests).

  ```python
  @app.post("/mcp")
  async def mcp_gateway(request: Request):
      body = await request.json()
      # Validate JSON-RPC structure
      if not isinstance(body, dict) or body.get("jsonrpc") != "2.0":
          return JSONResponse(status_code=400, content={
              "jsonrpc": "2.0", "id": None, "error": {
                  "code": -32600, "message": "Invalid Request"
              }
          })
      # Route to handler
      method = body.get("method")
      if method == "tools/list":
          result = await handle_tools_list(body.get("params"))
      elif method == "tools/call":
          result = await handle_tools_call(body.get("params"))
      else:
          return JSONResponse(content={
              "jsonrpc": "2.0", "id": body.get("id"),
              "error": {"code": -32601, "message": f"Method not found: {method}"}
          })
      return JSONResponse(content={
          "jsonrpc": "2.0", "id": body.get("id"), "result": result
      })
  ```

- **Express:** Same pattern. Parse JSON body, validate structure, delegate to handlers.

- **Go net/http:** Same pattern. `json.Decode` the request body into a `JSONRPCRequest` struct, validate, dispatch.

**MCP-specific invariants:**

```
∀MCP server S:
  S must respond to initialize with its protocol version and capabilities
  S must respond to tools/list with all tools it supports
  S must NOT call tools without a tools/call request
  S must respond to tools/call within timeout (default 60s, configurable)
  S must NOT send unsolicited responses (notifications only)
  S must close the connection cleanly on shutdown

∀MCP client C:
  C must send initialize before any other request
  C must send notifications/initialized after receiving initialize response
  C must NOT reuse message IDs across requests
  C must handle timeouts (server may not respond)
  C must handle errors (server may return error for any request)
```

**Inbox application:**
- MCP gateway: The gateway is the bridge between the inbox API and the MCP tool ecosystem. The gateway exposes an HTTP endpoint that accepts JSON-RPC messages. The gateway routes to the appropriate MCP server (stdio, HTTP+SSE, or WebSocket based on the tool's configuration).
- Textual TUI: The TUI may communicate with the MCP gateway via HTTP. The TUI constructs JSON-RPC messages and sends them to the gateway. The TUI handles JSON-RPC error responses.
- MCP server: The inbox project may expose MCP tools (e.g., `search_inbox`, `get_message`, `send_message`). These tools are registered in the MCP server's `tools/list` response. The tools are implemented as FastAPI endpoints or as standalone MCP servers.

**btw-v1 application:**
- livelm API: The API may be used as an MCP tool. The tool's `inputSchema` describes the LLM prompt parameters. The tool's handler calls the LLM provider and returns the result.

**Bridge application:**
- Gateway: The bridge gateway may expose MCP tools for system management. The MCP protocol is the interface between the AI agent and the bridge. The bridge must implement the MCP server contract (initialize, tools/list, tools/call, etc.).

---

## Framework-Specific: FastAPI/Python Applied to Inbox

The inbox project uses FastAPI as its web framework. Here are the specific contract
enforcements.

### Dependency Injection

**Invariant:**
```
∀dependency D:
  D is a callable (async def or def)
  D returns a value that is injected into the handler
  If D uses yield: code before yield runs on request, code after yield runs on response
  D's cleanup (after yield) runs even if the handler raises an exception
  D must not modify the request object (it's immutable in Starlette)
```

### Pydantic Models

**Invariant:**
```
∀Pydantic model M:
  M validates all input fields (type, constraints, defaults)
  M rejects unknown fields (model_config = {"extra": "forbid"})
  M serializes to JSON with all fields present
  ∀field F in M: F has a type annotation and a default or is required
  M must not contain sensitive fields (passwords, tokens) in string representation
```

### Router Organization

**Invariant:**
```
∀router R:
  R has a prefix (e.g., /api/chat, /api/mcp)
  R has tags for OpenAPI grouping
  R has a dependency for shared auth/validation
  R is included in the app with include_router
  ¬∃route: same path + method in two different routers
```

---

## Framework-Specific: Express/Node.js Applied to Context

### Request object mutation

**Invariant:**
```
∀Express middleware M:
  M may add properties to req (e.g., req.user, req.requestId)
  M must NOT delete properties set by other middleware
  M must NOT modify req.headers after next() is called
```

### Error propagation

**Invariant:**
```
∀error E passed to next(E):
  next(E) skips all normal middleware, goes to error middleware
  error middleware must send a response — if it also calls next(E), Express's default
  error handler returns 500 with stack trace
  ¬∃error middleware: sends response AND calls next(E)
```

---

## Framework-Specific: Go net/http Applied to Context

### ResponseWriter contract

**Invariant:**
```
∀handler H using http.ResponseWriter w:
  w.WriteHeader() must be called before w.Write()
  w.WriteHeader() can be called only once — subsequent calls are silently ignored
  w.Write() on a hijacked connection panics
  w.Header() must be modified before w.WriteHeader() or w.Write()
  After w.WriteHeader() or w.Write(), w.Header() modifications are ignored
```

### Server configuration

**Invariant:**
```
∀http.Server S:
  S.ReadTimeout is set (prevents slow-client attacks)
  S.WriteTimeout is set (prevents slow-response attacks)
  S.IdleTimeout is set (closes idle keep-alive connections)
  S.MaxHeaderBytes is set (prevents large header attacks)
  S.ErrorLog is set (prevents missed errors)
  S.Shutdown(ctx) is called on SIGTERM/SIGINT
```

---

## Summary: Contract Enforcement Layers

```
Layer                Enforced by          Violation consequence
─────────────────────────────────────────────────────────────────
HTTP protocol        Server/Client        Connection reset, 4xx/5xx
JSON-RPC structure   MCP gateway          Parse error, invalid request
Middleware chain     Framework            Wrong response, double-write
Event loop           Runtime (asyncio)    Blocked handlers, timeout
Connection pool      HTTP client          Leaked FD, connection stall
CORS                 Browser              Blocked response, no JS access
CSP                  Browser              Blocked resource, violation report
Rate limiting        Application          429 Too Many Requests
Idempotency          Application          Duplicate resource creation
Error handling       Application          Client can't parse error
```

Each layer has the same structure: a contract, an invariant, and a violation consequence.
The violation at a lower layer (HTTP protocol) is harder to recover from than a violation
at a higher layer (error handling). The goal is to catch violations at the application
layer, where they can be recovered with a structured error response.