# Activation

Deployment [37403970062](https://github.com/maxexcloo/homelab-fly/actions/runs/37403970062)
succeeded on 6 October 2026. The live page contains 62 checks with domain-first
grouping and Homelab infrastructure. Dynamic 1Password resolution succeeded,
native Fly mail and Tailscale credentials were preserved, and the obsolete
`CONFIG` repository variable was removed.

Private checks reached hotdog, kimbap, hsp and taco; gateway and hass recovered
after startup. Redlib returned HTTP 200 with its discovered token, followed by
HTTP 404 on a subsequent check. Successful deployment does not imply every
monitored service is healthy.

Remaining work:

1. Configure `FLY_DEPLOY_TOKEN` in Homelab and Kubelab with Actions write access
   only to `maxexcloo/homelab-fly`, then verify their installed dispatch jobs.
2. Investigate the observed LaraPaper timeout, TrueNAS connection refusal on
   port 8443, bento/nanokvm ICMP failures and intermittent Redlib response.
   These checks follow the source repositories' current declarations.
3. Verify mail delivery during a genuine failure and recovery. Delivery has not
   been tested as part of this deployment; existing alert thresholds are retained.
