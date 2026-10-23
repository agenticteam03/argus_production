#!/usr/bin/env bash
# ACR-0018 phase 16 step 4: the team's client CA for the private path, run on a LAPTOP (never on vm-095). The CA's
# private key is AES-256 encrypted with a passphrase openssl asks for (never on a command line), in ARGUS_EDGE_CA_DIR
# (default ~/.argus-edge-ca, 0700); a copy is kept by the other administrator (D3). vm-095 gets only ca.crt and
# crl.pem. A person's private key is made on their own machine and never leaves it: they send the CSR only.
#   CA holder:  bash ops/edge-ca.sh init                          the CA (10 years) and an empty CRL
#               bash ops/edge-ca.sh sign <person> <person.csr>    a 90-day client certificate -> <person>.crt
#               bash ops/edge-ca.sh revoke <person>               revoke their certificates, then a new CRL
#               bash ops/edge-ca.sh crl                           a new CRL (it is valid 30 days: renew it monthly)
#               bash ops/edge-ca.sh list                          the certificates issued, with their state
#   A person:   bash ops/edge-ca.sh person-key <person>           <person>.key (0600) and <person>.csr, in the cwd
#               bash ops/edge-ca.sh person-p12 <person>           <person>.p12 for the browser, from .key and .crt
# Copy ca.crt and crl.pem to vm-095's /opt/argus-v18/edge-ops/ (the deploy block does it, with the lease).
set -euo pipefail
# Git Bash on Windows would turn /O=Argus/CN=... into a Windows path; this switch is a no-op elsewhere
export MSYS_NO_PATHCONV=1

CA=${ARGUS_EDGE_CA_DIR:-$HOME/.argus-edge-ca}
# On Windows (Git Bash), openssl's config file needs C:/... (no backslash, no /c/...): cygpath -m gives that form
if command -v cygpath >/dev/null 2>&1; then CA=$(cygpath -m "$CA"); fi
DAYS=${ARGUS_EDGE_CERT_DAYS:-90}
# Tests only: the passphrase from a file (openssl reads it; never an argument). People type it when openssl asks.
PASS=(); [ -z "${ARGUS_EDGE_CA_PASSFILE:-}" ] || PASS=(-pass "file:$ARGUS_EDGE_CA_PASSFILE")
PASSIN=(); [ -z "${ARGUS_EDGE_CA_PASSFILE:-}" ] || PASSIN=(-passin "file:$ARGUS_EDGE_CA_PASSFILE")
stop() { echo "EDGE CA STOP: $*"; exit 1; }
person_ok() { [[ "${1:-}" =~ ^[a-z][a-z0-9_-]{1,31}$ ]] || stop "a person is a lower-case handle, not '${1:-}'"; }

conf() {
  cat > "$CA/ca.cnf" <<EOF
[ca]
default_ca = argus
[argus]
dir = $CA
database = \$dir/index.txt
new_certs_dir = \$dir/issued
serial = \$dir/serial
crlnumber = \$dir/crlnumber
certificate = \$dir/ca.crt
private_key = \$dir/ca.key
default_md = sha256
default_days = $DAYS
default_crl_days = 30
policy = only_cn
unique_subject = no
copy_extensions = none
[only_cn]
commonName = supplied
[client]
basicConstraints = critical, CA:FALSE
keyUsage = critical, digitalSignature
extendedKeyUsage = clientAuth
[root]
basicConstraints = critical, CA:TRUE, pathlen:0
keyUsage = critical, keyCertSign, cRLSign
subjectKeyIdentifier = hash
EOF
}

case "${1:-}" in
  init)
    [ ! -e "$CA/ca.key" ] || stop "$CA/ca.key exists: one CA per team"
    mkdir -p "$CA/issued" && chmod 700 "$CA"
    conf; : > "$CA/index.txt"; echo 1000 > "$CA/serial"; echo 1000 > "$CA/crlnumber"
    openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -aes-256-cbc "${PASS[@]}" -out "$CA/ca.key"
    chmod 600 "$CA/ca.key"
    openssl req -new -x509 -key "$CA/ca.key" "${PASSIN[@]}" -days 3650 -subj "/O=Argus/CN=Argus private path CA" \
      -config "$CA/ca.cnf" -extensions root -out "$CA/ca.crt"
    openssl ca -config "$CA/ca.cnf" "${PASSIN[@]}" -gencrl -out "$CA/crl.pem"
    echo "EDGE CA READY: $CA/ca.crt and $CA/crl.pem to vm-095; keep ca.key here and its copy with the other administrator" ;;
  sign)
    person_ok "${2:-}"; [ -s "${3:-}" ] || stop "usage: sign <person> <person.csr>"
    [ -s "$CA/ca.key" ] || stop "no CA in $CA (init first)"
    conf
    openssl req -in "$3" -noout -verify 2>/dev/null || stop "$3 is not a valid CSR"
    openssl ca -config "$CA/ca.cnf" "${PASSIN[@]}" -batch -extensions client -subj "/O=Argus/CN=$2" -in "$3" -out "$CA/issued/$2.crt"
    cp "$CA/issued/$2.crt" "./$2.crt"
    echo "EDGE CERT SIGNED: ./$2.crt for $2, $DAYS days (send it back; the key never travels)" ;;
  revoke)
    person_ok "${2:-}"; conf
    n=0
    # index.txt: state, expiry, revocation date (empty while valid), serial, file, subject; awk keeps the empty field
    for serial in $(awk -F'\t' -v cn="/CN=$2" '$1 == "V" && substr($6, length($6) - length(cn) + 1) == cn {print $4}' \
                      "$CA/index.txt"); do
      openssl ca -config "$CA/ca.cnf" "${PASSIN[@]}" -revoke "$CA/issued/$serial.pem" -crl_reason superseded; n=$((n + 1))
    done
    openssl ca -config "$CA/ca.cnf" "${PASSIN[@]}" -gencrl -out "$CA/crl.pem"
    echo "EDGE CERTS REVOKED: $n of $2; copy the new crl.pem to vm-095 and reload the edge" ;;
  crl)
    conf; openssl ca -config "$CA/ca.cnf" "${PASSIN[@]}" -gencrl -out "$CA/crl.pem"
    echo "EDGE CRL: $CA/crl.pem (valid 30 days); copy it to vm-095" ;;
  list)
    [ -s "$CA/index.txt" ] || stop "no certificates issued"
    awk -F'\t' '{split($6, s, "CN="); print $1 == "V" ? "valid  " : "revoked", "until", $2, "serial", $4, s[2]}' "$CA/index.txt" ;;
  person-key)
    person_ok "${2:-}"; [ ! -e "$2.key" ] || stop "$2.key exists"
    (umask 077; openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -out "$2.key")
    openssl req -new -key "$2.key" -subj "/O=Argus/CN=$2" -out "$2.csr"
    echo "EDGE KEY: $2.key stays here (0600); send $2.csr to the CA holder" ;;
  person-p12)
    person_ok "${2:-}"; [ -s "$2.key" ] && [ -s "$2.crt" ] || stop "needs $2.key and $2.crt in this folder"
    openssl pkcs12 -export -inkey "$2.key" -in "$2.crt" -name "Argus $2" "${PASS[@]/-pass/-passout}" -out "$2.p12"
    chmod 600 "$2.p12"
    echo "EDGE P12: $2.p12 to import into the browser (it asks for the export password you just set)" ;;
  *) stop "usage: init | sign <person> <csr> | revoke <person> | crl | list | person-key <person> | person-p12 <person>" ;;
esac
