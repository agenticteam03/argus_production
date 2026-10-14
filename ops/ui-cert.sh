#!/bin/sh
# ACR-0011 (T-0016 step 4e): the public UI edge's certificate, Let's Encrypt by HTTP-01 through argus-v18-ui's :80.
#   sudo sh /opt/argus-v18/app/ops/ui-cert.sh issue --as <developer> [--staging]   the first certificate
#   sudo sh /opt/argus-v18/app/ops/ui-cert.sh renew --scheduled                    the daily timer (argus-v18-certbot)
#   sudo sh /opt/argus-v18/app/ops/ui-cert.sh status                               the days left (read-only)
# certbot runs in a one-off container (CERTBOT_IMAGE, pinned); its state lives in <secrets>/tls/letsencrypt (0700
# root); the challenge files in /opt/argus-v18/acme, which argus-v18-ui serves read-only. The live key and chain are
# copied to <secrets>/tls/{fullchain,privkey}.pem readable by the edge's uid 101 only, then Nginx reloads (no
# restart). The domain comes from deploy/ui/vm-095.env (never in Git). A renewal touches no Argus data, so the timer
# needs no lease (--scheduled); `issue` does (the session marker).
set -eu
HOME_DIR=${ARGUS_DEPLOY_HOME:-/opt/argus-v18}
DOCKER=${ARGUS_DOCKER:-docker}
CERTBOT_IMAGE=${ARGUS_CERTBOT_IMAGE:-certbot/certbot:v2.11.0}
TLS=$HOME_DIR/secrets/tls
ACME=$HOME_DIR/acme
ENV_FILE=$HOME_DIR/app/deploy/ui/vm-095.env
CMD=${1:-}
shift || true
WHO=""; STAGING=""; SCHEDULED=""
while [ $# -gt 0 ]; do
  case "$1" in
    --as) WHO=${2:-}; shift ;;
    --staging) STAGING="--staging" ;;
    --scheduled) SCHEDULED=1 ;;
    *) echo "unknown argument $1"; exit 2 ;;
  esac
  shift
done
[ -s "$ENV_FILE" ] || { echo "no $ENV_FILE (ARGUS_UI_DOMAIN): copy deploy/ui/vm-095.env.example"; exit 1; }
DOMAIN=$(sed -n 's/^ARGUS_UI_DOMAIN=//p' "$ENV_FILE" | tr -d '[:space:]')
case "$DOMAIN" in ""|*example*|*/*|*" "*) echo "ARGUS_UI_DOMAIN is not set to a real name in $ENV_FILE"; exit 1 ;; esac

days_left() {
  [ -s "$TLS/fullchain.pem" ] || { echo "-1"; return; }
  end=$(openssl x509 -enddate -noout -in "$TLS/fullchain.pem" | cut -d= -f2)
  echo $(( ( $(date -d "$end" +%s) - $(date +%s) ) / 86400 ))
}
install_live() {   # the live chain and key, readable by the edge (uid 101) only
  live="$TLS/letsencrypt/live/$DOMAIN"
  for f in fullchain privkey; do
    t=$(mktemp "$TLS/.$f.XXXXXX")
    cat "$live/$f.pem" >"$t"
    chown 101:101 "$t"
    chmod 0400 "$t"
    mv "$t" "$TLS/$f.pem"
  done
  "$DOCKER" exec argus-v18-ui nginx -s reload >/dev/null 2>&1 && echo "nginx reloaded" || echo "argus-v18-ui not running: no reload"
}
certbot() {
  "$DOCKER" run --rm --name argus-v18-certbot \
    -v "$TLS/letsencrypt:/etc/letsencrypt" -v "$ACME:/var/www/acme" "$CERTBOT_IMAGE" "$@"
}

case "$CMD" in
  status)
    echo "UI CERT $DOMAIN: $(days_left) days left" ;;
  issue)
    [ -n "$WHO" ] || { echo "issue needs --as <developer>"; exit 2; }
    grep -q "^holder=$WHO " "$HOME_DIR/SESSION" 2>/dev/null || { echo "NOT YOUR SESSION - stop here"; exit 1; }
    [ -d "$HOME_DIR/secrets" ] || { echo "no $HOME_DIR/secrets"; exit 1; }       # never created or re-moded here
    install -d -m 0750 -o root -g 101 "$TLS"                   # the edge (uid 101) reads the two .pem files only
    install -d -m 0700 -o root -g root "$TLS/letsencrypt"      # certbot's account and history: root only
    install -d -m 0755 "$ACME"
    certbot certonly --non-interactive --agree-tos --register-unsafely-without-email $STAGING \
      --webroot -w /var/www/acme -d "$DOMAIN"
    install_live
    echo "UI CERT ISSUED $DOMAIN by $WHO: $(days_left) days left" ;;
  renew)
    [ -n "$SCHEDULED" ] || [ -n "$WHO" ] || { echo "renew needs --scheduled (the timer) or --as <developer>"; exit 2; }
    before=$(days_left)
    certbot renew --non-interactive --webroot -w /var/www/acme --quiet
    [ -s "$TLS/letsencrypt/live/$DOMAIN/fullchain.pem" ] || { echo "no live certificate: run issue first"; exit 1; }
    if ! cmp -s "$TLS/letsencrypt/live/$DOMAIN/fullchain.pem" "$TLS/fullchain.pem"; then install_live; fi
    echo "UI CERT $DOMAIN: $before -> $(days_left) days left" ;;
  *)
    echo "usage: ui-cert.sh issue --as <developer> [--staging] | renew --scheduled | renew --as <developer> | status"; exit 2 ;;
esac
