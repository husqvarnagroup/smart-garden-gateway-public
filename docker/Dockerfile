FROM debian:trixie

RUN apt-get update && apt-get -qy --no-install-recommends install \
    build-essential \
    chrpath \
    cpio \
    debianutils \
    diffstat \
    file \
    gawk \
    gcc \
    git \
    iputils-ping \
    libacl1 \
    locales \
    lz4 \
    python3 \
    python3-git \
    python3-jinja2 \
    python3-pexpect \
    python3-pip \
    python3-subunit \
    socat \
    sudo \
    texinfo \
    tig \
    unzip \
    vim \
    wget \
    xz-utils \
    zstd \
    && rm -rf /var/lib/apt/lists/*

RUN sed -i '/^# en_US.UTF-8 UTF-8/s/^# //' /etc/locale.gen && locale-gen
ENV LANG=en_US.UTF-8

RUN useradd --create-home --shell /bin/bash user \
    && echo 'user ALL=(ALL) NOPASSWD:ALL' >/etc/sudoers.d/user

USER user

COPY --chown=user:user sstate-cache /home/user/.cache/yocto/sstate-cache
