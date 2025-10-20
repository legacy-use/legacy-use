FROM node:20-alpine

ENV DEBIAN_FRONTEND=noninteractive

ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"
RUN corepack enable

WORKDIR /web

COPY package.json pnpm-lock.yaml /web/
RUN pnpm install --frozen-lockfile

COPY ./app /web/app
COPY ./public /web/public
COPY ./tsconfig.json /web/tsconfig.json
COPY ./vite.config.js /web/vite.config.js
COPY ./orval.config.ts /web/orval.config.ts
COPY ./index.html /web/index.html

EXPOSE 5173

CMD [ "pnpm", "start" ]
