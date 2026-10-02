# Builds the React app, then serves it with nginx (non-root) in front of the API.
# Build context is the repo root:  docker build -f deploy/nginx/Dockerfile .
FROM node:22-alpine AS build
WORKDIR /src
COPY Frontend/package.json Frontend/package-lock.json ./
RUN npm ci
COPY Frontend/ ./
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY deploy/nginx/nginx.conf /etc/nginx/nginx.conf
COPY deploy/nginx/snippets/ /etc/nginx/snippets/
COPY --from=build /src/dist /usr/share/nginx/html
EXPOSE 8080 8443
