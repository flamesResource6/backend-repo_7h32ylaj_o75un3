import os
import uuid
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import (
    User,
    SignupRequest,
    LoginRequest,
    ProfileUpdate,
    Session as SessionModel,
    Reflection as ReflectionModel,
)

app = FastAPI(title="LifeOS × TANA API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Utilities
def hash_password(password: str) -> str:
    salt = os.getenv("AUTH_SALT", "tana_salt")
    return hashlib.sha256((password + salt).encode()).hexdigest()


def generate_token() -> str:
    return uuid.uuid4().hex


class AuthUser(BaseModel):
    id: str
    name: str
    email: str


def to_object_id(value: str) -> ObjectId:
    try:
        return ObjectId(value)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID format")


def get_current_user(authorization: Optional[str] = Header(None)) -> AuthUser:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    token = authorization.split(" ")[1]
    token_doc = db["auth_token"].find_one({"token": token})
    if not token_doc:
        raise HTTPException(status_code=401, detail="Invalid token")
    if token_doc.get("expires_at") and token_doc["expires_at"] < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Token expired")
    user = db["user"].find_one({"_id": token_doc["user_id"]})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return AuthUser(id=str(user["_id"]), name=user.get("name", ""), email=user.get("email", ""))


@app.get("/")
def read_root():
    return {"message": "LifeOS × TANA backend running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set",
        "database_name": "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set",
        "connection_status": "Not Connected",
        "collections": [],
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            try:
                response["collections"] = db.list_collection_names()[:10]
                response["database"] = "✅ Connected & Working"
                response["connection_status"] = "Connected"
            except Exception as e:
                response["database"] = f"⚠️ Connected but error: {str(e)[:80]}"
        else:
            response["database"] = "⚠️ Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"
    return response


# Auth
@app.post("/auth/signup")
def signup(payload: SignupRequest):
    existing = db["user"].find_one({"email": payload.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user_doc = User(
        name=payload.name,
        email=payload.email,
        purpose=payload.purpose,
        age=payload.age,
        tana_mind=0,
        tana_money=0,
        tana_meaning=0,
        total_sessions=3,
        sessions_used=0,
    ).model_dump()

    res = db["user"].insert_one(user_doc)
    user_id = res.inserted_id

    db["credential"].insert_one(
        {
            "user_id": user_id,
            "password_hash": hash_password(payload.password),
            "created_at": datetime.now(timezone.utc),
        }
    )

    token = generate_token()
    db["auth_token"].insert_one(
        {
            "user_id": user_id,
            "token": token,
            "created_at": datetime.now(timezone.utc),
            "expires_at": datetime.now(timezone.utc) + timedelta(days=7),
        }
    )
    return {"token": token, "user_id": str(user_id)}


@app.post("/auth/login")
def login(payload: LoginRequest):
    user = db["user"].find_one({"email": payload.email})
    if not user:
        raise HTTPException(status_code=400, detail="Invalid email or password")
    cred = db["credential"].find_one({"user_id": user["_id"]})
    if not cred or cred.get("password_hash") != hash_password(payload.password):
        raise HTTPException(status_code=400, detail="Invalid email or password")
    token = generate_token()
    db["auth_token"].insert_one(
        {
            "user_id": user["_id"],
            "token": token,
            "created_at": datetime.now(timezone.utc),
            "expires_at": datetime.now(timezone.utc) + timedelta(days=7),
        }
    )
    return {"token": token, "user_id": str(user["_id"]) }


@app.get("/me")
def me(current: AuthUser = Depends(get_current_user)):
    user = db["user"].find_one({"_id": to_object_id(current.id)})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user["id"] = str(user.pop("_id"))
    return user


# Profile & Dashboard
@app.get("/dashboard")
def dashboard(current: AuthUser = Depends(get_current_user)):
    user = db["user"].find_one({"_id": to_object_id(current.id)})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    mind = int(user.get("tana_mind", 0))
    money = int(user.get("tana_money", 0))
    meaning = int(user.get("tana_meaning", 0))
    total = max(mind + money + meaning, 1)
    return {
        "name": user.get("name", ""),
        "purpose": user.get("purpose", "Healing"),
        "tana": {
            "mind": mind,
            "money": money,
            "meaning": meaning,
            "percentages": {
                "mind": round(mind / total * 100),
                "money": round(money / total * 100),
                "meaning": round(meaning / total * 100),
            },
        },
        "sessions": {
            "used": int(user.get("sessions_used", 0)),
            "total": int(user.get("total_sessions", 3)),
        },
    }


@app.post("/profile")
def update_profile(payload: ProfileUpdate, current: AuthUser = Depends(get_current_user)):
    update = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not update:
        return {"updated": False}
    db["user"].update_one({"_id": to_object_id(current.id)}, {"$set": update})
    return {"updated": True}


# Session booking
@app.post("/sessions")
def create_session(payload: SessionModel, current: AuthUser = Depends(get_current_user)):
    # Ensure the session is for the current user
    payload.user_id = current.id  # enforce

    user = db["user"].find_one({"_id": to_object_id(current.id)})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    used = int(user.get("sessions_used", 0))
    total = int(user.get("total_sessions", 3))
    if used >= total:
        return {"limited": True, "message": "Session limit reached"}

    session_doc = payload.model_dump()
    inserted_id = create_document("session", session_doc)

    # Increment usage and pillar based on topic keywords
    pillar_inc = None
    topic_lower = payload.topic.lower()
    if "mind" in topic_lower:
        pillar_inc = "tana_mind"
    elif "money" in topic_lower:
        pillar_inc = "tana_money"
    elif "meaning" in topic_lower:
        pillar_inc = "tana_meaning"

    updates = {"sessions_used": used + 1}
    if pillar_inc:
        updates[pillar_inc] = int(user.get(pillar_inc, 0)) + 1
    db["user"].update_one({"_id": to_object_id(current.id)}, {"$set": updates})

    # Simulate email notification by logging entry
    db["email_log"].insert_one(
        {
            "to": "Jagathisraj4@gmail.com",
            "subject": "New TANA Session Request",
            "body": f"User {user.get('name')} requested a session on {payload.topic} for {payload.date} {payload.time}",
            "created_at": datetime.now(timezone.utc),
        }
    )

    return {"created": True, "id": inserted_id}


@app.get("/sessions")
def list_sessions(current: AuthUser = Depends(get_current_user)):
    items = get_documents("session", {"user_id": current.id}, limit=100)
    for it in items:
        if "_id" in it:
            it["id"] = str(it.pop("_id"))
    return {"items": items}


# Reflections
@app.post("/reflections")
def add_reflection(payload: ReflectionModel, current: AuthUser = Depends(get_current_user)):
    if payload.user_id != current.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    doc = payload.model_dump()
    doc["created_at"] = datetime.now(timezone.utc)
    inserted_id = create_document("reflection", doc)

    pillar_map = {"Mind": "tana_mind", "Money": "tana_money", "Meaning": "tana_meaning"}
    user = db["user"].find_one({"_id": to_object_id(current.id)})
    if user:
        field = pillar_map.get(payload.pillar)
        if field:
            db["user"].update_one({"_id": to_object_id(current.id)}, {"$set": {field: int(user.get(field, 0)) + 1}})
    return {"created": True, "id": inserted_id}


@app.get("/reflections")
def list_reflections(current: AuthUser = Depends(get_current_user)):
    items = get_documents("reflection", {"user_id": current.id}, limit=200)
    for it in items:
        if "_id" in it:
            it["id"] = str(it.pop("_id"))
    return {"items": items}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
