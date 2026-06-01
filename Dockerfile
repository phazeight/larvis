FROM python:3.12-slim
WORKDIR /app
RUN pip install uv
COPY pyproject.toml .
RUN uv sync --no-dev
COPY larvis/ larvis/
EXPOSE 8765
CMD ["uv", "run", "python", "-m", "larvis"]
