import os
import sqlite3
from datetime import datetime, timedelta
from typing import Optional, Dict

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

DB_PATH = os.getenv('USERS_DB', os.path.join('data', 'users.db'))
SECRET_KEY = os.getenv('SECRET_KEY', 'change-this-secret')
ALGORITHM = 'HS256'
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")


def _get_conn():
    os.makedirs(os.path.dirname(DB_PATH) or '.', exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        hashed_password TEXT NOT NULL
    )""")
    conn.commit()
    return conn


def get_user_by_username(username: str) -> Optional[Dict]:
    conn = _get_conn()
    cur = conn.execute("SELECT id, username, hashed_password FROM users WHERE username = ?", (username,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return {"id": row[0], "username": row[1], "hashed_password": row[2]}


def get_user_by_id(user_id: int) -> Optional[Dict]:
    conn = _get_conn()
    cur = conn.execute("SELECT id, username, hashed_password FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return {"id": row[0], "username": row[1], "hashed_password": row[2]}


def create_user(username: str, password: str) -> Dict:
    if get_user_by_username(username) is not None:
        raise HTTPException(status_code=400, detail="Username already exists")
    hashed = pwd_context.hash(password)
    conn = _get_conn()
    cur = conn.execute("INSERT INTO users (username, hashed_password) VALUES (?, ?)", (username, hashed))
    conn.commit()
    user_id = cur.lastrowid
    conn.close()
    return {"id": user_id, "username": username}


def verify_password(plain_password, hashed_password) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def authenticate_user(username: str, password: str) -> Optional[Dict]:
    user = get_user_by_username(username)
    if not user:
        return None
    if not verify_password(password, user['hashed_password']):
        return None
    return {"id": user['id'], "username": user['username']}


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = int(payload.get("sub")) if payload.get("sub") else None
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = get_user_by_id(user_id)
    if user is None:
        raise credentials_exception
    return {"id": user['id'], "username": user['username']}
