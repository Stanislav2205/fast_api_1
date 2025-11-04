from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from contextlib import asynccontextmanager

from .database import get_db, engine
from .models import Advertisement, Base
from .schemas import AdvertisementCreate, AdvertisementUpdate, AdvertisementResponse

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield

app = FastAPI(title="Advertisements API", lifespan=lifespan)

@app.post("/advertisement", response_model=AdvertisementResponse)
async def create_ad(ad: AdvertisementCreate, db: AsyncSession = Depends(get_db)):
    db_ad = Advertisement(**ad.model_dump())
    db.add(db_ad)
    await db.commit()
    await db.refresh(db_ad)
    return db_ad

@app.get("/advertisement/{ad_id}", response_model=AdvertisementResponse)
async def get_ad(ad_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Advertisement).where(Advertisement.id == ad_id))
    ad = result.scalar_one_or_none()
    if not ad:
        raise HTTPException(404, "Advertisement not found")
    return ad

@app.patch("/advertisement/{ad_id}", response_model=AdvertisementResponse)
async def update_ad(ad_id: int, ad_update: AdvertisementUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Advertisement).where(Advertisement.id == ad_id))
    ad = result.scalar_one_or_none()
    if not ad:
        raise HTTPException(404, "Advertisement not found")
    
    update_data = ad_update.model_dump(exclude_unset=True)
    if update_data:
        await db.execute(update(Advertisement).where(Advertisement.id == ad_id).values(**update_data))
        await db.commit()
        result = await db.execute(select(Advertisement).where(Advertisement.id == ad_id))
        ad = result.scalar_one_or_none()
    return ad

@app.delete("/advertisement/{ad_id}")
async def delete_ad(ad_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Advertisement).where(Advertisement.id == ad_id))
    ad = result.scalar_one_or_none()
    if not ad:
        raise HTTPException(404, "Advertisement not found")
    await db.execute(delete(Advertisement).where(Advertisement.id == ad_id))
    await db.commit()
    return {"message": "Advertisement deleted"}

@app.get("/advertisement", response_model=List[AdvertisementResponse])
async def search_ads(
    title: Optional[str] = None,
    author: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    db: AsyncSession = Depends(get_db)
):
    query = select(Advertisement)
    if title:
        query = query.where(Advertisement.title.icontains(title))
    if author:
        query = query.where(Advertisement.author.icontains(author))
    if min_price is not None:
        query = query.where(Advertisement.price >= min_price)
    if max_price is not None:
        query = query.where(Advertisement.price <= max_price)
    
    result = await db.execute(query)
    return result.scalars().all()