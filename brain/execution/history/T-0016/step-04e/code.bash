# (archived) T-0016 step 4e, run 2026-10-14 by conantkd's agent over ssh; both leases, session 35297684bd04
# <PUBLIC_ADDR> = vm-095's public address: passed as an argument, kept out of Git (policies/SECURITY.md rule 4)
# =====================================================================================
# P.1 [VM vm-095 · bash] (ssh argus-vm095 'bash -s -- <PUBLIC_ADDR>' < this block) the branch, the name, the rules, the placeholder, the public edge (MUTATES)
# ROLLBACK: ui-firewall.sh remove --as <dev>; compose -f compose.ui.yml -f compose.public.yml down; (loopback back: -f compose.loopback.yml up -d)
ME=conantkd; BR=task/T-0016-playwright; PUBLIC_ADDR="$1"
grep -q "^holder=$ME " /opt/argus-v18/SESSION && echo "SESSION OK" || { echo "NOT YOUR SESSION - stop here"; exit 1; }
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
sudo bash /opt/argus-v18/app/ops/deploy.sh $BR --as $ME </dev/null | tail -1
# the public name of the UI: only on the VM (gitignored), never in Git
echo "ARGUS_UI_DOMAIN=$PUBLIC_ADDR" | sudo tee /opt/argus-v18/app/deploy/ui/vm-095.env >/dev/null
sudo chmod 0644 /opt/argus-v18/app/deploy/ui/vm-095.env
sudo git -C /opt/argus-v18/app status --porcelain </dev/null | head -3; echo "(checkout: only ignored files changed above if empty)"
sudo sh /opt/argus-v18/app/ops/ui-firewall.sh apply --as $ME </dev/null
sudo sh /opt/argus-v18/app/ops/ui-cert.sh bootstrap --as $ME </dev/null
cd /opt/argus-v18/app/deploy/ui
sudo docker compose -f compose.ui.yml -f compose.loopback.yml down </dev/null 2>&1 | tail -1
sudo docker compose --env-file vm-095.env -f compose.ui.yml -f compose.public.yml up -d --build </dev/null 2>&1 | tail -2
for i in $(seq 1 30); do s=$(sudo docker inspect -f '{{.State.Health.Status}}' argus-v18-ui </dev/null 2>/dev/null); [ "$s" = healthy ] && break; sleep 3; done
echo "ui: $(sudo docker inspect -f '{{.State.Status}} health={{.State.Health.Status}} restarts={{.RestartCount}} user={{.Config.User}} ro={{.HostConfig.ReadonlyRootfs}}' argus-v18-ui </dev/null)"
echo "ports: $(sudo docker port argus-v18-ui </dev/null | tr '\n' ' ')"
sudo docker logs argus-v18-ui 2>&1 </dev/null | grep -iE "emerg|error" | tail -3
cd ~
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1

# P.2 [VM vm-095 · bash] a staging dry run, then the certificate and the renewal timer (MUTATES)
sudo docker run --rm -v /opt/argus-v18/secrets/tls/letsencrypt:/etc/letsencrypt -v /opt/argus-v18/acme:/var/www/acme certbot/certbot:v5.8.0 certonly --dry-run --non-interactive --agree-tos --register-unsafely-without-email --cert-name argus-ui --webroot -w /var/www/acme --ip-address <PUBLIC_ADDR> --required-profile shortlived
sudo sh /opt/argus-v18/app/ops/ui-cert.sh issue --as conantkd
sudo install -m 0644 /opt/argus-v18/app/deploy/ui/systemd/argus-v18-certbot.{service,timer} /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now argus-v18-certbot.timer
sudo sh /opt/argus-v18/app/ops/ui-cert.sh renew --as conantkd    # expected: no renewal (more than 3 days left)
