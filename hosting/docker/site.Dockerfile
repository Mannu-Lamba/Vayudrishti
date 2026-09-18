# The website, the model test bench and the metrics dashboard on one port, served by the project's own
# server (tests/model-bench/server.mjs) with nothing in it changed.
#
# Two stages: the first installs the frontend dependencies and builds the website, the second keeps only the
# built files, the few static assets the pages request by path, and the server itself. Neither the frontend
# dependencies (about 500 MB) nor any build tool reaches the final image.
#
# Built from the project root, because the server reads files from several folders:
#   docker build -t vayudrishti-site -f hosting/docker/site.Dockerfile .

# ------------------------------------------------------------------ stage 1: build the website
FROM node:24-bookworm-slim AS web

WORKDIR /build
# Dependencies first, so a change to the source does not reinstall them.
COPY frontend/package.json frontend/yarn.lock ./
# yarn 1, because the project pins dependency versions with yarn's "resolutions".
RUN npx --yes yarn@1.22.22 install --frozen-lockfile

COPY frontend/ ./
RUN npx vite build

# ------------------------------------------------------------------ stage 2: the site container
FROM node:24-alpine AS runtime

WORKDIR /app
ENV NODE_ENV=production \
    PORT=3001 \
    BACKEND_URL=http://backend:8001

# The server and the two pages, exactly as they are in the repository.
COPY tests/model-bench/server.mjs tests/model-bench/index.html tests/model-bench/evaluation.html \
     tests/model-bench/samples.json tests/model-bench/evaluation.json ./tests/model-bench/
COPY hosting/docker/site-server.mjs ./hosting/docker/

# The built website.
COPY --from=web /build/dist ./frontend/dist

# Assets the pages request by path (/fonts/..., /vendor/maplibre/...), taken from the build stage.
COPY --from=web /build/node_modules/@fontsource/ibm-plex-sans/files ./frontend/node_modules/@fontsource/ibm-plex-sans/files
COPY --from=web /build/node_modules/@fontsource/ibm-plex-mono/files ./frontend/node_modules/@fontsource/ibm-plex-mono/files
COPY --from=web /build/node_modules/maplibre-gl/dist ./frontend/node_modules/maplibre-gl/dist

# The three training reports the bench and the dashboard read at /reports/*.json.
COPY identification_model/reports/test_metrics.json ./identification_model/reports/test_metrics.json
COPY identification_model/reports/classification/classification_metrics.json ./identification_model/reports/classification/classification_metrics.json
COPY prediction_model/reports/test_metrics.json ./prediction_model/reports/test_metrics.json

# /img/ (identification_model/data/processed) is mounted at run time; see compose.yaml.

USER node
EXPOSE 3001

CMD ["node", "hosting/docker/site-server.mjs"]
