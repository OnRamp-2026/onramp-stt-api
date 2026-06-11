pipeline {
  agent {
    kubernetes {
      defaultContainer 'tools'
      yaml """
apiVersion: v1
kind: Pod
spec:
  restartPolicy: Never
  containers:
    - name: tools
      image: python:3.11-slim
      command:
        - cat
      tty: true
    - name: kaniko
      image: gcr.io/kaniko-project/executor:debug
      command:
        - /busybox/cat
      tty: true
      volumeMounts:
        - name: kaniko-docker-config
          mountPath: /kaniko/.docker
  volumes:
    - name: kaniko-docker-config
      emptyDir: {}
"""
    }
  }

  options {
    disableConcurrentBuilds()
    skipDefaultCheckout(true)
  }

  environment {
    IMAGE_REPOSITORY = 'amdp-registry.skala-ai.com/skala26a-cloud/onramp-stt-api'
  }

  stages {
    stage('Prepare Tools') {
      steps {
        sh '''
          set -eu
          apt-get update
          apt-get install -y --no-install-recommends git ca-certificates ffmpeg
          rm -rf /var/lib/apt/lists/*
        '''
      }
    }

    stage('Checkout') {
      steps {
        checkout scm
        sh 'git config --global --add safe.directory "${WORKSPACE}"'
        script {
          env.IMAGE_TAG = sh(
            script: 'git rev-parse --short=12 HEAD',
            returnStdout: true
          ).trim()
        }
      }
    }

    stage('Lint, Type Check and Test') {
      steps {
        sh '''
          set -eu
          python -m venv .venv
          . .venv/bin/activate
          pip install --upgrade pip
          pip install ".[dev]"
          ruff format --check app tests alembic
          ruff check app tests alembic
          mypy app
          pytest tests
        '''
      }
    }

    stage('Build Image Check') {
      when {
        changeRequest()
      }
      steps {
        container('kaniko') {
          sh '''
            set -eu
            /kaniko/executor \
              --context "${WORKSPACE}" \
              --dockerfile "${WORKSPACE}/Dockerfile" \
              --custom-platform=linux/amd64 \
              --destination "${IMAGE_REPOSITORY}:${IMAGE_TAG}" \
              --no-push
          '''
        }
      }
    }

    stage('Build and Push Image') {
      when {
        allOf {
          branch 'main'
          not {
            changeRequest()
          }
        }
      }
      steps {
        container('kaniko') {
          withCredentials([usernamePassword(
            credentialsId: 'harbor-robot-credential',
            usernameVariable: 'HARBOR_USERNAME',
            passwordVariable: 'HARBOR_PASSWORD'
          )]) {
            sh '''
              set -eu
              REGISTRY_HOST="${IMAGE_REPOSITORY%%/*}"
              AUTH="$(printf '%s:%s' "${HARBOR_USERNAME}" "${HARBOR_PASSWORD}" | base64 | tr -d '\\n')"
              cat > /kaniko/.docker/config.json <<EOF
{"auths":{"${REGISTRY_HOST}":{"auth":"${AUTH}"}}}
EOF
              /kaniko/executor \
                --context "${WORKSPACE}" \
                --dockerfile "${WORKSPACE}/Dockerfile" \
                --custom-platform=linux/amd64 \
                --destination "${IMAGE_REPOSITORY}:${IMAGE_TAG}" \
                --digest-file "${WORKSPACE}/image-digest.txt"
            '''
          }
        }
        script {
          env.IMAGE_DIGEST = readFile('image-digest.txt').trim()
          echo "Built image: ${env.IMAGE_REPOSITORY}@${env.IMAGE_DIGEST}"
        }
      }
    }
  }

  post {
    always {
      sh 'rm -rf .venv image-digest.txt || true'
    }
  }
}
