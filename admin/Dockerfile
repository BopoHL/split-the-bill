# The panel is a static SPA. This image exists only to produce the files and
# drop them into a volume that nginx serves — no Node process runs in prod,
# which matters on a 2 GB VPS.
FROM node:20-slim AS builder
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
ARG NEXT_PUBLIC_ADMIN_API_URL=/api/admin
ENV NEXT_PUBLIC_ADMIN_API_URL=$NEXT_PUBLIC_ADMIN_API_URL
RUN npm run build

FROM alpine:3.20
WORKDIR /dist
COPY --from=builder /app/out ./out
# Publish into the shared volume and exit; nginx mounts the same volume.
CMD ["sh", "-c", "rm -rf /var/www/admin/* && cp -r /dist/out/. /var/www/admin/"]
