# argus-v18-egress (ACR-0018 §18, phase 16): the only way out for the scheduler and the team's alert route. A forward
# proxy that tunnels https (CONNECT, port 443) to the names in `filter` and refuses every other destination. The
# scheduler sits on argus-v18-sched (internal: no route out); this proxy is on that network and on argus-v18-core.
FROM alpine:3.20
RUN apk add --no-cache tinyproxy
COPY tinyproxy.conf filter /etc/tinyproxy/
USER tinyproxy
ENTRYPOINT ["tinyproxy", "-d", "-c", "/etc/tinyproxy/tinyproxy.conf"]
