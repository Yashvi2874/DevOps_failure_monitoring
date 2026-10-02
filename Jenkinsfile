// CI/CD pipeline for the sensor dashboard.
//
//   Checkout -> Build & Test -> Validate Monitoring -> Build Image
//            -> Deploy -> Smoke Test (rolls back automatically if it fails)
//
// Every step runs through Docker, so the Jenkins machine itself only needs the
// Docker CLI. Jenkins talks to the host's Docker engine via the mounted socket.

pipeline {
    agent any

    options {
        timestamps()
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '30'))
        timeout(time: 20, unit: 'MINUTES')
    }

    triggers {
        // Check GitHub for new commits every minute. A webhook would be
        // instant, but GitHub can't reach a Jenkins running on a laptop.
        pollSCM('* * * * *')
    }

    parameters {
        booleanParam(
            name: 'SIMULATE_BAD_DEPLOY',
            defaultValue: false,
            description: 'Deploy this build with a failing /health check to demonstrate the automatic rollback.'
        )
    }

    environment {
        APP_IMAGE = 'sensor-dashboard'
        IMAGE_TAG = "${env.BUILD_NUMBER}"
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
                script {
                    env.GIT_SHORT = sh(script: 'git rev-parse --short HEAD', returnStdout: true).trim()
                    env.GIT_SUBJECT = sh(script: 'git log -1 --pretty=%s', returnStdout: true).trim()
                    currentBuild.description = "${env.GIT_SHORT}: ${env.GIT_SUBJECT}"
                }
            }
        }

        stage('Build & Test') {
            steps {
                // The "test" stage of app/Dockerfile has pytest and flake8 in it.
                // Running it as a container (instead of during the build) lets
                // us copy the JUnit report out even when tests fail.
                sh '''
                    docker build --target test -t ${APP_IMAGE}:test-${IMAGE_TAG} app
                    docker run --name sensor-tests-${BUILD_NUMBER} ${APP_IMAGE}:test-${IMAGE_TAG}
                '''
            }
            post {
                always {
                    sh '''
                        mkdir -p reports
                        docker cp sensor-tests-${BUILD_NUMBER}:/reports/junit.xml reports/junit.xml || true
                        docker rm -f sensor-tests-${BUILD_NUMBER} >/dev/null 2>&1 || true
                        docker rmi ${APP_IMAGE}:test-${IMAGE_TAG} >/dev/null 2>&1 || true
                    '''
                    junit allowEmptyResults: true, testResults: 'reports/junit.xml'
                }
            }
        }

        stage('Validate Monitoring') {
            steps {
                // Broken alert rules are as bad as broken code: if they don't
                // load, nobody gets told when the app fails.
                sh '''
                    docker compose build prometheus alertmanager alert-receiver
                    docker run --rm --entrypoint promtool sensor-prometheus:latest \
                        check config /etc/prometheus/prometheus.yml
                    docker run --rm --entrypoint promtool sensor-prometheus:latest \
                        test rules /etc/prometheus/tests/alert_rules_test.yml
                    docker run --rm --entrypoint amtool sensor-alertmanager:latest \
                        check-config /etc/alertmanager/alertmanager.yml
                    docker run --rm --entrypoint amtool sensor-alertmanager:latest config routes test \
                        --config.file=/etc/alertmanager/alertmanager.yml --verify.receivers=on-call-pager severity=critical
                    docker run --rm --entrypoint amtool sensor-alertmanager:latest config routes test \
                        --config.file=/etc/alertmanager/alertmanager.yml --verify.receivers=team-chat severity=warning
                    docker run --rm sensor-alert-receiver:latest python -m unittest -v
                '''
            }
        }

        stage('Build Image') {
            steps {
                sh '''
                    docker build --target runtime \
                        --build-arg APP_VERSION=1.0.${BUILD_NUMBER} \
                        --build-arg GIT_COMMIT=${GIT_SHORT} \
                        --build-arg BUILD_NUMBER=${BUILD_NUMBER} \
                        -t ${APP_IMAGE}:${IMAGE_TAG} app
                    docker image ls ${APP_IMAGE}
                '''
            }
        }

        stage('Deploy') {
            steps {
                // IMAGE_TAG (the build number) tells docker-compose.yml which
                // image to run. Only containers whose image changed are recreated.
                sh '''
                    export FORCE_UNHEALTHY=${SIMULATE_BAD_DEPLOY:-false}
                    docker compose up -d --no-build --remove-orphans
                    docker compose ps
                '''
            }
        }

        stage('Smoke Test') {
            steps {
                // Run the check from a throwaway container on the stack's network,
                // the same way Prometheus and users reach the app.
                sh '''
                    docker run --rm -i --network sensor-net -e EXPECTED_BUILD=${BUILD_NUMBER} \
                        ${APP_IMAGE}:${IMAGE_TAG} python - < scripts/smoke_test.py
                '''
            }
            post {
                success {
                    // Remember this build as the last known good one. :latest is
                    // what a plain `docker compose up -d` starts, so it should be
                    // the newest build that passed, not whatever was built locally.
                    sh '''
                        docker tag ${APP_IMAGE}:${IMAGE_TAG} ${APP_IMAGE}:stable
                        docker tag ${APP_IMAGE}:${IMAGE_TAG} ${APP_IMAGE}:latest
                    '''
                }
                failure {
                    sh 'sh scripts/rollback.sh'
                }
            }
        }
    }

    post {
        success {
            echo "Build ${env.BUILD_NUMBER} (${env.GIT_SHORT}) is live on http://localhost:8000"
            sh 'sh scripts/notify_alertmanager.sh resolved || true'
        }
        failure {
            // Pipeline failures go through the same alerting path as app failures.
            sh 'sh scripts/notify_alertmanager.sh firing || true'
        }
        always {
            // Keep the five newest numbered images and drop the rest.
            sh '''
                docker images ${APP_IMAGE} --format '{{.Tag}}' | grep -E '^[0-9]+$' | sort -n | head -n -5 \
                    | xargs -r -I{} docker rmi ${APP_IMAGE}:{} >/dev/null 2>&1 || true
                docker image prune -f >/dev/null 2>&1 || true
            '''
        }
    }
}
