# VayuDrishti backend: FastAPI with the three trained models (identification, classification, track forecast).
#
# Two stages. The builder installs the dependencies into a virtual environment, so compilers, pip's cache and
# the build metadata stay in that stage. The runtime image copies only that environment plus the application.
#
# The build context is this directory (backend/); at runtime the app reads nothing outside it.
#
#   docker build -t vayudrishti-backend --build-arg EMERGENT_INDEX_URL=<emergent package index> backend
#
#   docker run --rm -p 8001:8001 \
#     -e MONGODB_URI=mongodb://host.docker.internal:27017 \
#     -e MONGODB_APP_DATABASE=vayudrishti_local \
#     -e MONGODB_CYCLONE_DATABASE=cyclone_database \
#     -e FRONTEND_URL=http://localhost:3001 \
#     vayudrishti-backend
#
# MongoDB runs on the host: Docker Desktop resolves host.docker.internal by itself, while on Linux the run
# needs --add-host=host.docker.internal:host-gateway. backend/.env is deliberately kept out of the image
# (see .dockerignore), so every setting is passed at run time.

ARG PYTHON_VERSION=3.11.9

# ------------------------------------------------------------------ stage 1: build the virtual environment
FROM python:${PYTHON_VERSION}-slim-bookworm AS builder

# routers/analyst.py imports emergentintegrations at startup, and that package is served from Emergent's own
# index rather than PyPI. Pass the index URL at build time; without it pip cannot resolve the package.
ARG EMERGENT_INDEX_URL=""

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

# Compilers for any dependency that ships no wheel for this platform. They stay in this stage.
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt ./

# torch and torchvision come from PyTorch's CPU index. The default wheels carry bundled CUDA libraries and add
# several GB; inference here takes 20-50 ms per image on CPU, so the GPU build would be weight for nothing.
RUN pip install --upgrade pip \
 && pip install torch==2.14.0+cpu torchvision==0.29.0+cpu --index-url https://download.pytorch.org/whl/cpu

# Serving needs neither the test runners nor the linters that requirements.txt also lists.
RUN grep -vEi '^(pytest|pytest-xdist|pytest-asyncio|black|isort|flake8|mypy|torch|torchvision)([=<>!~[:space:]]|$)' \
        requirements.txt > /tmp/runtime-requirements.txt \
 && if [ -n "$EMERGENT_INDEX_URL" ]; then \
        pip install --extra-index-url "$EMERGENT_INDEX_URL" -r /tmp/runtime-requirements.txt; \
    else \
        pip install -r /tmp/runtime-requirements.txt; \
    fi

# ------------------------------------------------------------------ stage 2: runtime image
FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime

# libgomp1: torch's CPU kernels link against OpenMP. No curl is installed, so the health check uses Python.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgomp1 \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 10001 appuser

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ML_DEVICE=cpu \
    ML_MODELS_DIR=/app/models

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=appuser:appuser . /app

USER appuser
EXPOSE 8001


# One worker on purpose: every extra worker loads its own copy of the three models.
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]
