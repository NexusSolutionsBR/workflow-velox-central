# Pendências de Segurança — Velox

## Para produção, implementar antes do deploy:

### 1. Rate limiting no login (brute force)
- **Risco:** sem limite de tentativas, qualquer IP pode testar senhas indefinidamente
- **Solução:** instalar `slowapi` e aplicar `@limiter.limit("5/minute")` no `POST /auth/login`
- **Comandos:**
  ```bash
  pip install slowapi
  ```
  ```python
  # backend/app/main.py
  from slowapi import Limiter, _rate_limit_exceeded_handler
  from slowapi.util import get_remote_address
  from slowapi.errors import RateLimitExceeded

  limiter = Limiter(key_func=get_remote_address)
  app.state.limiter = limiter
  app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
  ```
  ```python
  # backend/app/api/auth.py
  from slowapi import Limiter
  from slowapi.util import get_remote_address
  from fastapi import Request

  limiter = Limiter(key_func=get_remote_address)

  @router.post("/login")
  @limiter.limit("5/minute")
  def login(request: Request, data: LoginRequest, ...):
      ...
  ```

### 2. Cookie `Secure=True` (HTTPS obrigatório em produção)
- **Risco:** em HTTP, o cookie de sessão pode ser interceptado em redes inseguras
- **Solução:** ativar a flag `secure=True` no `set_cookie` quando em produção
- **Arquivo:** `backend/app/api/auth.py`
  ```python
  # Adicionar no .env:
  # APP_ENV=production

  secure = settings.APP_ENV == "production"
  response.set_cookie(
      key="access_token",
      value=token,
      httponly=True,
      samesite="lax",
      secure=secure,   # True em produção
      max_age=86400,
      path="/",
  )
  ```
- Lembrar de adicionar `APP_ENV=production` no `.env` de produção

### 3. JWT_SECRET forte
- **Risco:** secret fraco pode ser quebrado por força bruta (HS256 é simétrico)
- **Solução:** gerar um secret de pelo menos 256 bits aleatórios
  ```bash
  python -c "import secrets; print(secrets.token_hex(32))"
  ```
- Substituir `your_jwt_secret_here` no `.env` pelo valor gerado
- Nunca versionar o `.env` com o secret real (garantir `.gitignore`)

### 4. HTTPS em produção
- Todo o tráfego deve passar por TLS
- Configurar proxy reverso (nginx/Traefik) com certificado SSL antes de expor o sistema
- Sem HTTPS, a flag `Secure` do cookie e o próprio JWT em trânsito ficam expostos

### 5. Registrar admins manualmente
- `/auth/register` está aberto (sem autenticação) e sempre cria `OPERATOR`
- Para criar usuários `ADMIN`, usar o script CLI:
  ```bash
  docker compose exec backend python -m app.scripts.create_user
  ```
- Avaliar se `/auth/register` deve ser desabilitado ou protegido por auth admin em produção

---

*Gerado em: 22/05/2026*
