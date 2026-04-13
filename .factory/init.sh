#!/bin/bash
set -e

mkdir -p backend/app/models backend/app/schemas backend/app/api backend/app/services backend/app/providers/llm backend/app/providers/image backend/app/providers/wordpress backend/app/tasks backend/tests backend/alembic/versions backend/artifacts

if [ ! -f backend/.env ]; then
  echo "DEBUG=true" > backend/.env
  echo "DATABASE_URL=sqlite+aiosqlite:///./dev.db" >> backend/.env
  echo "ENCRYPTION_KEY=$(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')" >> backend/.env
fi
