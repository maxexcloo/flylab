# Activation

Deployment [37408380214](https://github.com/maxexcloo/homelab-fly/actions/runs/37408380214)
succeeded on 6 October 2026. The live page contains 57 checks with domain-first
grouping and Homelab infrastructure. Dynamic 1Password resolution succeeded,
native Fly mail and Tailscale credentials were preserved, and the obsolete
`CONFIG` repository variable was removed.

Homepage now resolves machine references from Homelab's public inventory every
five minutes in both clusters. Gatus uses the same resolver with its selected
Homelab checkout. TrueNAS's link, widget and monitor use the declared management
port 443; its live check returned HTTP 200 after deployment. Home Assistant add-on
links remain navigation-only.

Private checks reached hotdog, kimbap, hsp and taco; gateway and hass recovered
after startup. Redlib returned HTTP 200 with its discovered token, followed by
HTTP 404 on a subsequent check. Successful deployment does not imply every
monitored service is healthy.

Remaining work:

1. Set `HOMELAB_FLY_DEPLOY_TOKEN` in both source repositories' Actions secrets.
   Keep its reference copy at `op://Homelab/GitHub Actions/homelab-fly-deploy-token`.
   The token needs Actions write access only to `maxexcloo/homelab-fly`.
   Kubelab dispatch is verified; verify Homelab after provisioning its secret.
2. Investigate the previously observed LaraPaper timeout, bento/nanokvm ICMP
   failures and intermittent Redlib response if they persist.
   These checks follow the source repositories' current declarations.
3. Verify mail delivery during a genuine failure and recovery. Delivery has not
   been tested as part of this deployment; existing alert thresholds are retained.
