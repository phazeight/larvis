FROM python:3.12-slim
WORKDIR /app
RUN pip install uv
# Install bun + lb
RUN apt-get update && apt-get install -y curl unzip && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL https://bun.sh/install | bash
ENV PATH="/root/.bun/bin:$PATH"
RUN bun install -g github:nikvdp/linear-beads
COPY pyproject.toml .
RUN uv sync --no-dev --no-install-project
COPY larvis/ larvis/
COPY .lb/ .lb/
RUN uv sync --no-dev
EXPOSE 8765
CMD ["uv", "run", "python", "-m", "larvis"]
