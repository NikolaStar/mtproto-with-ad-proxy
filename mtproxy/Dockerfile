FROM python:3.9-slim

RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir git+https://github.com/alexbers/mtprotoproxy.git@master

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

WORKDIR /config
VOLUME ["/config"]
EXPOSE 443

ENTRYPOINT ["/entrypoint.sh"]
