# AI System Design: AI-Powered Technical Project Manager (AI-TPM)

This document details the cognitive architecture, multi-agent collaboration logic, planning algorithms, predictive systems, prompts, and cost optimizations for the AI-Powered Technical Project Manager (AI-TPM).

---

## 1. AI Reasoning & Cognitive Architecture

The AI-TPM uses a hybrid reasoning system that combines **structured state machines** (for execution flow) with **probabilistic LLM reasoning** (for planning and assessment).

```
 [User Input / Event] ──► [Input Classifier & Goal Decomposition]
                                        │
                                        ▼ (Deconstruct to Sub-tasks)
                             [Planning & DAG Generator]
                                        │
                          ┌──────────────┴──────────────┐
                          ▼                             ▼
                  [Select Tool/Agent]            [Validate Constraints]
                          │                             │
                          └──────────────┬──────────────┘
                                        ▼
                             [Execute step in Sandbox]
                                        │
                                        ▼ (Self-Reflection Check)
                              [Critique / Verification]
                                        │
                      ┌──────────────────┴──────────────────┐
                      ▼ Pass                                ▼ Fail
              [Execute & Learn]                      [Rollback & Replanning]
```

### Goal Decomposition & Planning
* **Task Decomposition**: Goals are decomposed using a hierarchical task network (HTN) planner. The system breaks a high-level goal down into primitive tasks that map directly to registered tools.
* **Planning Loop**: The Planning Agent generates a Directed Acyclic Graph (DAG) of execution steps. Each node represents a specific task, and edges define dependency relationships.

### Tool & Agent Selection
* **Agent Routing**: The Manager Agent maps task requirements (declared in the DAG) to agent capability profiles.
* **Tool Validation**: Agents match task descriptions against the tool registry using semantic search over tool metadata schemas.

### Hallucination Prevention & Validation
* **Schema Enforcement**: Tool inputs are validated against Pydantic schemas before execution.
* **Execution Validation**: Tool outputs are verified by a separate verification check. If the output does not match expected post-conditions, the action is marked as failed, and the agent triggers a replanning loop.

### Human-in-the-Loop (HITL) & Learning
* **Approval Gates**: Mutating actions (e.g., merging code or deleting resources) require explicit human approval if the reasoning confidence falls below a set threshold.
* **Feedback Loop**: When a user rejects or modifies an agent's plan, the feedback is saved to the long-term memory vector index, helping the planning agent optimize future runs.

---

## 2. Multi-Agent Collaboration Protocol

Agents communicate asynchronously using a JSON-based envelope format over the shared Event Bus.

```
 [Manager Agent] ──(Dispatches Plan)──► [Event Bus] ──► [Execution Agent (Jira)]
                                                            │
                                                            ▼ (Performs action)
                                                        [Tool Registry]
                                                            │
                                                            ▼ (Returns result)
 [Manager Agent] ◄──(Update Event) ◄── [Event Bus] ◄────────┘
```

### Message Envelope Structure
```json
{
  "message_id": "uuid-v4",
  "correlation_id": "uuid-v4",
  "sender": "agent:manager",
  "recipient": "agent:jira",
  "timestamp": "2026-07-17T21:30:00Z",
  "payload": {
    "command": "CREATE_TICKET",
    "params": {
      "summary": "Fix validation bug in auth middleware",
      "project_key": "PROJ"
    }
  }
}
```

### Delegation & Conflict Resolution
* **Delegation**: The Manager Agent assigns sub-tasks by posting command events. The target agent claims the task, updates its status to `executing`, and processes the request.
* **Conflict Resolution**: Writes to shared project properties (e.g., ticket status) are resolved using **Optimistic Concurrency Control (OCC)**, using version numbers tracked by the Context Engine.
* **Retry Loop**: If an agent fails to respond within a set timeout window, the Manager Agent republishes the command event up to 3 times before routing the task to a failure recovery queue.

---

## 3. Planning Algorithm Case Study: "Why is Sprint 25 delayed?"

This section details how the Planning Agent resolves a complex question step-by-step.

```
       [User Input: "Why is Sprint 25 delayed?"]
                            │
                            ▼
     [Context Retrieval: Graph traversal & Semantic query]
                            │
                            ▼
     [Task Decomposition: Analyze tickets, commits, & logs]
                            │
                            ▼
  [Dependency Analysis: Critical path identification in DAG]
                            │
                            ▼
  [Verification: Validate metrics against current sprint state]
                            │
                            ▼
                 [Consolidate Diagnosis]
```

### Step 1: Context Retrieval
The system queries the database to retrieve relevant metadata:
* Retrieve Sprint 25 ticket states from the `projects` and `analytics_metrics` tables.
* Retrieve linked code repositories using the `repositories` table.
* Query the `context_snapshots` vector index for recent sprint updates.

### Step 2: Task Decomposition
The Planning Agent creates an execution DAG to analyze potential bottleneck sources:
* **Node A**: Analyze Jira ticket velocity and identify overdue tasks.
* **Node B**: Cross-reference uncompleted tickets with open GitHub Pull Requests.
* **Node C**: Check Slack logs for blockers or high-priority changes.
* **Node D**: Check developer calendar logs for potential meeting conflicts.

### Step 3: Dependency Graph & Analysis
The Planning Agent executes the DAG nodes to identify delays:
* **Node A Result**: Identifies that ticket `PROJ-101` (5 story points) is blocked by ticket `PROJ-99`.
* **Node B Result**: Pull Request `#404` (which resolves `PROJ-99`) has failed its CI test pipeline.
* **Node C Result**: Slack logs indicate the developer assigned to `PROJ-99` is out of office.
* **Node D Result**: Meeting logs show the team has had 4 hours of meetings per day this week.

### Step 4: Verification & Synthesis
The Analytics Agent calculates metric parameters:
* Current sprint velocity: 12 story points (expected: 25).
* Target completion confidence: 18% (calculated via Monte Carlo simulation).
* Critical path: `PR-404` -> `PROJ-99` -> `PROJ-101`.

### Step 5: Final Response Formulation
The Manager Agent consolidates the findings into an actionable summary:
* **Primary Cause**: Sprint 25 is delayed because ticket `PROJ-101` is blocked by `PROJ-99`, which is currently stuck on a failing PR (`PR-404`).
* **Secondary Factor**: High meeting overhead has reduced developer coding time.
* **Actionable Recommendation**: Reassign `PR-404` to an active developer to resolve the failing test.

---

## 4. Context Understanding & Aggregation

The Context Engine aggregates data from multiple sources into a single graph representation:

```
  [GitHub Commits]    [Jira Tickets]    [Slack Chats]    [Calendar Meetings]
         │                   │                │                   │
         └───────────┬───────┴────────┬───────┴───────────────────┘
                     ▼                ▼
             [Normalization & Mapping to Unified URNs]
                                      │
                                      ▼
                      [Knowledge Graph Adjacency Lists]
                                      │
                                      ▼
                        [pgvector Semantic Embeddings]
```

### Context Aggregation Strategy
* **Data Mapping**: Entities are assigned unique identifiers (URNs) to support cross-referencing.
* **Graph Relations**: Entities are linked using adjacency records in the database (e.g., linking a GitHub commit to a Jira issue).
* **Semantic Search**: Text content (such as Slack messages and meeting transcripts) is converted to vector embeddings and stored in the database.
* **Context Generation**: When a query is run, the engine builds a context payload by retrieving related graph nodes and performing semantic searches over vector databases.

---

## 5. Tool Selection Algorithm

The agent uses a decision tree model to determine the appropriate tool for a task:

```
                                [Identify Goal]
                                       │
                        ┌──────────────┴──────────────┐
                 Mutating Action?              Read Only?
                        │                             │
              ┌─────────┴─────────┐                   ▼
       High Risk?             Low Risk?        [Execute Local Search]
              │                   │
              ▼                   ▼
     [Human Approval]      [Execute Sandbox]
```

### Decision Parameters
* **Read Actions**: Handled by executing queries against local caches or vector databases.
* **Write/Mutate Actions**: Checked against the tool registry's security profile.
* **Scheduling/Time Actions**: Routed to the Calendar Agent.
* **Communication Actions**: Routed to the Slack Agent.
* **High-Risk Actions**: Routed to the human approval queue if the reasoning confidence falls below a set threshold.

---

## 6. Recommendation Engine

The system generates recommendations by processing context metrics through a scoring matrix.

### Recommendation Scenarios
1. **Developer Overload**: Triggered when a developer is assigned high-priority story points that exceed their average sprint velocity by 30%.
2. **Sprint Delay Prediction**: Simulated using Monte Carlo analyses on remaining task points.
3. **PR Bottlenecks**: Flags PRs that have been open for over 48 hours or have more than 15 unresolved comments.

### Recommendation Workflow Lifecycle
```
[Identify Issue] ──► [Evaluate Priority Score] ──► [Generate Options]
                                                        │
                            ┌───────────────────────────┴───────────────────────────┐
                            ▼ Approved                                              ▼ Rejected
                  [Publish Recommendation]                                   [Discard & Log]
```

---

## 7. Predictive Models & Math

The system uses statistical models to forecast project risks and timelines.

### Sprint Completion Forecast
Sprint completion likelihood is calculated using a Monte Carlo simulation.
* **Variables**:
  * $R$: Remaining story points in the sprint.
  * $V$: Historical sprint velocity distribution ($\mu_v$, $\sigma_v$).
  * $T$: Days remaining in the sprint.
* **Simulation Loop**:
  Run 10,000 iterations to calculate the probability of completing $R$ points within $T$ days:
  $$P(\text{Completion}) = \frac{1}{N} \sum_{i=1}^{N} \mathbb{I}\left(V_i \times T \ge R\right)$$

### Pull Request Merge Time Forecast
Predicts the hours needed to merge an open Pull Request.
* **Model**: Linear regression with weighted features.
* **Features**:
  * $C$: Code changes (lines of code).
  * $F$: Files changed.
  * $D$: Developer experience score.
  * $A$: Active reviewer response times.
* **Formula**:
  $$\text{Merge Time (Hours)} = w_1 C + w_2 F - w_3 D + \sum w_i A_i + \epsilon$$

### Developer Workload Score
Calculates developer load to prevent burnout.
* **Formula**:
  $$\text{Workload Score} = \sum_{i \in \text{Issues}} \text{PriorityWeight}_i \times \text{StoryPoints}_i$$
  * *Scale*: Values $> 1.5 \times \text{Historical Capacity}$ trigger an overload alert.

---

## 8. Memory Strategy

Memory is managed across five layers to optimize retrieval speeds and storage cost:

```
  [Ephemeral Workspace] ──► [Redis Hashes (Short-term)] ──► [Purged on complete]
  
  [Task Logs & Logs]    ──► [pgvector Index (Long-term)] ──► [Semantic search]
  
  [Chat Logs]           ──► [Summarization Worker]      ──► [Write summaries]
```

### Memory Retrieval Metrics
* **Semantic Search**: Text queries are converted into embeddings using an OpenAI text-embedding model. A cosine-distance query is run on the pgvector index.
* **Key-Value Match**: Exact keys (such as active configuration options or cached user states) are retrieved directly from Redis.
* **Summarization**: When conversation logs exceed the token threshold, the system summarizes the oldest entries, saves the summary to the vector index, and truncates the log.

---

## 9. Prompt Engineering Specification

Prompts are version-controlled and stored in the database (`prompt_versions`).

### Planning Prompt Template
```
System Role: You are the Planning Agent for an enterprise technical project manager.
Your task is to decompose the user's goal into a Directed Acyclic Graph (DAG) of execution steps.

Inputs:
- Project ID: {{project_id}}
- Goal: {{goal}}
- Active Context: {{context_summary}}

Constraints:
1. Output MUST be valid JSON matching the schema: {"steps": {"step_name": {"agent": "string", "command": "string", "dependencies": []}}}
2. Use only registered execution agents: GitHubAgent, JiraAgent, SlackAgent, CalendarAgent, AnalyticsAgent.
3. Validate dependencies to ensure no cycles exist.
```

### Reflection Prompt Template
```
System Role: You are the Reflection Agent.
Your task is to critique the proposed plan and check for logical errors, omissions, or security issues.

Proposed Plan:
{{proposed_plan}}

Context State:
{{context_state}}

Analyze:
1. Are the planned tool calls safe and authorized?
2. Does the plan contain logic loops?
3. What is the confidence score (0.0 to 1.0) of this plan?
```

---

## 10. Self-Reflection & Execution Loop

The system uses a self-reflection loop to validate and adjust its actions:

```
 [Plan] ──► [Execute Node in Sandbox] ──► [Observe Output] ──► [Reflect on Result]
                                                                        │
                                   ┌────────────────────────────────────┴────────────────────────────────────┐
                                   ▼ Pass                                                                    ▼ Fail
                            [Execute Next Node]                                                       [Trigger Replanning]
```

### Reflection Mechanics
1. **Observe**: The agent captures tool responses, exit codes, and error logs.
2. **Reflect**: The reflection agent evaluates whether the step met its target objectives.
3. **Improve**: If a step fails, the agent writes the error logs to its short-term memory, adjusts its approach, and regenerates the plan.

---

## 11. Human Approval System

Human approval policies are configured based on target safety requirements.

```
 [Action Requested] ──► [Check Confidence Score]
                               │
            ┌──────────────────┴──────────────────┐
            ▼ Score >= Threshold                  ▼ Score < Threshold
     [Execute Autonomously]               [Queue Approval Request]
```

### Action Category Policies
* **Autonomous Actions**: Read queries, Slack notifications, ticket status updates (confidence $>0.7$).
* **Approval Actions**: Pull Request merges, repository creations, calendar event cancellations, slack messaging broadcasts (confidence $<0.8$).

---

## 12. Failure Recovery & Resiliency

To handle system errors, the framework implements a multi-tier recovery strategy:

### Failure Strategies
* **Tool Failures**: Retry the operation using exponential backoff. If the failure persists, identify alternative tools that match the target capabilities.
* **API Outages**: Cache outgoing requests in the Event outbox queue, then pause processing until the provider API returns online.
* **LLM Hallucinations**: Run output validations. If validation fails, resubmit the prompt with the validation error details.

---

## 13. Model Routing Architecture

Tasks are routed to models based on speed, capability, and cost requirements:

```
                 [Incoming Task]
                        │
         ┌──────────────┼──────────────┐
         ▼ Context      ▼ Reasoning    ▼ Vector Search
     [Gemini 1.5]  [Claude 3.5 Sonnet] [text-embedding-3]
```

### Model Selection
* **Claude 3.5 Sonnet**: Used for complex reasoning, planning, code analysis, and reflection tasks.
* **Gemini 1.5 Flash**: Used for high-volume context parsing, log analysis, and database aggregation.
* **Open-Source (Llama 3)**: Used for classification, schema validation, and simple routing tasks.
* **Cohere Rerank**: Used to rank search results before injection into prompt contexts.

---

## 14. Cost Optimization Strategy

To control operating costs, we implement the following optimizations:

```
 [Token Ingestion] ──► [Reranker Filter] ──► [Summarized Prompt Context] ──► [LLM API call]
```

### Cost Optimization Controls
* **Reranking**: Use semantic filters to remove irrelevant text before passing prompts to the LLM.
* **Query Caching**: Cache common queries in Redis to avoid duplicate API calls.
* **Summarization**: Compress historical chat threads to keep prompt sizes small.
* **Structured Prompts**: Restrict agent response lengths to minimize output tokens.

---

## 15. Future Evolution: The Autonomous Engineering Manager

The AI-TPM is designed to support future evolution into an autonomous engineering manager.

```
                   [Continuous Project Monitor]
                                │
        ┌───────────────────────┼───────────────────────┐
        ▼                       ▼                       ▼
 [Sprint Retrospectives]  [Standup Summaries]     [Auto Load Balancer]
```

### Target Capabilities
* **Autonomous Standups**: The system monitors GitHub and Jira, identifies blockers, and publishes daily standup summaries on Slack.
* **Automatic Retrospectives**: Generates sprint retrospectives by analyzing cycle times, blocker tickets, and commit logs.
* **Dynamic Workload Balancing**: Automatically reassigns tasks if a developer becomes overloaded or goes out of office.
