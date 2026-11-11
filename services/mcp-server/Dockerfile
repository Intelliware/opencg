FROM node:22-alpine AS build
WORKDIR /app
RUN corepack enable
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY tsconfig.base.json ./
COPY packages/shared ./packages/shared
COPY services/mcp-server ./services/mcp-server
# --frozen-lockfile only: a stale lockfile must fail the build, not silently
# re-resolve.
RUN pnpm install --filter @opencg/mcp-server... --frozen-lockfile
RUN pnpm --filter @opencg/shared build && pnpm --filter @opencg/mcp-server build

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build --chown=node:node /app /app
USER node
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=5s --retries=6 \
  CMD wget -qO- http://127.0.0.1:8080/healthz >/dev/null || exit 1
CMD ["node", "services/mcp-server/dist/index.js"]
