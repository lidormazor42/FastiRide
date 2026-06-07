import os
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

app = FastAPI()
templates = Jinja2Templates(directory="templates")

VALID_PREFIX = "ozora-"


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/validate")
async def validate(request: Request, ticket_code: str = Form(...)):
    if ticket_code.lower().startswith(VALID_PREFIX):
        return RedirectResponse(url="/ride-board", status_code=303)
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "error": "Invalid ticket code. Must start with OZORA-"},
        status_code=400,
    )


@app.get("/ride-board", response_class=HTMLResponse)
async def ride_board(request: Request):
    return templates.TemplateResponse("board.html", {"request": request})


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
