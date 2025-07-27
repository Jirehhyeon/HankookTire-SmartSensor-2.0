#!/bin/bash

# HankookTire SmartSensor 2.0 - 모니터링 시스템 설정 스크립트
# 차세대 통합 스마트 타이어 센서 시스템 모니터링 구축

set -euo pipefail

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 로깅 함수
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING: $1${NC}"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}"
}

info() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')] INFO: $1${NC}"
}

# 스크립트 시작
log "🚀 HankookTire SmartSensor 2.0 모니터링 시스템 설정 시작"

# 환경 변수 설정
NAMESPACE=${NAMESPACE:-"hankook-smartsensor"}
MONITORING_NAMESPACE=${MONITORING_NAMESPACE:-"monitoring"}
CLUSTER_NAME=${CLUSTER_NAME:-"hankook-production"}

# 사전 요구사항 확인
check_prerequisites() {
    log "📋 사전 요구사항 확인 중..."
    
    # kubectl 설치 확인
    if ! command -v kubectl &> /dev/null; then
        error "kubectl이 설치되어 있지 않습니다."
        exit 1
    fi
    
    # 클러스터 연결 확인
    if ! kubectl cluster-info &> /dev/null; then
        error "Kubernetes 클러스터에 연결할 수 없습니다."
        exit 1
    fi
    
    # Helm 설치 확인 (선택사항)
    if command -v helm &> /dev/null; then
        info "✅ Helm 발견: $(helm version --short)"
        HELM_AVAILABLE=true
    else
        warn "Helm이 설치되어 있지 않습니다. 일부 기능이 제한될 수 있습니다."
        HELM_AVAILABLE=false
    fi
    
    log "✅ 사전 요구사항 확인 완료"
}

# 네임스페이스 생성
create_namespaces() {
    log "📁 네임스페이스 생성 중..."
    
    # 모니터링 네임스페이스 생성
    kubectl create namespace $MONITORING_NAMESPACE --dry-run=client -o yaml | kubectl apply -f -
    
    # 레이블 추가
    kubectl label namespace $MONITORING_NAMESPACE monitoring=enabled --overwrite
    kubectl label namespace $NAMESPACE monitoring=enabled --overwrite
    
    log "✅ 네임스페이스 생성 완료"
}

# Prometheus Operator 설치 (Helm 사용 시)
install_prometheus_operator() {
    if [ "$HELM_AVAILABLE" = true ]; then
        log "📊 Prometheus Operator 설치 중..."
        
        # Prometheus Community Helm 저장소 추가
        helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
        helm repo update
        
        # kube-prometheus-stack 설치
        helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
            --namespace $MONITORING_NAMESPACE \
            --create-namespace \
            --set prometheus.prometheusSpec.serviceMonitorSelectorNilUsesHelmValues=false \
            --set prometheus.prometheusSpec.podMonitorSelectorNilUsesHelmValues=false \
            --set prometheus.prometheusSpec.ruleSelectorNilUsesHelmValues=false \
            --set prometheus.prometheusSpec.retention=15d \
            --set prometheus.prometheusSpec.storageSpec.volumeClaimTemplate.spec.accessModes[0]=ReadWriteOnce \
            --set prometheus.prometheusSpec.storageSpec.volumeClaimTemplate.spec.resources.requests.storage=50Gi \
            --set alertmanager.alertmanagerSpec.storage.volumeClaimTemplate.spec.accessModes[0]=ReadWriteOnce \
            --set alertmanager.alertmanagerSpec.storage.volumeClaimTemplate.spec.resources.requests.storage=5Gi \
            --set grafana.persistence.enabled=true \
            --set grafana.persistence.size=10Gi \
            --set grafana.adminPassword=admin123! \
            --wait
            
        log "✅ Prometheus Operator 설치 완료"
    else
        warn "Helm이 없어 Prometheus Operator를 건너뜁니다."
    fi
}

# 모니터링 스택 배포
deploy_monitoring_stack() {
    log "📈 모니터링 스택 배포 중..."
    
    # AlertManager 배포
    log "🚨 AlertManager 배포 중..."
    kubectl apply -f ../kubernetes/alertmanager-deployment.yaml
    
    # ELK Stack 배포
    log "📝 ELK Stack 배포 중..."
    kubectl apply -f ../kubernetes/elk-stack.yaml
    
    # 모니터링 스택이 이미 있다면 추가로 배포
    if ! helm list -n $MONITORING_NAMESPACE | grep -q kube-prometheus-stack; then
        log "📊 기본 모니터링 스택 배포 중..."
        kubectl apply -f ../kubernetes/monitoring-stack.yaml
    fi
    
    log "✅ 모니터링 스택 배포 완료"
}

# Grafana 대시보드 설정
setup_grafana_dashboards() {
    log "📊 Grafana 대시보드 설정 중..."
    
    # Grafana Pod 대기
    kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=grafana -n $MONITORING_NAMESPACE --timeout=300s
    
    # 대시보드 ConfigMap 생성
    kubectl create configmap grafana-dashboards \
        --from-file=../grafana/dashboards/ \
        -n $MONITORING_NAMESPACE \
        --dry-run=client -o yaml | kubectl apply -f -
    
    # Provisioning 설정
    kubectl create configmap grafana-provisioning \
        --from-file=../grafana/provisioning/ \
        -n $MONITORING_NAMESPACE \
        --dry-run=client -o yaml | kubectl apply -f -
    
    # Grafana 재시작하여 설정 적용
    kubectl rollout restart deployment/grafana -n $MONITORING_NAMESPACE || \
    kubectl rollout restart deployment/kube-prometheus-stack-grafana -n $MONITORING_NAMESPACE
    
    log "✅ Grafana 대시보드 설정 완료"
}

# Prometheus 규칙 설정
setup_prometheus_rules() {
    log "📏 Prometheus 알림 규칙 설정 중..."
    
    # 알림 규칙 ConfigMap 생성
    kubectl create configmap hankook-alert-rules \
        --from-file=../prometheus/alert-rules/ \
        -n $MONITORING_NAMESPACE \
        --dry-run=client -o yaml | kubectl apply -f -
    
    # PrometheusRule CRD 생성 (Operator 사용 시)
    if kubectl get crd prometheusrules.monitoring.coreos.com &> /dev/null; then
        cat <<EOF | kubectl apply -f -
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: hankook-smartsensor-rules
  namespace: $MONITORING_NAMESPACE
  labels:
    app: hankook-smartsensor
    prometheus: kube-prometheus
    role: alert-rules
spec:
$(cat ../prometheus/alert-rules/hankook-sensor-alerts.yml | sed 's/^/  /')
EOF
    fi
    
    log "✅ Prometheus 알림 규칙 설정 완료"
}

# ServiceMonitor 생성 (Prometheus Operator 사용 시)
create_service_monitors() {
    if kubectl get crd servicemonitors.monitoring.coreos.com &> /dev/null; then
        log "🔍 ServiceMonitor 생성 중..."
        
        # HankookTire API ServiceMonitor
        cat <<EOF | kubectl apply -f -
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: hankook-api-monitor
  namespace: $MONITORING_NAMESPACE
  labels:
    app: hankook-smartsensor
spec:
  selector:
    matchLabels:
      app: hankook-api
  namespaceSelector:
    matchNames:
    - $NAMESPACE
  endpoints:
  - port: metrics
    interval: 30s
    path: /metrics
EOF

        # PostgreSQL ServiceMonitor
        cat <<EOF | kubectl apply -f -
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: postgres-monitor
  namespace: $MONITORING_NAMESPACE
  labels:
    app: hankook-smartsensor
spec:
  selector:
    matchLabels:
      app: postgres
  namespaceSelector:
    matchNames:
    - $NAMESPACE
  endpoints:
  - port: metrics
    interval: 30s
    path: /metrics
EOF

        # Redis ServiceMonitor
        cat <<EOF | kubectl apply -f -
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: redis-monitor
  namespace: $MONITORING_NAMESPACE
  labels:
    app: hankook-smartsensor
spec:
  selector:
    matchLabels:
      app: redis
  namespaceSelector:
    matchNames:
    - $NAMESPACE
  endpoints:
  - port: metrics
    interval: 30s
    path: /metrics
EOF

        # MQTT ServiceMonitor
        cat <<EOF | kubectl apply -f -
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: mosquitto-monitor
  namespace: $MONITORING_NAMESPACE
  labels:
    app: hankook-smartsensor
spec:
  selector:
    matchLabels:
      app: mosquitto
  namespaceSelector:
    matchNames:
    - $NAMESPACE
  endpoints:
  - port: metrics
    interval: 30s
    path: /metrics
EOF

        log "✅ ServiceMonitor 생성 완료"
    else
        warn "Prometheus Operator가 없어 ServiceMonitor를 건너뜁니다."
    fi
}

# 헬스체크 스크립트 배포
deploy_health_check() {
    log "🏥 헬스체크 스크립트 배포 중..."
    
    # 헬스체크 ConfigMap 생성
    kubectl create configmap health-check-script \
        --from-file=health-check.py \
        -n $NAMESPACE \
        --dry-run=client -o yaml | kubectl apply -f -
    
    # 헬스체크 CronJob 생성
    cat <<EOF | kubectl apply -f -
apiVersion: batch/v1
kind: CronJob
metadata:
  name: health-check
  namespace: $NAMESPACE
  labels:
    app: hankook-smartsensor
    component: monitoring
spec:
  schedule: "*/5 * * * *"  # 5분마다 실행
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: health-check
            image: python:3.11-slim
            command:
            - /bin/bash
            - -c
            - |
              pip install asyncio aiohttp psycopg2-binary redis
              python /scripts/health-check.py
            env:
            - name: POSTGRES_HOST
              value: "postgres-service"
            - name: POSTGRES_USER
              value: "hankook"
            - name: POSTGRES_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: database-credentials
                  key: password
            - name: REDIS_HOST
              value: "redis-service"
            - name: REDIS_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: redis-credentials
                  key: password
            - name: API_BASE_URL
              value: "http://api-service:8000"
            - name: SLACK_WEBHOOK_URL
              valueFrom:
                secretKeyRef:
                  name: alertmanager-secrets
                  key: slack-webhook
                  optional: true
            volumeMounts:
            - name: scripts
              mountPath: /scripts
            - name: logs
              mountPath: /var/log
          volumes:
          - name: scripts
            configMap:
              name: health-check-script
              defaultMode: 0755
          - name: logs
            emptyDir: {}
          restartPolicy: OnFailure
EOF

    log "✅ 헬스체크 스크립트 배포 완료"
}

# 로그 수집 설정
setup_log_collection() {
    log "📝 로그 수집 설정 중..."
    
    # Fluentd DaemonSet (Filebeat 대신 사용 가능)
    if [ "${USE_FLUENTD:-false}" = "true" ]; then
        log "🔄 Fluentd 로그 수집기 설정 중..."
        
        # Fluentd ConfigMap
        cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: ConfigMap
metadata:
  name: fluentd-config
  namespace: $NAMESPACE
data:
  fluent.conf: |
    <source>
      @type tail
      path /var/log/containers/hankook-*.log
      pos_file /var/log/fluentd-containers.log.pos
      tag kubernetes.*
      format json
      read_from_head true
    </source>
    
    <filter kubernetes.**>
      @type kubernetes_metadata
    </filter>
    
    <match kubernetes.**>
      @type elasticsearch
      host elasticsearch-service
      port 9200
      logstash_format true
      logstash_prefix hankook-smartsensor
    </match>
EOF

        # Fluentd DaemonSet
        cat <<EOF | kubectl apply -f -
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: fluentd
  namespace: $NAMESPACE
spec:
  selector:
    matchLabels:
      app: fluentd
  template:
    metadata:
      labels:
        app: fluentd
    spec:
      containers:
      - name: fluentd
        image: fluent/fluentd-kubernetes-daemonset:v1-debian-elasticsearch
        env:
        - name: FLUENT_ELASTICSEARCH_HOST
          value: "elasticsearch-service"
        - name: FLUENT_ELASTICSEARCH_PORT
          value: "9200"
        volumeMounts:
        - name: varlog
          mountPath: /var/log
        - name: varlibdockercontainers
          mountPath: /var/lib/docker/containers
          readOnly: true
        - name: config
          mountPath: /fluentd/etc/fluent.conf
          subPath: fluent.conf
      volumes:
      - name: varlog
        hostPath:
          path: /var/log
      - name: varlibdockercontainers
        hostPath:
          path: /var/lib/docker/containers
      - name: config
        configMap:
          name: fluentd-config
EOF
    fi
    
    log "✅ 로그 수집 설정 완료"
}

# 네트워크 정책 설정
setup_network_policies() {
    log "🔒 네트워크 정책 설정 중..."
    
    # 모니터링 네트워크 정책
    cat <<EOF | kubectl apply -f -
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: monitoring-network-policy
  namespace: $MONITORING_NAMESPACE
spec:
  podSelector: {}
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          name: $NAMESPACE
    - namespaceSelector:
        matchLabels:
          name: ingress-nginx
  - ports:
    - protocol: TCP
      port: 9090  # Prometheus
    - protocol: TCP
      port: 3000  # Grafana
    - protocol: TCP
      port: 9093  # AlertManager
  egress:
  - {} # 모든 외부 연결 허용 (DNS, 외부 알림 등)
EOF

    log "✅ 네트워크 정책 설정 완료"
}

# Ingress 설정 업데이트
update_ingress() {
    log "🌐 Ingress 설정 업데이트 중..."
    
    # 모니터링 도메인을 기존 Ingress에 추가
    kubectl patch ingress hankook-smartsensor-ingress -n $NAMESPACE --type='json' -p='[
      {
        "op": "add",
        "path": "/spec/rules/-",
        "value": {
          "host": "monitoring.hankook-smartsensor.com",
          "http": {
            "paths": [
              {
                "path": "/prometheus",
                "pathType": "Prefix",
                "backend": {
                  "service": {
                    "name": "prometheus-service",
                    "port": {
                      "number": 9090
                    }
                  }
                }
              },
              {
                "path": "/grafana",
                "pathType": "Prefix",
                "backend": {
                  "service": {
                    "name": "grafana-service",
                    "port": {
                      "number": 3000
                    }
                  }
                }
              },
              {
                "path": "/alertmanager",
                "pathType": "Prefix",
                "backend": {
                  "service": {
                    "name": "alertmanager-service",
                    "port": {
                      "number": 9093
                    }
                  }
                }
              },
              {
                "path": "/kibana",
                "pathType": "Prefix",
                "backend": {
                  "service": {
                    "name": "kibana-service",
                    "port": {
                      "number": 5601
                    }
                  }
                }
              }
            ]
          }
        }
      }
    ]' || warn "Ingress 업데이트 실패 - 수동으로 확인하세요."
    
    log "✅ Ingress 설정 업데이트 완료"
}

# 상태 확인
check_deployment_status() {
    log "✅ 배포 상태 확인 중..."
    
    info "네임스페이스 상태:"
    kubectl get namespaces | grep -E "$NAMESPACE|$MONITORING_NAMESPACE"
    
    info "모니터링 Pod 상태:"
    kubectl get pods -n $MONITORING_NAMESPACE
    
    info "서비스 상태:"
    kubectl get svc -n $MONITORING_NAMESPACE
    
    info "Ingress 상태:"
    kubectl get ingress -n $NAMESPACE
    
    # 포트포워딩 정보 제공
    echo ""
    info "🌐 모니터링 시스템 접속 정보:"
    echo "  Grafana:      kubectl port-forward -n $MONITORING_NAMESPACE svc/grafana-service 3000:3000"
    echo "               브라우저에서 http://localhost:3000 접속 (admin/admin123!)"
    echo ""
    echo "  Prometheus:   kubectl port-forward -n $MONITORING_NAMESPACE svc/prometheus-service 9090:9090"
    echo "               브라우저에서 http://localhost:9090 접속"
    echo ""
    echo "  AlertManager: kubectl port-forward -n $MONITORING_NAMESPACE svc/alertmanager-service 9093:9093"
    echo "               브라우저에서 http://localhost:9093 접속"
    echo ""
    echo "  Kibana:       kubectl port-forward -n $NAMESPACE svc/kibana-service 5601:5601"
    echo "               브라우저에서 http://localhost:5601 접속"
}

# 정리 함수
cleanup() {
    log "🧹 정리 작업 중..."
    # 필요시 정리 작업 수행
}

# 메인 실행 함수
main() {
    log "🎯 HankookTire SmartSensor 2.0 모니터링 시스템 설정 시작"
    
    # 단계별 실행
    check_prerequisites
    create_namespaces
    install_prometheus_operator
    deploy_monitoring_stack
    setup_prometheus_rules
    create_service_monitors
    setup_grafana_dashboards
    deploy_health_check
    setup_log_collection
    setup_network_policies
    update_ingress
    
    # 배포 완료 대기
    log "⏳ 서비스 준비 상태 대기 중..."
    kubectl wait --for=condition=ready pod -l app=prometheus -n $MONITORING_NAMESPACE --timeout=300s || warn "Prometheus 준비 시간 초과"
    kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=grafana -n $MONITORING_NAMESPACE --timeout=300s || warn "Grafana 준비 시간 초과"
    
    check_deployment_status
    
    log "🎉 HankookTire SmartSensor 2.0 모니터링 시스템 설정 완료!"
    
    # 성공 메시지
    echo ""
    echo "======================================================="
    echo "🚀 HankookTire SmartSensor 2.0 모니터링 시스템 준비 완료!"
    echo "======================================================="
    echo ""
    echo "📊 Grafana Dashboard: https://monitoring.hankook-smartsensor.com/grafana"
    echo "📈 Prometheus Metrics: https://monitoring.hankook-smartsensor.com/prometheus"
    echo "🚨 AlertManager: https://monitoring.hankook-smartsensor.com/alertmanager"
    echo "📝 Kibana Logs: https://monitoring.hankook-smartsensor.com/kibana"
    echo ""
    echo "🔐 기본 로그인 정보:"
    echo "  Grafana: admin / admin123!"
    echo ""
    echo "⚡ 다음 단계:"
    echo "  1. Grafana에서 데이터소스 확인"
    echo "  2. 대시보드 커스터마이징"
    echo "  3. 알림 채널 설정 (Slack, Email)"
    echo "  4. 백업 및 보안 설정"
    echo ""
}

# 에러 처리
trap cleanup EXIT
trap 'error "스크립트 실행 중 오류 발생"; exit 1' ERR

# 메인 함수 실행
main "$@"