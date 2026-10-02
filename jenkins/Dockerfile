# Jenkins with everything this project needs baked in:
#   - Docker CLI, Compose and Buildx, so pipeline steps can drive the host's
#     Docker engine through the mounted /var/run/docker.sock
#   - the plugins listed in plugins.txt
#   - Configuration as Code (casc.yaml): admin user and the pipeline job are
#     created on startup, so there is no setup wizard to click through
FROM jenkins/jenkins:2.580.1-lts-jdk21

USER root
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
 && install -m 0755 -d /etc/apt/keyrings \
 && curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc \
 && chmod a+r /etc/apt/keyrings/docker.asc \
 && . /etc/os-release \
 && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian ${VERSION_CODENAME} stable" \
      > /etc/apt/sources.list.d/docker.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends docker-ce-cli docker-compose-plugin docker-buildx-plugin \
 && rm -rf /var/lib/apt/lists/*

USER jenkins
ENV JAVA_OPTS="-Djenkins.install.runSetupWizard=false" \
    CASC_JENKINS_CONFIG=/var/jenkins_conf/casc.yaml

COPY --chown=jenkins:jenkins plugins.txt /usr/share/jenkins/ref/plugins.txt
RUN jenkins-plugin-cli --plugin-file /usr/share/jenkins/ref/plugins.txt
COPY --chown=jenkins:jenkins casc.yaml /var/jenkins_conf/casc.yaml
