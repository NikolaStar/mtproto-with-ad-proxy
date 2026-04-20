FROM python:3.12-slim

RUN pip install --no-cache-dir mtprotoproxy

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

WORKDIR /config
VOLUME ["/config"]
EXPOSE 443

ENTRYPOINT ["/entrypoint.sh"]
