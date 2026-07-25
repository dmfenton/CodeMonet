# Stage 1: Build
FROM node:24.18.0-alpine@sha256:a0b9bf06e4e6193cf7a0f58816cc935ff8c2a908f81e6f1a95432d679c54fbfd AS builder

WORKDIR /app

# Copy workspace config
COPY package.json package-lock.json ./
COPY shared/package.json ./shared/
COPY web/package.json ./web/

# Install dependencies
RUN npm ci --workspace @code-monet/web --workspace @code-monet/shared \
    --include-workspace-root=true

# Copy source code
COPY shared/ ./shared/
COPY web/ ./web/

# Build shared library first
RUN npm run build -w shared

# Build web (client + server bundles)
ARG VERSION=dev
ENV VERSION=${VERSION}
RUN npm run build -w web

# Stage 2: Production
FROM node:24.18.0-alpine@sha256:a0b9bf06e4e6193cf7a0f58816cc935ff8c2a908f81e6f1a95432d679c54fbfd

WORKDIR /app

# Copy package files for production deps only
COPY package.json package-lock.json ./
COPY shared/package.json ./shared/
COPY web/package.json ./web/

# Install only the server workspaces' production dependencies. Excluding the
# React Native app keeps mobile packages and their install scripts out of SSR.
RUN npm ci --omit=dev \
        --workspace @code-monet/web --workspace @code-monet/shared \
        --include-workspace-root=false \
    && npm cache clean --force \
    && rm -rf /usr/local/lib/node_modules/npm /usr/local/bin/npm /usr/local/bin/npx

# Copy built artifacts from builder
COPY --from=builder /app/shared/dist ./shared/dist
COPY --from=builder /app/web/dist ./web/dist

# Copy the erasable-syntax TypeScript server for Node's native type stripping.
COPY web/server.ts ./web/

# Set ownership and switch to the non-root user provided by the Node image.
RUN chown -R node:node /app
USER node

# Set production environment
ENV NODE_ENV=production
ENV PORT=3000

# Expose SSR server port
EXPOSE 3000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD node -e "fetch('http://localhost:3000/health').then(r => r.ok ? process.exit(0) : process.exit(1)).catch(() => process.exit(1))"

# Node 24 strips erasable TypeScript syntax natively, avoiding a global
# unpinned runtime dependency on tsx.
CMD ["node", "web/server.ts"]
