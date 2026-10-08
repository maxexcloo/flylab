# Activation

Deployment [37710520724](https://github.com/maxexcloo/flylab/actions/runs/37710520724)
succeeded on 8 October 2026. Both Homelab and Kubelab validation workflows
successfully dispatched Gatus deployments using their validated revisions.
The dispatch credential is configured in both source repositories.

Gatus renders 57 checks from the shared inventory. Dynamic 1Password resolution
succeeds, and deployment preserves the native Fly mail and Tailscale credentials.
Homepage resolves machine references from the same Homelab inventory every five
minutes in both clusters.

Homelab's infrastructure apply completed, and its follow-up plan reported no
changes. Both Kubernetes clusters reconciled Kubelab commit `516a432`; all Flux
stages and Helm releases were ready, with no unready Pods.

Remaining checks:

1. Restore connectivity to Bento and NanoKVM. Both fail LAN and Tailscale
   reachability checks. Tailscale last saw Bento on 3 September and NanoKVM on
   5 October 2026. Their monitoring remains enabled.
2. Verify mail delivery during a genuine failure and recovery. Delivery has not
   been tested as part of this deployment; existing alert thresholds are retained.
