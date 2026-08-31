FROM node:22-alpine AS builder

# Install pnpm
RUN corepack enable && corepack prepare pnpm@latest --activate

WORKDIR /app

COPY package.json pnpm-lock.yaml* ./
RUN pnpm install --frozen-lockfile

COPY . .
RUN pnpm build

# Serve the built bundle with nginx
FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html

# Route all paths to index.html so React Router works
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
