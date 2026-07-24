# Implementation Rules & Guidelines: AI-Powered TPM

This document outlines the strict rules and guidelines for implementing changes in the AI-Powered Technical Project Manager (AI-TPM) codebase.

---

## 1. Clean Architecture Boundaries
* **Strict Separation of Concerns**: Keep business use cases (services), database access (repositories/CRUD), and delivery (API/websockets) decoupled.
* **Inner circles cannot reference outer circles**: Domain schemas (`schemas/`) and database models (`models/`) must not import database session helpers or API routing frameworks.
* **Stateless Services**: Service classes must be stateless and accept database sessions or adapters via dependency injection on every call.
* **Repository Pattern (CRUD)**: Direct database queries using SQLAlchemy must not be written inside API routers or services. Use repository classes or CRUD helpers to interact with the database.

---

## 2. Row-Level Security (RLS) & Multi-Tenancy Rules
* **Direct Tenant Columns**: To avoid nested join queries and ensure optimal index scanning, `organization_id` must exist directly on all operational/tenant-specific tables.
* **Tenant Isolation**: Row-Level Security (RLS) must be enabled on all tenant-specific tables to enforce database boundaries at the database engine level.
* **Bypass Policies**: SuperAdmin/system operations can bypass RLS via session configurations (`app.bypass_rls = 'true'`), which must be scoped to the transaction block (`is_local=True`) to avoid connection pool leakage.

---

## 3. Post-Fix Action Plan
* **Post-Fix Action Plan Requirement**: After completing any code fix, configuration change, or bug fix, ALWAYS provide clear, step-by-step instructions on what the user should do next to test, verify, or interact with the change (e.g., browser refresh, terminal command to run, endpoint to call, UI buttons to click).

---

## 4. Coding & Testing Standards
* **Conventional Commits**: Commit messages must follow the Conventional Commits specification.
* **Unit Testing**: Tests must isolate logic by mocking external calls, databases, and APIs. Code coverage target: > 85%.
* **Integration Testing**: Runs end-to-end tests against real PostgreSQL, Redis, and Celery containers.
