#!/bin/bash
set -e

# Create frontend directory if it doesn't exist
mkdir -p frontend/src/app frontend/src/components frontend/src/lib frontend/src/hooks frontend/public

# Copy .env.local.example to .env.local if it doesn't exist
if [ ! -f frontend/.env.local ]; then
  cp frontend/.env.local.example frontend/.env.local 2>/dev/null || true
fi

# Install dependencies
cd frontend
npm install
cd ..
