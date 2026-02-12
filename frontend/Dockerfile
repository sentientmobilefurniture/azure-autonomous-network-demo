# ============================================================================
# Frontend — React + Vite build → nginx static server with API reverse proxy
# ============================================================================

# Stage 1: Build the React application
FROM node:20-alpine AS build

WORKDIR /app

# Layer 1: Install dependencies (cached unless package.json changes)
COPY package.json package-lock.json* ./
RUN npm ci --silent

# Layer 2: Copy source and build
COPY . .
RUN npm run build

# Stage 2: Serve with nginx
FROM nginx:alpine

# Remove default nginx config
RUN rm /etc/nginx/conf.d/default.conf

# Copy our template (envsubst will resolve API_BACKEND_URL at runtime)
COPY nginx.conf.template /etc/nginx/templates/default.conf.template

# Copy built React app
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

# nginx:alpine's default entrypoint runs envsubst on /etc/nginx/templates/*.template
# and writes results to /etc/nginx/conf.d/, then starts nginx.
# We just need to make sure API_BACKEND_URL is set as an env var.
CMD ["nginx", "-g", "daemon off;"]
