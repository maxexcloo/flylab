# Activation

1. Confirm the read-only 1Password service account can read the retained Gatus
   mail and Tailscale references and `Cluster: syd/Redlib/monitoring-token`.
   Keep the mail key sending-only; resolve references only in GitHub Actions.
2. Install the receiving Fly workflow, then configure `FLY_DEPLOY_TOKEN` in Homelab and Kubelab
   with Actions write access only to `maxexcloo/homelab-fly` and install their dispatches.
3. Deploy the reviewed changes and verify private DNS/Tailscale reachability and
   Redlib's token bypass. Prove one failed and one recovered mail alert without
   exposing credentials.
4. Remove the unused `CONFIG` repository variable after successful migration.
