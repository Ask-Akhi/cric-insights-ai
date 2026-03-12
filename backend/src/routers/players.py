from fastapi import APIRouter

router = APIRouter()

@router.get("/")
def list_players(q: str | None = None):
    # ...placeholder implementation...
    return {"players": [], "query": q}
