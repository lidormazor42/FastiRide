import os
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

VALID_PREFIX = "ozora-"


class TicketRequest(BaseModel):
    ticket_code: str


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.post("/api/validate")
async def validate(body: TicketRequest):
    if body.ticket_code.lower().startswith(VALID_PREFIX):
        return {"valid": True}
    return {"valid": False, "error": "Invalid ticket code. Must start with OZORA-"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
