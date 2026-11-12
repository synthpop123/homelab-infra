# Upstream's own Dockerfile, built from its tagged source: the published image is amd64-only and
# only tagged latest. server.patch swaps the raw JSON message for format.js and reads the credentials
# from the environment. The version pin is a compose build arg (see compose.yaml).
FROM node:26-alpine

ARG ALERTER_VERSION

RUN addgroup -S app && adduser -S app -G app

WORKDIR /app

ADD https://github.com/SashaBusinaro/komodo-telegram-alerter/archive/refs/tags/${ALERTER_VERSION}.tar.gz /tmp/src.tar.gz
COPY server.patch format.js /tmp/

RUN apk add --no-cache --virtual .patch-deps patch && \
    mkdir /tmp/upstream && \
    tar xzf /tmp/src.tar.gz -C /tmp/upstream --strip-components=1 && \
    cp /tmp/upstream/src/package.json /tmp/upstream/src/package-lock.json /tmp/upstream/src/server.js /tmp/format.js . && \
    patch server.js /tmp/server.patch && \
    apk del .patch-deps && \
    npm ci --omit=dev --ignore-scripts && \
    npm cache clean --force && \
    rm -rf /tmp/upstream /tmp/src.tar.gz /tmp/server.patch /tmp/format.js && \
    chown -R app:app /app

USER app

EXPOSE 3000

CMD ["node", "server.js"]
