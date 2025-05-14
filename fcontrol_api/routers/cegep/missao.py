from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from fcontrol_api.database import get_session

Session = Annotated[AsyncSession, Depends(get_session)]

router = APIRouter(prefix='/missoes')
