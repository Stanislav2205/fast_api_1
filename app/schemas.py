from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class AdvertisementCreate(BaseModel):
    title: str
    description: str
    price: float
    author: str

class AdvertisementUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    author: Optional[str] = None

class AdvertisementResponse(BaseModel):
    id: int
    title: str
    description: str
    price: float
    author: str
    created_at: datetime

    class Config:
        from_attributes = True