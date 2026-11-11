FROM nginx:1.27-alpine

RUN apk add --no-cache openssl

COPY docker/nginx/nginx.conf /etc/nginx/conf.d/default.conf
COPY docker/nginx/entrypoint.sh /docker-entrypoint.d/99-generate-certs.sh
RUN chmod +x /docker-entrypoint.d/99-generate-certs.sh
