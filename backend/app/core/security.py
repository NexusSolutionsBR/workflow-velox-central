import jwt
import bcrypt
from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from typing import Annotated, Optional
from sqlmodel import Session
from app.core.config import settings
from app.core.database import get_session
from app.models.domain import User

# auto_error=False permite fallback para cookie quando o header não está presente
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )

def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(),
    ).decode("utf-8")

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(days=1))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm="HS256")

def get_current_user(
    request: Request,
    token_from_header: Annotated[Optional[str], Depends(oauth2_scheme)],
    session: Annotated[Session, Depends(get_session)],
) -> User:
    # Cookie httpOnly tem prioridade; Bearer header como fallback (ex: Swagger UI)
    token = request.cookies.get("access_token") or token_from_header
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Não autenticado",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exception
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
        user_id: str = payload.get("id")
        if user_id is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception

    user = session.get(User, user_id)
    if user is None:
        raise credentials_exception
    return user

CurrentUserDep = Annotated[User, Depends(get_current_user)]
DbSessionDep = Annotated[Session, Depends(get_session)]

def require_role(roles: list[str]):
    def role_checker(current_user: CurrentUserDep):
        if current_user.role not in roles:
            raise HTTPException(status_code=403, detail="Acesso negado: permissão insuficiente")
        return current_user
    return role_checker

# Dependência reutilizável para rotas restritas a administradores.
AdminUserDep = Annotated[User, Depends(require_role(["ADMIN"]))]
