from typing import List, Optional, Any, Dict, Literal
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field, model_validator

class UserBase(BaseModel):
    email: str = Field(..., example="")
    full_name: Optional[str] = Field(None, example="")  

class UserCreate(UserBase):
    password: str = Field(..., example="")

class UserUpdate(UserBase):
    password: Optional[str] = Field(None, example="")
    is_active: Optional[bool] = Field(None, example=True)
    is_superuser: Optional[bool] = Field(None, example=False)

class UserResponse(UserBase):
    id: UUID
    is_active: bool

    model_config = {"from_attributes": True}
