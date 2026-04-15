#!/bin/bash
set -e

# Install frontend dependencies
cd frontend
npm install
cd ..

# Verify backend venv exists (for pytest)
if [ ! -d "backend/.venv" ]; then
    echo "backend/.venv not found — skipping Python install"
fi
