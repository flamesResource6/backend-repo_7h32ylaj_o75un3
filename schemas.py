"""
Database Schemas for LifeOS × TANA

Each Pydantic model represents a collection in MongoDB.
Collection name is the lowercase of the class name.
"""
from pydantic import BaseModel, Field, EmailStr
from typing import Optional, Literal
from datetime import datetime

# User profile and TANA pillars
class User(BaseModel):
    name: str = Field(..., description="Full name")
    email: EmailStr = Field(..., description="Email address")
    purpose: Literal["Healing", "Growth", "Direction"] = Field(..., description="User purpose choice")
    age: Optional[int] = Field(None, ge=0, le=120, description="Age in years")
    tana_mind: int = Field(0, ge=0, description="TANA Mind score")
    tana_money: int = Field(0, ge=0, description="TANA Money score")
    tana_meaning: int = Field(0, ge=0, description="TANA Meaning score")
    total_sessions: int = Field(3, ge=0, description="Total sessions available")
    sessions_used: int = Field(0, ge=0, description="Number of sessions used")

# Internal auth model (not exposed as a collection schema but used for validation)
class SignupRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    purpose: Literal["Healing", "Growth", "Direction"]
    age: Optional[int] = None

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    purpose: Optional[Literal["Healing", "Growth", "Direction"]] = None
    age: Optional[int] = None

class Session(BaseModel):
    user_id: str
    topic: str
    date: str
    time: str
    feedback: Optional[str] = None
    spatial_url: Optional[str] = None
    status: Literal["requested", "scheduled", "completed", "cancelled"] = "requested"

class Reflection(BaseModel):
    user_id: str
    pillar: Literal["Mind", "Money", "Meaning"]
    entry_text: str
    mood: Optional[str] = None
    created_at: Optional[datetime] = None
