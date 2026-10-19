FROM ghcr.io/maxexcloo/gatus-tailscale:v5.37.0
WORKDIR /app
COPY app/ ./
COPY --chmod=755 start.sh start.sh
ENTRYPOINT ["/app/start.sh"]
