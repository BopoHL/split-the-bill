FROM node:20-slim AS base
WORKDIR /app

FROM base AS deps
COPY package.json package-lock.json ./
RUN npm ci

FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_TELEGRAM_BOT_USERNAME
ARG NEXT_PUBLIC_POSTHOG_KEY
ARG NEXT_PUBLIC_POSTHOG_HOST
ARG NEXT_PUBLIC_POSTHOG_DISABLE_REPLAY
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_TELEGRAM_BOT_USERNAME=$NEXT_PUBLIC_TELEGRAM_BOT_USERNAME \
    NEXT_PUBLIC_POSTHOG_KEY=$NEXT_PUBLIC_POSTHOG_KEY \
    NEXT_PUBLIC_POSTHOG_HOST=$NEXT_PUBLIC_POSTHOG_HOST \
    NEXT_PUBLIC_POSTHOG_DISABLE_REPLAY=$NEXT_PUBLIC_POSTHOG_DISABLE_REPLAY

RUN npm run build

FROM base AS runner
WORKDIR /app

ARG ENV=production
ENV ENV=$ENV \
    NODE_ENV=$ENV \
    PORT=3000

RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

RUN mkdir -p .next && chown nextjs:nodejs .next

# `output: standalone` traces the modules the server actually reaches and ships
# them inside .next/standalone — 72 MB against 772 MB for the full tree. The
# whole node_modules used to be copied on top of that, so every deploy pulled
# three quarters of a gigabyte of build-time dependencies that nothing ran.
COPY --from=builder --chown=nextjs:nodejs /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/package.json ./package.json
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

# Only the built server. `npm run dev` was reachable here in theory but never in
# practice: this stage has no sources for Next to compile. Local development
# runs against the `deps` stage with the working copy mounted.
CMD ["node", "server.js"]