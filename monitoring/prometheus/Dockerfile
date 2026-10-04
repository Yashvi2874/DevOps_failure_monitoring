# baked in (not bind-mounted) so Jenkins can deploy it through the Docker socket
FROM prom/prometheus:v3.13.4
COPY prometheus.yml /etc/prometheus/prometheus.yml
COPY alert_rules.yml /etc/prometheus/alert_rules.yml
COPY tests/ /etc/prometheus/tests/
