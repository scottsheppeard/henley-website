# thehenley.com.au — build the static site, then serve it.
#
# The runtime stage has no Node, no build tools and no source: just nginx and a
# directory of files. Nothing in the shipped image can execute.

# ── Build ───────────────────────────────────────────────────────────────────
FROM node:22-bookworm-slim AS build

WORKDIR /app

# npm ci, not npm install: it installs exactly the lockfile and fails if
# package.json and the lockfile disagree, which is the whole point of having one.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# The token generator normally reads the brand kit at
# /mnt/persistent/git/branding/henley, which is not mounted here — and should
# not be, because a container that needs the brand repo to build is a container
# nobody else can build. tokens.css is generated into the build context by the
# deploy script (npm run tokens) before docker build runs.
RUN test -f src/styles/tokens.css \
 || (echo "src/styles/tokens.css is missing: run 'npm run tokens' before building" >&2; exit 1)
RUN npx astro build

# ── Runtime ─────────────────────────────────────────────────────────────────
FROM nginx:alpine

# Runs unprivileged. nginx:alpine ships an `nginx` user; the config listens on
# 8080 rather than 80 so no capability is needed to bind it.
RUN rm -f /etc/nginx/conf.d/default.conf \
 && mkdir -p /var/cache/nginx/client_body /var/cache/nginx/proxy \
             /var/cache/nginx/fastcgi /var/cache/nginx/uwsgi /var/cache/nginx/scgi \
 && chown -R nginx:nginx /var/cache/nginx

COPY deploy/nginx.conf /etc/nginx/nginx.conf
COPY deploy/redirects.conf deploy/redirects-map.conf deploy/security-headers.conf /etc/nginx/conf.d/
COPY --from=build /app/dist /usr/share/nginx/html

# Fail the build rather than the deploy if the config is malformed.
#
# `nginx -t` loads the config, which creates the pid file — as root, because
# this layer is root. Left behind, it is a root-owned file the runtime nginx
# user cannot open, and the container exits on start with a permission error
# that says nothing about where it came from.
RUN nginx -t -c /etc/nginx/nginx.conf \
 && rm -f /var/cache/nginx/nginx.pid

USER nginx
EXPOSE 8080

HEALTHCHECK --interval=60s --timeout=5s --start-period=5s --retries=3 \
  CMD wget -q -O /dev/null http://127.0.0.1:8080/nginx-health || exit 1

CMD ["nginx", "-g", "daemon off;"]
