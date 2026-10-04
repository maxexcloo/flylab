# Plan

This file contains only unfinished work. Current architecture and operations
are documented in `README.md`; completed migration history remains in Git.

## External Monitoring

1. Remove this repository's stale dependency on the retained `CONFIG`
   repository variable. Keep Fly machine, certificate, alerting and UI
   configuration here; the current `homelab` root no longer owns or publishes a
   service catalogue.
2. During the ephemeral render, check out public Kubelab `main` and run
   `scripts/render_service_inventory.sh --include-static` from that checkout. It
   derives HTTP probes from standard `HTTPRoute` resources, routes declared in
   upstream app-template `HelmRelease` values and static Homepage `services.yaml`
   entries carrying `siteMonitor`. Read the Git-owned configuration rather than
   querying a running Homepage instance. Do not add another service schema or
   publish the inventory through a GitHub variable. Fail if an enabled entry
   uses an unsupported shape. Keep route-specific overrides and provider and DNS
   probes as direct Gatus YAML fragments; Gatus natively merges its configuration
   directory.
3. Use `<cluster> / <Homepage group>` for generated groups and the Homepage name
   without an old target suffix. The current baseline is 30 enabled and accepted
   routes: 24 from `mbk` and six from `syd`. The 11 static Homepage entries do
   not overlap those routes, producing 41 unique service probes. Include
   Cloudflare and Control D DNS checks and provider checks as direct fragments.
   Remove all 33 retained `excloo.dev` catalogue probes, the old `au-truenas` and
   `au-hsp` suffixes, stopped Docker targets and deleted service URLs. Fail
   rendering on conflicting duplicates, invalid URLs or an empty generated route
   inventory.
4. Preserve the independent Fly failure domain, sending-only mail credential,
   Tailscale reachability, alert thresholds and Redlib `X-Gatus-Token` bypass.
   Prove one failing and one recovered alert without exposing the token.
