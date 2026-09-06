# Frontend image: Next.js standalone output.
# NEXT_PUBLIC_* vars are baked at BUILD time — set them as build args /
# Railway build-time variables, not only runtime env.
FROM node:22-alpine AS build
RUN corepack enable
WORKDIR /app
COPY package.json pnpm-lock.yaml* ./
RUN pnpm install --frozen-lockfile || pnpm install
COPY . .
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN pnpm build

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production
# Standalone output: server.js + minimal node_modules; static + public
# must be copied alongside or pages ship unstyled.
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public
CMD ["sh", "-c", "PORT=${PORT:-3000} node server.js"]
