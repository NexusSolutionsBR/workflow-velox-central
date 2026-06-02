from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel
from app.core.security import DbSessionDep, verify_password, create_access_token
from app.core.config import settings
from app.models.domain import User
from sqlmodel import select

router = APIRouter()


class LoginRequest(BaseModel):
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
        httponly=True,
        samesite="lax",
        secure=settings.COOKIE_SECURE,
        max_age=86400,
        path="/",
    )
    # Token devolvido no corpo para uso externo (clientes/integrações fora do browser).
    # No browser, o cookie httpOnly continua sendo a fonte usada pelo frontend.
    return {"access_token": token, "token_type": "bearer", "user": {"id": user.id, "name": user.name, "role": user.role}}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(key="access_token", path="/")
    return {"message": "Logout realizado"}
