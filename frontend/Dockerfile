# 前端 Dockerfile（Nuxt  SSL）
FROM node:24-slim AS builder
WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install --no-audit --no-fund

COPY . .
ENV NUXT_PUBLIC_API_BASE=http://localhost:8000
RUN npm run build

# 运行阶段
FROM node:24-slim AS runner
WORKDIR /app
COPY --from=builder /app/.output ./.output
COPY --from=builder /app/package.json ./

ENV NODE_ENV=production
ENV NUXT_PUBLIC_API_BASE=http://localhost:8000

EXPOSE 3000
CMD ["node", ".output/server/index.mjs"]
