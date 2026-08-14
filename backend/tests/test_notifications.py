import asyncio
import uuid
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

import app.db.base # Register models
from app.main import app
from app.models.tenant import Organization, User
from app.models.notification import Notification
from app.db.session import SessionLocal
from tests._auth_helpers import create_authenticated_headers


async def test_notifications_flow():
    print("Initializing Notifications API validation tests...")

    suffix = uuid.uuid4().hex[:6]
    org_a_id = None
    org_b_id = None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            async with SessionLocal() as session:
                org_a = Organization(name=f"Notif Tenant Org A {suffix}", domain=f"notif-a-{suffix}.com")
                org_b = Organization(name=f"Notif Tenant Org B {suffix}", domain=f"notif-b-{suffix}.com")
                session.add_all([org_a, org_b])
                await session.commit()
            org_a_id, org_b_id = org_a.id, org_b.id

            # Org A has two distinct users -- notifications must be scoped per-user, not
            # merely per-organization.
            headers_a1 = await create_authenticated_headers(client, org_a_id, email=f"a1-{suffix}@example.com")
            headers_a2 = await create_authenticated_headers(client, org_a_id, email=f"a2-{suffix}@example.com")
            headers_b = await create_authenticated_headers(client, org_b_id, email=f"b1-{suffix}@example.com")

            async with SessionLocal() as session:
                res = await session.execute(select(User).where(User.organization_id == org_a_id).order_by(User.email))
                users_a = res.scalars().all()
                user_a1 = next(u for u in users_a if u.email.startswith("a1-"))
                user_a2 = next(u for u in users_a if u.email.startswith("a2-"))
                res = await session.execute(select(User).where(User.organization_id == org_b_id))
                user_b = res.scalars().first()

            print(f"Test orgs/users created. Org A={org_a_id} (user1={user_a1.id}, user2={user_a2.id}) Org B={org_b_id} (user={user_b.id})")

            # Seed real Notification rows directly (no application flow currently generates
            # notifications -- this feature's documented scope is only the mark-as-read
            # mutation itself, per api_contract.md section 16.A).
            async with SessionLocal() as session:
                notif_1 = Notification(organization_id=org_a_id, user_id=user_a1.id, title="Sprint Alert", body="CONFIDENTIAL: Sprint 14 at risk.")
                notif_2 = Notification(organization_id=org_a_id, user_id=user_a1.id, title="PR Merged", body="Your PR #42 was merged.")
                session.add_all([notif_1, notif_2])
                await session.commit()
                await session.refresh(notif_1)
                await session.refresh(notif_2)
                notif_1_id, notif_2_id = notif_1.id, notif_2.id

            # 1. Org B cannot mark Org A's user's notification as read by supplying its ID.
            print("\nTest 1: Verifying Org B cannot mark Org A's notification as read...")
            res = await client.put(
                "/api/v1/notifications/read",
                json={"notification_ids": [str(notif_1_id)]},
                headers=headers_b,
            )
            assert res.status_code == 200, res.text
            body = res.json()
            assert body["updated_count"] == 0, f"Org B should not be able to mark Org A's notification read, got: {body}"
            print("SUCCESS: Org B's attempt updated zero notifications.")

            async with SessionLocal() as session:
                unchanged = await session.get(Notification, notif_1_id)
                assert unchanged.is_read is False, "Org B's rejected attempt must not mutate Org A's notification"
            print("SUCCESS: Org A's notification remains unread after Org B's rejected attempt.")

            # 2. A second user WITHIN the same organization cannot mark user_a1's
            # notification as read either -- ownership is per-user, not merely per-org.
            print("\nTest 2: Verifying a same-org, different user cannot mark another user's notification as read...")
            res = await client.put(
                "/api/v1/notifications/read",
                json={"notification_ids": [str(notif_1_id)]},
                headers=headers_a2,
            )
            assert res.status_code == 200, res.text
            assert res.json()["updated_count"] == 0
            async with SessionLocal() as session:
                unchanged = await session.get(Notification, notif_1_id)
                assert unchanged.is_read is False
            print("SUCCESS: Same-org, different-user attempt updated zero notifications; notification remains unread.")

            # 3. The owning user CAN mark their own notifications as read.
            print("\nTest 3: Verifying the owning user can mark their own notifications as read...")
            res = await client.put(
                "/api/v1/notifications/read",
                json={"notification_ids": [str(notif_1_id), str(notif_2_id)]},
                headers=headers_a1,
            )
            assert res.status_code == 200, res.text
            body = res.json()
            assert body["requested_count"] == 2
            assert body["updated_count"] == 2
            print("SUCCESS: Owning user marked both of their own notifications as read.")

            async with SessionLocal() as session:
                n1 = await session.get(Notification, notif_1_id)
                n2 = await session.get(Notification, notif_2_id)
                assert n1.is_read is True
                assert n2.is_read is True
            print("SUCCESS: Both notifications are persisted as read in the database.")

            # 4. A mix of the owner's own (already-read) ID and a nonexistent ID behaves
            # gracefully -- no error, and the count reflects only genuinely-owned matches.
            print("\nTest 4: Verifying a nonexistent notification_id is handled gracefully...")
            res = await client.put(
                "/api/v1/notifications/read",
                json={"notification_ids": [str(notif_1_id), str(uuid.uuid4())]},
                headers=headers_a1,
            )
            assert res.status_code == 200, res.text
            body = res.json()
            assert body["requested_count"] == 2
            assert body["updated_count"] == 1
            print("SUCCESS: Nonexistent notification_id handled gracefully with no error.")

        finally:
            print("\nCleaning up notifications test database entries...")
            async with SessionLocal() as session:
                for oid in [o for o in [org_a_id, org_b_id] if o]:
                    notif_res = await session.execute(select(Notification).where(Notification.organization_id == oid))
                    for n in notif_res.scalars().all():
                        await session.delete(n)
                    user_res = await session.execute(select(User).where(User.organization_id == oid))
                    for u in user_res.scalars().all():
                        await session.delete(u)
                    await session.commit()

                    org_res = await session.execute(select(Organization).where(Organization.id == oid))
                    db_org = org_res.scalar_one_or_none()
                    if db_org:
                        await session.delete(db_org)
                await session.commit()
            print("Cleanup completed.")

    print("\nAll Notifications API tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_notifications_flow())
