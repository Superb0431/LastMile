# LastMile

A self-hosted medical follow-up Agent built with FastAPI, Redis Streams, and LiteLLM.

Chat UI is served on port **8000** once the stack is running.

## Pull

```bash
docker pull android0431/lastmile:0.11
```

## Minimal layout

Create an empty folder and add two files:

```text
lastmile/
├── .env
└── docker-compose.yml
```

### 1) `.env`

At least prepare these keys (use your own credentials):

```env
API_KEY=
MAIN_MODEL=
TAVILY_API_KEY=
REDIS_URL=redis://localhost:6379/0
```

Other knobs (timeouts, security filters, worker concurrency, etc.) exist, but defaults are usually fine for a first try.

### 2) `docker-compose.yml`

A typical three-service layout looks like this:

```yaml
services:
  redis:
    image: redis:7-alpine

  api:
    image: android0431/lastmile:0.11
    ports:
      - "8000:8000"
    env_file:
      - .env
    depends_on:
      - redis

  worker:
    image: android0431/lastmile:0.11
    env_file:
      - .env
    depends_on:
      - redis
```

> Tip: API and Worker must share the same Redis. If containers cannot talk to each other, check service discovery / `REDIS_URL`.

### 3) Start

```bash
docker compose up
```

Then open `http://127.0.0.1:8000/`.

## Expected behavior

- UI loads from the API container
- Chat tasks are consumed by the Worker
- Without a valid model key / search key, some tools will fail at runtime

## Notes

- Image tag `0.11` is the current demo build (`linux/amd64`)
- For advanced options, refer to the project configuration defaults inside the image
