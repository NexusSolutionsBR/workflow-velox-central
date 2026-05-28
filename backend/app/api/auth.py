from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel
from app.core.security import DbSessionDep, verify_password, get_password_hash, create_access_token
from app.models.domain import User
from sqlmodel import select

router = APIRouter()

class LoginRequest(BaseModel):
    email: str
    password: str

class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str


@router.post("/login")
def login(data: LoginRequest, response: Response, session: DbSessionDep):
    user = session.exec(select(User).where(User.email == data.email)).first()
    if not user or not verify_password(data.password, user.password):
        raise HTTPException(status_code=401, detail="Credenciais inválidas")

    token = create_access_token(data={"id": user.id, "role": user.role})
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,       # inacessível ao JavaScript
        samesite="lax",
        secure=False,        # True em produção (HTTPS)
        max_age=86400,       # 1 dia
        path="/",
    )
    return {"access_token": token, "token_type": "bearer", "user": {"id": user.id, "name": user.name, "role": user.role}}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(key="access_token", path="/")
    return {"message": "Logout realizado"}


@router.post("/register")
def register(data: RegisterRequest, session: DbSessionDep):
    existing = session.exec(select(User).where(User.email == data.email)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email já em uso")

    user = User(
        name=data.name,
        email=data.email,
        password=get_password_hash(data.password),
        role="OPERATOR",    # role fixo — não aceitar role do cliente
    )
    session.add(user)
    session.commit()
    return {"message": "Usuário criado"}
