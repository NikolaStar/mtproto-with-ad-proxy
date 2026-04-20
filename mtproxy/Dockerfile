FROM python:3.9-slim

RUN pip install --no-cache-dir mtprotoproxy && \
    python3 -c "\
import pathlib; \
f = pathlib.Path('/usr/local/bin/mtprotoproxy'); \
f.write_text(f.read_text().replace('asyncio.streams.IncompleteReadError', 'asyncio.IncompleteReadError')) \
"

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

WORKDIR /config
VOLUME ["/config"]
EXPOSE 443

ENTRYPOINT ["/entrypoint.sh"]
