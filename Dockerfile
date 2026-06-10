FROM python:3.10-slim

# Install system dependencies 
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install --no-cache-dir poetry==2.2.1
# Note: --no-cache-dir avoids storing the downloaded wheel/source in pip's cache
# directory. This helps keep the Docker image smaller.

# Set working directory
WORKDIR /app

# Copy only dependency files first
COPY pyproject.toml poetry.lock* README.md /app/

# Install deps (no-root => don't install project itself as a package)
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --without dev --no-root
# Additional notes on above command:
# Line #1: Tell Poetry NOT to create a virtual environment. Inside Docker, you do not want a venv. You want all packages installed directly into the system Python inside the image.
# Line #2:
# --no-interaction: Disable any prompts or questions. (Docker needs to run non-interactively)
# --no-ansi: Remove colorized outuputs for cleaner logs
# --without dev: Install only production dependencies, ignoring [tool.poetry.dev-dependencies].
# --no-root: Do not install the project itself as a package. Only install dependencies. Don’t attempt to install the app package itself yet

# Copy the source code!
COPY src/ /app/src/

# Copy the Streamlit theme config so the deployed UI container loads the dark theme.
# WORKDIR is /app and streamlit runs from there, so it reads /app/.streamlit/config.toml.
COPY .streamlit/ /app/.streamlit/

# Install root package now that code exists
RUN poetry install --only-root --no-interaction --no-ansi

# Expose FastAPI default port and set env vars
ENV API_PORT=8000
EXPOSE 8000

# Start API (use env var for port)
CMD ["sh", "-c", "uvicorn api.api_setup:app --host 0.0.0.0 --port ${API_PORT}"]


# docker build -t refinance_tool .
# docker run --name refinance_api --env-file .env -p 8000:8000 refinance_tool
