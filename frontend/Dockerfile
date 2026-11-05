FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install

FROM node:22-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# Inlined sa client bundle sa build time (kailangan sa production Docker)
ARG NEXT_PUBLIC_API_URL
ARG BACKEND_ORIGIN
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
ENV BACKEND_ORIGIN=${BACKEND_ORIGIN}
RUN test -n "$NEXT_PUBLIC_API_URL" || (echo "NEXT_PUBLIC_API_URL is required for production build." && exit 1)
RUN test -n "$BACKEND_ORIGIN" || (echo "BACKEND_ORIGIN is required for production build." && exit 1)
RUN node -e "const u=process.env.NEXT_PUBLIC_API_URL||''; if(!(u.startsWith('https://')||u.startsWith('/api-proxy'))){throw new Error('NEXT_PUBLIC_API_URL must be HTTPS or /api-proxy');}"
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ARG BACKEND_ORIGIN
ENV NODE_ENV=production
ENV PORT=8080
ENV BACKEND_ORIGIN=${BACKEND_ORIGIN}
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/node_modules ./node_modules
EXPOSE 8080
CMD ["npm", "run", "start", "--", "-p", "8080"]
