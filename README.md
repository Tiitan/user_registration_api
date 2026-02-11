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

## Run tests

```bash
docker compose run --rm test
```

Or with profiles:

```bash
docker compose --profile test up --build test
```
