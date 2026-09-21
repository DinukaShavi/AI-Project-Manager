import json
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID
from loguru import logger
from app.db.session import SessionLocal
from app.services.context import ContextEngineService
from app.services.context_snapshot import ContextSnapshotService
from app.services.integration import IntegrationService
from app.repositories.graph import GraphRepository

# GitHub's own PR-description linking keywords (close/closes/closed, fix/fixes/fixed,
# resolve/resolves/resolved) followed by an issue reference, e.g. "Resolves #42".
_RESOLVES_PATTERN = re.compile(r"(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)", re.IGNORECASE)

# Namespace for deriving stable UUIDs from external provider identifiers (GitHub issue/PR
# numbers, Jira issue keys, Slack message timestamps) -- ContextChunk.source_id is a UUID
# column shared with the manual /context/index API, so external non-UUID keys are mapped
# deterministically rather than migrating the column. The same external id always derives
# the same UUID, which is what makes ContextEngineService.index_document's delete-then-reindex
# idempotency work correctly across repeated/redelivered events for the same entity.
_SOURCE_ID_NAMESPACE = uuid.UUID("6f6a9b0a-6e6a-4a7a-9e2e-6c8f2a6b7d1c")


def derive_source_id(provider: str, external_id: str) -> UUID:
    return uuid.uuid5(_SOURCE_ID_NAMESPACE, f"{provider}:{external_id}")


class ContextIngestionService:
    """Consumes real webhook/backup-sync events published to the Event Bus (github_stream,
    jira_stream, slack_stream) and indexes their real text content into the Context Engine
    (ContextChunk/ContextEmbedding), so the Context Engine reflects real integration activity
    automatically instead of only what a caller manually POSTs to /context/index.

    Registered as the handler for BackgroundEventWorker's context-ingestion subscriptions
    (app/workers/event_worker.py). Each call opens its own DB session, matching every other
    background-loop handler in this codebase (outbox loop, calendar poller, etc.) since a
    long-lived subscribe() loop must not hold one session across arbitrarily many events.
    """

    def _parse_field(self, value: Any) -> Any:
        """event_data fields arrive as native Python objects when InMemoryEventBus dispatches
        (dev/test default, USE_REDIS=False) but as flat strings from Redis Streams in
        production (USE_REDIS=True) -- decode JSON-looking strings back into dict/list."""
        if isinstance(value, str) and value[:1] in "{[":
            try:
                return json.loads(value)
            except (json.JSONDecodeError, ValueError):
                return value
        return value

    async def handle_event(self, msg_id: str, event_data: dict) -> None:
        try:
            organization_id = UUID(str(event_data.get("organization_id")))
        except (TypeError, ValueError):
            logger.warning(f"Context ingestion: skipping event {msg_id} with missing/invalid organization_id.")
            return

        raw_project_id = event_data.get("project_id")
        project_id: Optional[UUID] = None
        if raw_project_id and raw_project_id not in ("None", "null"):
            try:
                project_id = UUID(str(raw_project_id))
            except ValueError:
                project_id = None

        payload = self._parse_field(event_data.get("payload")) or {}
        if not isinstance(payload, dict):
            return
        provider = payload.get("provider", "")

        extracted = None
        if provider == "github":
            extracted = self._extract_github(payload)
        elif provider == "jira":
            extracted = self._extract_jira(payload)
        elif provider == "slack":
            extracted = self._extract_slack(payload)
        elif provider == "calendar":
            extracted = self._extract_calendar(payload)

        if not extracted:
            return
        source_type, external_id, text, metadata, resolve = extracted
        if not text or not text.strip():
            return

        async with SessionLocal() as session:
            if project_id is None and resolve is not None:
                integration_service = IntegrationService(session)
                try:
                    project_id = await resolve(integration_service, organization_id)
                except Exception as e:
                    logger.warning(f"Context ingestion: project resolution failed for event {msg_id}: {e}")

            source_id = derive_source_id(provider, external_id)
            indexed_successfully = False
            try:
                context_service = ContextEngineService(session)
                chunks = await context_service.index_document(
                    organization_id=organization_id,
                    source_type=source_type,
                    source_id=source_id,
                    text=text,
                    project_id=project_id,
                    metadata=metadata,
                )
                indexed_successfully = True
                logger.info(
                    f"Context ingestion: indexed {len(chunks)} chunk(s) for {source_type}:{external_id} "
                    f"(org={organization_id})."
                )
            except Exception as e:
                logger.error(f"Context ingestion: failed to index event {msg_id} ({source_type}:{external_id}): {e}")

            # Push the real activity live to any connected WebSocket clients for this org
            # (Phase 66) -- reuses the same ConnectionManager the OAuth connection-status
            # broadcast already uses, rather than a second real-time mechanism. Skipped when
            # indexing failed, or no real project was resolved (an unscoped event isn't
            # useful against project-scoped dashboard UI).
            if indexed_successfully and project_id is not None:
                try:
                    from datetime import datetime, timezone
                    from app.realtime.connection_manager import get_connection_manager

                    await get_connection_manager().broadcast_to_organization(
                        {
                            "event": "activity_update",
                            "payload": {
                                "source_type": source_type,
                                "provider": provider,
                                "title": metadata.get("title", "") if metadata else "",
                                "project_id": str(project_id),
                                "url": (metadata or {}).get("url"),
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                            },
                        },
                        organization_id,
                    )
                except Exception as e:
                    logger.warning(f"Context ingestion: activity broadcast failed for event {msg_id}: {e}")

            # Derive Knowledge Graph edges from the same already-parsed payload. Edges are
            # project-scoped (KnowledgeGraphEdge.project_id is NOT NULL), so events that
            # couldn't resolve a project are skipped here -- they were still worth indexing
            # as context above, but aren't queryable via GET /context/projects/{id}/graph
            # without a project anyway.
            if project_id is not None:
                edges = await self._extract_graph_edges(provider, payload, session=session, organization_id=organization_id)
                if edges:
                    try:
                        graph_repo = GraphRepository(session)
                        for source_urn, target_urn, relation_type in edges:
                            await graph_repo.upsert_edge(
                                organization_id, project_id, source_urn, target_urn, relation_type
                            )
                        await session.commit()
                        logger.info(
                            f"Context ingestion: wrote {len(edges)} graph edge(s) for {source_type}:{external_id}."
                        )
                    except Exception as e:
                        logger.error(f"Context ingestion: failed to write graph edges for {msg_id}: {e}")

            # Real one-way Jira issue -> ProjectTask sync (Phase 76): Jira is the source of
            # truth, so this always overwrites title/status/assignee from the real issue.
            # Never runs for events that couldn't resolve a real project (a task needs one).
            if provider == "jira" and project_id is not None:
                try:
                    from app.services.jira_task_sync import JiraTaskSyncService

                    task = await JiraTaskSyncService(session).sync_task_from_issue(
                        organization_id=organization_id,
                        project_id=project_id,
                        issue_key=external_id,
                        summary=(metadata or {}).get("title", ""),
                        status_category=(metadata or {}).get("status_category"),
                        assignee_account_id=(metadata or {}).get("assignee_account_id"),
                    )
                    if task:
                        await session.commit()
                        logger.info(f"Context ingestion: synced ProjectTask for Jira issue {external_id}.")
                except Exception as e:
                    logger.error(f"Context ingestion: Jira task sync failed for event {msg_id}: {e}")

            # Regenerate the project's ContextSnapshot if it's stale (Phase 68) -- throttled
            # so a burst of events doesn't spam regenerations; never runs for events that
            # couldn't resolve a real project, and never breaks real ingestion if it fails.
            if indexed_successfully and project_id is not None:
                try:
                    snapshot_service = ContextSnapshotService(session)
                    if await snapshot_service.is_snapshot_stale(organization_id, project_id):
                        await snapshot_service.generate_snapshot(organization_id, project_id)
                        logger.info(f"Context ingestion: regenerated ContextSnapshot for project {project_id}.")
                except Exception as e:
                    logger.warning(f"Context ingestion: snapshot generation failed for event {msg_id}: {e}")

    async def _extract_graph_edges(
        self,
        provider: str,
        payload: Dict[str, Any],
        session: Optional[Any] = None,
        organization_id: Optional[UUID] = None,
    ) -> List[Tuple[str, str, str]]:
        """Derive (source_urn, target_urn, relation_type) triples from the same normalized
        payload already used for text extraction -- no separate parsing pass. Returns an
        empty list for the (common) case where an event carries no linkable relationship.

        Every provider's user-node URN resolves to a real internal `User` when one is real and
        linked (GitHub/Jira via `ExternalIdentity`, Phase 75; Calendar via a direct `User.email`
        match, Phase 74), and falls back to the external identifier (GitHub login, Jira
        accountId, raw email) when no real link exists -- an honest, expected outcome for an
        assignee/attendee who's never connected their account, not an error."""
        edges: List[Tuple[str, str, str]] = []
        raw = payload.get("raw_payload") or {}

        if provider == "github":
            repo = payload.get("repository") or (raw.get("repository") or {}).get("full_name", "")
            if "pull_request" in raw:
                pr = raw["pull_request"]
                number = pr.get("number")
                pr_urn = f"urn:github:pr:{repo}#{number}"
                for issue_num in _RESOLVES_PATTERN.findall(pr.get("body") or ""):
                    edges.append((pr_urn, f"urn:github:issue:{repo}#{issue_num}", "RESOLVES"))
                assignee = pr.get("assignee") or {}
                login = assignee.get("login")
                if login:
                    fallback = f"urn:github:user:{login}"
                    gh_id = assignee.get("id")
                    target = await self._resolve_user_urn(session, organization_id, "github", str(gh_id) if gh_id else None, fallback)
                    edges.append((pr_urn, target, "ASSIGNED_TO"))
            elif "issue" in raw:
                issue = raw["issue"]
                number = issue.get("number")
                issue_urn = f"urn:github:issue:{repo}#{number}"
                assignee = issue.get("assignee") or {}
                login = assignee.get("login")
                if login:
                    fallback = f"urn:github:user:{login}"
                    gh_id = assignee.get("id")
                    target = await self._resolve_user_urn(session, organization_id, "github", str(gh_id) if gh_id else None, fallback)
                    edges.append((issue_urn, target, "ASSIGNED_TO"))

        elif provider == "jira":
            issue_key = payload.get("issue_key") or ""
            if issue_key:
                fields = (raw.get("issue") or {}).get("fields", {})
                account_id = (fields.get("assignee") or {}).get("accountId")
                if account_id:
                    fallback = f"urn:jira:user:{account_id}"
                    target = await self._resolve_user_urn(session, organization_id, "jira", account_id, fallback)
                    edges.append((f"urn:jira:issue:{issue_key}", target, "ASSIGNED_TO"))

        elif provider == "calendar":
            external_id = payload.get("external_event_id") or ""
            if external_id:
                meeting_urn = f"urn:calendar:meeting:{external_id}"
                for email in payload.get("attendees") or []:
                    target_urn = f"urn:user:email:{email}"
                    if session is not None and organization_id is not None:
                        from sqlalchemy import func, select
                        from app.models.tenant import User

                        res = await session.execute(
                            select(User).where(
                                User.organization_id == organization_id,
                                func.lower(User.email) == email.lower(),
                            )
                        )
                        matched_user = res.scalar_one_or_none()
                        if matched_user:
                            target_urn = f"urn:user:id:{matched_user.id}"
                    edges.append((meeting_urn, target_urn, "ATTENDS"))

        return edges

    async def _resolve_user_urn(
        self,
        session: Optional[Any],
        organization_id: Optional[UUID],
        provider: str,
        external_account_id: Optional[str],
        fallback_urn: str,
    ) -> str:
        """Real, tenant-scoped `ExternalIdentity` lookup (Phase 75) -- resolves a GitHub/Jira
        external account id to `urn:user:id:{id}` when a real, active link exists; returns the
        unchanged external-identifier URN otherwise (unlinked is an honest, expected outcome,
        not an error)."""
        if session is None or organization_id is None or not external_account_id:
            return fallback_urn
        from app.services.external_identity import ExternalIdentityService

        user_id = await ExternalIdentityService(session).resolve_user_by_external_account(
            organization_id, provider, external_account_id
        )
        return f"urn:user:id:{user_id}" if user_id else fallback_urn

    def _extract_github(self, payload: Dict[str, Any]) -> Optional[Tuple[str, str, str, Dict[str, Any], Optional[Any]]]:
        raw = payload.get("raw_payload") or {}
        repo_full_name = payload.get("repository") or (raw.get("repository") or {}).get("full_name", "")
        action = (raw.get("action") or "").lower()
        if action == "deleted":
            return None

        async def resolve(integration_service: IntegrationService, organization_id: UUID):
            return await integration_service.resolve_project_for_github_repo(organization_id, repo_full_name)

        if "issue" in raw and "pull_request" not in raw:
            issue = raw["issue"]
            number = issue.get("number")
            title = issue.get("title") or ""
            body = issue.get("body") or ""
            if not (title or body):
                return None
            return (
                "github_issue",
                f"{repo_full_name}#{number}",
                f"{title}\n\n{body}".strip(),
                {"repo": repo_full_name, "number": number, "action": action, "url": issue.get("html_url"), "title": title},
                resolve,
            )

        if "pull_request" in raw:
            pr = raw["pull_request"]
            number = pr.get("number")
            title = pr.get("title") or ""
            body = pr.get("body") or ""
            if not (title or body):
                return None
            return (
                "github_pr",
                f"{repo_full_name}#{number}",
                f"{title}\n\n{body}".strip(),
                {"repo": repo_full_name, "number": number, "action": action, "url": pr.get("html_url"), "title": title},
                resolve,
            )

        if "comment" in raw:
            comment = raw["comment"]
            comment_id = comment.get("id")
            body = comment.get("body") or ""
            if not body:
                return None
            return (
                "github_comment",
                f"{repo_full_name}#comment-{comment_id}",
                body,
                {"repo": repo_full_name, "comment_id": comment_id, "action": action, "url": comment.get("html_url"), "title": body[:80]},
                resolve,
            )

        return None

    def _extract_jira(self, payload: Dict[str, Any]) -> Optional[Tuple[str, str, str, Dict[str, Any], Optional[Any]]]:
        issue_key = payload.get("issue_key") or ""
        if not issue_key:
            return None
        project_key = payload.get("project_key") or ""

        async def resolve(integration_service: IntegrationService, organization_id: UUID):
            return await integration_service.resolve_project_for_jira_key(organization_id, project_key)

        if payload.get("source") == "backup_sync":
            summary = payload.get("summary") or ""
            status = payload.get("status") or ""
            if not summary:
                return None
            return (
                "jira_issue",
                issue_key,
                summary,
                {
                    "project_key": project_key, "issue_key": issue_key, "status": status,
                    "source": "backup_sync", "title": summary,
                    "status_category": payload.get("status_category"),
                    "assignee_account_id": payload.get("assignee_account_id"),
                },
                resolve,
            )

        raw = payload.get("raw_payload") or {}
        fields = (raw.get("issue") or {}).get("fields", {})
        summary = fields.get("summary") or ""
        description = fields.get("description") or ""
        if isinstance(description, dict):
            # Jira Cloud may send Atlassian Document Format for description; only plain text
            # summaries are indexed here rather than parsing full ADF node trees.
            description = ""
        if not (summary or description):
            return None
        status = (fields.get("status") or {}).get("name", "")
        return (
            "jira_issue",
            issue_key,
            f"{summary}\n\n{description}".strip(),
            {
                "project_key": project_key, "issue_key": issue_key, "status": status,
                "source": "webhook", "title": summary,
                "status_category": ((fields.get("status") or {}).get("statusCategory") or {}).get("key"),
                "assignee_account_id": (fields.get("assignee") or {}).get("accountId"),
            },
            resolve,
        )

    def _extract_slack(self, payload: Dict[str, Any]) -> Optional[Tuple[str, str, str, Dict[str, Any], Optional[Any]]]:
        raw = payload.get("raw_payload") or {}
        event_body = raw.get("event") or {}
        sub_type = event_body.get("type", "")
        if sub_type != "message":
            return None
        # Edits/deletes/bot messages/thread-broadcast echoes carry no top-level "text" or
        # represent a mutation of an already-indexed message; only plain new messages are indexed.
        if event_body.get("subtype"):
            return None
        text = event_body.get("text") or ""
        if not text.strip():
            return None
        channel = payload.get("channel") or event_body.get("channel") or ""
        ts = event_body.get("ts") or ""
        if not channel or not ts:
            return None

        async def resolve(integration_service: IntegrationService, organization_id: UUID):
            return await integration_service.resolve_project_for_slack_channel(organization_id, channel)

        return (
            "slack_message",
            f"{channel}:{ts}",
            text,
            {"channel": channel, "ts": ts, "user": payload.get("user") or event_body.get("user"), "title": text[:80]},
            resolve,
        )

    def _extract_calendar(self, payload: Dict[str, Any]) -> Optional[Tuple[str, str, str, Dict[str, Any], Optional[Any]]]:
        """Calendar meetings (Phase 73) -- unlike GitHub/Jira/Slack, there's no `resolve`
        callback here: sync_calendar_events/create_calendar_event both already know the real
        project_id at the point a Meeting is written (Calendar events are project-scoped from
        creation, never inferred from repo/project-key/channel like the other three), so this
        is called with project_id already set."""
        external_id = payload.get("external_event_id") or ""
        if not external_id:
            return None
        title = payload.get("title") or ""
        description = payload.get("description") or ""
        if not (title or description):
            return None
        attendees = payload.get("attendees") or []
        text = f"{title}\n\n{description}".strip()
        if attendees:
            text += f"\n\nAttendees: {', '.join(attendees)}"
        return (
            "calendar_meeting",
            external_id,
            text,
            {
                "title": title,
                "start_time": payload.get("start_time"),
                "attendees": attendees,
                "url": payload.get("html_link"),
            },
            None,
        )
