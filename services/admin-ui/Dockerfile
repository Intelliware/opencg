FROM node:22-alpine AS build
WORKDIR /app
RUN corepack enable
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY tsconfig.base.json ./
COPY packages/shared ./packages/shared
COPY services/admin-ui ./services/admin-ui
# --frozen-lockfile only: a stale lockfile must fail the build, not silently
# re-resolve.
RUN pnpm install --filter @opencg/admin-ui... --frozen-lockfile
RUN pnpm --filter @opencg/shared build
RUN pnpm --filter @opencg/admin-ui build

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production \
    # Next standalone binds to $HOSTNAME; Docker sets it to the container id,
    # which would make the in-container healthcheck unreachable on loopback.
    HOSTNAME=0.0.0.0 \
    PORT=3000
COPY --from=build --chown=node:node /app/services/admin-ui/.next/standalone /app/
COPY --from=build --chown=node:node /app/services/admin-ui/.next/static /app/services/admin-ui/.next/static
COPY --from=build --chown=node:node /app/services/admin-ui/public /app/services/admin-ui/public
USER node
EXPOSE 3000
HEALTHCHECK --interval=10s --timeout=5s --retries=6 \
  CMD wget -qO- http://127.0.0.1:3000/api/healthz >/dev/null || exit 1
CMD ["node", "services/admin-ui/server.js"]
