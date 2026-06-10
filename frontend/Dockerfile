# ── TradingAgents Frontend — Multi-stage Production Dockerfile ───────────────
#
# Stage 1 (build): node:20-alpine installs deps and runs `npm run build`.
#   VITE_API_BASE is injected as a build-arg so the compiled JS bundle uses a
#   relative path (/api/v1) instead of an absolute URL.  This means the same
#   image works regardless of the server's domain name.
#
# Stage 2 (runtime): nginx:alpine serves the static dist/ directory and proxies
#   /api/v1/* requests to the backend container.  No Node.js in the final image.

# ── Stage 1: Build ────────────────────────────────────────────────────────────
FROM node:20-alpine AS build

WORKDIR /app

# Copy dependency manifests first to exploit Docker layer caching:
# node_modules is rebuilt only when package.json / package-lock.json change.
COPY package.json package-lock.json* ./

RUN npm ci --prefer-offline

# Inject the API base URL at build time.
# Default is a relative path so Nginx can proxy without CORS.
# Override at build time: docker build --build-arg VITE_API_BASE=https://api.example.com/api/v1
ARG VITE_API_BASE=/api/v1
ENV VITE_API_BASE=$VITE_API_BASE

# Copy source and build
COPY . .
RUN npm run build

# ── Stage 2: Runtime (Nginx) ──────────────────────────────────────────────────
FROM nginx:alpine AS runtime

# Remove the default nginx config
RUN rm /etc/nginx/conf.d/default.conf

# Copy our custom config (handles SPA routing + API proxy)
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy compiled assets from the build stage
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
