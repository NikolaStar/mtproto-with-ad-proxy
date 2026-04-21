FROM python:3.9-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://raw.githubusercontent.com/alexbers/mtprotoproxy/master/mtprotoproxy.py \
    -o /usr/local/bin/mtprotoproxy && chmod +x /usr/local/bin/mtprotoproxy

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

WORKDIR /config
VOLUME ["/config"]
EXPOSE 443

ENTRYPOINT ["/entrypoint.sh"]
