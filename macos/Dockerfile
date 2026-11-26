ARG NODE_BASE=node:24-bookworm-slim
ARG PYTHON_BASE=python:3.12-slim-bookworm
FROM ${NODE_BASE} AS node-app
WORKDIR /app
COPY simulator/package.json simulator/package-lock.json ./simulator/
RUN npm --prefix simulator ci --no-audit --no-fund
COPY simulator ./simulator
COPY dashboard ./dashboard
COPY shared ./shared
COPY simulation ./simulation
COPY mqtt ./mqtt
COPY macos ./macos
COPY package.json ./
ENV SMARTBIN_BIND_HOST=0.0.0.0
CMD ["node", "dashboard/server.mjs"]

FROM ${PYTHON_BASE} AS python-app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app/history
COPY history ./
COPY ontology /app/ontology
CMD ["python", "-m", "twin_history", "serve", "--host", "0.0.0.0"]
