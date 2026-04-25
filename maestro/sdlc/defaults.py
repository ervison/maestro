"""Technical defaults injected into every SDLC discovery run.

These constraints apply when the user request does not explicitly override them.
They are prepended to the effective prompt so every artifact generator — PRD,
NFR, API-contracts, data-model, etc. — sees them as authoritative from the start.
"""

TECHNICAL_DEFAULTS = """\
## AUTHORITATIVE TECHNICAL DEFAULTS

The following constraints are MANDATORY and NON-NEGOTIABLE.
They apply to every artifact generated in this session unless the user EXPLICITLY overrides them with specific contradicting instructions.

MANDATE: Do NOT rationalize deviations. Common forbidden rationalizations:
- "The user didn't mention a database" -> Use PostgreSQL unless stated otherwise.
- "A simpler stack would suffice" -> The defaults are already chosen for production-grade simplicity.
- "This feature doesn't need auth" -> All features inherit the JWT RBAC model.
- "100% coverage is unrealistic" -> It is the non-negotiable baseline. No exceptions.
- "The user might prefer another language" -> Go is the backend default. State it as such unless overridden.

These defaults exist because ambiguity in upstream artifacts propagates as broken specs downstream.
Enforce them unconditionally.

---

## Technical Defaults (apply when not overridden by user)

The following technical decisions are the project baseline. Apply them to every
artifact unless the user request explicitly specifies a different choice.

### Persistence
- Database: **PostgreSQL** (latest stable)
- Every entity that can be created must also support Read, Update, Delete, and
  List — implement full CRUD.
- Soft delete: use a `deleted_at TIMESTAMPTZ` column instead of physical DELETE
  on all primary business entities.
- Database migrations must be versioned (goose or golang-migrate); no raw
  `CREATE TABLE` in application startup code.
- Pagination for list endpoints must use **cursor-based** pagination (not
  offset/page-number) to remain efficient at scale.

### Backend
- Language / framework: **Go** (standard `net/http` or Gin — prefer stdlib
  unless the API surface clearly benefits from a router framework).
- All business logic and data access live exclusively in the backend.
- No credentials, secrets, or business rules in the frontend.
- API style: **REST JSON** with consistent envelope responses.
- Every endpoint must be documented in an **OpenAPI 3.x spec** (generated or
  hand-authored, committed alongside the code).
- Configuration (DB URL, JWT secret, ports, etc.) via **environment variables**
  only — no hardcoded values.

### Authentication & Authorization
- Authentication: **JWT Bearer tokens** — short-lived access token + refresh
  token pattern; no server-side sessions.
- Authorization: **RBAC** with at minimum two roles — `admin` and `user` —
  even if not mentioned, whenever the system has multiple users.

### Frontend
- Framework: **Next.js** (App Router) with **shadcn/ui** components and
  **Tailwind CSS**.
- The frontend is presentation-only: it calls the backend API and renders data.
  No business rules, no direct database access, no sensitive credentials.

### Infrastructure / Developer Experience
- Local development orchestration: **Docker Compose** (app service + postgres
  service, optionally adminer/pgweb for DB inspection).

### Code Quality & Testing
- **TDD is mandatory and non-negotiable.** Every feature and bug fix must start
  with a failing test. No production code is written before a test that requires
  it exists.
- **Code coverage: 100% line + branch coverage** is the target. CI must fail if
  coverage drops below 100%. Exceptions require explicit annotation and code
  review approval.
- Lint is mandatory on every commit: **golangci-lint** for Go backend,
  **ESLint + Prettier** for Next.js frontend. CI must fail on lint errors.
- Commit messages must follow **Conventional Commits**
  (`feat:`, `fix:`, `test:`, `refactor:`, etc.).

### Observability
- **Structured logging**: use `slog` in Go (never `fmt.Println` or unstructured
  strings). Log level configurable via `LOG_LEVEL` env var.
- **Health check**: every backend service must expose `GET /health` returning
  `{"status": "ok"}` with HTTP 200.
- **Prometheus metrics**: every backend service must expose `GET /metrics` in
  Prometheus text format. Include at minimum: request count, request latency
  histogram, and error rate — per endpoint.

### Security
- **Password hashing**: always use **bcrypt** (cost ≥ 12) or **argon2id**.
  Never MD5, SHA1, SHA256, or any reversible encoding.
- **Secrets in environment variables only**: API keys, JWT secrets, DB
  credentials, third-party tokens — all via env vars. Never hardcoded, never
  committed to the repository. Provide a `.env.example` with all required
  variables documented (no real values).
- **CORS**: configurable via `CORS_ALLOWED_ORIGINS` env var; never default to
  wildcard `*` in production.
- **Rate limiting**: apply to all public/unauthenticated API endpoints.
- **HTTPS**: mandatory in production; TLS terminates at the load
  balancer/reverse proxy (not the app).
- **Security headers**: configure Helmet-equivalent headers in Next.js
  (`next.config.js`): CSP, HSTS, X-Frame-Options, X-Content-Type-Options.

### API Design
- **Versioning**: all API routes must be prefixed with `/api/v1/` from day one.
  Never expose unversioned endpoints.
- **Error format**: all error responses must use a consistent envelope:
  ```json
  {"error": {"code": "SNAKE_CASE_CODE", "message": "Human-readable description"}}
  ```
  HTTP status code must be appropriate (400 client error, 401 unauth, 403
  forbidden, 404 not found, 422 validation, 500 server error).
- **Entity IDs**:
  - Public-facing IDs (in API responses, URLs, references): **UUID v4**.
  - Internal database primary keys: **auto-increment integer** (never exposed
    via API). Each entity has both `id BIGSERIAL` (internal) and
    `public_id UUID DEFAULT gen_random_uuid()` (external).

### Repository & CI
- `.env.example`: committed to the repository with every required variable
  documented. Real values never committed.
- `Makefile` with standard targets: `make dev`, `make test`, `make lint`,
  `make migrate`, `make build`.
- `README.md` minimum content: prerequisites, how to run locally, environment
  variables reference.
- CI pipeline (GitHub Actions) must enforce: lint → test (with coverage gate) →
  build → security scan on every pull request.

### File Storage / Uploads
- **Development**: local filesystem storage is acceptable for simplicity.
- **Production**: recommend object storage (S3-compatible: AWS S3, GCS, MinIO,
  Cloudflare R2). The specific provider is the user's choice. The application
  must abstract storage behind an interface so the backend is swappable without
  code changes — use an env var to select the adapter (`STORAGE_BACKEND=local`
  vs `STORAGE_BACKEND=s3`).
- Never store uploaded files on the web server's filesystem in production
  (breaks horizontal scaling and causes data loss on redeploy).

---

## ENFORCEMENT

Every generated artifact MUST reflect the above defaults.
If a default conflicts with an explicit user instruction, the user instruction wins — document the override explicitly in the artifact.
If no explicit override exists, the default stands. Silence is NOT an override.
"""
