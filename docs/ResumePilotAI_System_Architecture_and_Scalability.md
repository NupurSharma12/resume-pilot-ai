# ResumePilotAI — System Architecture, Design Patterns & Scalability

## 1. Purpose

ResumePilotAI is an AI-assisted job-preparation platform:

**Resume + JD → Analysis → Interview Preparation → Career Conversation → Tailoring → Apply → Post-Apply Analysis → History / Resume**

The central architectural decision is that a **JobPreparation is the durable unit of work**. PostgreSQL stores durable workflow state; frontend session state represents the active UI; historical preparations can be rehydrated when the user chooses to continue.

## 2. High-Level Architecture

```text
Browser (React + TypeScript)
          │ REST/JSON
          ▼
FastAPI API
 ├── API endpoints / validation
 ├── Workflows / domain logic
 ├── Orchestration / persistence boundaries
 ├── LLM Gateway
 └── transient session state
          │
          ├──────────────► LLM Providers
          │
          ▼
      PostgreSQL
          │
          └── Resume / versions / JobPreparation
```

The important separation is:

**Domain / Workflow → Persistence abstraction → PostgreSQL implementation**

Business logic does not need to know which persistence implementation is being used.

## 3. Core Architectural Principles

### JobPreparation as the durable unit

A single preparation ties together resume, JD, analysis, interview preparation, career conversation, tailoring, application and post-apply analysis.

This makes an entire user journey recoverable and gives History a natural aggregate-like boundary.

### Durable state vs transient state

**Durable:** resumes, versions, analysis, interview preparation, conversation transcript, tailoring decisions, applied version, post-apply analysis and checkpoints.

**Transient:** React navigation/UI state and currently active in-memory workflow/session objects.

Rule:

> Persist business/workflow state, not arbitrary UI state.

### Provider-agnostic LLM boundary

Workflows call an `LLMGateway`/Protocol instead of a provider SDK directly.

```text
Workflow → LLMGateway → Provider
                       ├── OpenAI
                       ├── other provider
                       └── mock/test provider
```

This enables provider replacement, deterministic tests, structured output, streaming, usage/cost metadata and fallback strategies.

## 4. Backend Design

### FastAPI API layer

Endpoints handle request validation, loading required state, invoking workflows, response mapping and HTTP error handling. They should remain thin.

### Workflow layer

Workflows represent business operations such as Resume Analysis, Interview Preparation, Career Conversation, Tailoring and Post-Apply Analysis.

They coordinate prompts, LLM calls, domain models and persistence without becoming generic "god services".

### Prompt builders

Prompts are separated from orchestration for readability, testing, versioning and maintainability.

### Persistence Protocol

The application defines a persistence contract implemented by both in-memory and PostgreSQL stores.

Benefits:

- dependency inversion
- easy unit testing
- local development
- integration testing
- future storage replacement

### PostgreSQL

The production-oriented implementation uses PostgreSQL + SQLAlchemy async + asyncpg, connection pooling, short-lived sessions, transactions and row locking where concurrent writes matter.

Alembic owns schema migrations.

## 5. Frontend Design

### Route-oriented React architecture

```text
App
 └── DashboardLayout
      ├── Dashboard
      ├── Career Conversation
      ├── Interview Preparation
      ├── Tailored Resume
      ├── History
      └── Settings
```

### ResumeSessionContext

Context is the active workflow/session boundary. It prevents excessive prop drilling while keeping UI state separate from durable database state.

### API clients

HTTP calls live in dedicated API client modules:

```text
Page → API client → HTTP → FastAPI
```

This improves reuse, testing and consistency.

### Shared components

Shared presentation components are extracted when semantics are genuinely shared, such as Interview Preparation rendering between History and the active preparation page.

### Deterministic E2E

Playwright uses mocked API flows for deterministic UI tests, avoiding live LLM availability and quota as test dependencies.

## 6. Key Design Decisions

| Decision | Reason |
|---|---|
| JobPreparation as durable unit | Makes a whole user journey recoverable |
| Relational core + JSONB AI results | Stable relationships stay relational; evolving AI output stays flexible |
| Immutable resume versions | Preserves history and enables comparison |
| Persistence Protocol | Decouples business logic from infrastructure |
| Async backend | Efficient for DB, HTTP and LLM I/O |
| LLM Gateway | Provider independence and testability |
| Structured LLM output | Validated, predictable domain data |
| Deterministic enrichment | Lower cost, latency and nondeterminism |
| Prompt builders | Separates prompt engineering from orchestration |
| Transactions | Atomic business mutations |
| Row locking | Protects concurrent writes |
| Explicit checkpoints | Enables resume/rehydration |
| React Context | Avoids prop drilling |
| API client modules | Clean frontend/backend boundary |
| Mocked E2E | Stable CI |
| PostgreSQL | Durable shared source of truth |

## 7. Consistency Model

ResumePilotAI is primarily a **workflow-oriented CRUD system with transactional state transitions**, not an event-sourced system.

A JobPreparation contains related durable state. A business mutation should update all related durable state atomically when it represents one operation.

Example:

```text
Apply tailoring selection
       ↓
update selection + applied resume version
       ↓
single transaction
```

## 8. Scalability: ~1,000 Users

Keep the architecture simple.

```text
Load Balancer
     │
 ┌───┴───┐
 API   API
 └───┬───┘
     ▼
PostgreSQL
     │
Object Storage
```

Likely bottlenecks are LLM latency/rate limits, database connections, document processing and long-running requests—not raw CPU.

At this scale:

- 2–4 stateless API instances can be sufficient depending on traffic
- use managed PostgreSQL
- use object storage for resumes
- add basic metrics/logging/tracing
- consider a worker queue for expensive AI operations

## 9. Scalability: ~1 Million Users

Move to explicitly distributed components:

```text
CDN → Load Balancer → API fleet
                         │
                 ┌───────┴───────┐
                 ▼               ▼
               Redis           Queue
                                 │
                               Workers
                 └───────┬───────┘
                         ▼
                    PostgreSQL
                   /                         primary       replicas
                         +
                    Object Storage
```

Important changes:

### Stateless API

Every API instance must be disposable. Durable state cannot depend on process memory.

### Queue + workers

Use asynchronous workers for resume parsing, expensive LLM calls, enrichment and post-apply analysis.

### Redis

Use for caching, rate limiting and selected ephemeral coordination—not as the authoritative JobPreparation store.

### Database scaling

Start with indexing, query optimization, connection pooling and read replicas. Partition/shard only when evidence shows a single cluster is insufficient.

## 10. Scalability: ~1 Billion Users

At this scale, capacity planning must be based on actual:

- DAU/MAU
- peak RPS
- concurrency
- read/write ratio
- LLM RPS
- payload size
- storage growth
- geographic distribution

A possible architecture:

```text
Global Routing
      │
 ┌────┼────┐
 ▼    ▼    ▼
Region A/B/C
 │    │    │
API fleets
 │    │    │
Queues + workers
 │    │    │
Regional data stores
 └────┼────┘
  global data strategy
```

Consider multi-region deployment, partitioning, sharding, regional data placement, global routing and advanced caching only when justified.

Key principle:

> One billion registered users does not mean one billion concurrent users. Scale based on workload, not headline user count.

## 11. Database Scaling

### Vertical scaling

First improve CPU, RAM, storage, indexes, queries and connection pooling.

### Read scaling

Use read replicas for History browsing, search and reporting.

### Partitioning

Partition by time, tenant/user or geography when table size and access patterns justify it.

### Sharding

Only when a single PostgreSQL cluster is insufficient. A shard key such as `hash(user_id)` can work when most queries are user-scoped, but cross-shard queries must be minimized.

## 12. LLM Scalability

LLM workloads are likely to become one of the platform's major bottlenecks.

Optimize:

### Prompt size

Avoid repeatedly sending complete resumes and conversations when compact representations are sufficient.

### Deterministic processing

If Python can perform the transformation, do not spend an LLM call on it.

### Caching

Cache safe/idempotent results using appropriate keys such as input hashes + prompt version + model version.

### Model routing

```text
simple task → cheaper/faster model
complex task → stronger model
```

### Rate limiting and concurrency

Limit by user, tenant, provider and model.

### Provider fallback

The LLM gateway provides a natural place for provider failover.

## 13. File Storage

At scale, large resume files should live in object storage rather than PostgreSQL.

```text
Browser
   ↓
pre-signed upload
   ↓
Object Storage
   ↓
JobPreparation stores metadata/reference
```

Benefits: independent scaling, cheaper storage, large-file support and CDN integration.

## 14. API Performance

Use:

- cursor/keyset pagination for large History datasets
- bounded page sizes
- lightweight list responses
- full JobPreparation retrieval only when needed
- HTTP compression
- database connection pooling
- explicit timeouts for external dependencies

Current History can reasonably remain at 10 recent records; search/pagination can evolve later.

## 15. Caching

Good candidates:

- History metadata
- resume metadata
- job/company metadata
- configuration
- rate-limit counters

Do not use cache as the source of truth for JobPreparation or important mutations.

> Cache for performance, never because the database model is inconvenient.

## 16. Reliability

Design for:

- LLM timeouts
- provider rate limits
- database failures
- worker crashes
- duplicate requests
- retries
- partial completion
- frontend refresh
- backend restart

Mutating operations should be retry-safe. Stable `job_preparation_id` and transactional persistence already provide a strong foundation; explicit idempotency keys can be added later for high-scale APIs.

## 17. Observability

Important metrics:

- request latency/error rate
- DB latency and pool utilization
- queue depth/worker throughput
- LLM latency
- token usage
- LLM cost
- cache hit ratio

Use structured logs and distributed tracing with request/correlation IDs:

```text
HTTP request
   ↓
workflow
   ↓
database / LLM / queue
```

## 18. Security

Resumes contain personal information, so security is architectural, not an afterthought.

Consider:

- authentication
- authorization
- tenant isolation
- encryption in transit/at rest
- secret management
- signed object-storage URLs
- least-privilege DB roles
- audit logging
- PII retention/deletion
- secure LLM-provider handling

Every JobPreparation query must be authorized against the authenticated user/tenant.

## 19. Multi-Tenancy

For SaaS:

```text
User
 └── Tenant / Account
       └── JobPreparations
```

Early scale can use a `tenant_id` column with indexes and strict authorization.

Later, consider tenant-aware caching, rate limits, noisy-neighbor controls and dedicated infrastructure for large enterprise tenants.

## 20. Evolution Path

### Stage 1 — Current

```text
React → FastAPI → PostgreSQL → LLM provider
```

### Stage 2 — ~1K

Add managed infrastructure, multiple stateless APIs, object storage and observability.

### Stage 3 — ~1M

Add queues/workers, Redis, read replicas, CDN and autoscaling.

### Stage 4 — Very large/global

Add multi-region architecture, partitioning/sharding and advanced routing only when justified.

> Do not build Stage 4 architecture for a Stage 1 problem.

## 21. Interview Perspective

### Why PostgreSQL?

The system has strongly related durable entities and transactional updates. PostgreSQL gives transactions, constraints, JSONB, indexing and mature operational tooling.

### Why JSONB?

Core relationships are stable and relational, while AI-generated structures evolve quickly. JSONB lets us evolve AI output without creating migrations for every prompt/output change.

### Why a Protocol?

Dependency inversion. Workflows depend on a persistence contract rather than SQLAlchemy/PostgreSQL. This enables memory implementations, integration tests and future infrastructure changes.

### Why not Redis as the database?

Redis is excellent for fast ephemeral data, caching and coordination. PostgreSQL is the authoritative durable store for JobPreparation.

### Why async?

The workload is I/O-heavy: database, HTTP, LLM and object storage. Async lets workers efficiently spend time waiting on external systems.

### How would you scale it?

A strong system-design answer:

> I would first identify the actual bottleneck. Around 1K users, I'd keep a stateless FastAPI fleet, managed PostgreSQL, object storage and observability. As traffic grows, I'd move expensive AI/document operations behind queues and workers, add Redis for caching/rate limiting, and read replicas for database scaling. At global scale I'd consider partitioning, sharding and multi-region deployment based on access patterns. LLM latency, quotas and cost become major scaling dimensions, so I'd use model routing, prompt minimization, deterministic processing, caching and provider fallbacks.

### What is likely the hardest scaling problem?

LLM workloads have high/variable latency, rate limits and cost. Decoupling expensive work from synchronous APIs and controlling concurrency is therefore critical.

## 22. Design Principles to Remember

1. Separate domain logic from infrastructure.
2. Keep APIs thin.
3. Keep workflows explicit.
4. Make durable state authoritative.
5. Keep UI state transient.
6. Prefer deterministic computation over unnecessary LLM calls.
7. Make expensive work asynchronous at scale.
8. Keep services stateless for horizontal scaling.
9. Use PostgreSQL as the source of truth.
10. Use caching to improve performance, not correctness.
11. Make mutations retry-safe.
12. Measure before introducing distributed complexity.
13. Scale the bottleneck, not the architecture diagram.
14. Treat LLM latency, quota and cost as first-class capacity constraints.
15. Design security and tenant isolation before multi-user scale makes them painful.

## 23. One-Sentence Architecture Summary

> ResumePilotAI is a workflow-oriented AI web application with a React/TypeScript frontend, async FastAPI backend, provider-agnostic LLM gateway, workflow/domain layers and PostgreSQL-backed durable JobPreparation state, designed to evolve from a simple stateless deployment into a queue-driven, horizontally scaled, multi-region architecture as workload grows.
