FROM nginx:alpine

RUN mkdir -p /etc/nginx/certs && chmod 700 /etc/nginx/certs

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
