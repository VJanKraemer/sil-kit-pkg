FROM debian:sid

RUN apt-get update
RUN apt-get install -y build-essential ninja-build cmake \
        libyaml-cpp-dev libasio-dev libfmt-dev libspdlog-dev \
        devscripts dh-cmake lld dh-make wget

ENV SILKIT_VERSION=4.0.37
ENV SILKIT_SOURCE_URL=
ENV SILKIT_VERSION_POST=-rc2
ENV SILKIT_PACKAGING_REPO=https://github.com/VJanKraemer/sil-kit-pkg.git
ENV USER=packager

ENTRYPOINT ["./.github/actions/build_deb.sh"]
