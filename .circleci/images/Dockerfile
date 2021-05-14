FROM debian:buster

ENV DEBIAN_FRONTEND noninteractive

# Install Yocto dependencies
RUN apt-get -qy update && apt-get -qy dist-upgrade && \
    apt-get -qy --no-install-recommends install \
    build-essential \
    ca-certificates \
    chrpath \
    cpio \
    diffstat \
    file \
    gawk \
    gcc-multilib \
    git-core \
    python-minimal \
    python2.7 \
    python3 \
    socat \
    texinfo \
    unzip \
    wget \
    ;

# Create a non-root user that will perform the actual build
RUN id build 2>/dev/null || useradd --create-home build --shell /bin/bash
RUN apt-get -qy update && apt-get install -y sudo
RUN echo "build ALL=(ALL) NOPASSWD: ALL" | tee -a /etc/sudoers

# Fix error "Please use a locale setting which supports utf-8."
# See https://wiki.yoctoproject.org/wiki/TipsAndTricks/ResolvingLocaleIssues
RUN apt-get install -y locales
RUN sed -i -e 's/# en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen && \
    echo 'LANG="en_US.UTF-8"'>/etc/default/locale && \
    dpkg-reconfigure --frontend=noninteractive locales && \
    update-locale LANG=en_US.UTF-8

ENV LC_ALL en_US.UTF-8
ENV LANG en_US.UTF-8
ENV LANGUAGE en_US.UTF-8

USER build
WORKDIR /home/build
CMD "/bin/bash"
