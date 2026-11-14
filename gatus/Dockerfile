# syntax=docker/dockerfile:1
FROM docker.io/twinproduction/gatus:v5.38.0 AS gatus
FROM docker.io/tailscale/tailscale:v1.104.7 AS tailscale

FROM alpine:3.24
RUN apk add --no-cache ca-certificates iptables ip6tables \
    && mkdir -p /var/cache/tailscale /var/lib/tailscale /var/run/tailscale
WORKDIR /app
COPY --from=gatus /gatus gatus
COPY --from=tailscale /usr/local/bin/tailscaled tailscaled
COPY --from=tailscale /usr/local/bin/tailscale tailscale
COPY app/ ./
COPY --chmod=755 start.sh start.sh
ENV GATUS_CONFIG_PATH=/app/config
ENTRYPOINT ["/app/start.sh"]
