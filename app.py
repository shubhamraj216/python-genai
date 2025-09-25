# app_inmemory_mongo.py
"""
Modified FastAPI app that uses an in-memory Mongo-like store scoped per-user.
- Provides simple InMemoryMongo with collections, per-user scoping, and basic CRUD.
- Backing-file persistence is optional (PERSIST=True/False). By default it's True
  and writes to the existing assets/users json files so you keep compatibility.
- All asset metadata is owner-scoped by default; operations respect owner_id.
- The API surface remains compatible with your original app but now uses the
  in-memory DB layer instead of direct file helpers.

This keeps behavior "user-directed" and makes the metadata clearly per-user.
"""

import os
import json
import mimetypes
from uuid import uuid4
from datetime import datetime, timezone, timedelta
from threading import Lock
from typing import Dict, Any, Optional, List

import uvicorn
from fastapi import FastAPI, HTTPException, Path, Depends, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from zoneinfo import ZoneInfo

# Gemini client (ensure google-genai installed and GEMINI_BEARER env var set)
try:
    from google import genai
    from google.genai import types
except Exception:
    genai = None
    types = None

# password hashing and JWT
from passlib.context import CryptContext
from jose import jwt, JWTError

# ---------- Config ----------
ASSETS_DIR = "assets/generated"

os.makedirs(ASSETS_DIR, exist_ok=True)

# Toggle persistence: when True, snapshot in-memory DB to files
PERSIST = True

# ---------- Default personas template ----------
# ---------- Default personas template ----------
DEFAULT_PERSONAS = [
    {
        "name": "Artistic Realism",
        "description": (
            "High-detail, realistic yet artistic style. Combines DSLR/medium-format "
            "camera aesthetics with painterly composition. "
            "Includes realistic lighting, accurate anatomy, natural skin/textures, "
            "and cinematic color grading. DSLR configuration: 35mm–85mm prime lens, "
            "f/1.4–f/2.8 aperture, shallow depth of field (bokeh), ISO 100–400, "
            "soft studio or natural golden-hour lighting. "
            "Think cinematic realism fused with fine art photography."
        ),
        "icon": "📸",
        "tags": ["artistic", "realistic", "cinematic", "DSLR", "photography"],
        "is_active": True,  # default active
    },
    {
        "name": "Cartoon Pop",
        "description": (
            "Vibrant cartoon / illustrative style. Bold outlines, saturated colors, "
            "playful proportions, cel-shading or soft shading variants. Great for "
            "stylized characters and background art — like high-quality animation stills."
        ),
        "icon": "🧸",
        "tags": ["cartoon", "illustrative", "bright", "stylized"],
        "is_active": False,
    },
]




# ---------- In-memory Mongo-like store ----------
class InMemoryMongo:
    """A tiny thread-safe in-memory DB with Mongo-like semantics for simple apps.

    - Collections: arbitrary string keys (e.g. 'users', 'assets')
    - Each collection is a dict of id -> document
    - Documents are plain dicts and must contain an 'id' field if inserted via insert_one
    - find supports simple equality matching across top-level keys
    - owner scoping is supported by passing owner_id to queries (it filters by owner_id)
    """

    def __init__(self):
        self._lock = Lock()
        self._collections: Dict[str, Dict[str, Dict[str, Any]]] = {}

    def _ensure_collection(self, name: str):
        with self._lock:
            if name not in self._collections:
                self._collections[name] = {}

    def insert_one(self, collection: str, document: Dict[str, Any]):
        self._ensure_collection(collection)
        with self._lock:
            doc = dict(document)
            if "id" not in doc:
                doc["id"] = str(uuid4())
            self._collections[collection][doc["id"]] = doc
            return doc

    def find(self, collection: str, filter: Optional[Dict[str, Any]] = None, owner_id: Optional[str] = None) -> List[Dict[str, Any]]:
        self._ensure_collection(collection)
        results = []
        with self._lock:
            for doc in self._collections[collection].values():
                if owner_id is not None and doc.get("owner_id") != owner_id:
                    continue
                if not filter:
                    results.append(dict(doc))
                    continue
                match = True
                for k, v in filter.items():
                    if doc.get(k) != v:
                        match = False
                        break
                if match:
                    results.append(dict(doc))
        return results

    def find_one(self, collection: str, filter: Dict[str, Any], owner_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        res = self.find(collection, filter, owner_id)
        return res[0] if res else None

    def update_one(self, collection: str, filter: Dict[str, Any], patch: Dict[str, Any], owner_id: Optional[str] = None) -> Dict[str, Any]:
        self._ensure_collection(collection)
        with self._lock:
            for id_, doc in self._collections[collection].items():
                if owner_id is not None and doc.get("owner_id") != owner_id:
                    continue
                match = True
                for k, v in filter.items():
                    if doc.get(k) != v:
                        match = False
                        break
                if match:
                    doc.update(patch)
                    self._collections[collection][id_] = doc
                    return dict(doc)
        raise KeyError("document not found")

    def delete_one(self, collection: str, filter: Dict[str, Any], owner_id: Optional[str] = None) -> Dict[str, Any]:
        self._ensure_collection(collection)
        with self._lock:
            for id_, doc in list(self._collections[collection].items()):
                if owner_id is not None and doc.get("owner_id") != owner_id:
                    continue
                match = True
                for k, v in filter.items():
                    if doc.get(k) != v:
                        match = False
                        break
                if match:
                    removed = self._collections[collection].pop(id_)
                    return dict(removed)
        raise KeyError("document not found")

    def dump_to_files(self):
        """Dump every collection to a JSON file under assets/db/<collection>.json for easy inspection."""
        if not PERSIST:
            return
        # ensure folder
        db_folder = os.path.join("assets", "db")
        os.makedirs(db_folder, exist_ok=True)

        with self._lock:
            # shallow copy of collections
            collections_copy = {k: list(v.values()) for k, v in self._collections.items()}

        for coll_name, docs in collections_copy.items():
            path = os.path.join(db_folder, f"{coll_name}.json")
            try:
                with open(path, "w") as f:
                    json.dump({coll_name: docs}, f, indent=2, default=str)
            except Exception as e:
                # don't crash the app if writing fails; log to stdout for visibility
                print(f"warning: failed to write collection {coll_name} to {path}: {e}")

    def load_from_files(self):
        """
        Load collections from assets/db/<collection>.json if present.
        Useful at startup to populate in-memory DB with previously persisted data.
        """
        if not PERSIST:
            return
        db_folder = os.path.join("assets", "db")
        os.makedirs(db_folder, exist_ok=True)

        # look for any json file in the folder and attempt to load it
        for fname in os.listdir(db_folder):
            if not fname.endswith(".json"):
                continue
            full = os.path.join(db_folder, fname)
            try:
                with open(full, "r") as f:
                    payload = json.load(f)
                # payload expected shape: { "<collection>": [ ...docs... ] }
                if isinstance(payload, dict):
                    for coll_name, docs in payload.items():
                        if isinstance(docs, list):
                            for d in docs:
                                # Insert but avoid duplicate IDs if already in memory
                                # insert_one will assign an id if missing; preserve id if present
                                # but if id exists in memory skip to avoid dup
                                if isinstance(d, dict):
                                    existing = None
                                    if "id" in d:
                                        existing = None
                                        # ensure collection exists
                                        self._ensure_collection(coll_name)
                                        with self._lock:
                                            existing = self._collections.get(coll_name, {}).get(d["id"])
                                    if existing:
                                        # skip duplicate
                                        continue
                                    # insert a shallow copy so in-memory has its own dict
                                    self.insert_one(coll_name, dict(d))
            except Exception as e:
                print(f"warning: failed to load {full}: {e}")


# instantiate DB and load existing files (if desired)
db = InMemoryMongo()
if PERSIST:
    db.load_from_files()

# ---------- JWT / password config ----------
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-prod")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 30
GUEST_TOKEN_EXPIRE_MINUTES = 60 * 24  # 1 day
GUEST_QUOTA_DEFAULT = 5

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

app = FastAPI(title="ImageGen + Gemini + Metadata + Auth (InMemory DB)")

# CORS - restrict in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static assets
app.mount("/assets", StaticFiles(directory="assets"), name="assets")


# ---------- Usage defaults & helpers ----------
DEFAULT_DAILY_LIMIT = int(os.environ.get("DAILY_LIMIT", "25"))

def _utc_today_iso():
    return datetime.now(timezone.utc).date().isoformat()

def ensure_user_usage_fields(user_doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensure user doc has usage tracking fields. Returns the patched doc (but does NOT persist).
    Fields:
      - daily_limit (int)
      - usage_today_date (ISO date str)
      - usage_today_count (int)
    """
    patched = dict(user_doc)
    if "daily_limit" not in patched:
        patched["daily_limit"] = DEFAULT_DAILY_LIMIT
    if "usage_today_date" not in patched or not patched.get("usage_today_date"):
        patched["usage_today_date"] = _utc_today_iso()
    if "usage_today_count" not in patched:
        patched["usage_today_count"] = 0
    return patched

def get_user_usage(user_id: str) -> Dict[str, int]:
    """
    Compute usage / counts for a given user.
    Returns dict with generations_today, daily_limit, total_assets, total_images, total_downloads, liked_count
    """
    user = get_user_by_id(user_id) or {}
    user = ensure_user_usage_fields(user)

    # ensure today's slate is correct (if date changed, treat count as 0)
    today = _utc_today_iso()
    usage_today = int(user.get("usage_today_count", 0)) if user.get("usage_today_date") == today else 0
    daily_limit = int(user.get("daily_limit", DEFAULT_DAILY_LIMIT))

    # assets owned by user
    assets = db.find("assets", owner_id=user_id) or []
    total_assets = len(assets)
    total_images = sum(1 for a in assets if (a.get("type") or "").startswith("image"))
    total_downloads = sum(int(a.get("downloads", 0) or 0) for a in assets)
    liked_count = sum(1 for a in assets if bool(a.get("liked", False)))

    return {
        "generations_today": usage_today,
        "daily_limit": daily_limit,
        "total_assets": total_assets,
        "total_images": total_images,
        "total_downloads": total_downloads,
        "liked_count": liked_count,
        "counts": {
            "liked": liked_count,
            "downloaded": sum(1 for a in assets if int(a.get("downloads",0))>0),
            "history": total_assets
        }
    }

def increment_user_usage(user_id: str, delta: int = 1, persist: bool = True) -> Dict[str, Any]:
    """
    Increment usage_today_count for user (resetting if date changed). Returns updated user doc.
    Will raise HTTPException(403) if increment would exceed daily_limit.
    """
    user = get_user_by_id(user_id)
    if not user:
        raise KeyError("user not found")

    user = ensure_user_usage_fields(user)
    today = _utc_today_iso()
    # if day changed, reset to 0
    if user.get("usage_today_date") != today:
        user["usage_today_date"] = today
        user["usage_today_count"] = 0

    current = int(user.get("usage_today_count", 0))
    limit = int(user.get("daily_limit", DEFAULT_DAILY_LIMIT))
    if current + delta > limit:
        raise HTTPException(status_code=403, detail="Daily usage limit reached")

    # increment
    user["usage_today_count"] = current + delta
    # persist
    update_user_fields(user["id"], {"usage_today_date": user["usage_today_date"], "usage_today_count": user["usage_today_count"], "daily_limit": user.get("daily_limit", DEFAULT_DAILY_LIMIT)})
    return user



# ---------- Conversations (owner-scoped) ----------
def create_conversation(owner_id: str, title: Optional[str] = None) -> Dict[str, Any]:
    """
    Create a conversation container. Fields:
      id, owner_id, title, created_at, updated_at, messages (list)
    """
    now = datetime.now(timezone.utc).isoformat()
    conv = {
        "id": str(uuid4()),
        "owner_id": owner_id,
        "title": title or f"Conversation {now}",
        "created_at": now,
        "updated_at": now,
        "messages": [],  # messages: { id, role, content, timestamp, assets?: [{id,url,prompt}] }
    }
    inserted = db.insert_one("conversations", conv)
    if PERSIST:
        db.dump_to_files()
    return inserted

def list_conversations(owner_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    """
    Return conversations for owner sorted by updated_at desc (recent first).
    """
    convs = db.find("conversations", owner_id=owner_id) or []
    convs_sorted = sorted(convs, key=lambda c: c.get("updated_at", ""), reverse=True)
    return convs_sorted[:limit]

def get_conversation(conv_id: str, owner_id: Optional[str] = None) -> Dict[str, Any]:
    c = db.find_one("conversations", {"id": conv_id}, owner_id=owner_id)
    if not c:
        raise KeyError("conversation not found")
    return c

def append_message_to_conversation(conv_id: str, message: Dict[str, Any], owner_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Append message to conversation.messages and update updated_at.
    message should contain: id, role ('user'|'assistant'), content, timestamp, optional assets
    """
    try:
        conv = db.find_one("conversations", {"id": conv_id}, owner_id=owner_id)
        if not conv:
            raise KeyError("conversation not found")
        msgs = conv.get("messages", [])
        msgs.append(message)
        now = datetime.now(timezone.utc).isoformat()
        updated = db.update_one("conversations", {"id": conv_id}, {"messages": msgs, "updated_at": now}, owner_id=owner_id)
        if PERSIST:
            db.dump_to_files()
        return updated
    except KeyError:
        raise


# ---------- Helper wrappers that use the in-memory DB ----------
def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    return db.find_one("users", {"email": email})


def get_user_by_id(uid: str) -> Optional[Dict[str, Any]]:
    return db.find_one("users", {"id": uid})


def create_user(email: str, password: str, is_guest: bool = False, guest_quota: Optional[int] = None, first_name: Optional[str] = None, last_name: Optional[str] = None) -> Dict[str, Any]:
    if get_user_by_email(email):
        raise ValueError("email exists")
    uid = str(uuid4())
    hashed = pwd_context.hash(password) if password else ""
    now = datetime.now(timezone.utc).isoformat()
    user = {
        "id": uid,
        "email": email,
        "password_hash": hashed,
        "is_guest": bool(is_guest),
        "guest_quota": int(guest_quota) if guest_quota is not None else (GUEST_QUOTA_DEFAULT if is_guest else 0),
        "created_at": now,
        "reset_token": None,
        "first_name": first_name or "",
        "last_name": last_name or "",

        "daily_limit": DEFAULT_DAILY_LIMIT,
        "usage_today_date": _utc_today_iso(),
        "usage_today_count": 0,
    }
    inserted = db.insert_one("users", user)

    # create default personas for the new user
    # first persona should be active by default; others inactive
    for i, tmpl in enumerate(DEFAULT_PERSONAS):
        create_persona(
            owner_id=inserted["id"],
            name=tmpl["name"],
            description=tmpl["description"],
            icon=tmpl.get("icon", "🎯"),
            tags=tmpl.get("tags", []),
            is_active=bool(tmpl.get("is_active")) if i == 0 else False
        )
    if PERSIST:
        db.dump_to_files()
    return inserted


def update_user_fields(uid: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    try:
        updated = db.update_one("users", {"id": uid}, patch)
        if PERSIST:
            db.dump_to_files()
        return updated
    except KeyError:
        raise KeyError("user not found")


def verify_password(plain: str, hashed: str) -> bool:
    if not hashed:
        return False
    return pwd_context.verify(plain, hashed)


def authenticate_user(email: str, password: str) -> Dict[str, Any]:
    user = get_user_by_email(email)
    if not user:
        raise ValueError("user not found")
    if not verify_password(password, user.get("password_hash", "")):
        raise ValueError("invalid credentials")
    return user


# ---------- Persona helpers (owner-scoped) ----------
def create_persona(owner_id: str, name: str, description: str = "", icon: str = "🎯", tags: Optional[List[str]] = None, is_active: bool = False):
    tags = tags or []
    persona = {
        "id": str(uuid4()),
        "owner_id": owner_id,
        "name": name,
        "description": description,
        "icon": icon,
        "tags": tags,
        "is_active": bool(is_active),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    inserted = db.insert_one("personas", persona)
    if PERSIST:
        db.dump_to_files()
    return inserted


def list_personas(owner_id: str):
    return db.find("personas", owner_id=owner_id)


def get_persona(pid: str, owner_id: Optional[str] = None):
    p = db.find_one("personas", {"id": pid}, owner_id=owner_id)
    if not p:
        raise KeyError("persona not found")
    return p


def update_persona(pid: str, patch: Dict[str, Any], owner_id: Optional[str] = None):
    patch["updated_at"] = datetime.now(timezone.utc).isoformat()
    updated = db.update_one("personas", {"id": pid}, patch, owner_id=owner_id)
    if PERSIST:
        db.dump_to_files()
    return updated


def delete_persona(pid: str, owner_id: Optional[str] = None):
    removed = db.delete_one("personas", {"id": pid}, owner_id=owner_id)
    if PERSIST:
        db.dump_to_files()
    return removed


def activate_persona(pid: str, owner_id: str):
    # set all other's is_active=False, then set this to True
    # First find existing active and set false (owner-scoped)
    ps = db.find("personas", owner_id=owner_id)
    for p in ps:
        if p.get("is_active"):
            try:
                db.update_one("personas", {"id": p["id"]}, {"is_active": False}, owner_id=owner_id)
            except KeyError:
                pass
    # Activate requested persona
    updated = db.update_one("personas", {"id": pid}, {"is_active": True, "updated_at": datetime.now(timezone.utc).isoformat()}, owner_id=owner_id)
    if PERSIST:
        db.dump_to_files()
    return updated

# ---------- JWT helpers ----------
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": int(expire.timestamp())})
    token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return token


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Could not validate credentials")


# ---------- Auth dependency ----------
def get_current_user(creds: HTTPAuthorizationCredentials = Depends(security)):
    token = creds.credentials
    payload = decode_token(token)
    uid = payload.get("sub")
    if not uid:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    user = get_user_by_id(uid)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


# ---------- Asset metadata functions (owner-scoped) using DB ----------
def add_asset_metadata(aid: str, type_: str, url: str, prompt: str, owner_id: Optional[str] = None):
    # No-op if same id exists for same owner
    existing = db.find_one("assets", {"id": aid}, owner_id=owner_id)
    if existing:
        return existing
    new = {
        "id": aid,
        "type": type_,
        "url": url,
        "prompt": prompt,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "liked": False,
        "downloads": 0,
        "owner_id": owner_id,
    }
    ins = db.insert_one("assets", new)
    if PERSIST:
        db.dump_to_files()
    return ins


def update_asset_field(asset_id: str, patch: Dict[str, Any], owner_id: Optional[str] = None) -> Dict[str, Any]:
    try:
        updated = db.update_one("assets", {"id": asset_id}, patch, owner_id=owner_id)
        if PERSIST:
            db.dump_to_files()
        return updated
    except KeyError:
        raise KeyError("asset not found")


def remove_asset_metadata_only(asset_id: str, owner_id: Optional[str] = None) -> Dict[str, Any]:
    try:
        removed = db.delete_one("assets", {"id": asset_id}, owner_id=owner_id)
        if PERSIST:
            db.dump_to_files()
        return removed
    except KeyError:
        raise KeyError("asset not found")


# ---------- Simple models ----------
class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    conversation_id: Optional[str] = None


class AuthSignupReq(BaseModel):
    email: str
    password: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class AuthLoginReq(BaseModel):
    email: str
    password: str


# ---------- Gemini integration & saving (owner-aware) ----------
def save_binary_file_return_url(file_name: str, data: bytes) -> str:
    path = os.path.join(ASSETS_DIR, file_name)
    with open(path, "wb") as f:
        f.write(data)
    # Return relative URL path (served by static mount)
    return f"/assets/generated/{file_name}"


def call_gemini_generate_stream_and_save(prompt: str, owner_id: Optional[str] = None):
    """
    If genai client not available, this function will raise. In tests you can
    mock this function and call add_asset_metadata manually.
    """
    if genai is None or types is None:
        raise RuntimeError("genai client not available (google-genai not installed or import failed)")

    api_key = os.environ.get("GEMINI_BEARER", "AIzaSyATjKDFn6AktOx1I9gXS6-IFYEat40Je4c")
    if not api_key:
        raise RuntimeError("GEMINI_BEARER env var not set")

    client = genai.Client(api_key=api_key)
    model = "gemini-2.5-flash-image-preview"

    contents = [
        types.Content(role="user", parts=[types.Part.from_text(text=prompt)])
    ]
    generate_content_config = types.GenerateContentConfig(
        response_modalities=["IMAGE", "TEXT"],
        system_instruction=[types.Part.from_text(text="You are an image-generation assistant.")],
    )

    assembled_text_parts = []
    saved_assets = []

    for chunk in client.models.generate_content_stream(
        model=model, contents=contents, config=generate_content_config
    ):
        # collect chunk text if present
        # if getattr(chunk, "text", None):
        #     assembled_text_parts.append(chunk.text)

        if not (chunk and chunk.candidates and chunk.candidates[0].content):
            continue

        candidate = chunk.candidates[0]
        content = candidate.content
        if getattr(content, "parts", None):
            for part in content.parts:
                inline = getattr(part, "inline_data", None)
                if inline and getattr(inline, "data", None):
                    file_extension = mimetypes.guess_extension(inline.mime_type) or ".bin"
                    aid = str(uuid4())
                    filename = f"{aid}{file_extension}"
                    url = save_binary_file_return_url(filename, inline.data)
                    # persist metadata immediately (with owner)
                    add_asset_metadata(aid, "image" if inline.mime_type.startswith("image/") else "file", url, prompt, owner_id)
                    saved_assets.append({"id": aid, "type": "image", "url": url, "prompt": prompt})
                else:
                    # maybe text part
                    text = getattr(part, "text", None)
                    if text:
                        assembled_text_parts.append(text)

    assembled_text = "\n".join(p for p in assembled_text_parts if p)
    return assembled_text.strip(), saved_assets


# ---------- Auth endpoints ----------
@app.post("/api/auth/signup")
def signup(req: AuthSignupReq = Body(...)):
    if get_user_by_email(req.email):
        raise HTTPException(status_code=400, detail="Email already in use")
    try:
        # pass first/last into create_user
        user = create_user(req.email, req.password, is_guest=False, first_name=req.first_name or "", last_name=req.last_name or "")
    except ValueError:
        raise HTTPException(status_code=400, detail="Could not create user")

    # create token payload including name for convenience
    token = create_access_token({"sub": user["id"], "email": user["email"], "is_guest": False})
    # return both token and user profile (frontend will use this to show name)
    return {"access_token": token, "token_type": "bearer", "user": { "id": user["id"], "email": user["email"], "first_name": user.get("first_name",""), "last_name": user.get("last_name","") }}

# --- Add a protected /api/auth/me endpoint so frontend can fetch user info after login ---
@app.get("/api/auth/me")
def me(user: Dict[str, Any] = Depends(get_current_user)):
    # don't return password hash
    u = get_user_by_id(user["id"])
    u = ensure_user_usage_fields(u)
    return {
        "id": u["id"],
        "email": u["email"],
        "first_name": u.get("first_name", ""),
        "last_name": u.get("last_name", ""),
        "is_guest": u.get("is_guest", False),
        "guest_quota": u.get("guest_quota", 0),
        "daily_limit": int(u.get("daily_limit", DEFAULT_DAILY_LIMIT)),
        "usage_today_count": int(u.get("usage_today_count", 0)) if u.get("usage_today_date") == _utc_today_iso() else 0
    }

@app.post("/api/auth/login")
def login(req: AuthLoginReq = Body(...)):
    try:
        user = authenticate_user(req.email, req.password)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token({"sub": user["id"], "email": user["email"], "is_guest": user.get("is_guest", False)})
    return {"access_token": token, "token_type": "bearer"}


@app.post("/api/auth/guest")
def create_guest():
    uid = str(uuid4())
    guest_email = f"guest+{uid}@local"
    user = create_user(guest_email, password="", is_guest=True, guest_quota=GUEST_QUOTA_DEFAULT)
    token = create_access_token({"sub": user["id"], "email": user["email"], "is_guest": True},
                                expires_delta=timedelta(minutes=GUEST_TOKEN_EXPIRE_MINUTES))
    return {"access_token": token, "expires_in_minutes": GUEST_TOKEN_EXPIRE_MINUTES, "token_type": "bearer"}


@app.post("/api/auth/forgot-password")
def forgot_password(email: str = Body(...)):
    user = get_user_by_email(email)
    if not user:
        # don't reveal whether email exists
        return {"ok": True}
    rt = str(uuid4())
    update_user_fields(user["id"], {"reset_token": rt})
    # In prod: send email. Here return token for testing.
    return {"ok": True, "reset_token": rt}


# ---------- Protected generation endpoint ----------
# ---------- Conversation endpoints ----------
@app.post("/api/conversations")
def api_create_conversation(payload: Dict[str, Any] = Body(...), user: Dict[str, Any] = Depends(get_current_user)):
    """
    Create a new conversation for current user.
    payload: { title?: string }
    returns conversation object
    """
    title = str(payload.get("title")) if payload else None
    conv = create_conversation(owner_id=user["id"], title=title)
    return conv

@app.get("/api/conversations")
def api_list_conversations(user: Dict[str, Any] = Depends(get_current_user), limit: int = 20):
    """
    List recent conversations for current user (most recent first).
    """
    convs = list_conversations(owner_id=user["id"], limit=limit)
    # Return shallow metadata (no messages) to keep response small
    shallow = [{
        "id": c["id"],
        "title": c.get("title"),
        "created_at": c.get("created_at"),
        "updated_at": c.get("updated_at"),
        "message_count": len(c.get("messages", []))
    } for c in convs]
    return {"conversations": shallow}

@app.get("/api/recent-conversations")
def api_list_conversations(user: Dict[str, Any] = Depends(get_current_user), limit: int = 5):
    """
    List conversations for current user updated within the last 24 hours (most recent first).
    """
    convs = list_conversations(owner_id=user["id"], limit=limit)  # get more, then filter
    cutoff = datetime.now(timezone.utc) - timedelta(days=1)

    filtered = []
    for c in convs:
        try:
            updated_at = datetime.fromisoformat(c.get("updated_at"))
        except Exception:
            continue
        if updated_at >= cutoff:
            filtered.append(c)

    # Sort after filtering (desc by updated_at)
    convs_sorted = sorted(filtered, key=lambda c: c.get("updated_at", ""), reverse=True)

    shallow = [{
        "id": c["id"],
        "title": c.get("title"),
        "created_at": c.get("created_at"),
        "updated_at": c.get("updated_at"),
        "message_count": len(c.get("messages", []))
    } for c in convs_sorted[:limit]]

    return {"conversations": shallow}

@app.get("/api/conversations/{conv_id}")
def api_get_conversation(conv_id: str = Path(...), user: Dict[str, Any] = Depends(get_current_user)):
    try:
        conv = get_conversation(conv_id, owner_id=user["id"])
        return conv
    except KeyError:
        raise HTTPException(status_code=404, detail="conversation not found")
@app.post("/api/generate")
def generate(req: GenerateRequest, user: Dict[str, Any] = Depends(get_current_user)):
    """
    Accepts:
      { prompt: "...", conversation_id?: "..." }

    Behavior:
      - append a user message to conversation (create conv if missing)
      - call Gemini -> saves inline asset files & asset metadata (owner-scoped)
      - append assistant message (with saved_assets) to conversation
      - increment usage only after successful generation
    """
    prompt = req.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt required")

    # Guest quota enforcement
    if user.get("is_guest"):
        quota = int(user.get("guest_quota", 0))
        if quota <= 0:
            raise HTTPException(status_code=403, detail="Guest quota exhausted")
        update_user_fields(user["id"], {"guest_quota": quota - 1})

    # Check daily usage BEFORE calling Gemini
    usr = get_user_by_id(user["id"])
    if not usr:
        raise HTTPException(status_code=401, detail="User not found")
    usr = ensure_user_usage_fields(usr)
    today = _utc_today_iso()
    usage_today = int(usr.get("usage_today_count", 0)) if usr.get("usage_today_date") == today else 0
    daily_limit = int(usr.get("daily_limit", DEFAULT_DAILY_LIMIT))
    if usage_today >= daily_limit:
        raise HTTPException(status_code=403, detail="Daily usage limit reached")

    # Prepare conversation: use provided conv id or create one
    conv_id = req.conversation_id
    if conv_id:
        # verify exists and belongs to user
        try:
            _ = get_conversation(conv_id, owner_id=user["id"])
        except KeyError:
            raise HTTPException(status_code=404, detail="conversation not found")
    else:
        now_ist = datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Kolkata"))
        title = f"Chat {now_ist.strftime('%b %d, %Y %I:%M %p IST')}"
        conv = create_conversation(owner_id=user["id"], title=title)
        conv_id = conv["id"]

    # Build and append the user message first (persist immediately)
    user_msg = {
        "id": str(uuid4()),
        "role": "user",
        "content": prompt,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        append_message_to_conversation(conv_id, user_msg, owner_id=user["id"])
    except KeyError:
        raise HTTPException(status_code=500, detail="failed to append user message to conversation")

    # Call Gemini and save assets (owner-aware)
    try:
        assistant_text, saved_assets = call_gemini_generate_stream_and_save(prompt, owner_id=user["id"])
    except Exception as e:
        # generation failed: user message retained. Return error to client.
        raise HTTPException(status_code=500, detail=f"generation error: {str(e)}")

    # Increment usage only after successful generation
    try:
        increment_user_usage(user["id"], delta=1)
    except HTTPException:
        # concurrent limit reached — defensive; we already saved assets and messages,
        # but respond with 403 to the client to highlight limit.
        raise HTTPException(status_code=403, detail="Daily usage limit reached (concurrent)")

    if not assistant_text:
        assistant_text = f"I've created assets based on your prompt: \"{prompt}\"."

    # Build assistant message (with assets)
    assistant_msg = {
        "id": str(uuid4()),
        "role": "assistant",
        "content": assistant_text,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "assets": saved_assets,  # each saved asset = {id, type, url, prompt}
    }

    # Append assistant message to conversation
    try:
        append_message_to_conversation(conv_id, assistant_msg, owner_id=user["id"])
    except KeyError:
        # If append fails, we log and continue — assets + user message already persisted.
        print(f"warning: failed to append assistant message to conversation {conv_id}")

    # Return assistant message + conversation id so frontend can remain bound to conversation
    return {"message": assistant_msg, "conversation_id": conv_id}



@app.get("/api/usage")
def usage(user: Dict[str, Any] = Depends(get_current_user)):
    """
    Returns computed usage and counts for the current user.
    Example:
    {
      "generations_today": 0,
      "daily_limit": 25,
      "total_assets": 0,
      "total_images": 0,
      "total_downloads": 0,
      "liked_count": 0,
      "counts": { "liked": 0, "downloaded": 0, "history": 0 }
    }
    """
    try:
        u = get_user_by_id(user["id"])
        if not u:
            raise HTTPException(status_code=404, detail="user not found")
        return get_user_usage(user["id"])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"failed to compute usage: {str(e)}")



# ---------- asset endpoints (owner-scoped) ----------
@app.get("/api/assets")
def list_assets(user: Dict[str, Any] = Depends(get_current_user)):
    assets = db.find("assets", owner_id=user["id"]) or []
    return {"assets": assets}


@app.post("/api/assets")
def create_asset(payload: Dict[str, Any] = Body(...), user: Dict[str, Any] = Depends(get_current_user)):
    try:
        aid = str(payload.get("id", str(uuid4())))
        atype = str(payload["type"])
        url = str(payload["url"])
        prompt = str(payload.get("prompt", ""))
    except Exception:
        raise HTTPException(status_code=400, detail="invalid payload")

    added = add_asset_metadata(aid, atype, url, prompt, owner_id=user["id"])
    return added


@app.post("/api/assets/{asset_id}/toggle-like")
def toggle_like(asset_id: str = Path(...), user: Dict[str, Any] = Depends(get_current_user)):
    try:
        # find asset owned by user
        a = db.find_one("assets", {"id": asset_id}, owner_id=user["id"])
        if not a:
            raise HTTPException(status_code=404, detail="asset not found")
        new_liked = not bool(a.get("liked", False))
        if not new_liked:
            removed = remove_asset_metadata_only(asset_id, owner_id=user["id"])
            return {"deleted": True, "id": asset_id}
        else:
            updated = update_asset_field(asset_id, {"liked": True}, owner_id=user["id"])
            return updated
    except KeyError:
        raise HTTPException(status_code=404, detail="asset not found")


@app.post("/api/assets/{asset_id}/increment-download")
def increment_download(asset_id: str = Path(...), user: Dict[str, Any] = Depends(get_current_user)):
    try:
        a = db.find_one("assets", {"id": asset_id}, owner_id=user["id"])
        if not a:
            raise HTTPException(status_code=404, detail="asset not found")
        new_downloads = int(a.get("downloads", 0)) + 1
        updated = update_asset_field(asset_id, {"downloads": new_downloads}, owner_id=user["id"])
        return updated
    except KeyError:
        raise HTTPException(status_code=404, detail="asset not found")

# list personas for current user
@app.get("/api/personas")
def api_list_personas(user: Dict[str, Any] = Depends(get_current_user)):
    ps = list_personas(user["id"])
    return {"personas": ps}

# create persona
@app.post("/api/personas")
def api_create_persona(payload: Dict[str, Any] = Body(...), user: Dict[str, Any] = Depends(get_current_user)):
    try:
        name = str(payload["name"])
    except Exception:
        raise HTTPException(status_code=400, detail="name is required")
    description = str(payload.get("description", ""))
    icon = str(payload.get("icon", "🎯"))
    tags = list(payload.get("tags", []))
    persona = create_persona(user["id"], name, description=description, icon=icon, tags=tags, is_active=bool(payload.get("is_active", False)))
    return persona

# update persona
@app.put("/api/personas/{persona_id}")
def api_update_persona(persona_id: str = Path(...), payload: Dict[str, Any] = Body(...), user: Dict[str, Any] = Depends(get_current_user)):
    try:
        updated = update_persona(persona_id, payload, owner_id=user["id"])
        return updated
    except KeyError:
        raise HTTPException(status_code=404, detail="persona not found")

# delete persona
@app.delete("/api/personas/{persona_id}")
def api_delete_persona(persona_id: str = Path(...), user: Dict[str, Any] = Depends(get_current_user)):
    try:
        # ensure at least one persona remains
        ps = list_personas(user["id"])
        if len(ps) <= 1:
            raise HTTPException(status_code=400, detail="At least one persona must exist")
        removed = delete_persona(persona_id, owner_id=user["id"])
        return {"deleted": True, "persona": removed}
    except KeyError:
        raise HTTPException(status_code=404, detail="persona not found")

# activate persona
@app.post("/api/personas/{persona_id}/activate")
def api_activate_persona(persona_id: str = Path(...), user: Dict[str, Any] = Depends(get_current_user)):
    try:
        updated = activate_persona(persona_id, owner_id=user["id"])
        return updated
    except KeyError:
        raise HTTPException(status_code=404, detail="persona not found")


@app.get("/healthz")
def health():
    return {"status": "ok"}


# ----------------- Run server directly -----------------
if __name__ == "__main__":
    # Allow configuring host/port via env vars
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("app:app", host=host, port=port, reload=True)
