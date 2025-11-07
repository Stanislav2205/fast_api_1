from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from contextlib import asynccontextmanager
from datetime import timedelta

from .database import get_db, engine
from .models import Advertisement, User, Base
from .schemas import (
    AdvertisementCreate, AdvertisementUpdate, AdvertisementResponse,
    UserCreate, UserUpdate, UserResponse,
    LoginRequest, LoginResponse
)
from .auth import (
    get_password_hash, verify_password, create_access_token,
    get_optional_user, get_current_active_user
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield

app = FastAPI(title="Advertisements API", lifespan=lifespan)

@app.post("/login", response_model=LoginResponse)
async def login(login_data: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == login_data.username))
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(login_data.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )
    
    access_token = create_access_token(data={"sub": user.username}, expires_delta=timedelta(hours=48))
    return LoginResponse(token=access_token)

@app.post("/user", response_model=UserResponse)
async def create_user(user: UserCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == user.username))
    existing_user = result.scalar_one_or_none()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )
    
    if user.group not in ["user", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Group must be 'user' or 'admin'"
        )
    
    db_user = User(
        username=user.username,
        password=get_password_hash(user.password),
        group=user.group
    )
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)
    return UserResponse(id=db_user.id, username=db_user.username, group=db_user.group)

@app.get("/user/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Получение пользователя по id (доступно неавторизованным)"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserResponse(id=user.id, username=user.username, group=user.group)

@app.patch("/user/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_update: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    if current_user.group != "admin" and current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions"
        )
    
    if user_update.group is not None and current_user.group != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin can change user group"
        )
    
    if user_update.group is not None and user_update.group not in ["user", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Group must be 'user' or 'admin'"
        )
    
    update_data = user_update.model_dump(exclude_unset=True)
    if "password" in update_data:
        update_data["password"] = get_password_hash(update_data["password"])
    
    if "username" in update_data:
        result = await db.execute(select(User).where(User.username == update_data["username"]))
        existing_user = result.scalar_one_or_none()
        if existing_user and existing_user.id != user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already registered"
            )
    
    if update_data:
        await db.execute(update(User).where(User.id == user_id).values(**update_data))
        await db.commit()
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
    
    return UserResponse(id=user.id, username=user.username, group=user.group)

@app.delete("/user/{user_id}")
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    if current_user.group != "admin" and current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions"
        )
    
    await db.execute(delete(User).where(User.id == user_id))
    await db.commit()
    return {"message": "User deleted"}

@app.post("/advertisement", response_model=AdvertisementResponse)
async def create_ad(
    ad: AdvertisementCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user)
):
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    
    ad_data = ad.model_dump()
    ad_data["owner_id"] = current_user.id
    db_ad = Advertisement(**ad_data)
    db.add(db_ad)
    await db.commit()
    await db.refresh(db_ad)
    return db_ad

@app.get("/advertisement/{ad_id}", response_model=AdvertisementResponse)
async def get_ad(
    ad_id: int,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Advertisement).where(Advertisement.id == ad_id))
    ad = result.scalar_one_or_none()
    if not ad:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Advertisement not found")
    return ad

@app.patch("/advertisement/{ad_id}", response_model=AdvertisementResponse)
async def update_ad(
    ad_id: int,
    ad_update: AdvertisementUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user)
):
    result = await db.execute(select(Advertisement).where(Advertisement.id == ad_id))
    ad = result.scalar_one_or_none()
    if not ad:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Advertisement not found")
    
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    
    if current_user.group != "admin":
        if ad.owner_id is None or ad.owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions"
            )
    
    update_data = ad_update.model_dump(exclude_unset=True)
    if update_data:
        await db.execute(update(Advertisement).where(Advertisement.id == ad_id).values(**update_data))
        await db.commit()
        result = await db.execute(select(Advertisement).where(Advertisement.id == ad_id))
        ad = result.scalar_one_or_none()
    return ad

@app.delete("/advertisement/{ad_id}")
async def delete_ad(
    ad_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user)
):
    result = await db.execute(select(Advertisement).where(Advertisement.id == ad_id))
    ad = result.scalar_one_or_none()
    if not ad:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Advertisement not found")
    
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    
    if current_user.group != "admin":
        if ad.owner_id is None or ad.owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions"
            )
    
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
