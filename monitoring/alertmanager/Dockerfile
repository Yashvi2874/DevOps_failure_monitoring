# The config is baked into the image instead of bind-mounted, so the stack can
# be deployed by Jenkins (which talks to Docker through its socket and has no
# shared folders with the host).
FROM prom/alertmanager:v0.34.1
COPY alertmanager.yml /etc/alertmanager/alertmanager.yml
