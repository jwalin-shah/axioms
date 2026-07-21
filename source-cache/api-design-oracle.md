# API Design Oracle

Sources:
- Fielding, Roy T. "Architectural Styles and the Design of Network-based Software Architectures" (UC Irvine, 2000) — Chapter 5: Representational State Transfer (REST)
- Masse, Mark. "REST API Design Rulebook" (O'Reilly, 2011)
- Google API Design Guide (google.aip.dev, 2017-present)
- gRPC documentation (grpc.io, 2015-present)
- JSON:API Specification (jsonapi.org, 2015)
- MCP Protocol Specification (modelcontextprotocol.io, 2024)
- Microsoft REST API Guidelines (github.com/Microsoft/api-guidelines, 2016)

This oracle covers the cross-cutting concerns of API design across REST, gRPC, and MCP protocols. The invariants apply to all of orbit's API surfaces: the internal gRPC layer, the bridge gateway, the inbox FastAPI service, and the btw-v1 livelm API.

---

## 1. Resource Modeling — Nouns Not Verbs

**Principle:** Every endpoint identifies a resource (a noun), and the HTTP method identifies the action (a verb). The URL path names what you are talking about; the method says what you want to do to it. This is the foundational constraint of REST (Fielding §5.2.1: "resource identification in requests").

**Invariant:**
```
∀endpoint E: path(E) identifies a resource (noun) ∧ method(E) identifies the action (verb)
∀method M ∈ {GET, POST, PUT, PATCH, DELETE}: M has a single, consistent semantic across all endpoints
GET /users        → list (safe, idempotent, cacheable)
POST /users       → create (neither safe nor idempotent)
GET /users/{id}   → read (safe, idempotent, cacheable)
PUT /users/{id}   → replace (idempotent)
PATCH /users/{id} → partial update (not necessarily idempotent — use with care)
DELETE /users/{id}→ delete (idempotent)
```

**Purpose:** The noun/verb separation is what makes REST scalable. A client that understands the HTTP methods can interact with any resource without out-of-band knowledge. Action URLs (`/getUsers`, `/createUser`, `/deleteUserById`) bypass this and require the client to know N different action URLs instead of 5 methods × 1 resource URL. Every verb in a URL is a design smell.

**Enforcement patterns:**

- **REST (any framework):** `POST /users` not `POST /createUser`. `GET /users/{id}/orders` not `GET /getOrdersForUser`. The path is a hierarchy of nouns; the last segment is a noun. Query parameters are filters, not actions: `GET /users?status=active` not `GET /getActiveUsers`.
- **gRPC:** Service definitions are collections of RPCs on a resource. `service UserService { rpc GetUser(GetUserRequest) returns (User); }` not `service UserActions { rpc GetUser(...); rpc CreateUser(...); rpc UpdateUser(...); }`. The protobuf package name is the namespace; the service name is the resource.
- **MCP:** Tools are named as verbs on a resource pattern. `get_user`, `create_user`, `list_users`, `delete_user` — the tool name is `{verb}_{resource}`, not `{verb}{noun}`. Resources expose `{scheme}://{path}` URIs: `user://{id}`, `order://{id}/items`.

**Framework-specific:**
- **FastAPI (Python):** `@app.get("/users")` not `@app.get("/get-users")`. Use `@router.post("/users", response_model=User)` not `@router.post("/users/create")`. Path parameters are `{user_id}` not `{action}`.
- **Express/Node.js:** `router.get('/users')` not `router.get('/getUsers')`. `router.post('/users/:id/orders')` not `router.post('/users/:id/createOrder')`.
- **Go (net/http or chi):** `r.Get("/users", listUsers)` not `r.Get("/getUsers", listUsers)`. Group by resource: `r.Route("/users", func(r chi.Router) { ... })`.

**Applications:**
- **orbit (internal gRPC):** `service DispatchService { rpc DispatchTask(DispatchTaskRequest) returns (DispatchTaskResponse); }`. The service is named after the resource. The RPC is a verb on that resource. No `DispatchService { rpc DoDispatch(...); rpc CancelDispatch(...); }` — the verb already says what it does.
- **bridge (gateway):** `POST /api/v1/spawn` spawns a new agent. `GET /api/v1/spawn/{id}` reads spawn status. `DELETE /api/v1/spawn/{id}` cancels a spawn. The resource is `spawn`; the methods are uniform. No `POST /api/v1/spawnAgent` or `POST /api/v1/cancelSpawn`.
- **inbox (FastAPI):** `GET /api/v1/conversations` lists conversations. `POST /api/v1/conversations` creates one. `GET /api/v1/conversations/{id}` reads one. `POST /api/v1/conversations/{id}/messages` creates a message sub-resource. No `POST /api/v1/getConversations` or `POST /api/v1/fetchMessages`.
- **btw-v1 (livelm API):** `POST /api/v1/chat/completions` — the resource is `chat/completions`. The method is POST because the operation is not idempotent (side effects: token consumption, state changes). The path is a noun phrase, not a verb.

---

## 2. Error Responses — Structured, Consistent, Actionable

**Principle:** Every error response has a consistent structure with a machine-readable code, a human-readable message, and optional details. The client should never need to parse an HTML body or a free-text string to determine what went wrong. Bare 500s with HTML bodies are never acceptable.

**Invariant:**
```
∀error response R: R has a JSON body with fields: error.code, error.message, error.details
∀error code C: C is a machine-readable string in UPPER_SNAKE_CASE (e.g., INVALID_ARGUMENT, NOT_FOUND, PERMISSION_DENIED, UNAUTHENTICATED, RESOURCE_EXHAUSTED, INTERNAL)
∀error message M: M is a human-readable sentence explaining what went wrong and how to fix it
∀HTTP 500 response: the body is a structured error, never an HTML stack trace
```

**Purpose:** Error handling is where most API clients are fragile. A structured error response lets the client write a generic error handler that works for all endpoints. Unstructured errors (HTML, plain text, inconsistent JSON) force every client to write per-endpoint error parsing, which is never done, which means errors are silently swallowed, which means bugs are invisible.

**Enforcement patterns:**

- **REST:** Use the HTTP status code (4xx for client errors, 5xx for server errors). The body is always JSON with the standard structure. Do not return 200 with `{"error": "..."}` — the status code IS the error class; the body is the details.
- **gRPC:** Use canonical error codes (google.rpc.Code). Map to HTTP equivalents in the gRPC-HTTP transcoding. Return a `google.rpc.Status` proto with `code`, `message`, and `details`.
- **MCP:** JSON-RPC 2.0 error responses: `{"jsonrpc": "2.0", "id": 1, "error": {"code": -32601, "message": "Method not found", "data": ...}}`. Error codes follow the JSON-RPC spec: `-32700` (parse error), `-32600` (invalid request), `-32601` (method not found), `-32602` (invalid params), `-32603` (internal error).

**Error code taxonomy (Google AIP-193):**
| Code | HTTP Status | When |
|---|---|---|
| `INVALID_ARGUMENT` | 400 | Client provided malformed input |
| `FAILED_PRECONDITION` | 400 | Request is valid but system state prevents it (e.g., trying to delete a non-empty bucket) |
| `OUT_OF_RANGE` | 400 | A value is outside the allowed range |
| `UNAUTHENTICATED` | 401 | No valid credentials |
| `PERMISSION_DENIED` | 403 | Credentials present but insufficient |
| `NOT_FOUND` | 404 | Resource doesn't exist |
| `ABORTED` | 409 | Conflict (e.g., concurrent modification) |
| `ALREADY_EXISTS` | 409 | Resource already exists |
| `RESOURCE_EXHAUSTED` | 429 | Rate limit exceeded |
| `CANCELLED` | 499 | Request cancelled by client |
| `INTERNAL` | 500 | Unexpected server error |
| `UNAVAILABLE` | 503 | Service temporarily unavailable |
| `DEADLINE_EXCEEDED` | 504 | Request timed out |

**Framework-specific:**
- **FastAPI:** Use `HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "NOT_FOUND", "message": "User not found"})`. Override the default 422 to use the canonical error format. Use `@app.exception_handler` to catch unhandled exceptions and return structured errors.
- **Express/Node.js:** Middleware that catches all errors: `app.use((err, req, res, next) => { res.status(err.status || 500).json({ error: { code: err.code || 'INTERNAL', message: err.message } }) })`. Never return the raw error object.
- **Go (net/http):** A `WriteError(w, code, message)` helper that writes the JSON body and sets the status code. Never write `http.Error(w, err.Error(), 500)` — that produces plain text.

**Applications:**
- **orbit (internal gRPC):** All RPCs return `google.rpc.Status` as the error model. `DispatchTask` returns `UNAVAILABLE` when the dispatch queue is full, `INVALID_ARGUMENT` when the task spec is malformed.
- **bridge (gateway):** All API responses use the `{"error": {"code": "...", "message": "..."}}` envelope. 500 from the backend is translated to `UNAVAILABLE` with a sanitized message (no stack traces). 401 from missing/invalid API key is `UNAUTHENTICATED` with a message explaining how to authenticate.
- **inbox (FastAPI):** Custom exception handler converts all Pydantic validation errors to `INVALID_ARGUMENT` with field-level details in the `details` array. A 500 handler catches unhandled exceptions, logs the full stack trace, and returns `INTERNAL` with a generic message.
- **btw-v1 (livelm API):** OpenAI-compatible error format: `{"error": {"code": "invalid_api_key", "message": "Incorrect API key provided", "type": "authentication_error"}}`. The `type` field is the category; `code` is the specific error.

---

## 3. Versioning — Backwards-Incompatible Changes Require a New Version

**Principle:** A change to an API is either backwards-compatible (additive, no breaking changes) or backwards-incompatible (removing fields, changing types, changing semantics). Backwards-compatible changes go in the same version. Backwards-incompatible changes require a new version. The version is part of the service contract, visible to the client.

**Invariant:**
```
∀API change C: compatible(C) → C is deployed in the current version
∀API change C: ¬compatible(C) → C requires a new version
∀version V: V is a monotonically increasing integer or date string (/v1/, /v2/)
∀client request: the version is explicit (URL prefix, header, or query param)
```

**Backwards-compatible changes (same version):**
- Adding a new endpoint
- Adding an optional field to a request
- Adding a field to a response (clients ignore unknown fields)
- Widening an input type (e.g., int32 → int64)
- Loosening validation (e.g., making a required field optional)
- Changing the implementation (same contract)

**Backwards-incompatible changes (new version):**
- Removing an endpoint
- Removing a field from a response
- Making an optional field required
- Narrowing an input type
- Tightening validation
- Changing the semantics of an existing field
- Changing the URL structure

**Enforcement patterns:**

- **URL prefix (most common):** `/v1/users`, `/v2/users`. Simple, explicit, cache-friendly. The version is visible in logs and metrics. The downside: URL structure is baked into client code and bookmarks.
- **Accept header (content negotiation):** `Accept: application/vnd.api+v1+json`. The version is in the header, not the URL. Cleaner URLs but harder to discover and debug. Used by GitHub API v3.
- **Query parameter:** `GET /users?version=1`. Fragile — easy to miss, hard to enforce in middleware. Avoid for production APIs.
- **gRPC:** Package versioning: `package api.v1;`, `package api.v2;`. The protobuf package name encodes the version. Services are `v1.UserService`, `v2.UserService`. The server serves both versions simultaneously.

**Framework-specific:**
- **FastAPI:** `APIRouter(prefix="/v1")` per version. Multiple routers, each with its own version prefix. `app.mount("/v1", v1_router)`, `app.mount("/v2", v2_router)`.
- **Express/Node.js:** `router.use('/v1', v1Router)`, `router.use('/v2', v2Router)`. Each version is a separate router module.
- **Go (chi):** `r.Route("/v1", func(r chi.Router) { ... })`, `r.Route("/v2", func(r chi.Router) { ... })`. Each version is a separate route group.

**Applications:**
- **orbit (internal gRPC):** `package orbitpb.v1;`. If the DispatchTask RPC needs a breaking change, create `package orbitpb.v2;` with `service DispatchServiceV2`. The server implements both versions. Old clients continue to use v1.
- **bridge (gateway):** `/api/v1/spawn` is the current version. When a breaking change is needed, `/api/v2/spawn` is added. The v1 endpoint is maintained for a deprecation window (documented in the response header `X-API-Deprecated: true`).
- **inbox (FastAPI):** `/api/v1/conversations`. The v1 router is in `routers/v1/`. When v2 is needed, `routers/v2/` is added. The main app mounts both.
- **btw-v1 (livelm API):** The name `btw-v1` encodes the version. The API path is `/api/v1/chat/completions`. If the API changes incompatibly, the project becomes `btw-v2` or the path becomes `/api/v2/chat/completions`.

---

## 4. Pagination — Cursor-Based Preferred, No Unbounded Lists

**Principle:** Every list endpoint must paginate its results. The response includes a token or cursor for the next page. The request includes a page size with an upper bound. No endpoint returns an unbounded result set. Cursor-based pagination is preferred over offset-based because it is stable under concurrent writes (inserting a row doesn't shift subsequent pages).

**Invariant:**
```
∀list endpoint E: response(E) includes a next_page_token field (or next cursor)
∀list endpoint E: request(E) includes a page_size field with a documented max value
∀list endpoint E: page_size in request ≤ server-defined max_page_size
∀offset-based pagination: offset + page_size may miss or duplicate rows under concurrent writes
∀cursor-based pagination: cursor is opaque to the client (usually a base64-encoded row ID or timestamp)
```

**Purpose:** Unbounded queries are a reliability risk. A list endpoint that returns all results works fine with 10 rows but crashes the server with 10 million. Pagination is a hard requirement, not a performance optimization. Cursor-based pagination is preferred because it is stable under concurrent modification — the cursor points to a specific row, not a position that can shift.

**Pagination patterns:**

- **Cursor-based (preferred):**
  ```
  Request:  GET /users?page_size=20&cursor=abc123
  Response: { "data": [...], "next_page_token": "def456", "total_size": 150 }
  ```
  The cursor is opaque — typically a base64-encoded `{id, created_at}` tuple. The server decodes it and queries `WHERE (created_at, id) > (cursor_ts, cursor_id) ORDER BY created_at, id LIMIT page_size`. The `total_size` field is optional and may be approximate (expensive to compute on large datasets).

- **Offset-based (acceptable for small datasets):**
  ```
  Request:  GET /users?page=2&page_size=20
  Response: { "data": [...], "total_pages": 8, "total_items": 150 }
  ```
  The offset is `(page - 1) * page_size`. The `total_pages` and `total_items` fields require a `COUNT(*)` query, which is expensive on large datasets. Under concurrent writes, items may be missed or duplicated between pages.

**Framework-specific:**
- **FastAPI:** `Query(page_size: int = Query(20, ge=1, le=100), cursor: str | None = None)`. The response model includes `next_page_token: str | None`. The database layer uses `cursor` for `WHERE (id) > (decoded_cursor) LIMIT page_size`.
- **Express/Node.js:** `req.query.page_size = Math.min(parseInt(req.query.page_size) || 20, 100)`. The response includes `nextPageToken`. The database layer uses `cursor` for `WHERE id > ? ORDER BY id LIMIT ?`.
- **Go (any router):** `cursor` and `pageSize` are parsed from query params. `pageSize` is clamped: `if pageSize > 100 { pageSize = 100 }`. The response struct includes `NextPageToken string`.

**Applications:**
- **orbit (internal gRPC):** `ListTasks` RPC uses cursor-based pagination. `ListTasksRequest` has `page_size` (max 100) and `page_token`. `ListTasksResponse` has `next_page_token` and `tasks`. The cursor is the task ID.
- **bridge (gateway):** `GET /api/v1/spawns` uses cursor-based pagination. The `Link` header provides `rel="next"` with the cursor URL. The response body includes `next_page_token`.
- **inbox (FastAPI):** `GET /api/v1/conversations` uses cursor-based pagination. The cursor is a base64-encoded `{updated_at, id}` tuple. `page_size` defaults to 20, max 100. The response includes `next_page_token` and `total_estimated` (approximate count from the index).
- **btw-v1 (livelm API):** Not applicable — chat completions are not a list endpoint. If a list endpoint is added (e.g., `GET /api/v1/models`), it uses cursor-based pagination with `page_size` and `after` cursor.

---

## 5. Idempotency — Safe Replay for POST and PATCH

**Principle:** An idempotency key allows a client to safely retry a POST or PATCH request without executing the operation multiple times. The server stores the (key, response) pair for a TTL and returns the stored response on replay. This is critical for network-sensitive operations where a timeout might leave the client unsure whether the request was processed.

**Invariant:**
```
∀idempotent request R (POST/PATCH with Idempotency-Key header):
  server stores (key, response) for a configured TTL
  server checks for existing key before executing the operation
  replay with same key returns the stored response, does not re-execute
  replay with different key creates a new operation
  replay with same key but different request body → 422 UNPROCESSABLE_ENTITY (key locked to the original body)
```

**Purpose:** Network failures are inevitable. A client sends a POST request, the server processes it, but the response is lost in transit. The client doesn't know whether the request succeeded. Without idempotency, the client must choose between retrying (risk of duplicate) or not retrying (risk of data loss). With idempotency, the client retries safely.

**Idempotency key lifecycle:**
1. Client generates a UUID for the request and sends it as `Idempotency-Key: uuid-here`
2. Server checks if the key exists in the idempotency store
3. If not found: execute the operation, store (key, response), return the response
4. If found: return the stored response without executing
5. After TTL (typically 24 hours): the key expires and may be purged

**Enforcement patterns:**

- **REST:** `Idempotency-Key` header on POST and PATCH. GET, PUT, DELETE are already idempotent by HTTP semantics. The idempotency store is a key-value store (Redis, in-memory cache, or database table) with TTL.
- **gRPC:** Not natively supported in the protobuf spec. Implemented as a field in the request proto: `string idempotency_key = 1;`. The server checks the key before executing.
- **MCP:** JSON-RPC request IDs serve as idempotency keys for `tools/call`. The server caches the result by request ID for a TTL. Replay with the same request ID returns the cached result.

**Framework-specific:**
- **FastAPI:** Middleware that reads `Idempotency-Key` from the header, checks a Redis cache, and either returns the cached response or passes through. The middleware must handle the race condition between the check and the store (use Redis `SETNX` or a database transaction with `ON CONFLICT DO NOTHING`).
- **Express/Node.js:** Middleware that wraps the route handler. The middleware checks the idempotency key before the handler runs and caches the response after. The key is stored in Redis with a TTL.
- **Go (any router):** Middleware that reads `Idempotency-Key` from the header, acquires a lock on the key (Redis `SETNX` or database `FOR UPDATE`), checks the cache, and either returns the cached response or passes through.

**Applications:**
- **orbit (internal gRPC):** `DispatchTask` includes an `idempotency_key` field. The dispatch server checks if the key has been processed before creating a new task. This is critical because dispatch is a network-sensitive operation — the client might timeout waiting for the response and retry.
- **bridge (gateway):** `POST /api/v1/spawn` requires an `Idempotency-Key` header. The bridge stores the (key, spawn_id) pair. If the client retries with the same key, the bridge returns the existing spawn_id instead of creating a new spawn.
- **inbox (FastAPI):** `POST /api/v1/conversations/{id}/messages` requires an `Idempotency-Key` header. This prevents duplicate messages when the client retries a failed POST. The key is stored in Redis with a 24-hour TTL.
- **btw-v1 (livelm API):** `POST /api/v1/chat/completions` does not require idempotency by default (OpenAI-compatible APIs generally don't), but the infrastructure supports it. If a client supplies an `Idempotency-Key` header, the server deduplicates the request.

---

## 6. Rate Limiting Headers — Inform the Client, Enforce the Limit

**Principle:** Every API response includes rate limit headers so the client knows its current usage and can back off proactively. When the limit is exceeded, the server returns 429 Too Many Requests with a Retry-After header. The rate limit is enforced at the gateway or middleware layer, not in individual handlers.

**Invariant:**
```
∀response R from a rate-limited endpoint:
  R includes X-RateLimit-Limit (the quota per window)
  R includes X-RateLimit-Remaining (requests remaining in the current window)
  R includes X-RateLimit-Reset (Unix timestamp when the window resets)
∀429 response: R includes Retry-After header (seconds to wait, or HTTP-date)
∀rate limit: the limit is enforced BEFORE the request reaches the handler
```

**Purpose:** Rate limiting protects the server from abuse and misconfigured clients. The headers give the client enough information to implement exponential backoff without guessing. A client that sees `X-RateLimit-Remaining: 0` knows to stop sending requests until the reset time. Without headers, the client only discovers the limit when it gets a 429, which is too late.

**Header semantics (from Google AIP-4221 and GitHub API conventions):**
| Header | Meaning | Example |
|---|---|---|
| `X-RateLimit-Limit` | Max requests per window | `X-RateLimit-Limit: 1000` |
| `X-RateLimit-Remaining` | Requests left in current window | `X-RateLimit-Remaining: 432` |
| `X-RateLimit-Reset` | Unix timestamp when window resets | `X-RateLimit-Reset: 1623456789` |
| `Retry-After` | Seconds to wait (on 429 only) | `Retry-After: 30` |

**Enforcement patterns:**

- **REST:** Gateway middleware reads the rate limit state from the token bucket or sliding window counter, sets the headers, and returns 429 when the limit is exceeded. The handler never sees the rate limit check.
- **gRPC:** Rate limiting is enforced at the interceptor level. The interceptor checks the rate limit before calling the handler. The 429 status is returned as `RESOURCE_EXHAUSTED` with a `retry_delay` in the error details.
- **MCP:** The transport layer (stdio or SSE) does not have rate limit headers. The server enforces rate limits internally and returns JSON-RPC error `-32000` (server error) with a `retry_after` field in the data.

**Framework-specific:**
- **FastAPI:** A dependency `RateLimiter` that checks the rate limit and raises `HTTPException(429)` with `Retry-After` and `X-RateLimit-*` headers. Use `@app.middleware("http")` for gateway-level enforcement.
- **Express/Node.js:** `express-rate-limit` middleware with `standardHeaders: true` and `legacyHeaders: false`. The middleware sets the `X-RateLimit-*` headers and returns 429 with `Retry-After`.
- **Go (any router):** The `tokenrouter` package in orbit already implements rate limiting. The gateway middleware calls `router.Acquire(ctx)` before dispatching to the handler. The response headers are set from the token router state.

**Applications:**
- **orbit (internal gRPC):** The `tokenrouter` in `pkg/tokenrouter` enforces rate limits for API keys. The dispatch service calls `router.Acquire(ctx)` before dispatching a task. The response includes `X-RateLimit-*` headers in the gRPC trailing metadata.
- **bridge (gateway):** The bridge enforces rate limits at the gateway level. Every response includes `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `X-RateLimit-Reset`. The rate limit is per API key, enforced by the tokenrouter.
- **inbox (FastAPI):** Rate limiting is enforced by a middleware that reads the `X-API-Key` header and checks the rate limit. The response includes the standard rate limit headers. The rate limit is per-user, per-endpoint.
- **btw-v1 (livelm API):** OpenAI-compatible rate limit headers: `X-RateLimit-Limit-Requests`, `X-RateLimit-Remaining-Requests`, `X-RateLimit-Reset-Requests`. Also `X-RateLimit-Limit-Tokens` for token-based rate limiting. 429 responses include `Retry-After`.

---

## 7. gRPC Patterns — Protobuf Contracts, Deadlines, Streaming

**Principle:** gRPC uses protobuf service definitions as the contract between client and server. Every RPC must have a deadline set by the client, and the server must check `ctx.Err()` in long-running operations. Streaming is a first-class concept: unary (request-response), server-streaming (single request, stream of responses), client-streaming (stream of requests, single response), and bidirectional streaming (stream of requests and responses).

**Invariant:**
```
∀RPC R: client sets a deadline (context.WithTimeout or context.WithDeadline)
∀RPC R: server checks ctx.Err() at least once per iteration in streaming RPCs
∀RPC R: server does not hold a mutex across a blocking I/O call
∀streaming RPC S: server handles client cancellation (ctx.Done()) within the stream loop
∀streaming RPC S: server closes the stream when the iteration is complete
```

**Purpose:** gRPC without deadlines is a memory leak. A client that crashes without a deadline leaves the server running the RPC indefinitely. The server must check the context to detect cancellation. Without `ctx.Err()` checks, a streaming RPC can run forever even after the client disconnects. Holding a mutex across a blocking I/O call (network, disk, channel send) causes contention that can deadlock the server.

**gRPC streaming patterns:**

- **Unary:** `rpc GetUser(GetUserRequest) returns (User);` — Simple request-response. The client sets a deadline. The server returns the response or an error.
- **Server-streaming:** `rpc ListUsers(ListUsersRequest) returns (stream User);` — The client sends one request. The server sends multiple responses. The server checks `ctx.Err()` between sends. The client calls `Recv()` in a loop until `io.EOF`.
- **Client-streaming:** `rpc SendHeartbeats(stream Heartbeat) returns (Ack);` — The client sends multiple requests. The server processes them incrementally and returns a single response. The server reads in a loop until `io.EOF`.
- **Bidirectional streaming:** `rpc Chat(stream ChatMessage) returns (stream ChatMessage);` — Both sides send and receive independently. Each side checks `ctx.Err()` in its loop. The gRPC framing handles interleaving.

**Protobuf conventions (Google AIP-121, AIP-122):**
- Request message: `{resource_name}Request` — e.g., `GetUserRequest`, `CreateUserRequest`
- Response message: `{resource_name}Response` — e.g., `GetUserResponse`, `CreateUserResponse`
- Standard fields: `name` (resource name), `parent` (parent resource), `request_id` (idempotency key)
- Fields are `snake_case` in proto, translated to `camelCase` in JSON
- Enums start with `ENUM_TYPE_UNSPECIFIED` as the zero value (required by protobuf semantics)

**Framework-specific:**
- **Go (google.golang.org/grpc):** `stream.Context().Err()` is checked in the stream loop. `defer` closes resources. `grpc.MaxRecvMsgSize` and `grpc.MaxSendMsgSize` are set on the server. Middleware is implemented as gRPC interceptors (unary and stream).
- **Python (grpc.aio):** `await context.cancel()` for cancellation. `async for` for server-streaming. `async with` for the channel. Deadline is set on the stub: `stub.GetUser(request, timeout=5)`.
- **Node.js (@grpc/grpc-js):** `call.on('cancelled', callback)` for cancellation. Streaming: `call.on('data', handler)`, `call.on('end', handler)`. Deadline is set on the call: `stub.getUser(request, { deadline: Date.now() + 5000 })`.

**Applications:**
- **orbit (internal gRPC):** `DispatchTask` is a unary RPC with a deadline. `WatchTask(task_id)` is a server-streaming RPC that sends status updates. The stream loop checks `ctx.Err()` between sends. The `pkg/dispatch` service sets a 30-second deadline on all RPCs.
- **bridge (gateway):** The bridge translates REST requests to gRPC calls. The gRPC call inherits the HTTP request context. The HTTP timeout is set to the gRPC deadline minus a buffer for the translation.
- **inbox (FastAPI):** Not applicable — inbox is a REST API, not gRPC. But the inbox calls gRPC services internally; those calls set deadlines.
- **btw-v1 (livelm API):** Not applicable — btw-v1 is a REST API with the OpenAI-compatible schema. If the livelm backend is gRPC, the btw-v1 server sets deadlines on all gRPC calls to the backend.

---

## 8. MCP Protocol — Tools, Resources, and Prompts

**Principle:** The Model Context Protocol (MCP) defines a standard interface between LLM hosts and servers. Every MCP server implements `tools/list` and `tools/call`, plus at least one of `resources` or `prompts`. The protocol uses JSON-RPC 2.0 framing. The transport is either stdio (subprocess) or SSE (HTTP).

**Invariant:**
```
∀MCP server S: S implements tools/list and tools/call
∀MCP server S: S implements at least one of resources or prompts
∀MCP server S: all messages use JSON-RPC 2.0 framing: {"jsonrpc": "2.0", "id": N, "method": "M", "params": {...}}
∀MCP tool T: T has a name, description, and inputSchema (JSON Schema)
∀MCP resource R: R has a URI pattern (scheme://path) and a name
∀MCP prompt P: P has a name and a list of messages
```

**Purpose:** MCP provides a standard interface for LLMs to interact with tools and data sources. The `tools/list` endpoint lets the LLM discover available tools dynamically. The `tools/call` endpoint executes the tool. Resources and prompts provide data and conversation templates. The JSON-RPC 2.0 framing ensures consistent error handling and request tracking.

**MCP capabilities:**

- **Tools:** `tools/list` returns available tools. `tools/call` executes a tool with the given arguments. Tools are stateless — the server manages state. Tool arguments are validated against the `inputSchema`.
- **Resources:** `resources/list` returns available resources. `resources/read` returns the resource content. Resources are identified by URI: `file:///path/to/file`, `db://users/123`, `api://weather/current`. Resources can be dynamic (e.g., `api://weather/current` returns different data each time).
- **Prompts:** `prompts/list` returns available prompts. `prompts/get` returns the prompt template with arguments filled in. Prompts are deterministic — same arguments produce the same messages.
- **Sampling (optional):** `sampling/createMessage` lets the server request the LLM to generate a response. This is the reverse direction — the server asks the LLM to do something.

**Error handling in MCP:**
- JSON-RPC 2.0 error codes: `-32700` (parse error), `-32600` (invalid request), `-32601` (method not found), `-32602` (invalid params), `-32603` (internal error)
- Method-level errors: `{"jsonrpc": "2.0", "id": 1, "error": {"code": -32603, "message": "Tool execution failed", "data": {"tool": "get_user", "args": {"id": "123"}, "error": "User not found"}}}`
- The `id` field must be present in the request and echoed in the response. A notification (no `id`) does not expect a response.

**Framework-specific:**
- **Go (mcp-go):** Define tools as `mcp.Tool` structs with `Name`, `Description`, and `InputSchema`. Register them with `server.AddTool(tool, handler)`. The handler receives the JSON-RPC request and returns the result.
- **Python (mcp-python):** `@server.tool(name="get_user", description="Get a user by ID")` decorator. The function receives the arguments as a dict. The return value is a `ToolResult` or a dict.
- **Node.js (@modelcontextprotocol/sdk):** `server.setRequestHandler(ListToolsRequestSchema, handler)` and `server.setRequestHandler(CallToolRequestSchema, handler)`. The handler is an async function that returns the result.

**Applications:**
- **orbit (internal):** orbit exposes an MCP server for agent tool access. Tools include `dispatch_task`, `read_file`, `write_file`, `run_shell`. The MCP server runs over stdio transport, spawned by the agent host.
- **bridge (gateway):** bridge exposes an MCP server for agent lifecycle management. Tools include `spawn_agent`, `get_agent_status`, `list_agents`, `kill_agent`. Resources include `agent://{id}/logs`, `agent://{id}/status`.
- **inbox (FastAPI):** inbox exposes an MCP server for conversation management. Tools include `send_message`, `get_conversation`, `list_conversations`. Resources include `conversation://{id}/messages`, `conversation://{id}/metadata`.
- **btw-v1 (livelm API):** The btw-v1 API is a REST API, not an MCP server. However, the MCP protocol is used internally for tool registration. The btw-v1 server registers tools with the MCP host and handles tool calls.

---

## 9. Authentication — Bearer Tokens, API Keys, OAuth2

**Principle:** Every request to a protected endpoint must include a valid authentication credential. The authentication mechanism is consistent across all endpoints. Missing or invalid credentials return 401. Valid credentials with insufficient scope return 403. The auth layer is a middleware, not per-endpoint logic.

**Invariant:**
```
∀request R to a protected endpoint E:
  R includes a valid auth header (Authorization: Bearer <token> or X-API-Key: <key>)
  server validates the credential before executing the handler
  invalid/missing credential → 401 UNAUTHENTICATED
  valid credential, insufficient scope → 403 PERMISSION_DENIED
```

**Authentication mechanisms:**

- **Bearer tokens (OAuth2):** `Authorization: Bearer <token>`. The token is a JWT or opaque string. The server validates the token (signature, expiry, issuer, audience). JWTs are self-contained (no database lookup), but they cannot be revoked easily (short TTL mitigates this). Opaque tokens require a database lookup but can be revoked immediately.
- **API keys:** `X-API-Key: <key>` or `Authorization: Bearer <key>`. Simpler than OAuth2. The key is a random string stored in the database. The server looks up the key, checks the rate limit, and identifies the client. API keys are long-lived and require secure storage.
- **OAuth2 flow:** 1. Client requests authorization from the user. 2. User authorizes and gets a code. 3. Client exchanges the code for a token. 4. Client uses the token for API calls. 5. Token refresh extends the session.

**Authorization (scopes and roles):**
- Scopes: Fine-grained permissions. `read:users`, `write:users`, `admin:users`. The token includes the scopes. The server checks the scope before executing the handler.
- Roles: Coarse-grained permissions. `admin`, `user`, `readonly`. The server checks the role. Roles are typically mapped to scopes internally.
- Resource-level permissions: `user:123:read` — permission is scoped to a specific resource.

**Framework-specific:**
- **FastAPI:** `Depends(get_current_user)` dependency that validates the token. `Depends(require_scope("read:users"))` dependency that checks the scope. The `OAuth2PasswordBearer` flow handles token acquisition. The `HTTPBearer` flow handles API keys.
- **Express/Node.js:** Middleware: `app.use('/api', authenticate)`. The middleware reads the `Authorization` header, validates the token, and sets `req.user`. Scope checking: `requireScope('read:users')` middleware.
- **Go (any router):** Middleware that reads the `Authorization` header, validates the JWT or API key, and sets the user in the context. The middleware is applied to the route group: `r.Group(func(r chi.Router) { r.Use(authMiddleware) })`.

**Applications:**
- **orbit (internal gRPC):** The gRPC server uses a TLS client certificate or a bearer token for authentication. The auth interceptor validates the token before the RPC handler. The token includes the caller identity and scope. RPC-specific authorization is a separate interceptor.
- **bridge (gateway):** API keys are passed as `X-API-Key` header. The bridge validates the key against the database. Rate limits are per API key. The bridge also supports OAuth2 bearer tokens for user-facing endpoints. 401 and 403 responses use the structured error format.
- **inbox (FastAPI):** JWT bearer tokens for user authentication. API keys for service-to-service communication. The auth dependency is applied to the `v1` router. Public endpoints (health check, docs) are excluded from auth.
- **btw-v1 (livelm API):** OpenAI-compatible API key authentication. The key is passed as `Authorization: Bearer <key>` and looked up in the database. Invalid keys return 401 with the OpenAI-compatible error format: `{"error": {"code": "invalid_api_key", "message": "Incorrect API key provided", "type": "authentication_error"}}`.

---

## 10. Observability — Request ID Propagation, Structured Logging, Metrics

**Principle:** Every request is traceable through the system via a unique request ID. The request ID is generated at the entry point (gateway) and propagated to all downstream services. Every log line includes the request ID. Every service exports metrics for request count, latency, and error rate. This is the foundation of debugging distributed systems.

**Invariant:**
```
∀request R: X-Request-ID or X-Correlation-ID is generated at the entry point or propagated from the client
∀request R: the request ID is propagated to all downstream services (gRPC metadata, HTTP headers, MCP JSON-RPC)
∀log line L: L includes the request_id field
∀service S: S exports metrics for request count, latency (p50/p95/p99), and error rate by endpoint
```

**Purpose:** In a distributed system, a single user request hits multiple services. Without a request ID, correlating logs across services requires matching timestamps and guessing. With a request ID, you search for the ID and see every log line across every service. The request ID is the single thread that connects all the pieces.

**Observability patterns:**

- **Request ID propagation:**
  - Entry point (gateway): If the client provides a request ID, propagate it. If not, generate one (`uuid.New()` or `ulid.Make()`).
  - REST: `X-Request-ID` header. The gateway sets it on the request and passes it to downstream services.
  - gRPC: `X-Request-ID` in the gRPC metadata. The client passes it in the context; the server reads it from the metadata.
  - MCP: The request ID is sent as part of the notification or request params. The server echoes it in the response.
  - Logging: Every log line includes `request_id`. The structured logger (zerolog, zap, structlog) adds the field automatically.

- **Structured logging:**
  - Log in JSON format, not plain text. JSON is parseable by log aggregation tools.
  - Every log line includes: `timestamp`, `level`, `request_id`, `service`, `message`, and any operation-specific fields.
  - Error logs include: `error`, `stack_trace` (at ERROR level), `code` (error code).
  - No `fmt.Println` for logging. Use a structured logger.

- **Metrics:**
  - Every endpoint exports: `requests_total`, `request_duration_seconds` (histogram), `errors_total` (by error code).
  - Metrics are aggregated by endpoint, method, and status code.
  - Prometheus format: `http_requests_total{method="GET", endpoint="/users", status="200"} 1000`.
  - Dashboards: p50/p95/p99 latency, error rate, request rate, rate limit hits.

**Framework-specific:**
- **FastAPI:** `@app.middleware("http")` that generates/propagates the request ID, adds it to the request state, and passes it to the response as `X-Request-ID`. The logger is configured with `structlog` that adds `request_id` from the context.
- **Express/Node.js:** `express-request-id` middleware for request ID generation. `pino` or `winston` for structured logging. `prom-client` for Prometheus metrics. The request ID is propagated via `req.id`.
- **Go (any router):** Middleware that reads the `X-Request-ID` header, generates one if missing, and sets it in the context. The structured logger (zerolog, zap) reads the request ID from the context. Metrics are exported via `promhttp.Handler()`.

**Applications:**
- **orbit (internal gRPC):** The gRPC interceptor generates or propagates the request ID in the metadata. Every log line includes `request_id`. Metrics: `orbit_dispatch_requests_total`, `orbit_dispatch_duration_seconds`, `orbit_dispatch_errors_total` (by error code). The `pkg/dispatch` service logs every dispatch attempt with the request ID.
- **bridge (gateway):** The bridge is the entry point for all external requests. It generates the request ID if the client doesn't provide one. The request ID is propagated to all downstream services (gRPC metadata, MCP JSON-RPC). Every response includes `X-Request-ID`.
- **inbox (FastAPI):** Middleware generates the request ID and adds it to the response. The request ID is propagated to the gRPC backend. Every log line includes `request_id`. Metrics: `inbox_requests_total`, `inbox_request_duration_seconds`, `inbox_errors_total`.
- **btw-v1 (livelm API):** The request ID is the `X-Request-ID` header. The btw-v1 server propagates it to the livelm backend. Every log line includes `request_id`. Metrics: `btw_requests_total`, `btw_request_duration_seconds`, `btw_tokens_total` (aggregated token usage).

---

## The API Design Test

For any API endpoint, ask:

1. **Resource modeling:** Is the path a noun? Does the HTTP method match the action? Or is there a verb in the URL?
2. **Error responses:** Is the error body structured? Does it have a machine-readable code? Or is it an HTML page?
3. **Versioning:** Is the version explicit? Would a breaking change require a new version?
4. **Pagination:** Does the list endpoint paginate? Is there a `next_page_token`? Is the page size bounded?
5. **Idempotency:** Can the client safely retry a POST? Is there an `Idempotency-Key` mechanism?
6. **Rate limiting:** Are the `X-RateLimit-*` headers present? Is 429 handled?
7. **gRPC patterns:** Is the deadline set? Is `ctx.Err()` checked? Are streams closed on completion?
8. **MCP protocol:** Does the server implement `tools/list` and `tools/call`? Is the transport consistent?
9. **Authentication:** Is the auth middleware applied? Is 401 vs 403 correct? Are scopes enforced?
10. **Observability:** Is `X-Request-ID` propagated? Does every log line include it? Are metrics exported?

API design is the contract between services. The invariants above are the terms of that contract. Every violation is a bug that will be felt in production — a missing rate limit header causes a client to hammer the server, a missing request ID makes a debugging session take hours, a verb in the URL makes every client integration harder.