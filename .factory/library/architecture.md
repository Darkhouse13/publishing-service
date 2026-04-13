# Architecture: Publishing Service Backend

## Overview
A FastAPI-based backend service designed to automate SEO content generation and WordPress publishing. Built with a service-oriented architecture that decouples API routing, business logic, and third-party provider integrations.

## Core Components
- **API Layer (FastAPI):** RESTful endpoints for managing blogs, credentials, and pipeline configurations. Uses Pydantic for request/response validation.
- **Service Layer:** Houses the business logic for CRUD operations and provider orchestration. Encapsulates database interactions.
- **Database Layer (SQLAlchemy 2.0):** Async ORM with UUID primary keys. Supports SQLite (local dev) and PostgreSQL (production).
- **Provider Abstraction Layer:** ABCs for LLM, Image Generation, and WordPress publishing. Allows for swapping implementations (e.g., DeepSeek vs. OpenAI) without touching core logic.
- **Task Infrastructure (Celery + Redis):** Async background worker system for long-running pipeline tasks (e.g., scraping, LLM generation).

## Data Flow
1. **Request:** Client hits a FastAPI endpoint.
2. **Service:** Router calls the appropriate service method.
3. **Database:** Service uses SQLAlchemy `AsyncSession` to interact with the DB.
4. **Encryption:** Sensitive credentials (API keys) are encrypted using Fernet before storage and decrypted only when instantiating a provider.
5. **Provider:** For pipeline tasks, the service layer instantiates a provider via the `ProviderFactory` using stored credentials.
6. **Background Task:** Long-running operations are offloaded to Celery workers via Redis.

## System Invariants
- **Async Everywhere:** All I/O operations (DB, HTTP) must be asynchronous.
- **UUIDs:** All primary keys are UUIDs.
- **UTC Timestamps:** All timestamps are stored and handled in UTC with timezone info.
- **Soft Delete:** Blogs are never permanently deleted from the DB; they are marked as inactive.
- **Encryption at Rest:** Sensitive keys MUST be encrypted with Fernet. No plaintext secrets in the DB.
- **No Decrypted Secrets in API:** API responses must NEVER include decrypted credentials or passwords.
- **Provider Decoupling:** Business logic must depend on Provider ABCs, not concrete implementations.
