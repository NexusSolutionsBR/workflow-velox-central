import httpx
from app.core.config import settings


async def fetch_session_messages(session_id: str):
    """
    Busca todas as mensagens de uma sessão da Helena, paginando via
    `Page` + `hasMorePages` (paginação por número de página, não cursor).
    """
    all_messages = []
    page = 1
    headers = {"Authorization": f"Bearer {settings.HELENA_API_KEY}"}

    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            params = {
                "SessionId": session_id,
                "PageNumber": page,
                "PageSize": 100,
                "OrderBy": "createdAt",
                "OrderDirection": "ASCENDING"
            }
            try:
                response = await client.get(
                    settings.HELENA_API_URL, params=params, headers=headers
                )
                response.raise_for_status()
                data = response.json()
            except Exception as e:
                print(f"Erro buscando página {page}: {e}. Retornando {len(all_messages)} itens parciais.")
                return all_messages

            if isinstance(data, list):
                all_messages.extend(data)
                return all_messages

            if not isinstance(data, dict):
                return all_messages

            items = data.get("items", [])
            all_messages.extend(items)
            print(
                f"[Helena] Página {data.get('pageNumber', page)}/{data.get('totalPages', '?')} — "
                f"{len(items)} itens (acumulado: {len(all_messages)}/{data.get('totalItems', '?')})"
            )

            if not data.get("hasMorePages"):
                return all_messages
            page += 1

    return all_messages
