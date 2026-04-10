#!/bin/bash
source venv/bin/activate
export PORT=8001
uvicorn app.main:app --host 0.0.0.0 --port $PORT --reload
