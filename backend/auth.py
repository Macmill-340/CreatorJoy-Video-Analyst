import os
from dotenv import load_dotenv
import jwt
from datetime import datetime, timedelta, timezone
import bcrypt
from fastapi import Depends, status, HTTPException
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel


load_dotenv()

SECRET_KEY = os.getenv('SECRET_ENV_KEY')
ALGORITHM = os.getenv('ALGORITHM_ENV_KEY')

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))

def create_access_token(data:dict, expires_delta: timedelta=timedelta(hours=2)) -> str:
    to_encode=data.copy()
    expire=datetime.now(timezone.utc) + expires_delta
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

class UserContext(BaseModel):
    username: str
    role: str
    tenant_id: int


def get_current_user(token: str = Depends(oauth2_scheme)) -> UserContext:
    """Dependency that extracts user info & tenant_id from JWT token"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        role: str = payload.get("role")
        tenant_id: int = payload.get("tenant_id")

        if username is None or role is None or tenant_id is None:
            raise HTTPException(status_code=401, detail="Invalid token claims.")
        return UserContext(username=username, role=role, tenant_id=tenant_id)
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token.")