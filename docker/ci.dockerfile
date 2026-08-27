ARG BASE_IMAGE=ghcr.io/husqvarnagroup/smart-garden-gateway-public/dev:latest
FROM ${BASE_IMAGE}

# UID/GID of the "runner" user on GitHub-hosted ubuntu-24.04 images
ARG CI_UID=1001
ARG CI_GID=1001

USER root

RUN groupmod -g ${CI_GID} user \
    && usermod -u ${CI_UID} -g ${CI_GID} user \
    && chown -R user:user /home/user

USER user
