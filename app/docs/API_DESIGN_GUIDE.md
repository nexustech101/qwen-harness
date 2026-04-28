## API Design Guide - Best Practices And Project Structure

A robust production FastAPI project should be structured around **separation of concerns**, not around FastAPI itself. FastAPI should be the delivery layer, not the center of your architecture.

The core philosophy is:

> **Routes should handle HTTP. Services should handle business logic. Repositories should handle persistence. Models should represent database state. Schemas should represent API contracts.**

FastAPI’s own docs recommend splitting larger applications across multiple files using `APIRouter`, which is similar in purpose to Flask blueprints. ([FastAPI][1]) FastAPI also does not force a specific database or ORM; SQLModel, SQLAlchemy, PostgreSQL, MySQL, SQLite, and others are all viable. ([FastAPI][2])

A strong production structure looks like this:

```text
project/
│
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── dependencies.py
│   ├── exceptions.py
│   ├── logging.py
│
│   ├── api/
│   │   ├── __init__.py
│   │   ├── router.py
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── router.py
│   │       └── routes/
│   │           ├── __init__.py
│   │           ├── users.py
│   │           ├── auth.py
│   │           ├── invoices.py
│   │           └── health.py
│
│   ├── core/
│   │   ├── __init__.py
│   │   ├── security.py
│   │   ├── settings.py
│   │   ├── permissions.py
│   │   └── constants.py
│
│   ├── db/
│   │   ├── __init__.py
│   │   ├── session.py
│   │   ├── base.py
│   │   └── migrations/
│
│   ├── models/
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── invoice.py
│   │   └── payment.py
│
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── invoice.py
│   │   ├── payment.py
│   │   └── common.py
│
│   ├── repositories/
│   │   ├── __init__.py
│   │   ├── user_repository.py
│   │   ├── invoice_repository.py
│   │   └── payment_repository.py
│
│   ├── services/
│   │   ├── __init__.py
│   │   ├── user_service.py
│   │   ├── auth_service.py
│   │   ├── invoice_service.py
│   │   ├── payment_service.py
│   │   └── email_service.py
│
│   ├── tasks/
│   │   ├── __init__.py
│   │   ├── email_tasks.py
│   │   └── invoice_tasks.py
│
│   ├── integrations/
│   │   ├── __init__.py
│   │   ├── stripe_client.py
│   │   ├── paypal_client.py
│   │   └── smtp_client.py
│
│   └── utils/
│       ├── __init__.py
│       ├── datetime.py
│       ├── pagination.py
│       └── validators.py
│
├── tests/
│   ├── conftest.py
│   ├── unit/
│   ├── integration/
│   └── e2e/
│
├── alembic/
│   ├── versions/
│   └── env.py
│
├── scripts/
│   ├── seed_db.py
│   └── create_admin.py
│
├── pyproject.toml
├── alembic.ini
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── .env.pro
├── .env.dev
├── API_REFERENCE.md
├── ARCHITECTURE.md
├── CLAUDE.md
├── CODEX.md
└── README.md
```

## The main idea

A weak FastAPI project often looks like this:

```text
routes.py
models.py
schemas.py
database.py
main.py
```

That is fine for a tutorial, but it does not scale. Once your app grows, those files become dumping grounds.

A production structure should make the following questions easy to answer:

| Question                               | Where should I look?              |
| -------------------------------------- | --------------------------------- |
| Where is the HTTP endpoint?            | `api/v1/routes/`                  |
| Where is request/response validation?  | `schemas/`                        |
| Where is business logic?               | `services/`                       |
| Where are database tables defined?     | `models/`                         |
| Where are database queries?            | `repositories/`                   |
| Where is authentication/security code? | `core/security.py`                |
| Where are external API clients?        | `integrations/`                   |
| Where is app configuration?            | `core/settings.py` or `config.py` |
| Where are background jobs?             | `tasks/`                          |

The goal is to avoid putting everything into routes.

A route should not know how to calculate invoice totals, hash passwords, decide permissions, talk to Stripe, or construct complex database queries. It should receive HTTP input, call the appropriate service, and return an HTTP response.

---

# Folder-by-folder philosophy

## `app/main.py`

This is the application entrypoint.

It should create the FastAPI app, register routers, middleware, exception handlers, startup/shutdown events, and health checks.

Example:

```python
from fastapi import FastAPI
from app.api.router import api_router
from app.core.settings import settings

def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
    )

    app.include_router(api_router)

    return app

app = create_app()
```

Keep this file small. It should compose the app, not contain business logic.

---

## `app/api/`

This is the HTTP/API layer.

It contains routers, route registration, versioning, and endpoint modules.

```text
api/
├── router.py
└── v1/
    ├── router.py
    └── routes/
        ├── users.py
        ├── auth.py
        └── invoices.py
```

### `api/router.py`

Top-level API router.

```python
from fastapi import APIRouter
from app.api.v1.router import router as v1_router

api_router = APIRouter()
api_router.include_router(v1_router, prefix="/api/v1")
```

### `api/v1/router.py`

Version-specific router.

```python
from fastapi import APIRouter
from app.api.v1.routes import users, auth, invoices

router = APIRouter()
router.include_router(auth.router, prefix="/auth", tags=["Auth"])
router.include_router(users.router, prefix="/users", tags=["Users"])
router.include_router(invoices.router, prefix="/invoices", tags=["Invoices"])
```

### `api/v1/routes/users.py`

Route files should be thin.

```python
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.user import UserCreate, UserRead
from app.services.user_service import UserService

router = APIRouter()

@router.post("/", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
):
    service = UserService(db)
    return service.create_user(payload)
```

The route should answer:

1. What HTTP method?
2. What URL?
3. What request schema?
4. What response schema?
5. Which service handles the operation?

That is mostly it.

---

## `app/schemas/`

Schemas are your **API contracts**.

These should usually be Pydantic models. They define what comes into and out of your API.

Example:

```python
from pydantic import BaseModel, EmailStr
from datetime import datetime

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str

class UserUpdate(BaseModel):
    full_name: str | None = None

class UserRead(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    created_at: datetime

    model_config = {
        "from_attributes": True
    }
```

A common mistake is using the same object for:

1. Database models
2. Request validation
3. Response serialization
4. Internal service objects

Do not do that in larger apps.

You usually want separate schemas:

```text
schemas/user.py

UserCreate
UserUpdate
UserRead
UserLogin
UserPasswordChange
UserPublic
```

### Good schema naming convention

```python
UserCreate      # incoming POST body
UserUpdate      # incoming PATCH/PUT body
UserRead        # outgoing API response
UserInDB        # internal representation, if needed
UserLogin       # auth input
UserPublic      # limited public-facing response
```

Schemas are especially important because FastAPI uses them for validation and OpenAPI generation. FastAPI’s data validation and documentation story is built heavily around Pydantic-style models and Python type hints. ([SQLModel][3])

---

## `app/models/`

Models represent database tables.

If using SQLAlchemy:

```python
from sqlalchemy import Boolean, Column, Integer, String, DateTime
from sqlalchemy.sql import func
from app.db.base import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
```

Models should not contain HTTP logic. They should not know about FastAPI routes, request bodies, response schemas, or status codes.

They represent persistent state.

### Models are not schemas

This is an important distinction:

| Layer      | Example          | Purpose         |
| ---------- | ---------------- | --------------- |
| Model      | `User`           | Database table  |
| Schema     | `UserCreate`     | Request body    |
| Schema     | `UserRead`       | Response body   |
| Service    | `UserService`    | Business logic  |
| Repository | `UserRepository` | Database access |

For small apps, SQLModel can combine table models and validation models, and SQLModel is designed to work well with FastAPI, Pydantic, and SQLAlchemy. ([SQLModel][3]) But for larger production apps, I still prefer separating database models from API schemas because it gives you stronger boundaries.

---

## `app/db/`

This folder owns database configuration and lifecycle.

```text
db/
├── session.py
├── base.py
└── migrations/
```

### `db/session.py`

Creates the engine/session and exposes the FastAPI dependency.

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.settings import settings

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

For async SQLAlchemy, this would use `create_async_engine`, `AsyncSession`, and `async_sessionmaker`.

### `db/base.py`

Collects metadata for migrations.

```python
from sqlalchemy.orm import declarative_base

Base = declarative_base()
```

You may also import your models here so Alembic can detect them.

---

## `app/repositories/`

Repositories isolate database access.

This is where you put queries.

```python
from sqlalchemy.orm import Session
from app.models.user import User

class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, user_id: int) -> User | None:
        return self.db.query(User).filter(User.id == user_id).first()

    def get_by_email(self, email: str) -> User | None:
        return self.db.query(User).filter(User.email == email).first()

    def create(self, user: User) -> User:
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user
```

The repository should not decide whether a user is allowed to do something. It should not decide business rules. It should not return HTTP exceptions.

It should answer:

> “How do I retrieve or persist this data?”

Not:

> “What should the application do?”

That is the service layer’s job.

---

## `app/services/`

Services contain business logic.

This is the most important folder in a production API.

Example:

```python
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate
from app.models.user import User
from app.core.security import hash_password

class UserService:
    def __init__(self, db: Session):
        self.user_repo = UserRepository(db)

    def create_user(self, payload: UserCreate) -> User:
        existing_user = self.user_repo.get_by_email(payload.email)

        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User with this email already exists.",
            )

        user = User(
            email=payload.email,
            full_name=payload.full_name,
            hashed_password=hash_password(payload.password),
        )

        return self.user_repo.create(user)
```

In a cleaner architecture, the service layer should raise domain-specific exceptions instead of FastAPI `HTTPException`, and the API layer should translate those exceptions into HTTP responses. For many FastAPI apps, using `HTTPException` inside services is acceptable, but it does couple business logic to FastAPI.

A more decoupled version:

```python
class UserAlreadyExistsError(Exception):
    pass
```

Then in your exception handler:

```python
@app.exception_handler(UserAlreadyExistsError)
async def user_exists_handler(request, exc):
    return JSONResponse(
        status_code=409,
        content={"detail": "User with this email already exists."},
    )
```

### What belongs in services?

Put this in services:

```text
- Creating users
- Authenticating users
- Calculating invoice totals
- Applying discounts
- Checking ownership/permissions
- Creating payment sessions
- Sending emails
- Coordinating multiple repositories
- Calling external integrations
- Enforcing business rules
```

Do not put these directly in routes.

---

## `app/core/`

This folder contains application-wide infrastructure and policy.

```text
core/
├── settings.py
├── security.py
├── permissions.py
├── constants.py
└── logging.py
```

### `core/settings.py`

Use Pydantic settings or environment-based configuration.

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "My API"
    VERSION: str = "1.0.0"
    DATABASE_URL: str
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    model_config = {
        "env_file": ".env"
    }

settings = Settings()
```

### `core/security.py`

Password hashing, JWT creation, token verification, etc.

```python
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)
```

### `core/permissions.py`

Authorization helpers.

```python
def require_admin(user):
    if not user.is_admin:
        raise PermissionDeniedError("Admin access required.")
```

The distinction:

| File             | Purpose                            |
| ---------------- | ---------------------------------- |
| `security.py`    | Auth primitives: hash, verify, JWT |
| `permissions.py` | Authorization rules                |
| `settings.py`    | Runtime configuration              |
| `constants.py`   | Shared constants                   |

---

## `app/dependencies.py`

FastAPI dependencies that are shared across routes.

Example:

```python
from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.auth_service import AuthService

def get_auth_service(db: Session = Depends(get_db)) -> AuthService:
    return AuthService(db)
```

For small apps, dependencies can live next to routes. For larger apps, centralize reusable dependencies here.

Common dependencies:

```text
- get_current_user
- get_current_active_user
- get_current_admin
- get_db
- get_pagination_params
- get_service
```

---

## `app/integrations/`

External systems go here.

```text
integrations/
├── stripe_client.py
├── paypal_client.py
├── sendgrid_client.py
├── s3_client.py
└── openai_client.py
```

These modules should wrap external APIs so the rest of your app does not depend directly on SDK details.

Example:

```python
class PaymentGatewayClient:
    def create_checkout_session(self, amount_cents: int, customer_email: str) -> str:
        ...
```

Your service calls this abstraction instead of importing Stripe directly everywhere.

Bad:

```python
import stripe

@router.post("/checkout")
def checkout():
    stripe.checkout.Session.create(...)
```

Better:

```python
class PaymentService:
    def create_checkout(self, invoice_id: int):
        return self.payment_client.create_checkout_session(...)
```

This makes testing much easier.

---

## `app/tasks/`

Background jobs and async work.

Examples:

```text
tasks/
├── email_tasks.py
├── invoice_tasks.py
├── cleanup_tasks.py
└── report_tasks.py
```

This may use:

```text
- FastAPI BackgroundTasks
- Celery
- RQ
- Dramatiq
- Arq
- APScheduler
```

Use this for work that should not block the HTTP request:

```text
- Sending emails
- Generating PDFs
- Syncing external APIs
- Long-running reports
- Webhook retries
- Cleanup jobs
```

---

## `app/utils/`

Generic helper functions.

Be careful with this folder. It often becomes a junk drawer.

Good utility modules:

```text
utils/
├── datetime.py
├── pagination.py
├── slugify.py
├── validators.py
└── file_size.py
```

Bad utility modules:

```text
utils/helpers.py
utils/misc.py
utils/common.py
```

If you cannot name the file precisely, the code probably belongs somewhere else.

---

## `app/exceptions.py`

Centralized application exceptions.

```python
class AppError(Exception):
    pass

class NotFoundError(AppError):
    pass

class PermissionDeniedError(AppError):
    pass

class ConflictError(AppError):
    pass
```

This helps decouple business logic from HTTP.

Example service:

```python
if not invoice:
    raise NotFoundError("Invoice not found.")
```

Then your FastAPI exception handler maps it to a response.

---

## `tests/`

Production projects need structured tests.

```text
tests/
├── conftest.py
├── unit/
│   ├── test_user_service.py
│   └── test_invoice_service.py
├── integration/
│   ├── test_user_routes.py
│   └── test_invoice_routes.py
└── e2e/
    └── test_checkout_flow.py
```

### Test categories

| Type              | Purpose                                        |
| ----------------- | ---------------------------------------------- |
| Unit tests        | Test services, pure logic, isolated components |
| Integration tests | Test API + DB + dependencies together          |
| E2E tests         | Test full user workflows                       |
| Contract tests    | Test request/response behavior                 |
| Repository tests  | Test complex database queries                  |

Your services should be easy to unit test without spinning up the entire app.

That is one of the biggest benefits of the structure.

---

# How the layers should communicate

Use this dependency direction:

```text
routes → services → repositories → models/db
```

And:

```text
services → integrations
services → schemas
routes → schemas
repositories → models
```

Avoid this:

```text
models → routes
repositories → routes
services → routes
schemas → services
integrations → routes
```

A good mental model:

```text
HTTP layer
    ↓
Application/business layer
    ↓
Persistence/integration layer
    ↓
Database/external APIs
```

Or:

```text
api/routes
    call
services
    call
repositories / integrations
    use
models / external clients
```

---

# Routes vs services vs repositories

This is the most important distinction.

## Routes

Routes are responsible for HTTP.

They should handle:

```text
- URL paths
- HTTP methods
- request schemas
- response schemas
- dependency injection
- status codes
- auth dependencies
```

Example:

```python
@router.post("/", response_model=InvoiceRead)
def create_invoice(
    payload: InvoiceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return InvoiceService(db).create_invoice(payload, current_user)
```

## Services

Services are responsible for business behavior.

They should handle:

```text
- validation beyond simple schema validation
- permissions
- workflows
- calculations
- orchestration
- calling repositories
- calling integrations
```

Example:

```python
def create_invoice(self, payload: InvoiceCreate, user: User):
    customer = self.customer_repo.get_by_id(payload.customer_id)

    if not customer:
        raise NotFoundError("Customer not found.")

    if customer.owner_id != user.id:
        raise PermissionDeniedError("Not your customer.")

    total = calculate_invoice_total(payload.line_items)

    invoice = Invoice(...)
    return self.invoice_repo.create(invoice)
```

## Repositories

Repositories are responsible for data access.

They should handle:

```text
- SELECT
- INSERT
- UPDATE
- DELETE
- joins
- filtering
- pagination queries
- persistence behavior
```

Example:

```python
def list_by_user(self, user_id: int, limit: int, offset: int):
    return (
        self.db.query(Invoice)
        .filter(Invoice.user_id == user_id)
        .offset(offset)
        .limit(limit)
        .all()
    )
```

---

# Recommended structure by project size

## Small project

For a small API:

```text
app/
├── main.py
├── database.py
├── models.py
├── schemas.py
├── routes/
└── services/
```

This is fine for demos, prototypes, and CRUD apps.

## Medium project

For a real production app:

```text
app/
├── api/
├── core/
├── db/
├── models/
├── schemas/
├── services/
├── repositories/
└── tests/
```

This is the sweet spot for most FastAPI projects.

## Large project

For a large modular system, organize by domain:

```text
app/
├── modules/
│   ├── users/
│   │   ├── routes.py
│   │   ├── schemas.py
│   │   ├── models.py
│   │   ├── service.py
│   │   └── repository.py
│   │
│   ├── invoices/
│   │   ├── routes.py
│   │   ├── schemas.py
│   │   ├── models.py
│   │   ├── service.py
│   │   └── repository.py
│   │
│   └── payments/
│       ├── routes.py
│       ├── schemas.py
│       ├── models.py
│       ├── service.py
│       └── repository.py
│
├── core/
├── db/
└── main.py
```

This is called **vertical slice architecture** or **domain-first architecture**.

Instead of grouping all schemas together and all services together, each feature owns its own files.

For example:

```text
modules/invoices/
├── routes.py
├── schemas.py
├── models.py
├── service.py
├── repository.py
└── tests.py
```

This scales better when the app gets large because invoice-related code stays together.

---

# Layer-based vs domain-based organization

There are two valid styles.

## Layer-based

```text
models/
schemas/
services/
repositories/
routes/
```

Best for:

```text
- small to medium apps
- teams still defining conventions
- CRUD-heavy APIs
- simpler onboarding
```

## Domain-based

```text
modules/
├── users/
├── invoices/
├── payments/
└── reports/
```

Best for:

```text
- larger apps
- complex domains
- multiple teams
- feature ownership
- bounded contexts
```

My recommendation:

Use **layer-based** while learning or building small-to-medium apps.

Use **domain-based** once your app has several major business domains.

For your style of projects — invoice systems, registries, agent tooling, admin dashboards — I would use a hybrid:

```text
app/
├── core/
├── db/
├── shared/
└── modules/
    ├── users/
    ├── auth/
    ├── invoices/
    ├── payments/
    └── documents/
```

Each module owns its own route/schema/model/service/repository.

---

# Example domain module structure

```text
app/modules/invoices/
├── __init__.py
├── routes.py
├── schemas.py
├── models.py
├── repository.py
├── service.py
├── permissions.py
├── dependencies.py
└── tests/
    ├── test_invoice_service.py
    └── test_invoice_routes.py
```

This is clean because everything related to invoices lives together.

Example:

```python
# app/modules/invoices/routes.py

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.invoices.schemas import InvoiceCreate, InvoiceRead
from app.modules.invoices.service import InvoiceService
from app.modules.auth.dependencies import get_current_user

router = APIRouter(prefix="/invoices", tags=["Invoices"])

@router.post("/", response_model=InvoiceRead)
def create_invoice(
    payload: InvoiceCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    return InvoiceService(db).create_invoice(payload, current_user)
```

```python
# app/modules/invoices/service.py

class InvoiceService:
    def __init__(self, db):
        self.invoice_repo = InvoiceRepository(db)

    def create_invoice(self, payload, current_user):
        total = sum(item.quantity * item.unit_price for item in payload.items)

        invoice = Invoice(
            user_id=current_user.id,
            client_id=payload.client_id,
            total=total,
            status="draft",
        )

        return self.invoice_repo.create(invoice)
```

```python
# app/modules/invoices/repository.py

class InvoiceRepository:
    def __init__(self, db):
        self.db = db

    def create(self, invoice):
        self.db.add(invoice)
        self.db.commit()
        self.db.refresh(invoice)
        return invoice
```

This is usually the structure I would recommend for production.

---

# What not to do

Avoid putting business logic in routes:

```python
@router.post("/invoices")
def create_invoice(payload: InvoiceCreate, db: Session = Depends(get_db)):
    total = 0

    for item in payload.items:
        total += item.quantity * item.unit_price

    invoice = Invoice(...)
    db.add(invoice)
    db.commit()

    send_email(...)
    return invoice
```

That becomes untestable and hard to maintain.

Better:

```python
@router.post("/invoices")
def create_invoice(payload: InvoiceCreate, db: Session = Depends(get_db)):
    return InvoiceService(db).create_invoice(payload)
```

---

# Practical naming conventions

Use singular for model files:

```text
models/user.py
models/invoice.py
models/payment.py
```

Use plural for routes/resources:

```text
routes/users.py
routes/invoices.py
routes/payments.py
```

Use explicit service names:

```text
user_service.py
invoice_service.py
payment_service.py
```

Use explicit schema names:

```text
UserCreate
UserRead
UserUpdate
InvoiceCreate
InvoiceRead
InvoiceUpdate
```

Use repository names:

```text
UserRepository
InvoiceRepository
PaymentRepository
```

Avoid vague names:

```text
manager.py
handler.py
helper.py
processor.py
common.py
misc.py
```

Unless the domain makes the meaning obvious.

---

# Recommended production stack

For a serious FastAPI backend, I would typically use:

```text
FastAPI
Pydantic v2
SQLAlchemy 2.x
Alembic
PostgreSQL
pytest
httpx
ruff
mypy or pyright
pre-commit
Docker
docker-compose
structlog or standard logging
```

Optional:

```text
Celery / Dramatiq / RQ for jobs
Redis for caching/jobs
Sentry for error tracking
Prometheus/OpenTelemetry for observability
Stripe/PayPal SDKs behind integration wrappers
```

---

Below is a clean developer-facing route map for the API.

```text
Base URL: /api/v1
```

# Auth

| Method | URL              | Intent                                             |
| ------ | ---------------- | -------------------------------------------------- |
| `POST` | `/auth/register` | Create a new user account                          |
| `POST` | `/auth/login`    | Authenticate user and return access/refresh tokens |
| `POST` | `/auth/refresh`  | Refresh an expired access token                    |
| `POST` | `/auth/logout`   | Invalidate the current session or refresh token    |
| `GET`  | `/auth/me`       | Return the currently authenticated user            |

# Users

| Method   | URL                  | Intent                                        |
| -------- | -------------------- | --------------------------------------------- |
| `GET`    | `/users/me`          | Get the current user profile                  |
| `PATCH`  | `/users/me`          | Update the current user profile               |
| `PATCH`  | `/users/me/password` | Change the current user’s password            |
| `DELETE` | `/users/me`          | Deactivate or delete the current user account |

# Invoices

| Method   | URL                               | Intent                                            |
| -------- | --------------------------------- | ------------------------------------------------- |
| `POST`   | `/invoices`                       | Create a new invoice                              |
| `GET`    | `/invoices`                       | List invoices for the authenticated user          |
| `GET`    | `/invoices/{invoice_id}`          | Get a single invoice by ID                        |
| `PATCH`  | `/invoices/{invoice_id}`          | Update a draft invoice                            |
| `DELETE` | `/invoices/{invoice_id}`          | Delete or archive a draft invoice                 |
| `POST`   | `/invoices/{invoice_id}/finalize` | Finalize an invoice so it can no longer be edited |
| `POST`   | `/invoices/{invoice_id}/send`     | Send an invoice to the client by email            |
| `POST`   | `/invoices/{invoice_id}/void`     | Void an invoice                                   |
| `GET`    | `/invoices/{invoice_id}/pdf`      | Retrieve or download the generated invoice PDF    |
| `POST`   | `/invoices/{invoice_id}/pdf`      | Generate or regenerate the invoice PDF            |

# Payments

| Method | URL                             | Intent                                   |
| ------ | ------------------------------- | ---------------------------------------- |
| `POST` | `/payments/checkout-session`    | Create a hosted payment checkout session |
| `GET`  | `/payments`                     | List payments for the authenticated user |
| `GET`  | `/payments/{payment_id}`        | Get a single payment record              |
| `POST` | `/payments/manual`              | Record an offline/manual payment         |
| `POST` | `/payments/{payment_id}/refund` | Issue a refund for a payment             |
| `POST` | `/payments/webhooks/stripe`     | Receive Stripe webhook events            |

# Health

| Method | URL             | Intent                                                           |
| ------ | --------------- | ---------------------------------------------------------------- |
| `GET`  | `/health`       | Basic service health check                                       |
| `GET`  | `/health/ready` | Readiness check for database, storage, and external dependencies |

# Full Route List

```text
POST   /api/v1/auth/register
POST   /api/v1/auth/login
POST   /api/v1/auth/refresh
POST   /api/v1/auth/logout
GET    /api/v1/auth/me

GET    /api/v1/users/me
PATCH  /api/v1/users/me
PATCH  /api/v1/users/me/password
DELETE /api/v1/users/me

POST   /api/v1/invoices
GET    /api/v1/invoices
GET    /api/v1/invoices/{invoice_id}
PATCH  /api/v1/invoices/{invoice_id}
DELETE /api/v1/invoices/{invoice_id}
POST   /api/v1/invoices/{invoice_id}/finalize
POST   /api/v1/invoices/{invoice_id}/send
POST   /api/v1/invoices/{invoice_id}/void
GET    /api/v1/invoices/{invoice_id}/pdf
POST   /api/v1/invoices/{invoice_id}/pdf

POST   /api/v1/payments/checkout-session
GET    /api/v1/payments
GET    /api/v1/payments/{payment_id}
POST   /api/v1/payments/manual
POST   /api/v1/payments/{payment_id}/refund
POST   /api/v1/payments/webhooks/stripe

GET    /api/v1/health
GET    /api/v1/health/ready
```

---

# Rule of thumb

When deciding where something belongs, ask:

## Is it HTTP-specific?

Put it in `routes/` or `api/`.

Examples:

```text
status codes
Depends()
APIRouter
response_model
query params
path params
headers
cookies
```

## Is it business logic?

Put it in `services/`.

Examples:

```text
create invoice
authenticate user
calculate total
apply discount
approve request
generate receipt
```

## Is it database access?

Put it in `repositories/`.

Examples:

```text
get user by email
list invoices by client
save payment
update status
delete record
```

## Is it a database table?

Put it in `models/`.

Examples:

```text
User
Invoice
Payment
LineItem
Session
```

## Is it request/response validation?

Put it in `schemas/`.

Examples:

```text
UserCreate
InvoiceRead
PaymentWebhookPayload
TokenResponse
```

## Is it an external API?

Put it in `integrations/`.

Examples:

```text
Stripe client
PayPal client
SendGrid client
S3 client
OpenAI client
```

## Is it app-wide policy?

Put it in `core/`.

Examples:

```text
settings
security
logging
permissions
exception classes
```

---

The strongest production FastAPI structure is not the one with the most folders. It is the one where each file has a narrow responsibility, dependencies point in one direction, and business logic can be tested without running the web server.

[1]: https://fastapi.tiangolo.com/tutorial/bigger-applications/?utm_source=chatgpt.com "Bigger Applications - Multiple Files"
[2]: https://fastapi.tiangolo.com/tutorial/sql-databases/?utm_source=chatgpt.com "SQL (Relational) Databases"
[3]: https://sqlmodel.tiangolo.com/?utm_source=chatgpt.com "SQLModel"

## Architecture Description

This backend is a **production-oriented FastAPI modular monolith** using **domain-first organization**, **layered architecture**, and **clean-architecture-inspired dependency direction**.

The system is designed as a single deployable service with strong internal module boundaries. Each domain owns its routes, schemas, models, repositories, services, permissions, and tests. This keeps the codebase cohesive without prematurely introducing distributed microservice complexity.

## Core Architectural Model

```text
Transport Layer
    ↓
Application / Service Layer
    ↓
Persistence + Integration Layer
    ↓
Database / External Infrastructure
```

The primary dependency flow is:

```text
routes → services → repositories → models/db
```

Supporting dependencies:

```text
services → integrations
routes → schemas
repositories → models
```

Invalid dependencies:

```text
models → routes
repositories → routes
services → routes
integrations → routes
```

## Design Principles

Routes handle **transport concerns**.

Services handle **business workflows**.

Repositories handle **persistence access**.

Models represent **database state**.

Schemas define **API contracts**.

Integrations wrap **external providers**.

Core modules define **cross-cutting concerns** such as configuration, security, logging, exceptions, middleware, and permissions.


## Domain Module Pattern

Each domain module follows a consistent vertical slice:

```text
modules/{domain}/
├── routes.py
├── schemas.py
├── models.py
├── repository.py
├── service.py
├── permissions.py
└── tests/
```

This structure supports **bounded context ownership**, **local reasoning**, and **feature-level maintainability**.

## Layer Responsibilities

### Routes

Routes are thin HTTP adapters.

They define:

```text
method
URL
request schema
response schema
status code
dependencies
auth requirements
```

Routes should not contain business logic, SQL queries, provider SDK calls, or transaction orchestration.

### Services

Services implement application use cases.

They enforce:

```text
business rules
permission checks
workflow orchestration
transaction boundaries
domain invariants
integration coordination
```

Services are the primary location for domain behavior.

### Repositories

Repositories isolate database access.

They provide:

```text
queries
persistence operations
filtering
pagination
lookup methods
data access boundaries
```

Repositories should not contain business policy or HTTP-specific behavior.

### Models

Models define relational database state.

They represent:

```text
tables
columns
indexes
constraints
relationships
timestamps
```

Models are not API schemas.

### Schemas

Schemas define request and response contracts.

They provide:

```text
input validation
output filtering
OpenAPI documentation
serialization boundaries
```

Schemas prevent internal fields from leaking to clients.

### Integrations

Integrations wrap external systems.

Examples:

```text
payment provider
email provider
object storage
AI provider
third-party APIs
```

Services depend on integration clients, not raw external SDKs.

## Runtime Architecture

The recommended runtime topology is:

```text
Client
  ↓
Reverse Proxy / TLS Termination
  ↓
FastAPI API Container
  ↓
PostgreSQL
Redis
Worker Container
Object Storage
External Providers
```

Core runtime components:

```text
FastAPI API service
PostgreSQL database
Redis for ephemeral infrastructure
background worker
reverse proxy
object storage
external integrations
```

## Redis Usage

Redis should be introduced for explicit infrastructure concerns:

```text
rate limiting
background job broker
cache
session/token denylist
idempotency keys
WebSocket pub/sub
distributed coordination
```

Redis should not be treated as the primary system of record.

## Background Work

Slow or retryable workflows should be moved out of the request path.

Examples:

```text
PDF generation
email sending
payment reconciliation
webhook processing
report exports
AI/agent tasks
```

The API should enqueue work and return quickly. Workers should handle retries, idempotency, and failure recovery.

## Realtime Design

Use WebSockets for bidirectional realtime workflows.

Use HTTP streaming or Server-Sent Events for one-way streams.

WebSocket concerns:

```text
authentication
authorization
connection lifecycle
disconnect handling
message schemas
rate limits
multi-instance pub/sub
```

Single-instance WebSockets can use an in-memory connection manager. Multi-instance WebSockets require shared pub/sub, commonly Redis.

## Data Design

The database should preserve domain correctness through:

```text
referential integrity
unique constraints
transaction boundaries
status transitions
auditability
idempotency
monetary precision
append-only records where appropriate
```

For payment and invoice systems, prefer immutable or append-only records for financial events.

Use migrations for every schema change.

## Security Model

Security is handled through layered controls:

```text
environment-based secrets
password hashing
JWT expiration
refresh-token strategy
strict CORS
HTTPS
rate limiting
authorization checks
webhook signature verification
least-privilege database access
audit logs
output filtering
no secrets in logs
```

Security-sensitive workflows require authentication, authorization, auditability, idempotency, and explicit error behavior.

## Observability

Production services should expose:

```text
structured logs
request IDs
health checks
readiness checks
error tracking
metrics
tracing
audit events
```

Observability should answer:

```text
what happened
where it happened
who triggered it
how long it took
why it failed
```

## Deployment Strategy

Start with a simple production topology:

```text
Docker Compose
FastAPI container
PostgreSQL container or managed database
Redis container or managed Redis
worker container
reverse proxy
```

Use Kubernetes only when orchestration requirements justify it:

```text
multi-service scheduling
horizontal scaling
self-healing
rolling deployments
service discovery
multi-node operation
platform standardization
```

Do not introduce Kubernetes before the system has clear operational need.

## Delivery Pipeline

The CI/CD pipeline should enforce:

```text
lint
format check
type check
unit tests
integration tests
migration validation
container build
security scan
image push
deployment
smoke test
rollback path
```

Deployment should be environment-driven and reproducible.

## Environment Strategy

Define separate environments:

```text
local
test
staging
production
```

Each environment should specify:

```text
database
redis
secrets
CORS origins
debug mode
logging level
external providers
migration behavior
deployment command
```

Configuration must come from environment variables or secret management, not hardcoded values.

## Production Readiness Criteria

A backend is production-ready when it has:

```text
thin routes
service-layer business logic
repository persistence boundaries
separate schemas and models
centralized exceptions
async-safe I/O
migrations
tests
structured logging
health/readiness checks
secure configuration
rate limiting
background workers
deployment automation
backup and recovery strategy
observability
```

## System Design Summary

This system is a **modular monolith** designed for operational simplicity, strong internal boundaries, and future scalability.

It avoids premature microservices while preserving clean domain separation. It supports async HTTP APIs, realtime streaming, background jobs, secure integrations, reliable persistence, and production deployment through containerized infrastructure.

The next design phase should define:

```text
runtime topology
deployment pipeline
environment strategy
data ownership
failure modes
security controls
observability model
backup and recovery plan
```