#!/bin/bash
source venv/bin/activate
export PORT=8000
uvicorn app.main:app --host 0.0.0.0 --port $PORT --reload
