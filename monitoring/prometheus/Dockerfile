# Config, rules and rule tests are baked into the image. The pipeline runs
# promtool from this same image to validate them before deploying.
FROM prom/prometheus:v3.13.4
COPY prometheus.yml /etc/prometheus/prometheus.yml
COPY alert_rules.yml /etc/prometheus/alert_rules.yml
COPY tests/ /etc/prometheus/tests/
