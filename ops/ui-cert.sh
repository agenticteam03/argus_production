#!/bin/sh
# ACR-0011 (T-0016 step 4e): the public UI edge's certificate, Let's Encrypt by HTTP-01 through argus-v18-ui's :80.
#   sudo sh /opt/argus-v18/app/ops/ui-cert.sh bootstrap --as <developer>          a self-signed placeholder, so the
#                                                                                 edge can start in public mode
#   sudo sh /opt/argus-v18/app/ops/ui-cert.sh issue --as <developer> [--staging]   the first real certificate
#   sudo sh /opt/argus-v18/app/ops/ui-cert.sh renew --scheduled                    the timer (argus-v18-certbot)
#   sudo sh /opt/argus-v18/app/ops/ui-cert.sh status                               the days left (read-only)
# ARGUS_UI_DOMAIN (deploy/ui/vm-095.env, never in Git) is a name or an IPv4 address. For an address, Let's Encrypt
# issues only its `shortlived` profile (about 6 days): certbot >= 5 with --ip-address. A renewal runs only when 3 days
# or less are left (the timer fires twice a day), so a short-lived certificate is renewed about twice a week, under
# Let's Encrypt's duplicate-certificate limit. certbot runs in a one-off container (CERTBOT_IMAGE, pinned); its state
# lives in <secrets>/tls/letsencrypt (0700 root); the challenge files in /opt/argus-v18/acme, which argus-v18-ui
# serves read-only. The live key and chain are copied to <secrets>/tls/{fullchain,privkey}.pem readable by the
# edge's uid 101 only, then Nginx reloads (no restart). A renewal touches no Argus data, so the timer needs no lease
# (--scheduled); bootstrap and issue do (the session marker).
set -eu
HOME_DIR=${ARGUS_DEPLOY_HOME:-/opt/argus-v18}
DOCKER=${ARGUS_DOCKER:-docker}
CERTBOT_IMAGE=${ARGUS_CERTBOT_IMAGE:-certbot/certbot:v5.8.0}
RENEW_DAYS=${ARGUS_UI_CERT_RENEW_DAYS:-3}
NAME=argus-ui                               # the certbot lineage, whatever the identifier
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
case "$DOMAIN" in ""|*example*|*/*|*" "*) echo "ARGUS_UI_DOMAIN is not set to a real name or address in $ENV_FILE"; exit 1 ;; esac
if echo "$DOMAIN" | grep -Eq '^[0-9]{1,3}(\.[0-9]{1,3}){3}$'; then
  ID="--ip-address $DOMAIN --required-profile shortlived"     # an address: Let's Encrypt's 6-day profile only
else
  ID="-d $DOMAIN"
fi

days_left() {
  [ -s "$TLS/fullchain.pem" ] || { echo "-1"; return; }
  end=$(openssl x509 -enddate -noout -in "$TLS/fullchain.pem" | cut -d= -f2)
  echo $(( ( $(date -d "$end" +%s) - $(date +%s) ) / 86400 ))
}
issuer() { [ -s "$TLS/fullchain.pem" ] && openssl x509 -issuer -noout -in "$TLS/fullchain.pem" | sed 's/^issuer=//' || echo none; }
put() {   # $1 = source file, $2 = name under <secrets>/tls: readable by the edge (uid 101) only, replaced atomically
  t=$(mktemp "$TLS/.$2.XXXXXX")
  cat "$1" >"$t"
  chown 101:101 "$t"
  chmod 0400 "$t"
  mv "$t" "$TLS/$2"
}
reload() { "$DOCKER" exec argus-v18-ui nginx -s reload >/dev/null 2>&1 && echo "nginx reloaded" || echo "argus-v18-ui not running: no reload"; }
install_live() { put "$TLS/letsencrypt/live/$NAME/fullchain.pem" fullchain.pem; put "$TLS/letsencrypt/live/$NAME/privkey.pem" privkey.pem; reload; }
certbot() {
  "$DOCKER" run --rm --name argus-v18-certbot \
    -v "$TLS/letsencrypt:/etc/letsencrypt" -v "$ACME:/var/www/acme" "$CERTBOT_IMAGE" "$@"
}
need_session() {
  [ -n "$WHO" ] || { echo "$CMD needs --as <developer>"; exit 2; }
  grep -q "^holder=$WHO " "$HOME_DIR/SESSION" 2>/dev/null || { echo "NOT YOUR SESSION - stop here"; exit 1; }
}
dirs() {
  [ -d "$HOME_DIR/secrets" ] || { echo "no $HOME_DIR/secrets"; exit 1; }       # never created or re-moded here
  install -d -m 0750 -o root -g 101 "$TLS"                   # the edge (uid 101) reads the two .pem files only
  install -d -m 0700 -o root -g root "$TLS/letsencrypt"      # certbot's account and history: root only
  install -d -m 0755 "$ACME"
}

case "$CMD" in
  status)
    echo "UI CERT $DOMAIN: $(days_left) days left; issuer: $(issuer)" ;;
  bootstrap)
    need_session; dirs
    if [ -s "$TLS/fullchain.pem" ]; then echo "a certificate is already there ($(issuer)): nothing done"; exit 0; fi
    w=$(mktemp -d)
    openssl req -x509 -newkey rsa:2048 -nodes -days 2 -subj "/CN=argus-bootstrap" -keyout "$w/key" -out "$w/crt" 2>/dev/null
    put "$w/crt" fullchain.pem; put "$w/key" privkey.pem; rm -rf "$w"
    echo "UI CERT BOOTSTRAP: self-signed placeholder for 2 days (replace it with issue)" ;;
  issue)
    need_session; dirs
    certbot certonly --non-interactive --agree-tos --register-unsafely-without-email $STAGING \
      --cert-name "$NAME" --webroot -w /var/www/acme $ID
    install_live
    echo "UI CERT ISSUED $DOMAIN by $WHO${STAGING:+ (STAGING: not trusted by browsers)}: $(days_left) days left; issuer: $(issuer)" ;;
  renew)
    [ -n "$SCHEDULED" ] || need_session
    left=$(days_left)
    if [ "$left" -gt "$RENEW_DAYS" ]; then echo "UI CERT $DOMAIN: $left days left, no renewal (at $RENEW_DAYS)"; exit 0; fi
    certbot renew --non-interactive --cert-name "$NAME" --force-renewal --webroot -w /var/www/acme --quiet
    install_live
    echo "UI CERT RENEWED $DOMAIN: $left -> $(days_left) days left" ;;
  *)
    echo "usage: ui-cert.sh bootstrap|issue --as <developer> [--staging] | renew --scheduled | renew --as <developer> | status"; exit 2 ;;
esac
