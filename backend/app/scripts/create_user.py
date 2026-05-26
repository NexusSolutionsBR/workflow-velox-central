"""
Script CLI para criar usuários no sistema Velox.

Uso:
  docker compose exec backend python -m app.scripts.create_user
"""

import sys
import getpass
from sqlmodel import SQLModel, Session, select
from app.core.database import engine
from app.core.security import get_password_hash
from app.models.domain import User


def main():
    SQLModel.metadata.create_all(engine)

    print("\n══════════════════════════════════════")
    print("  Velox — Criar Novo Usuário")
    print("══════════════════════════════════════\n")

    name = input("Nome completo: ").strip()
    if not name:
        print("❌ Nome não pode ser vazio.")
        sys.exit(1)

    email = input("E-mail: ").strip()
    if not email:
        print("❌ E-mail não pode ser vazio.")
        sys.exit(1)

    password = getpass.getpass("Senha: ")
    if len(password) < 6:
        print("❌ Senha deve ter pelo menos 6 caracteres.")
        sys.exit(1)

    confirm = getpass.getpass("Confirmar senha: ")
    if password != confirm:
        print("❌ As senhas não conferem.")
        sys.exit(1)

    print("\nRoles disponíveis: ADMIN, OPERATOR")
    role = input("Role [OPERATOR]: ").strip().upper() or "OPERATOR"
    if role not in ("ADMIN", "OPERATOR"):
        print("❌ Role inválida.")
        sys.exit(1)

    with Session(engine) as session:
        existing = session.exec(select(User).where(User.email == email)).first()
        if existing:
            print(f"❌ Já existe um usuário com o e-mail '{email}'.")
            sys.exit(1)

        user = User(
            name=name,
            email=email,
            password=get_password_hash(password),
            role=role,
        )
        session.add(user)
        session.commit()

    print(f"\n✅ Usuário '{name}' ({role}) criado com sucesso!")


if __name__ == "__main__":
    main()
