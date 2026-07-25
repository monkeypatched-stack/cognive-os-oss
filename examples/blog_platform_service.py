"""A small, real blog-publishing backend — FastAPI + MongoDB.

Publishing a post requires a valid API key (same SHA-256-hashed key
pattern as grocery_service.py); reading published posts is open, like a
real blog. Posts get a real, stable slug and are genuinely persisted —
GET /posts/{slug} after a POST returns exactly what was published,
independently of whatever called POST.

Run:
    export BLOG_MONGODB_URL=mongodb://localhost:27017   # optional, default
    export BLOG_DB_NAME=blog_platform                    # optional, default
    uvicorn examples.blog_platform_service:app --port 8835

On first boot (empty api_keys collection) one publisher API key is minted
and logged once — pin it with BLOG_PUBLISHER_API_KEY.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel

logger = logging.getLogger("blog_platform_service")

MONGODB_URL = os.getenv("BLOG_MONGODB_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("BLOG_DB_NAME", "blog_platform")


def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def _slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug or "post"


async def _seed(db: Any) -> None:
    if await db.api_keys.count_documents({}) == 0:
        publisher_key = os.getenv("BLOG_PUBLISHER_API_KEY") or secrets.token_urlsafe(24)
        await db.api_keys.insert_one({"_id": _hash_key(publisher_key), "owner": "n8n-publishing-agent"})
        logger.warning(
            "Seeded publisher API key (only SHA-256 hash stored) — "
            "PUBLISHER_API_KEY=%s — save this now.", publisher_key,
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = AsyncIOMotorClient(MONGODB_URL)
    db = client[DB_NAME]
    await client.admin.command("ping")
    await _seed(db)
    app.state.db = db
    logger.info("Connected to MongoDB %s (db=%s)", MONGODB_URL, DB_NAME)
    yield
    client.close()


app = FastAPI(title="Local Blog Platform", lifespan=lifespan)


async def require_publisher(
    request: Request, authorization: str | None = Header(default=None),
) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization: Bearer <key>")
    token = authorization[7:]
    record = await request.app.state.db.api_keys.find_one({"_id": _hash_key(token)})
    if record is None:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return record["owner"]


class PublishRequest(BaseModel):
    title: str
    content: str
    author: str = "cognitiveos"


@app.post("/posts")
async def publish_post(
    req: PublishRequest, request: Request, publisher: str = Depends(require_publisher),
) -> dict[str, Any]:
    db = request.app.state.db
    slug = _slugify(req.title)

    # Real uniqueness, not assumed: append a short suffix on collision
    # instead of overwriting an existing post at the same slug.
    candidate = slug
    suffix = 1
    while await db.posts.find_one({"_id": candidate}):
        suffix += 1
        candidate = f"{slug}-{suffix}"
    slug = candidate

    post = {
        "_id": slug,
        "title": req.title,
        "content": req.content,
        "author": req.author,
        "published_by": publisher,
        "published_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.posts.insert_one(dict(post))
    post["slug"] = post.pop("_id")
    post["url"] = f"/posts/{slug}"
    return post


@app.get("/posts/{slug}")
async def get_post(slug: str, request: Request) -> dict[str, Any]:
    post = await request.app.state.db.posts.find_one({"_id": slug})
    if post is None:
        raise HTTPException(status_code=404, detail="post_not_found")
    post["slug"] = post.pop("_id")
    return post


@app.get("/posts")
async def list_posts(request: Request) -> dict[str, Any]:
    cursor = request.app.state.db.posts.find({}, {"content": 0}).sort("published_at", -1)
    posts = []
    async for p in cursor:
        p["slug"] = p.pop("_id")
        posts.append(p)
    return {"results": posts}
