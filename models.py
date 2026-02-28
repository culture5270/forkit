from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class Comment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(default="Anonymous", max_length=100)
    message: str = Field(max_length=1000)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(unique=True, max_length=100)
    password_hash: str


class Favorite(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    name: str = Field(max_length=200)
    address: str = Field(default="", max_length=500)
    categories: str = Field(default="", max_length=200)
    website: str = Field(default="", max_length=500)
    saved_at: datetime = Field(default_factory=lambda: datetime.utcnow())
