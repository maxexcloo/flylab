# syntax=docker/dockerfile:1
FROM ghcr.io/maxexcloo/gatus-tailscale:v5.38.0
COPY app/ ./
COPY --chmod=755 start.sh start.sh
ENTRYPOINT ["/app/start.sh"]
