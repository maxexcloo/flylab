# Homelab Fly.io

Fly.io applications are deployed from this repository. Each top-level
directory containing `fly.toml` is one application.

Pushes deploy every application. The manual workflow can deploy one application
or explicitly delete one. Deployments resolve the fields declared in each
application's `secrets.json` through a read-only 1Password service account
limited to the Services vault, then send them directly to Fly.io.
