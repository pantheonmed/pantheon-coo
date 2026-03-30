from fastapi import FastAPI
import os

app = FastAPI(title="Pantheon COO OS")


@app.get("/health")
async def health():
    return {"status": "ok", "version": "2.0.0"}


@app.get("/")
async def root():
    return {"message": "Pantheon COO OS is running!"}
