# Architecture: Publishing Service Backend

## Overview
A FastAPI-based backend service that automates SEO content generation and WordPress publishing. Built with a service-oriented architecture that decouples API routing, business logic, and third-party provider integrations.

## Core Components
- **API Layer (FastAPI):** RESTful endpoints for managing blogs, credentials, pipeline configurations, runs, and articles. Uses Pydantic for request/response validation.
- **Service Layer:** Houses the business logic for CRUD operations and pipeline services (article generation, validation, image generation, publishing, CSV export).
- **Database Layer (SQLAlchemy 2.0):** Async ORM with UUID primary keys. Supports SQLite (local dev) and PostgreSQL (production).
- **Provider Abstraction Layer:** ABCs for LLM, Image Generation, and WordPress publishing. ProviderFactory resolves providers from DB credentials.
- **Task Infrastructure (Celery):** Background worker system. In eager mode (no Redis), tasks execute synchronously. In production, uses Redis broker.
- **Pipeline Engine:** Orchestrates article generation flow (generate → validate → images → publish → export). Supports single article and bulk (parallelized) modes.

## Data Model Relationships
```
Blog 1──1 PipelineConfig (blog_id unique FK)
Blog 1──N Run (blog_id FK)
Blog 1──N Article (blog_id FK, for single-article flow)
Run  1──N Article (run_id FK, nullable for single articles)
Credential (standalone, unique on provider+key_name)
```

## Pipeline Architecture
```
API endpoint (trigger)
    ↓
Celery task (sync entry point)
    ↓ asyncio.run()
Pipeline orchestration (async)
    ↓
Pipeline services (business logic)
    ↓
Providers (LLM, Image, WordPress) via ProviderFactory
```

### Services
- **ArticleGenerator** — LLM article generation with retry loop + validation + soft fixes
- **ArticleValidator** — LLM-powered article repair with JSON patch application
- **KeywordAnalyzer** — LLM keyword analysis producing BrainOutput from pin data
- **ImageGeneratorService** — Image generation + download via ImageProvider
- **PublisherService** — WordPress publishing (markdown→HTML, media upload, post creation)
- **CSVExporter** — Pinterest bulk-upload CSV with scheduled publish dates
- **CategoryResolver** — Category auto-assignment scoring algorithm (pure function)

### Dataclasses
- **ArticlePayload** — 7 fields: title, article_markdown, hero_image_prompt, detail_image_prompt, seo_title, meta_description, focus_keyword
- **BrainOutput** — 8 fields: primary_keyword, image_generation_prompt, pin_text_overlay, pin_title, pin_description, cluster_label, supporting_terms, seasonal_angle

### Pipeline Flows
1. **Single Article:** Load blog → create providers → generate → validate → images → publish → update DB
2. **Bulk Pipeline:** Create Run → for each keyword create Article → process concurrently via asyncio.Semaphore → update counts → generate CSV

## System Invariants
- **Async Everywhere:** All I/O operations (DB, HTTP) must be asynchronous. Only Celery task entry points use asyncio.run().
- **UUIDs:** All primary keys are UUIDs.
- **UTC Timestamps:** All timestamps stored in UTC with timezone info.
- **Soft Delete:** Blogs are never permanently deleted; marked as inactive.
- **Encryption at Rest:** Sensitive keys MUST be encrypted with Fernet.
- **No Decrypted Secrets in API:** API responses must NEVER include decrypted credentials.
- **Provider Decoupling:** Business logic depends on Provider ABCs, not concrete implementations.
- **No os.getenv()/load_dotenv():** All config from Settings class or database.
- **Per-Article Error Isolation:** One failing article does not kill the entire bulk run.
- **Status Persistence:** DB updates at each status transition for crash safety.
