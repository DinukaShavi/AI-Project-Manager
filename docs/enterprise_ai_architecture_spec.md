# Enterprise AI Architecture Specification: AI-Powered Technical Project Manager (AI-TPM)

This document provides complete, production-ready system design and architectural specifications for the fifteen (15) core AI systems of the AI-Powered Technical Project Manager (AI-TPM).

---

## 1. Agent Lifecycle State Machine

This system governs the execution lifecycle of AI agents within the multi-agent system.

```
       ┌───────────┐
       │  Created  │
       └─────┬─────┘
             │ Enqueue Task
             ▼
       ┌───────────┐
       │  Queued   │
       └─────┬─────┘
             │ Assign Worker
             ▼
       ┌───────────┐
       │ Planning  │◄───────────────────────────┐
       └─────┬─────┘                            │ Replanning
             │ Generate DAG                     │
             ▼                                  │
       ┌───────────┐                            │
       │ Executing ├────────────────────────────┤
       └─┬───┬───┬─┘                            │
         │   │   │                              │
         │   │   └─► [Tool Call] ──► Waiting    │
         │   │                       Tool       │
         │   │                        │         │
         │   │                        └─────────┘ Tool Result
         │   │
         │   └─► [Approval] ──► Waiting
         │                      Human
         │                       │
         │                       └──────────────┘ Approved
         │
         └─► [Reflection] ──► Retrying ──► (Fail) ──► Failed
                  │
                  └─────────────────────────► Completed
```

### Overview & Objectives
* **Overview**: Provides a state machine that tracks the execution status of agents. It ensures that execution states are persistent and audit-ready.
* **Objectives**: Guarantees recovery from worker crashes, prevents execution locks, and provides a clear audit log of all agent runs.

### Detailed State Specifications

| State Name | Database Code | Transition Trigger | Message Broker Event |
| :--- | :--- | :--- | :--- |
| **Created** | `CREATED` | Agent run requested by user or trigger. | `agent.run.created` |
| **Queued** | `QUEUED` | Task added to the Celery execution queue. | `agent.run.queued` |
| **Planning** | `PLANNING` | Worker claims task and begins generating the DAG. | `agent.run.planning.started` |
| **Executing** | `EXECUTING` | Agent executes plan nodes. | `agent.run.executing` |
| **Waiting Tool** | `WAITING_TOOL` | Agent suspends execution to await a tool result. | `agent.run.tool.waiting` |
| **Waiting Approval** | `WAITING_APPROVAL` | Execution suspends to await human approval. | `agent.run.approval.waiting` |
| **Reflection** | `REFLECTION` | Agent reviews the execution results of a step. | `agent.run.reflection` |
| **Retrying** | `RETRYING` | Self-correction loop triggers a step retry. | `agent.run.retrying` |
| **Completed** | `COMPLETED` | Execution finishes successfully. | `agent.run.completed` |
| **Cancelled** | `CANCELLED` | Execution is terminated by user command. | `agent.run.cancelled` |
| **Failed** | `FAILED` | Critical execution failure or maximum retries reached. | `agent.run.failed` |

### Database Schema representation (JSON Schema)
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "AgentExecutionState",
  "type": "object",
  "properties": {
    "execution_id": { "type": "string", "format": "uuid" },
    "agent_name": { "type": "string" },
    "status": {
      "type": "string",
      "enum": ["CREATED", "QUEUED", "PLANNING", "EXECUTING", "WAITING_TOOL", "WAITING_APPROVAL", "REFLECTION", "RETRYING", "COMPLETED", "CANCELLED", "FAILED"]
    },
    "current_step": { "type": "string" },
    "max_retries": { "type": "integer", "default": 3 },
    "retry_count": { "type": "integer", "default": 0 },
    "heartbeat_timeout_seconds": { "type": "integer", "default": 30 },
    "last_heartbeat": { "type": "string", "format": "date-time" }
  },
  "required": ["execution_id", "agent_name", "status"]
}
```

### Component Responsibilities & Operational Metrics
* **Supervisor**: Dispatches initial command events, monitors heartbeat states, and updates execution tables when an agent fails to respond.
* **Celery Worker**: Claims tasks, runs the agent execution loops, and writes thought logs to the database.
* **WebSocket Relayer**: Subscribes to execution update channels and broadcasts changes to client UIs.
* **Advantages**: Resilient execution monitoring, crash-safe state recovery, and simplified debugging using thought logs.
* **Disadvantages**: Database write overhead on high-frequency state updates.
* **Failure Scenario & Recovery**: If a worker crashes, the coordinator detects the missed heartbeats, marks the active step as failed, runs the registered rollback actions, and restarts execution.
* **Security & Scalability**: RLS is applied to execution tables. State data is partitioned by organization to ensure tenant isolation.

---

## 2. Distributed Locking Architecture

This system manages distributed coordination across multiple Celery workers to prevent concurrent writes to identical project resources.

```
 [Worker A] ──(Acquire Lock)──► [Redis Distributed Lock (Redlock)]
                                              │
                                              ▼ (Lock Granted)
                                [Perform Mutating Action]
                                              │
                                              ▼ (Release Lock)
                                [Redis Distributed Lock (Redlock)]
                                              ▲
                                              │ Waits (Retry Loop)
 [Worker B] ──────────────────────────────────┘
```

### Overview & Objectives
* **Overview**: Coordinates database writes across workers to ensure data consistency.
* **Objectives**: Prevents race conditions, avoids deadlocks, and enforces atomic updates across external integrations.

### Coordination Details
* **Redis Locks (Redlock)**: Distributed locks are managed using Redis Streams and Redis keys.
* **Lock Expiration**: Locks are assigned a Time-To-Live (TTL) of 30 seconds.
* **Lock Renewal**: Long-running operations run a background thread that extends the lock lease in Redis every 10 seconds.
* **Optimistic Concurrency Control (OCC)**: Used to manage database writes. Every table contains a `version` column. Updates verify that the version has not changed:
  $$\text{Update Criteria}: \text{version}_{\text{DB}} == \text{version}_{\text{read}}$$

### Comparison: OCC vs. Pessimistic Locking

| Metric | Optimistic Concurrency Control (OCC) | Pessimistic Locking |
| :--- | :--- | :--- |
| **Resource Contention** | High efficiency under low contention. | High efficiency under high contention. |
| **Database Overhead** | Minimal; uses standard index lookups. | High; locks rows and tables. |
| **Deadlock Risk** | None. | High. |
| **Scalability Impact** | Supports horizontal scaling. | Restricts throughput under load. |

### Component Responsibilities & Operational Metrics
* **Lock Manager**: Handles Redis connection pools and executes Redlock acquire/release scripts.
* **Background Lease Extender**: Background daemon that renews active locks.
* **Advantages**: Prevents database deadlocks, minimizes connection pool overhead, and ensures data consistency across workers.
* **Disadvantages**: Adds Redis latency to write operations.
* **Failure Scenario & Recovery**: If a worker dies while holding a lock, the Redis key expires after its 30-second TTL, allowing other queued workers to acquire the lock and resume processing.

---

## 3. LLM Timeout & Retry Architecture

This system manages retry logic and fallbacks for external LLM API calls to ensure system availability.

```
                  [Outbound LLM Request]
                            │
                            ▼
                    [Circuit Breaker]
                            │
             ┌──────────────┴──────────────┐
             ▼ Open                        ▼ Closed
     [Route to Fallback]           [Execute LLM Request]
                                           │
                         ┌─────────────────┴─────────────────┐
                         ▼ Success                           ▼ Timeout / Error
                [Process Response]                     [Exponential Backoff]
                                                             │
                                                             ▼ (Max retries reached?)
                                                ┌────────────┴────────────┐
                                                ▼ Yes                     ▼ No
                                        [Route to Fallback]       [Re-queue & Retry]
```

### Overview & Objectives
* **Overview**: Protects the system from third-party API outages by implementing timeouts, exponential backoffs, and circuit breakers.
* **Objectives**: Minimizes API costs, prevents application blocks during outages, and maintains system availability.

### Retry Design Specs
* **Timeout Threshold**: Maximum connection timeout is 10 seconds; write timeout is 30 seconds.
* **Exponential Backoff**: If an API call fails due to a rate limit or server error, the system retries after a calculated delay:
  $$\text{Delay} = \min\left(\text{Cap}, \text{Base} \times 2^{\text{attempt}}\right) + \text{jitter}$$
* **Circuit Breaker State Machine**:
  * **Closed**: Requests route directly to the primary provider (e.g., Claude 3.5 Sonnet).
  * **Open**: If error rates exceed 50% over a 10-second window, the circuit breaker opens, routing all requests to fallback models (e.g., GPT-4o or Llama 3) for 60 seconds.
  * **Half-Open**: After 60 seconds, a test request is sent to the primary provider. If successful, the circuit breaker closes.

### Component Responsibilities & Operational Metrics
* **Circuit Breaker Registry**: Tracks error rates and state transitions in Redis.
* **API Route Dispatcher**: Intercepts requests and routes them to active models based on circuit breaker states.
* **Advantages**: High availability, automated model fallbacks, and protection against API rate limits.
* **Disadvantages**: Context variations when switching between different model APIs.
* **Failure Scenario & Recovery**: If all upstream API providers fail, the dispatcher returns a structured exception, pauses active workflows, and sends a Slack alert to the operations team.

---

## 4. Prompt Context Window Manager

This system assembles prompts by retrieving and filtering context data to fit model context windows.

```
        [Raw User Request] ──► [Retrieve Related Context Data]
                                        │
                                        ▼ (Calculate token budgets)
                            [Context Token Budgeting]
                                        │
                                        ▼ (Sort by relevance)
                            [Priority Reranking Layer]
                                        │
                                        ▼ (Trim context to fit budget)
                            [Sliding Window Trimming]
                                        │
                                        ▼ (Format final context)
                              [Assembled Prompt]
```

### Overview & Objectives
* **Overview**: Manages prompt construction by budget filtering, sorting, and formatting context data.
* **Objectives**: Prevents context window overflows, minimizes token costs, and ensures relevant information is positioned at the top of the prompt.

### Token Budgeting Allocation (8,000 Token Target)

| Context Category | Token Allocation | Priority Rank | Trimming Strategy |
| :--- | :--- | :--- | :--- |
| **System Prompt & Role** | 1,000 | 1 (Highest) | Immutable; never trimmed. |
| **User Query** | 1,000 | 2 | Immutable; never trimmed. |
| **Jira Overdue Issues** | 2,000 | 3 | Truncate details using pagination templates. |
| **Recent Slack Summaries** | 1,500 | 4 | Drop old entries using a sliding window. |
| **Vector Memories** | 1,500 | 5 | Truncate vectors below a 0.8 cosine similarity. |
| **Git Commit Diffs** | 1,000 | 6 (Lowest) | Trim raw diff text down to file change stats. |

### Prompt Pipeline Logic
1. **Retrieve**: Query the Context Engine for relevant database and vector memories.
2. **Embed & Rerank**: Generate embeddings for the query and retrieve semantic memories from pgvector. Rank results using a reranker model.
3. **Filter**: Compress slack logs and meeting transcripts into bullet summaries.
4. **Assemble**: Construct the final prompt, positioning the core goal at the top of the context block.

### Component Responsibilities & Operational Metrics
* **Token Counter**: Calculates token counts for raw text strings using tiktoken.
* **Reranking Engine**: Ranks retrieved context items by relevance.
* **Advantages**: Predictable token usage, reduced costs, and minimized context degradation.
* **Disadvantages**: High retrieval overhead during surges in user activity.

---

## 5. Tool Permission Matrix

This system enforces Role-Based Access Control (RBAC) on tool execution paths.

### Overview & Objectives
* **Overview**: Evaluates tool call requests against organization policy configurations to prevent unauthorized actions.
* **Objectives**: Secures repository states, prevents data leaks, and enforces human-in-the-loop approvals.

### Tool Permission Mapping

| Tool Name / Action | Super Admin | Org Admin | Project Manager | Developer | Read-Only | Approval Policy |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **delete_repository** | Allowed | Denied | Denied | Denied | Denied | Requires Super Admin validation |
| **merge_pull_request** | Allowed | Allowed | Allowed | Allowed | Denied | PM approval required if CI fails |
| **create_jira_ticket** | Allowed | Allowed | Allowed | Allowed | Denied | Auto-executed |
| **deploy_release** | Allowed | Allowed | Allowed | Denied | Denied | PM validation required |
| **send_slack_broadcast** | Allowed | Allowed | Allowed | Allowed | Denied | Auto-executed |
| **modify_prompt** | Allowed | Allowed | Denied | Denied | Denied | Audit log recorded |

### Authorization Schema (JSON Schema)
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "ToolCallAuthorizationRequest",
  "type": "object",
  "properties": {
    "user_id": { "type": "string", "format": "uuid" },
    "role": { "type": "string", "enum": ["SuperAdmin", "OrgAdmin", "ProjectManager", "Developer", "Viewer"] },
    "tool_name": { "type": "string" },
    "target_resource_urn": { "type": "string" },
    "risk_level": { "type": "string", "enum": ["LOW", "MEDIUM", "HIGH", "CRITICAL"] }
  },
  "required": ["user_id", "role", "tool_name", "risk_level"]
}
```

### Component Responsibilities & Operational Metrics
* **Policy Decision Point (PDP)**: Evaluates whether a role is authorized to run a tool.
* **Approval Queuer**: Suspend executions and publishes approval requests to user notification channels.
* **Advantages**: Secures critical resources, tracks execution audits, and provides customizable policies.
* **Disadvantages**: Adds manual approval latency to automated workflows.

---

## 6. Prompt Versioning & Rollback Architecture

This system manages versioning, testing, and deployments for agent prompts.

```
       [Prompt Editor] ──► [Save Draft (v1.1.0-draft)]
                                  │
                                  ▼ (Run automated tests)
                          [Staging Tests Check]
                                  │
                                  ▼ (Review & Approval)
                           [Approve Draft]
                                  │
                  ┌───────────────┴───────────────┐
                  ▼ Canary (10% Traffic)          ▼ Rollback (Triggered)
           [Deploy v1.1.0]                 [Restore v1.0.0]
```

### Overview & Objectives
* **Overview**: Provides version control, testing pipelines, and deployment controls for system prompts.
* **Objectives**: Prevents prompt regressions, tracks prompt histories, and supports zero-downtime rollbacks.

### Deployment & Testing
* **Versioning**: Prompts use SemVer (e.g., `v1.2.0`). Minor updates cover phrasing tweaks; major updates indicate structural schema changes.
* **A/B Testing**: The system can route a percentage of traffic (e.g., 10%) to a new prompt version (Canary deployment) and evaluate its performance against the control version.
* **Automated Rollback**: If tool execution failures or hallucination rates exceed baseline thresholds after a prompt update, the system automatically rolls back to the previous stable version.

### Component Responsibilities & Operational Metrics
* **Prompt Registry**: Serves active prompts from Redis caches.
* **AB Router**: Routes agent runs to prompt versions based on configured traffic weights.
* **Advantages**: Safe prompt deployments, rollback capabilities, and tracking of historical performance.
* **Disadvantages**: Increases storage requirements for prompt versions and test logs.

---

## 7. AI Evaluation & Benchmark Framework

This system monitors agent performance by measuring planning accuracy, tool execution success rates, and token costs.

```
        [Agent Output] ──► [Evaluation Pipeline (Celery)]
                                     │
                 ┌───────────────────┼───────────────────┐
                 ▼                   ▼                   ▼
         [Calculate KPIs]   [Semantic Assertions]  [Save Metrics]
                 │                   │                   │
                 └───────────────────┬───────────────────┘
                                     ▼
                             [Dashboard Alerts]
```

### Key Performance Indicators (KPIs)
* **Planning Accuracy**: Measures whether the generated DAG plan matches reference templates for a task.
* **Tool Success Rate**: The percentage of tool calls completed without error:
  $$\text{TSR} = \frac{\text{Success Tool Calls}}{\text{Total Tool Calls}} \times 100$$
* **Hallucination Rate**: Calculated using semantic contradiction checks (LLM-as-a-judge) on outputs against context states.
* **User Satisfaction Score**: Percentage of recommendations accepted by users.

### Benchmark Assertions Schema
```json
{
  "test_suite": "sprint_planning_assessment",
  "assertions": [
    {
      "metric": "planning_accuracy",
      "operator": "gte",
      "threshold": 0.90
    },
    {
      "metric": "hallucination_rate",
      "operator": "lte",
      "threshold": 0.02
    }
  ]
}
```

### Component Responsibilities & Operational Metrics
* **Benchmark Suite Runner**: Executes agent test runs on synthetic datasets during CI pipelines.
* **Metric Collector**: Aggregates production runs telemetry into analytics tables.
* **Advantages**: Automated performance regressions checks, metric tracking, and cost monitoring.
* **Disadvantages**: Increases token costs during benchmarking runs.

---

## 8. Model Routing & Fallback Strategy

This system selects and routes tasks to the most cost-effective model that satisfies execution constraints.

```
                                [Incoming Task]
                                       │
                        ┌──────────────┴──────────────┐
                 Complex Task?                 Simple Task?
                        │                             │
              ┌─────────┴─────────┐                   ▼
       High Budget?           Low Budget?       [Llama 3 / local model]
              │                   │
              ▼                   ▼
     [Claude 3.5 Sonnet]     [Gemini 1.5 Flash]
```

### Routing Matrix

| Task Category | Primary Model | Fallback Model | Selection Criteria |
| :--- | :--- | :--- | :--- |
| **DAG Generation** | Claude 3.5 Sonnet | GPT-4o | Requires complex reasoning and JSON output. |
| **Context Analysis** | Gemini 1.5 Flash | Llama 3 (8B) | Requires large context window and low cost. |
| **Output Reflection** | Claude 3.5 Sonnet | GPT-4o | Requires high accuracy checks. |
| **Entity Embeddings** | text-embedding-3-small | Cohere-embed | Cost-effective vector embedding generation. |
| **Search Reranking** | Cohere Rerank | Local Cross-Encoder | Optimized search result relevance. |

### Fallback Lifecycle
1. **Primary Model Attempt**: Dispatch request to the primary model (e.g., Claude 3.5 Sonnet).
2. **Retry Loop**: If a rate limit (HTTP 429) or server error (HTTP 5xx) is encountered, retry the request with exponential backoff.
3. **Fallback Route**: If retries fail or a circuit breaker opens, route the request to the fallback model (e.g., GPT-4o).

### Component Responsibilities & Operational Metrics
* **Router**: Selects the target model based on task constraints.
* **Failover Handler**: Manages fallbacks and model schema mappings.
* **Advantages**: Optimized token costs, high availability, and fallback protection.
* **Disadvantages**: Model switches can cause variations in response formats.

---

## 9. AI Cost Monitoring Dashboard

This system tracks and analyzes LLM API token usage and costs across the platform.

### Overview & Objectives
* **Overview**: Aggregates token consumption metrics to generate reports and alerts for cost management.
* **Objectives**: Prevents run-away costs, tracks margins by organization, and identifies inefficient prompts.

### Cost Tracking Schemas
```json
{
  "timestamp": "2026-07-17T21:40:00Z",
  "organization_id": "uuid-v4",
  "user_id": "uuid-v4",
  "agent_name": "PlanningAgent",
  "model": "claude-3-5-sonnet",
  "tokens": {
    "prompt": 4500,
    "completion": 850
  },
  "cost_usd": 0.02625,
  "cache_hits_tokens": 1200
}
```

### Cost Formula
$$\text{Total Cost} = \sum (\text{Prompt Tokens} \times \text{Rate}_{\text{input}}) + \sum (\text{Completion Tokens} \times \text{Rate}_{\text{output}}) - \text{Savings}_{\text{cache}}$$

### Component Responsibilities & Operational Metrics
* **Usage Collector**: Intercepts API responses, parses token metrics, and writes records to the database.
* **Billing Engine**: Generates cost dashboards and triggers alerts if an organization exceeds its budget.
* **Advantages**: Detailed visibility into costs, customizable alerts, and optimization tracking.
* **Disadvantages**: Logging overhead under high request volumes.

---

## 10. Memory Lifecycle & Garbage Collection

This system manages memory layers, expiration policies, and summarization pipelines.

```
 [Short-term Memory] ──(TTL Expired)──► [Summarization Engine]
                                                  │
                                                  ▼ (Aggregate Text)
                                        [Write to pgvector]
                                                  │
                                                  ▼ (Archive Details)
                                       [Cold Storage (S3)]
```

### Memory Expiration Policy

| Memory Layer | Storage Engine | Expiration Policy | Garbage Collection Trigger |
| :--- | :--- | :--- | :--- |
| **Short-term** | Redis | 1 hour TTL. | Auto-deleted by Redis keyspace events. |
| **Conversation** | PostgreSQL | Saved indefinitely; summarized after 10 messages. | Celery job runs conversation summarizer. |
| **Project Context** | pgvector | Rebuild index weekly to optimize search. | HNSW index rebuild scheduled weekly. |
| **Historical Logs** | PostgreSQL | Move to cold storage after 90 days. | DB partition rotator copies data to S3. |

### Memory Compression Pipeline
1. **Identify**: Find conversation logs that exceed the token threshold.
2. **Summarize**: Send the older 30% of messages to an LLM worker to generate a bulleted summary.
3. **Index**: Write the summary to the pgvector database.
4. **Prune**: Truncate the detailed conversation logs, preserving only the recent history.

### Component Responsibilities & Operational Metrics
* **Memory Rotator**: Moves historical logs to cold storage.
* **HNSW Index Rebuilder**: Rebuilds vector indexes to maintain search performance.
* **Advantages**: Reduced storage costs, optimized search speeds, and protection against context window overflows.
* **Disadvantages**: Risk of losing detailed information during summarization loops.

---

## 11. Observability & Distributed Tracing

This system implements distributed tracing and performance metrics tracking using OpenTelemetry.

```
 [API Gateway] ──(Trace Context)──► [FastAPI Router] ──(Trace Context)──► [Celery Worker]
       │                                   │                                    │
       └─────────────────────────┬─────────┴────────────────────────────────────┘
                                 ▼ (Export Traces)
                           [Jaeger Collector]
                                 │
                                 ▼
                         [Grafana Dashboard]
```

### Telemetry Tracing Metrics
* **API Latency**: Time required to process HTTP requests.
* **Tool Call Latency**: Execution duration of external tool actions.
* **LLM Latency**: Network round-trip time for LLM API calls.
* **Workflow Duration**: Time required to complete a DAG workflow execution.
* **Agent Run Duration**: Combined execution time of an agent's reasoning cycles.

### Trace Context Propagation Schema
```json
{
  "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
  "tracestate": "congo=t61rcWkgMzE,rojo=00f067aa0ba902b7",
  "correlation_id": "uuid-v4"
}
```

### Component Responsibilities & Operational Metrics
* **OTel Collector**: Collects traces and exports them to visualization systems (e.g., Jaeger).
* **Metrics Exporter**: Publishes performance metrics to Prometheus scraping endpoints.
* **Advantages**: End-to-end request tracing, performance monitoring, and simplified debugging.
* **Disadvantages**: Minor application latency overhead from trace collection.

---

## 12. Advanced Rate Limiting Architecture

This system implements rate limit protections using Redis token buckets.

```
                  [Incoming Request]
                          │
                          ▼
            [Read Tenant Limits from Redis]
                          │
             ┌────────────┴────────────┐
             ▼ Tokens Available        ▼ Out of Tokens
     [Deduct Token & Process]     [Reject: HTTP 429]
                                           │
                                           ▼ (Include headers)
                                  [Retry-After: 30s]
```

### Multi-Dimensional Limits

| Dimension | Rate Limit | Token Refill Rate | Burst Limit |
| :--- | :--- | :--- | :--- |
| **User Access** | 60 requests/min | 1 token/sec | 100 |
| **Organization** | 600 requests/min | 10 tokens/sec | 1,000 |
| **API Keys** | 120 requests/min | 2 tokens/sec | 200 |
| **WebSockets** | 100 messages/min | 1.6 tokens/sec | 150 |
| **LLM Calls** | 20 calls/min | 0.33 tokens/sec | 30 |

### Token Bucket Logic
* **Deduction**: Every incoming request deducts one token from the Redis bucket.
* **Refill**: The bucket refills at the configured rate up to the maximum burst limit.
* **Adaptive Throttling**: The system increases the rate limit threshold for a tenant if database or server load metrics fall below target utilization baselines.

### Component Responsibilities & Operational Metrics
* **Rate Limit Middleware**: Evaluates incoming requests and returns HTTP 429 if the token bucket is empty.
* **Redis Store**: Tracks token counts and last-refill timestamps.
* **Advantages**: Protects the system from resource starvation, supports adaptive throttling, and implements rate limit headers.
* **Disadvantages**: Adds Redis read/write latency to request paths.

---

## 13. Enterprise Security Architecture

This system implements security controls, row-level tenant isolation, encryption, and prompt injection defense.

```
 [User Input] ──► [Prompt Injection Check] ──► [PII Data Masking] ──► [API Processing]
                                                                            │
                                                                            ▼
                                                                 [Row-Level Security]
                                                                            │
                                                                            ▼
                                                                  [AES-256 Encrypted DB]
```

### Security Controls
* **Secrets Management (Vault)**: Credentials are encrypted using keys managed in HashiCorp Vault.
* **AES-256-GCM Encryption**: OAuth tokens and keys are encrypted before database insertion.
* **Row-Level Security (RLS)**: Enforced in PostgreSQL using `tenant_id` session variables.
* **Prompt Injection Defense**: Input requests are scanned using classification models to block prompt injection attempts.
* **PII Detection & Data Masking**: Scans input payloads to mask personally identifiable information (PII) before logging or sending data to external APIs.

### Security Implementation Matrix
* **Authentication**: JWT tokens with PKCE.
* **Authorization**: RBAC permissions enforced via PDP middleware.
* **Database Isolation**: PostgreSQL schemas isolate tenant databases or enforce strict RLS.
* **Network Security**: TLS 1.3 is enforced on all API routes.

---

## 14. Knowledge Graph Evolution Strategy

This system maintains and updates the project's knowledge graph to track relationships between development entities.

```
 [Event: Commit Linked to PR] ──► [Entity Linker Engine]
                                            │
                                            ▼ (Calculate relation weight)
                                  [Inference Pipeline]
                                            │
                                            ▼
                                [Update PostgreSQL Graph]
                                            │
                                            ▼ (Generate Semantic Embeddings)
                                  [Vector Index Sync]
```

### Graph Node & Edge Structure
* **Nodes**: `User`, `Sprint`, `Issue`, `PullRequest`, `Commit`, `Deployment`, `Incident`, `Document`, `AI_Memory`.
* **Relationships**: `assigned_to`, `blocked_by`, `merged_in`, `mentioned_in`, `reviews`, `depends_on`.

### Relationship Scoring Formula
Determines relationship weights dynamically:
$$\text{Weight} = \text{BaseWeight} \times (1.0 - \text{DecayFactor} \times \text{AgeDays})$$

### Knowledge Graph Evolution Pipeline
1. **Link**: The system detects references in commits and Slack messages to link entities.
2. **Infer**: Identifies implicit dependencies (e.g., if a developer modifies a file that blocks a PR, link the developer to the blocking issue).
3. **Decay**: Decreases relationship weights over time if no new interactions occur.

### Component Responsibilities & Operational Metrics
* **Graph Traverser**: Resolves relational queries using recursive database lookups.
* **Relationship Decayer**: Runs a daily job to update relationship weights.
* **Advantages**: Resolves complex relational queries, tracks project context, and updates dependencies.
* **Disadvantages**: High database overhead for recursive graph queries.

---

## 15. Multi-Tenant Isolation Strategy

This system enforces multi-tenant isolation across all databases, caches, queues, and compute environments.

```
                           [Tenant Web API Gateway]
                                      │
          ┌───────────────────────────┼───────────────────────────┐
          ▼                           ▼                           ▼
 ┌───────────────────┐       ┌───────────────────┐       ┌───────────────────┐
 │ PostgreSQL DB     │       │   Redis Cache     │       │   Celery Queue    │
 │ (RLS by Tenant ID)│       │ (Keys by Tenant)  │       │ (Queues by Tenant)│
 └───────────────────┘       └───────────────────┘       └───────────────────┘
```

### Isolation Matrix

| Layer | Isolation Strategy | Enforcement Mechanism |
| :--- | :--- | :--- |
| **PostgreSQL** | Row-Level Security (RLS) | Tables configure RLS policies utilizing `tenant_id`. |
| **pgvector** | Namespace Index Isolation | Queries include `tenant_id` filters. |
| **Redis** | Key Namespace Partitioning | Keys are prefixed with the tenant ID: `tenant:{id}:*`. |
| **Event Bus** | Topic Routing Key Isolation | Routing keys are prefixed with the tenant ID. |
| **Background Workers**| Queue Isolation | High-priority tenants route to dedicated worker queues. |
| **WebSockets** | Channel Isolation | Connections are authenticated and bound to tenant channels. |

### Operational Rationale
* **Row-Level Security (RLS)**: Enforces data isolation within a single database, reducing infrastructure overhead while maintaining tenant boundaries.
* **Key Namespace Partitioning**: Simple prefixing in Redis provides fast, isolated keyspaces without the overhead of multiple Redis instances.
* **Queue Isolation**: Enforces resource isolation, ensuring resource-heavy tasks from one tenant do not block other tenants' queues.
* **Cross-Tenant Audits**: Automated monitors scan query plans and databases to identify and alert on data leaks.

---

## 16. Architectural Decision Records (ADR)

### ADR 007: Redis Streams vs. PostgreSQL Transactional Outbox for Event Bus
* **Context**: We need to guarantee event delivery while minimizing database write overhead.
* **Decision**: We use **PostgreSQL tables** as the transactional outbox store (ensuring atomic commits), coupled with **Redis Streams** as the active event broker.
* **Consequence**: Delivers transactional consistency and fast message routing, with automatic recovery via outbox database logs in the event of a broker outage.

### ADR 008: pgvector vs. Dedicated Vector Database (Pinecone/Milvus)
* **Context**: Deploying a dedicated vector database increases system complexity and operational costs.
* **Decision**: Use **PostgreSQL with the pgvector extension** and HNSW indexes.
* **Consequence**: Keeps the data stack simple, maintains transactional consistency, and supports fast semantic search within a single database instance.

### ADR 009: Claude 3.5 Sonnet vs. GPT-4o for Primary Agent Planning
* **Context**: Agent planning tasks require high reasoning accuracy and consistent JSON formatting.
* **Decision**: Route planning tasks to **Claude 3.5 Sonnet**, using **GPT-4o** as a fallback.
* **Consequence**: Maximizes planning accuracy and reduces formatting errors, with GPT-4o providing a high-availability fallback path.
