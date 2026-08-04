# Homelab Fly.io

Fly.io applications are deployed from this repository. Each top-level
directory containing `fly.toml` is one application.

Pushes deploy every application. The manual workflow can deploy one application
or explicitly delete one. Secrets remain SOPS-encrypted in Git and are decrypted
only on the deployment runner.
