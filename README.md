# Homelab Fly.io

Fly.io service implementations and deployment templates live in this
repository. The homelab config supplies the non-secret deployment instances
and shared service inventory.

Pushes deploy every configured Fly instance. Manual workflows can deploy one
instance or explicitly delete an app. Deployments render the selected service,
resolve its `op://` references through a read-only 1Password service account,
and send secrets directly to Fly.io.
