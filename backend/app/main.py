from fastapi import FastAPI

app = FastAPI()

@app.get("/")  # <-- define la ruta raíz
def read_root():
    return {"message": "¡Hola, FastAPI está funcionando!"}

@app.get("/health")
def health():
    return {"status": "ok"}

# uvicorn app.main:app --reload
