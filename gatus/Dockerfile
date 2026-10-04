FROM ghcr.io/twin/gatus:v5.37.0 AS gatus
FROM docker.io/tailscale/tailscale:v1.102.5 AS tailscale
FROM alpine:3.24.2
RUN apk add --no-cache ca-certificates iptables ip6tables \
    && mkdir -p /var/cache/tailscale /var/lib/tailscale /var/run/tailscale
WORKDIR /app
COPY --from=gatus /gatus gatus
COPY --from=tailscale /usr/local/bin/tailscaled tailscaled
COPY --from=tailscale /usr/local/bin/tailscale tailscale
COPY app/ ./
COPY --chmod=755 start.sh start.sh
ENTRYPOINT ["/app/start.sh"]
