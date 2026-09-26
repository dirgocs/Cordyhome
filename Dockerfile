# ---- Interface (SvelteKit → arquivos estáticos) ----
FROM node:22-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# ---- Hub (Python) ----
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    CORDYHOME_DATA=/data \
    CORDYHOME_WEB=/app/web \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /bin/uv
WORKDIR /app/hub
COPY hub/pyproject.toml hub/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY hub/ ./
RUN uv sync --frozen --no-dev
COPY --from=web /web/build /app/web

VOLUME /data
EXPOSE 8420
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8420/api/health')"
CMD ["/app/hub/.venv/bin/cordyhome"]
