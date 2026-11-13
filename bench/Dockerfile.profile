# Profiling image: the gateway image plus py-spy. Not used by the production Dockerfile.
ARG BASE_IMAGE=shieldwall-gateway:bench
FROM ${BASE_IMAGE}
USER root
RUN pip install --no-cache-dir py-spy==0.4.1
USER shieldwall
