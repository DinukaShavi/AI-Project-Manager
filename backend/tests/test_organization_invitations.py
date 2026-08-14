import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

import app.db.base # Register models
from app.main import app
from app.models.tenant import Organization, User, Role
from app.models.invitation import Invitation
from app.db.session import SessionLocal
from app.core.security import get_password_hash


async def test_organization_invitations_flow():
    print("Initializing Organization Creation & Invitation validation tests...")

    suffix = uuid.uuid4().hex[:6]
    org_a_id = None
    org_b_id = None
    created_user_ids = []

    org_name = f"Invite Test Org {suffix}"
    domain = f"invite-{suffix}.com"
    admin_email = f"invite-admin-{suffix}@example.com"
    admin_password = "InviteAdminPass123!"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            # 1. Organization creation is the real, unauthenticated bootstrap endpoint.
            print("\nTest 1: Creating a new organization with its founding OrgAdmin...")
            res = await client.post(
                "/api/v1/organizations",
                json={
                    "organization_name": org_name,
                    "admin_email": admin_email,
                    "admin_full_name": "Founding Admin",
                    "admin_password": admin_password,
                    "domain": domain,
                },
            )
            assert res.status_code == 201, f"Expected 201, got {res.status_code}: {res.text}"
            body = res.json()
            org_a_id = uuid.UUID(body["organization_id"])
            admin_user_id = uuid.UUID(body["admin_user"]["id"])
            created_user_ids.append(admin_user_id)
            assert body["name"] == org_name
            assert set(body["admin_user"]["roles"]) == {"Developer", "OrgAdmin"}, body["admin_user"]["roles"]
            print(f"SUCCESS: Organization {org_a_id} created with OrgAdmin {admin_user_id}.")

            # 2. Duplicate admin email is rejected with a clean 400.
            print("\nTest 2: Verifying a duplicate admin email is rejected...")
            res = await client.post(
                "/api/v1/organizations",
                json={
                    "organization_name": "Another Org",
                    "admin_email": admin_email,
                    "admin_full_name": "Someone Else",
                    "admin_password": admin_password,
                },
            )
            assert res.status_code == 400, f"Expected 400, got {res.status_code}: {res.text}"
            print("SUCCESS: Duplicate admin email correctly rejected.")

            # 3. Duplicate domain is rejected.
            print("\nTest 3: Verifying a duplicate domain is rejected...")
            res = await client.post(
                "/api/v1/organizations",
                json={
                    "organization_name": "Yet Another Org",
                    "admin_email": f"other-{suffix}@example.com",
                    "admin_full_name": "Someone Else",
                    "admin_password": admin_password,
                    "domain": domain,
                },
            )
            assert res.status_code == 400, f"Expected 400, got {res.status_code}: {res.text}"
            print("SUCCESS: Duplicate domain correctly rejected.")

            admin_res = await client.post("/api/v1/auth/login", json={"email": admin_email, "password": admin_password})
            assert admin_res.status_code == 200
            admin_headers = {"Authorization": f"Bearer {admin_res.json()['access_token']}"}

            org_b_admin_email = f"invite-b-admin-{suffix}@example.com"
            org_b = Organization(name=f"Invite Test Org B {suffix}", domain=f"invite-b-{suffix}.com")
            async with SessionLocal() as session:
                session.add(org_b)
                await session.flush()
                org_b_id = org_b.id
                org_b_admin_role = (await session.execute(select(Role).where(Role.name == "OrgAdmin"))).scalar_one()
                org_b_admin = User(
                    organization_id=org_b_id, email=org_b_admin_email, full_name="Org B Admin",
                    hashed_password=get_password_hash(admin_password),
                )
                org_b_admin.roles.append(org_b_admin_role)
                session.add(org_b_admin)
                await session.commit()
            org_b_login = await client.post("/api/v1/auth/login", json={"email": org_b_admin_email, "password": admin_password})
            assert org_b_login.status_code == 200, org_b_login.text
            org_b_headers = {"Authorization": f"Bearer {org_b_login.json()['access_token']}"}

            # 4. A non-admin (Developer) cannot create invitations.
            print("\nTest 4: Verifying a Developer cannot create invitations (403)...")
            dev_email = f"invite-dev-{suffix}@example.com"
            res = await client.post(
                "/api/v1/users/register",
                json={"email": dev_email, "full_name": "Plain Dev", "organization_id": str(org_a_id), "password": admin_password},
            )
            assert res.status_code == 201, res.text
            created_user_ids.append(uuid.UUID(res.json()["id"]))
            dev_login = await client.post("/api/v1/auth/login", json={"email": dev_email, "password": admin_password})
            dev_headers = {"Authorization": f"Bearer {dev_login.json()['access_token']}"}

            res = await client.post("/api/v1/organizations/invitations", json={"email": "someone@example.com", "role_name": "Developer"}, headers=dev_headers)
            assert res.status_code == 403, f"Expected 403, got {res.status_code}: {res.text}"
            print("SUCCESS: Developer correctly denied invitation creation.")

            # 5. OrgAdmin creates a real invitation; token returned once.
            print("\nTest 5: OrgAdmin creates an invitation...")
            invitee_email = f"invitee-{suffix}@example.com"
            res = await client.post(
                "/api/v1/organizations/invitations",
                json={"email": invitee_email, "role_name": "ProjectManager"},
                headers=admin_headers,
            )
            assert res.status_code == 201, f"Expected 201, got {res.status_code}: {res.text}"
            invite_body = res.json()
            token = invite_body["token"]
            assert invite_body["email"] == invitee_email
            assert invite_body["role"] == "ProjectManager"
            assert invite_body["status"] == "pending"
            assert token
            print(f"SUCCESS: Invitation created for {invitee_email} with role ProjectManager.")

            # 6. Re-inviting the same email supersedes the old invite (no duplicate pending rows).
            print("\nTest 6: Verifying re-inviting the same email supersedes the previous token...")
            res = await client.post(
                "/api/v1/organizations/invitations",
                json={"email": invitee_email, "role_name": "ProjectManager"},
                headers=admin_headers,
            )
            assert res.status_code == 201, res.text
            new_token = res.json()["token"]
            assert new_token != token

            res = await client.get("/api/v1/organizations/invitations", headers=admin_headers)
            assert res.status_code == 200
            matching = [i for i in res.json()["invitations"] if i["email"] == invitee_email]
            pending = [i for i in matching if i["status"] == "pending"]
            assert len(pending) == 1, f"Expected exactly 1 pending invite after re-invite, got {len(pending)}"
            assert any(i["status"] == "revoked" for i in matching), "Expected the superseded invite to be marked revoked"
            assert "token" not in matching[0], "GET /organizations/invitations must never return the raw token"
            print("SUCCESS: Re-inviting superseded the stale token; list never exposes tokens.")
            token = new_token

            # 7. Inviting an existing org member is rejected.
            print("\nTest 7: Verifying inviting an existing member is rejected...")
            res = await client.post(
                "/api/v1/organizations/invitations",
                json={"email": dev_email, "role_name": "Developer"},
                headers=admin_headers,
            )
            assert res.status_code == 400, f"Expected 400, got {res.status_code}: {res.text}"
            print("SUCCESS: Inviting an existing member correctly rejected.")

            # 8. THE CRITICAL CHECK: an unrelated org's admin cannot see or revoke Org A's invitation.
            print("\nTest 8: Verifying cross-tenant isolation on invitations...")
            res = await client.get("/api/v1/organizations/invitations", headers=org_b_headers)
            assert res.status_code == 200
            assert all(i["email"] != invitee_email for i in res.json()["invitations"]), "Org B must not see Org A's invitations"

            res_db = None
            async with SessionLocal() as session:
                inv_res = await session.execute(select(Invitation).where(Invitation.token == token))
                inv_row = inv_res.scalar_one()
                res_db = inv_row.id
            res = await client.delete(f"/api/v1/organizations/invitations/{res_db}", headers=org_b_headers)
            assert res.status_code == 404, f"Expected 404 for cross-tenant revoke, got {res.status_code}: {res.text}"
            async with SessionLocal() as session:
                inv_row = await session.get(Invitation, res_db)
                assert inv_row.status == "pending", "Org B's rejected revoke attempt must not have changed Org A's invitation"
            print("SUCCESS: Cross-tenant invitation access correctly rejected (404); state unchanged.")

            # 9. Accepting the invitation creates a real user with the invited role, in the
            # inviting organization -- not whatever the request body might claim.
            print("\nTest 9: Accepting the invitation creates a real account with the invited role...")
            res = await client.post(
                f"/api/v1/organizations/invitations/{token}/accept",
                json={"full_name": "Invited PM", "password": "InviteePass123!"},
            )
            assert res.status_code == 201, f"Expected 201, got {res.status_code}: {res.text}"
            accepted = res.json()
            created_user_ids.append(uuid.UUID(accepted["id"]))
            assert accepted["organization_id"] == str(org_a_id)
            assert "ProjectManager" in accepted["roles"]
            print("SUCCESS: Invitation accepted; user created under the correct org with the invited role.")

            login_res = await client.post("/api/v1/auth/login", json={"email": invitee_email, "password": "InviteePass123!"})
            assert login_res.status_code == 200, "Newly accepted user must be able to log in"
            print("SUCCESS: Newly invited user can log in.")

            # 10. Reusing the same (now-accepted) token is rejected.
            print("\nTest 10: Verifying an already-accepted token cannot be reused...")
            res = await client.post(
                f"/api/v1/organizations/invitations/{token}/accept",
                json={"full_name": "Second Attempt", "password": "AnotherPass123!"},
            )
            assert res.status_code == 400, f"Expected 400, got {res.status_code}: {res.text}"
            print("SUCCESS: Token reuse correctly rejected.")

            # 11. An unknown token 404s.
            print("\nTest 11: Verifying an unknown token returns 404...")
            res = await client.post(
                "/api/v1/organizations/invitations/not-a-real-token/accept",
                json={"full_name": "Nobody", "password": "WhateverPass123!"},
            )
            assert res.status_code == 404, f"Expected 404, got {res.status_code}: {res.text}"
            print("SUCCESS: Unknown token correctly returns 404.")

            # 12. An expired invitation is rejected.
            print("\nTest 12: Verifying an expired invitation is rejected...")
            expired_token = uuid.uuid4().hex + uuid.uuid4().hex
            async with SessionLocal() as session:
                expired_inv = Invitation(
                    organization_id=org_a_id,
                    email=f"expired-{suffix}@example.com",
                    role_name="Developer",
                    token=expired_token,
                    status="pending",
                    expires_at=datetime.now(timezone.utc) - timedelta(days=1),
                )
                session.add(expired_inv)
                await session.commit()
            res = await client.post(
                f"/api/v1/organizations/invitations/{expired_token}/accept",
                json={"full_name": "Too Late", "password": "TooLatePass123!"},
            )
            assert res.status_code == 400, f"Expected 400, got {res.status_code}: {res.text}"
            assert "expired" in res.text.lower()
            print("SUCCESS: Expired invitation correctly rejected.")

            # 13. Revoke: OrgAdmin can revoke a pending invitation, and the revoked token can no
            # longer be accepted.
            print("\nTest 13: Verifying OrgAdmin can revoke a pending invitation...")
            res = await client.post(
                "/api/v1/organizations/invitations",
                json={"email": f"revokeme-{suffix}@example.com", "role_name": "Viewer"},
                headers=admin_headers,
            )
            assert res.status_code == 201, res.text
            revoke_body = res.json()
            res = await client.delete(f"/api/v1/organizations/invitations/{revoke_body['invitation_id']}", headers=admin_headers)
            assert res.status_code == 200, res.text
            assert res.json()["status"] == "revoked"

            res = await client.post(
                f"/api/v1/organizations/invitations/{revoke_body['token']}/accept",
                json={"full_name": "Revoked Person", "password": "RevokedPass123!"},
            )
            assert res.status_code == 400, f"Expected 400 for revoked token, got {res.status_code}: {res.text}"
            print("SUCCESS: Revoked invitation correctly rejected on accept attempt.")

        finally:
            print("\nCleaning up organization invitations test database entries...")
            async with SessionLocal() as session:
                for oid in [o for o in [org_a_id, org_b_id] if o]:
                    inv_res = await session.execute(select(Invitation).where(Invitation.organization_id == oid))
                    for inv in inv_res.scalars().all():
                        await session.delete(inv)
                await session.commit()

                for oid in [o for o in [org_a_id, org_b_id] if o]:
                    user_res = await session.execute(select(User).where(User.organization_id == oid))
                    for u in user_res.scalars().all():
                        await session.delete(u)
                await session.commit()

                for oid in [o for o in [org_a_id, org_b_id] if o]:
                    org_row = await session.get(Organization, oid)
                    if org_row:
                        await session.delete(org_row)
                await session.commit()
            print("Cleanup completed.")

    print("\nAll Organization Creation & Invitation tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_organization_invitations_flow())
