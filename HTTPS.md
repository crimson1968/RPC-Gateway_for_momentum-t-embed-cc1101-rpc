# LAN HTTPS deployment

Scope: LAN-only, no login, requested by user. This is prepared configuration;
AdGuard and Traefik have not been modified remotely.

1. Replace gateway.py with this package version and rebuild the image. It allows
   HTTPS origins for MCP as well as HTTP origins; the browser UI already supports
   same-host HTTPS requests.
2. Replace the existing tembed-gateway service with the block in
   compose.traefik-lan.yaml. Preserve mcp-dockhand, opencode and the proxy network.
   Remove the old ports section: the HTTPS variant publishes no direct host port.
3. In AdGuard Home add a DNS rewrite:
   domain: tembed-gateway.myhomelabs.work
   answer: the LAN IP of Traefik, NOT the CC1101 address.
   Existing dockhand.myhomelabs.work resolved locally to 192.168.178.224 during
   preparation. Confirm that this is Traefik before using it.
4. Deploy the rebuilt service. The existing websecure entrypoint, proxy Docker
   network and cloudflare certificate resolver are reused from your stack.
5. Open https://tembed-gateway.myhomelabs.work/
   MCP endpoint: https://tembed-gateway.myhomelabs.work/mcp
   Docker-internal MCP remains http://tembed-gateway:8000/mcp.

The LAN middleware allows source 192.168.178.0/24. It does not trust arbitrary
X-Forwarded-For values. If Traefik sees a NAT/proxy address instead, inspect the
actual source address before changing the rule. Do not remove the LAN restriction
or allow a public proxy subnet merely to make a 403 disappear.

The cloudflare resolver must already have valid DNS-challenge credentials and
manage myhomelabs.work, as for your other routers. AdGuard DNS rewrites only
provide name resolution; Traefik obtains and serves the TLS certificate.
No public DNS entry or inbound port-forward is needed for a DNS-01 certificate.

No claims are made that DNS, certificate issuance or NAS deployment have been
completed. Those require changes in your actual AdGuard/Dockhand configuration.

Sources:
https://doc.traefik.io/traefik/reference/routing-configuration/http/middlewares/ipallowlist/
https://v2.doc.traefik.io/traefik/routing/providers/docker/
https://github.com/AdguardTeam/AdGuardHome/wiki/Configuration
