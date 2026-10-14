FROM ghcr.io/maxexcloo/gatus-tailscale@sha256:85e1643a045376bb20b9bd9abfa6b7f5be62ba7681e27882b190e8ac9357dba4
WORKDIR /app
COPY app/ ./
COPY --chmod=755 start.sh start.sh
ENTRYPOINT ["/app/start.sh"]
