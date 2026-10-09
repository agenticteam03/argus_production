# argus-v18-tunnel: keeps the restricted SSH tunnel vm-095 -> vm-166 open (encrypted cross-host path, v1.8 §3.2).
FROM alpine:3.20
RUN apk add --no-cache openssh-client autossh
ENTRYPOINT ["autossh", "-M", "0", "-N", \
  "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=3", "-o", "ExitOnForwardFailure=yes", \
  "-o", "StrictHostKeyChecking=yes", "-o", "UserKnownHostsFile=/secrets/known_hosts", "-o", "BatchMode=yes", \
  "-i", "/secrets/id_ed25519", \
  "-L", "0.0.0.0:18701:127.0.0.1:18701", "-L", "0.0.0.0:18702:127.0.0.1:18702", \
  "-L", "0.0.0.0:18703:127.0.0.1:18703", "-L", "0.0.0.0:18704:127.0.0.1:18704", \
  "-L", "0.0.0.0:18090:127.0.0.1:18090", "-L", "0.0.0.0:18091:127.0.0.1:18091"]
# T-0022: 18091 = vm-166's Argus-owned Alertmanager (needs permitopen="127.0.0.1:18091" on the tunnel account).
# The destination (argus-v18-tunnel@<vm-166 private IP>) is the compose `command:`, read from the VM-local
# /opt/argus-v18/hosts.env (never committed; template: deploy/hosts.env.example).
