from fastapi import Header, HTTPException

# ... resto do arquivo permanece igual ...

@router.post("/bot/stop")
async def bot_stop(authorization: str | None = Header(default=None)):
    global _bot

    if _API_TOKEN:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401)
        token = authorization.split(" ", 1)[1]
        if token != _API_TOKEN:
            raise HTTPException(status_code=401)

    if _bot is not None:
        _bot.stop()
    return {"status": "stopped"}
