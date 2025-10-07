#!/bin/bash

# Start the FastAPI app first (it's the primary service)
echo "Starting FastAPI app..."
uvicorn app.api.main:app --host 0.0.0.0 --port 3000 &
APP_PID=$!

# Give the app a moment to start
sleep 2

# Start the worker in the background (with retry logic)
echo "Starting Docket worker..."
python -m app.worker &
WORKER_PID=$!

# Function to cleanup processes
cleanup() {
    echo "Shutting down..."
    kill $WORKER_PID $APP_PID 2>/dev/null
    wait $WORKER_PID $APP_PID 2>/dev/null
    exit 0
}

# Handle shutdown signals
trap cleanup SIGTERM SIGINT

# Wait for the main app process (worker can restart if needed)
wait $APP_PID

# If the main app exits, shut down everything
echo "Main app exited, shutting down..."
cleanup
