from fastapi import APIRouter, Depends, HTTPException, Request, status

from lib.access import email_domain, get_access_policy, save_domains
from lib.audit import record_audit
from lib.db import db
from models.auth import AccessPolicy, AuthUser, DomainRequest, ManagedUser, RoleUpdateRequest, utc_now
from routers.auth import require_admin, resolve_role


router = APIRouter()


async def _managed_user(document: dict) -> ManagedUser:
    role = document.get("role")
    if role not in ("analyst", "admin"):
        # Legacy operator without a stored role: resolve exactly as sign-in would and persist it.
        role = await resolve_role(document["email"], None)
        await db.users.update_one({"user_id": document["user_id"]}, {"$set": {"role": role}})
    active = await db.user_sessions.count_documents({"user_id": document["user_id"], "expires_at": {"$gt": utc_now()}})
    return ManagedUser(
        user_id=document["user_id"], email=document["email"], name=document["name"], picture=document.get("picture"),
        role=role, created_at=document.get("created_at"), last_login_at=document.get("last_login_at"), active_sessions=active,
    )


@router.get("/access-policy", response_model=AccessPolicy)
async def read_access_policy(_: AuthUser = Depends(require_admin)):
    return await get_access_policy()


@router.post("/access-policy/domains", response_model=AccessPolicy)
async def add_domain(payload: DomainRequest, request: Request, admin: AuthUser = Depends(require_admin)):
    policy = await get_access_policy()
    if payload.domain in policy.allowed_domains:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"{payload.domain} is already approved")
    domains = [*policy.allowed_domains, payload.domain]
    own_domain = email_domain(admin.email)
    auto_included = policy.open_access and own_domain not in domains
    if auto_included:
        domains.append(own_domain)  # first restriction must never lock out the administrator applying it
    updated = await save_domains(domains, admin.email)
    await record_audit("admin.domain_added", actor=admin, request=request, target=payload.domain, details={"allowed_domains": updated.allowed_domains, **({"auto_included": own_domain} if auto_included else {})})
    return updated


@router.delete("/access-policy/domains/{domain}", response_model=AccessPolicy)
async def remove_domain(domain: str, request: Request, admin: AuthUser = Depends(require_admin)):
    domain = domain.strip().lower()
    policy = await get_access_policy()
    if domain not in policy.allowed_domains:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{domain} is not on the allowlist")
    remaining = [item for item in policy.allowed_domains if item != domain]
    if remaining and domain == email_domain(admin.email):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Removing your own domain would lock you out of the console")
    updated = await save_domains(remaining, admin.email)
    await record_audit("admin.domain_removed", actor=admin, request=request, target=domain, details={"allowed_domains": updated.allowed_domains})
    return updated


@router.get("/users", response_model=list[ManagedUser])
async def list_users(_: AuthUser = Depends(require_admin)):
    documents = await db.users.find({}, {"_id": 0}).sort("created_at", 1).to_list(500)
    return [await _managed_user(document) for document in documents]


@router.patch("/users/{user_id}/role", response_model=ManagedUser)
async def update_role(user_id: str, payload: RoleUpdateRequest, request: Request, admin: AuthUser = Depends(require_admin)):
    if user_id == admin.user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot change your own role")
    document = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Operator not found")
    previous = document.get("role", "analyst")
    await db.users.update_one({"user_id": user_id}, {"$set": {"role": payload.role, "updated_at": utc_now()}})
    document["role"] = payload.role
    await record_audit("admin.role_changed", actor=admin, request=request, target=document["email"], details={"from": previous, "to": payload.role})
    return await _managed_user(document)
