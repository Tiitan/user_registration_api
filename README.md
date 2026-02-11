# user_registration_api

Dailymotion user registration test project.

## Run with Docker Compose

```bash
docker compose up --build
```

API URL: `http://localhost:8000`

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- Heartbeat: `http://localhost:8000/heartbeat`

The API connects to MySQL on startup through FastAPI lifespan.

## Database initialization

MySQL automatically runs SQL files from `/docker-entrypoint-initdb.d` only when initializing
a new data directory. This project mounts `db/init/001_init_schema.sql` there to create the
tables from `docs/architecture.md`:

- `users`
- `activation_codes`
- `outbox_events`

Schema initialization is one-time for a given MySQL volume. If you change schema later,
this setup does not provide migrations.

To force re-initialization locally:

```bash
docker compose down -v
docker compose up --build
```

## Run tests

```bash
docker compose run --rm test
```

Or with profiles:

```bash
docker compose --profile test up --build test
```
