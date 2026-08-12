FROM node:22-alpine AS build
WORKDIR /app
RUN corepack enable
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml* ./
COPY tsconfig.base.json ./
COPY packages/shared ./packages/shared
COPY services/admin-ui ./services/admin-ui
# No `|| pnpm install` fallback: it turned a stale-lockfile failure into a
# silent unfrozen resolve, so the image could install versions nobody pinned.
RUN pnpm install --filter @opencg/admin-ui... --frozen-lockfile
RUN pnpm --filter @opencg/shared build
RUN pnpm --filter @opencg/admin-ui build

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app/services/admin-ui/.next/standalone /app/
COPY --from=build /app/services/admin-ui/.next/static /app/services/admin-ui/.next/static
COPY --from=build /app/services/admin-ui/public /app/services/admin-ui/public
EXPOSE 3000
CMD ["node", "services/admin-ui/server.js"]
