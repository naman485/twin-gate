FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates curl unzip && rm -rf /var/lib/apt/lists/*

# GBrain (optional at runtime): bun + a linked checkout, so the hosted copy has recall too.
RUN curl -fsSL https://bun.sh/install | bash \
    && git clone --depth 1 https://github.com/garrytan/gbrain.git /opt/gbrain \
    && cd /opt/gbrain && /root/.bun/bin/bun install && /root/.bun/bin/bun link
ENV PATH="/root/.bun/bin:${PATH}" \
    GBRAIN_BIN=/root/.bun/bin/gbrain \
    GBRAIN_HOME=/app/.gbrain

WORKDIR /app
COPY . /app

# The hosted copy runs the rules agent (no Ollama in a 1 GB container) and, when
# CREATEOS_SANDBOX_API_KEY is set in the deployment's env, forks real sandboxes per twin.
ENV PORT=3000 \
    TWIN_AGENT=rules \
    TWIN_BRAIN=/app/brain \
    TWIN_STATE=/app/state \
    PYTHONUNBUFFERED=1

RUN rm -rf /app/brain /app/state && cp -R /app/brain-seed /app/brain && mkdir -p /app/state \
    && git config --global user.name "twin-gate" && git config --global user.email "twin@local" \
    && git config --global init.defaultBranch main

EXPOSE 3000
CMD ["python3", "server.py"]
