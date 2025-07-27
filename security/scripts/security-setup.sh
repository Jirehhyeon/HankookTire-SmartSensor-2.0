#!/bin/bash

# HankookTire SmartSensor 2.0 - Security System Setup Script
# 차세대 통합 스마트 타이어 센서 시스템 보안 시스템 구축

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
log "🔐 HankookTire SmartSensor 2.0 보안 시스템 설정 시작"

# 환경 변수 설정
NAMESPACE=${NAMESPACE:-"hankook-smartsensor"}
SECURITY_NAMESPACE=${SECURITY_NAMESPACE:-"hankook-security"}
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
    
    # OpenSSL 확인
    if ! command -v openssl &> /dev/null; then
        error "OpenSSL이 설치되어 있지 않습니다."
        exit 1
    fi
    
    log "✅ 사전 요구사항 확인 완료"
}

# 네임스페이스 생성
create_namespaces() {
    log "📁 보안 네임스페이스 생성 중..."
    
    # 보안 네임스페이스 생성
    kubectl create namespace $SECURITY_NAMESPACE --dry-run=client -o yaml | kubectl apply -f -
    
    # 레이블 추가
    kubectl label namespace $SECURITY_NAMESPACE security.hankook.io/managed=true --overwrite
    kubectl label namespace $SECURITY_NAMESPACE security.hankook.io/classification=restricted --overwrite
    kubectl label namespace $NAMESPACE monitoring=enabled --overwrite
    
    log "✅ 보안 네임스페이스 생성 완료"
}

# 보안 시크릿 생성
generate_security_secrets() {
    log "🔑 보안 시크릿 생성 중..."
    
    # JWT 시크릿 키 생성
    JWT_SECRET=$(openssl rand -hex 32)
    kubectl create secret generic jwt-secrets \
        --from-literal=secret-key="$JWT_SECRET" \
        -n $SECURITY_NAMESPACE \
        --dry-run=client -o yaml | kubectl apply -f -
    
    # 마스터 암호화 키 생성
    MASTER_KEY=$(openssl rand -hex 32)
    kubectl create secret generic crypto-secrets \
        --from-literal=master-key="$MASTER_KEY" \
        -n $SECURITY_NAMESPACE \
        --dry-run=client -o yaml | kubectl apply -f -
    
    # API 키 생성
    API_KEY=$(openssl rand -base64 32)
    kubectl create secret generic api-secrets \
        --from-literal=api-key="$API_KEY" \
        -n $SECURITY_NAMESPACE \
        --dry-run=client -o yaml | kubectl apply -f -
    
    # TLS 인증서 생성
    generate_tls_certificates
    
    log "✅ 보안 시크릿 생성 완료"
}

# TLS 인증서 생성
generate_tls_certificates() {
    log "📜 TLS 인증서 생성 중..."
    
    # 임시 디렉토리 생성
    CERT_DIR=$(mktemp -d)
    cd "$CERT_DIR"
    
    # CA 개인키 생성
    openssl genrsa -out ca-key.pem 4096
    
    # CA 인증서 생성
    openssl req -new -x509 -days 3650 -key ca-key.pem -out ca-cert.pem -subj "/C=KR/ST=Seoul/L=Seoul/O=HankookTire/OU=SmartSensor/CN=HankookTire-CA"
    
    # 서버 개인키 생성
    openssl genrsa -out server-key.pem 4096
    
    # 서버 인증서 요청 생성
    openssl req -new -key server-key.pem -out server.csr -subj "/C=KR/ST=Seoul/L=Seoul/O=HankookTire/OU=SmartSensor/CN=hankook-smartsensor.com"
    
    # 서버 인증서 생성
    cat > server-ext.cnf <<EOF
authorityKeyIdentifier=keyid,issuer
basicConstraints=CA:FALSE
keyUsage = digitalSignature, nonRepudiation, keyEncipherment, dataEncipherment
subjectAltName = @alt_names

[alt_names]
DNS.1 = hankook-smartsensor.com
DNS.2 = *.hankook-smartsensor.com
DNS.3 = oauth2-service.hankook-security.svc.cluster.local
DNS.4 = crypto-service.hankook-security.svc.cluster.local
DNS.5 = network-security-service.hankook-security.svc.cluster.local
IP.1 = 127.0.0.1
EOF
    
    openssl x509 -req -days 365 -in server.csr -CA ca-cert.pem -CAkey ca-key.pem -CAcreateserial -out server-cert.pem -extensions v3_req -extfile server-ext.cnf
    
    # 인증서를 시크릿으로 저장
    kubectl create secret tls tls-certificates \
        --cert=server-cert.pem \
        --key=server-key.pem \
        -n $SECURITY_NAMESPACE \
        --dry-run=client -o yaml | kubectl apply -f -
    
    # CA 인증서 시크릿 저장
    kubectl create secret generic ca-certificates \
        --from-file=ca-cert.pem \
        -n $SECURITY_NAMESPACE \
        --dry-run=client -o yaml | kubectl apply -f -
    
    # 임시 파일 삭제
    cd -
    rm -rf "$CERT_DIR"
    
    log "✅ TLS 인증서 생성 완료"
}

# GeoIP 데이터베이스 다운로드
download_geoip_database() {
    log "🌍 GeoIP 데이터베이스 다운로드 중..."
    
    # GeoLite2 데이터베이스 다운로드 (무료 버전)
    GEOIP_URL="https://github.com/P3TERX/GeoLite.mmdb/raw/download/GeoLite2-Country.mmdb"
    GEOIP_FILE=$(mktemp)
    
    if curl -L -o "$GEOIP_FILE" "$GEOIP_URL" 2>/dev/null; then
        # ConfigMap으로 저장
        kubectl create configmap geoip-database \
            --from-file=GeoLite2-Country.mmdb="$GEOIP_FILE" \
            -n $SECURITY_NAMESPACE \
            --dry-run=client -o yaml | kubectl apply -f -
        
        rm -f "$GEOIP_FILE"
        log "✅ GeoIP 데이터베이스 다운로드 완료"
    else
        warn "GeoIP 데이터베이스 다운로드 실패. 기본 설정으로 계속합니다."
        # 빈 ConfigMap 생성
        kubectl create configmap geoip-database \
            --from-literal=placeholder="no-geoip-data" \
            -n $SECURITY_NAMESPACE \
            --dry-run=client -o yaml | kubectl apply -f -
    fi
}

# 보안 스택 배포
deploy_security_stack() {
    log "🛡️ 보안 스택 배포 중..."
    
    # 보안 스택 배포
    kubectl apply -f ../deployment/security-stack.yaml
    
    # 배포 상태 확인
    log "⏳ 보안 서비스 준비 상태 대기 중..."
    
    # OAuth2 Server 대기
    kubectl wait --for=condition=available deployment/oauth2-server -n $SECURITY_NAMESPACE --timeout=300s || warn "OAuth2 Server 준비 시간 초과"
    
    # Network Security Manager 대기
    kubectl wait --for=condition=available deployment/network-security-manager -n $SECURITY_NAMESPACE --timeout=300s || warn "Network Security Manager 준비 시간 초과"
    
    # Crypto Manager 대기
    kubectl wait --for=condition=available deployment/crypto-manager -n $SECURITY_NAMESPACE --timeout=300s || warn "Crypto Manager 준비 시간 초과"
    
    log "✅ 보안 스택 배포 완료"
}

# 보안 정책 설정
setup_security_policies() {
    log "📜 보안 정책 설정 중..."
    
    # Pod Security Policy 설정
    cat <<EOF | kubectl apply -f -
apiVersion: policy/v1beta1
kind: PodSecurityPolicy
metadata:
  name: hankook-security-psp
  namespace: $SECURITY_NAMESPACE
spec:
  privileged: false
  allowPrivilegeEscalation: false
  requiredDropCapabilities:
    - ALL
  volumes:
    - 'configMap'
    - 'emptyDir'
    - 'projected'
    - 'secret'
    - 'downwardAPI'
    - 'persistentVolumeClaim'
  runAsUser:
    rule: 'MustRunAsNonRoot'
  seLinux:
    rule: 'RunAsAny'
  fsGroup:
    rule: 'RunAsAny'
  readOnlyRootFilesystem: false
EOF

    # Security Context Constraints (OpenShift)
    if kubectl api-resources | grep -q securitycontextconstraints; then
        cat <<EOF | kubectl apply -f -
apiVersion: security.openshift.io/v1
kind: SecurityContextConstraints
metadata:
  name: hankook-security-scc
allowHostDirVolumePlugin: false
allowHostIPC: false
allowHostNetwork: false
allowHostPID: false
allowHostPorts: false
allowPrivilegedContainer: false
allowedCapabilities: null
defaultAddCapabilities: null
requiredDropCapabilities:
- KILL
- MKNOD
- SETUID
- SETGID
runAsUser:
  type: MustRunAsNonRoot
seLinuxContext:
  type: MustRunAs
volumes:
- configMap
- downwardAPI
- emptyDir
- persistentVolumeClaim
- projected
- secret
EOF
    fi
    
    log "✅ 보안 정책 설정 완료"
}

# RBAC 설정
setup_rbac() {
    log "👥 RBAC 설정 중..."
    
    # Security Admin Role
    cat <<EOF | kubectl apply -f -
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: hankook-security-admin
rules:
- apiGroups: [""]
  resources: ["secrets", "configmaps"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
- apiGroups: ["apps"]
  resources: ["deployments", "replicasets"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
- apiGroups: ["networking.k8s.io"]
  resources: ["networkpolicies"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
- apiGroups: ["policy"]
  resources: ["podsecuritypolicies"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: hankook-security-admin-binding
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: hankook-security-admin
subjects:
- kind: ServiceAccount
  name: oauth2-server
  namespace: $SECURITY_NAMESPACE
- kind: ServiceAccount
  name: network-security-manager
  namespace: $SECURITY_NAMESPACE
- kind: ServiceAccount
  name: crypto-manager
  namespace: $SECURITY_NAMESPACE
EOF

    log "✅ RBAC 설정 완료"
}

# 모니터링 연동
setup_monitoring_integration() {
    log "📊 모니터링 연동 설정 중..."
    
    # ServiceMonitor 생성 (Prometheus Operator 사용 시)
    if kubectl get crd servicemonitors.monitoring.coreos.com &> /dev/null; then
        cat <<EOF | kubectl apply -f -
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: hankook-security-monitor
  namespace: monitoring
  labels:
    app: hankook-security
spec:
  selector:
    matchLabels:
      component: authentication
  namespaceSelector:
    matchNames:
    - $SECURITY_NAMESPACE
  endpoints:
  - port: metrics
    interval: 30s
    path: /metrics
---
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: hankook-network-security-monitor
  namespace: monitoring
  labels:
    app: hankook-network-security
spec:
  selector:
    matchLabels:
      component: network-security
  namespaceSelector:
    matchNames:
    - $SECURITY_NAMESPACE
  endpoints:
  - port: metrics
    interval: 30s
    path: /metrics
---
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: hankook-crypto-monitor
  namespace: monitoring
  labels:
    app: hankook-crypto
spec:
  selector:
    matchLabels:
      component: encryption
  namespaceSelector:
    matchNames:
    - $SECURITY_NAMESPACE
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

# 보안 알림 규칙 설정
setup_security_alerts() {
    log "🚨 보안 알림 규칙 설정 중..."
    
    # Prometheus 알림 규칙 생성
    if kubectl get crd prometheusrules.monitoring.coreos.com &> /dev/null; then
        cat <<EOF | kubectl apply -f -
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: hankook-security-alerts
  namespace: monitoring
  labels:
    app: hankook-security
    prometheus: kube-prometheus
    role: alert-rules
spec:
  groups:
  - name: hankook_security_alerts
    interval: 30s
    rules:
    
    # 인증 실패 알림
    - alert: HighAuthenticationFailureRate
      expr: rate(authentication_failures_total[5m]) > 10
      for: 2m
      labels:
        severity: warning
        service: authentication
        team: security
      annotations:
        summary: "높은 인증 실패율 감지"
        description: "지난 5분간 인증 실패율이 {{ \$value }}회/초를 초과했습니다."
        
    # 차단된 IP 증가
    - alert: HighBlockedIPRate
      expr: rate(blocked_ips_total[5m]) > 5
      for: 1m
      labels:
        severity: critical
        service: network-security
        team: security
      annotations:
        summary: "차단된 IP 급증"
        description: "지난 5분간 {{ \$value }}개의 IP가 차단되었습니다."
        
    # 암호화 오류 증가
    - alert: CryptographicErrors
      expr: rate(crypto_errors_total[5m]) > 1
      for: 1m
      labels:
        severity: critical
        service: encryption
        team: security
      annotations:
        summary: "암호화 오류 발생"
        description: "지난 5분간 {{ \$value }}개의 암호화 오류가 발생했습니다."
        
    # 보안 서비스 다운
    - alert: SecurityServiceDown
      expr: up{job=~".*security.*"} == 0
      for: 1m
      labels:
        severity: critical
        service: security
        team: platform
      annotations:
        summary: "보안 서비스 다운"
        description: "보안 서비스 {{ \$labels.instance }}가 다운되었습니다."
        
    # DDoS 공격 감지
    - alert: DDoSAttackDetected
      expr: rate(http_requests_total[1m]) > 1000
      for: 30s
      labels:
        severity: critical
        service: network-security
        team: security
      annotations:
        summary: "DDoS 공격 감지"
        description: "비정상적으로 높은 요청율 감지: {{ \$value }}req/sec"
EOF

        log "✅ 보안 알림 규칙 설정 완료"
    else
        warn "Prometheus Operator가 없어 알림 규칙을 건너뜁니다."
    fi
}

# Ingress 업데이트
update_ingress() {
    log "🌐 Ingress 보안 설정 업데이트 중..."
    
    # 보안 서비스를 기존 Ingress에 추가
    kubectl patch ingress hankook-smartsensor-ingress -n $NAMESPACE --type='json' -p='[
      {
        "op": "add",
        "path": "/spec/rules/-",
        "value": {
          "host": "security.hankook-smartsensor.com",
          "http": {
            "paths": [
              {
                "path": "/auth",
                "pathType": "Prefix",
                "backend": {
                  "service": {
                    "name": "oauth2-service",
                    "port": {
                      "number": 8001
                    }
                  }
                }
              },
              {
                "path": "/security",
                "pathType": "Prefix",
                "backend": {
                  "service": {
                    "name": "network-security-service",
                    "port": {
                      "number": 8003
                    }
                  }
                }
              },
              {
                "path": "/crypto",
                "pathType": "Prefix",
                "backend": {
                  "service": {
                    "name": "crypto-service",
                    "port": {
                      "number": 8005
                    }
                  }
                }
              }
            ]
          }
        }
      }
    ]' || warn "Ingress 업데이트 실패 - 수동으로 확인하세요."
    
    log "✅ Ingress 보안 설정 업데이트 완료"
}

# 보안 테스트 실행
run_security_tests() {
    log "🧪 보안 테스트 실행 중..."
    
    # 인증 서비스 테스트
    info "OAuth2 서비스 테스트 중..."
    kubectl run security-test --rm -i --restart=Never --image=curlimages/curl -- \
        curl -f http://oauth2-service.hankook-security.svc.cluster.local:8001/health || warn "OAuth2 서비스 테스트 실패"
    
    # 네트워크 보안 서비스 테스트
    info "네트워크 보안 서비스 테스트 중..."
    kubectl run security-test --rm -i --restart=Never --image=curlimages/curl -- \
        curl -f http://network-security-service.hankook-security.svc.cluster.local:8003/health || warn "네트워크 보안 서비스 테스트 실패"
    
    # 암호화 서비스 테스트
    info "암호화 서비스 테스트 중..."
    kubectl run security-test --rm -i --restart=Never --image=curlimages/curl -- \
        curl -f http://crypto-service.hankook-security.svc.cluster.local:8005/health || warn "암호화 서비스 테스트 실패"
    
    log "✅ 보안 테스트 완료"
}

# 상태 확인
check_deployment_status() {
    log "✅ 보안 시스템 배포 상태 확인 중..."
    
    info "네임스페이스 상태:"
    kubectl get namespaces | grep -E "$NAMESPACE|$SECURITY_NAMESPACE"
    
    info "보안 Pod 상태:"
    kubectl get pods -n $SECURITY_NAMESPACE
    
    info "보안 서비스 상태:"
    kubectl get svc -n $SECURITY_NAMESPACE
    
    info "시크릿 상태:"
    kubectl get secrets -n $SECURITY_NAMESPACE
    
    info "Ingress 상태:"
    kubectl get ingress -n $NAMESPACE
    
    # 포트포워딩 정보 제공
    echo ""
    info "🔐 보안 시스템 접속 정보:"
    echo "  OAuth2 Server:    kubectl port-forward -n $SECURITY_NAMESPACE svc/oauth2-service 8001:8001"
    echo "                   브라우저에서 http://localhost:8001/health 접속"
    echo ""
    echo "  Network Security: kubectl port-forward -n $SECURITY_NAMESPACE svc/network-security-service 8003:8003"
    echo "                   브라우저에서 http://localhost:8003/health 접속"
    echo ""
    echo "  Crypto Manager:   kubectl port-forward -n $SECURITY_NAMESPACE svc/crypto-service 8005:8005"
    echo "                   브라우저에서 http://localhost:8005/health 접속"
}

# 정리 함수
cleanup() {
    log "🧹 정리 작업 중..."
    # 필요시 정리 작업 수행
}

# 메인 실행 함수
main() {
    log "🎯 HankookTire SmartSensor 2.0 보안 시스템 설정 시작"
    
    # 단계별 실행
    check_prerequisites
    create_namespaces
    generate_security_secrets
    download_geoip_database
    deploy_security_stack
    setup_security_policies
    setup_rbac
    setup_monitoring_integration
    setup_security_alerts
    update_ingress
    run_security_tests
    
    # 배포 완료 대기
    log "⏳ 보안 서비스 안정화 대기 중..."
    sleep 30
    
    check_deployment_status
    
    log "🎉 HankookTire SmartSensor 2.0 보안 시스템 설정 완료!"
    
    # 성공 메시지
    echo ""
    echo "======================================================="
    echo "🔐 HankookTire SmartSensor 2.0 보안 시스템 준비 완료!"
    echo "======================================================="
    echo ""
    echo "🔒 OAuth2 Authentication: https://security.hankook-smartsensor.com/auth"
    echo "🛡️ Network Security: https://security.hankook-smartsensor.com/security"
    echo "🔐 Cryptographic Services: https://security.hankook-smartsensor.com/crypto"
    echo ""
    echo "🔑 보안 기능:"
    echo "  ✅ JWT 기반 인증/인가"
    echo "  ✅ 역할 기반 접근 제어 (RBAC)"
    echo "  ✅ AES-256 데이터 암호화"
    echo "  ✅ 네트워크 방화벽 및 침입 탐지"
    echo "  ✅ 지역별 접근 제어"
    echo "  ✅ DDoS 방어"
    echo "  ✅ API 속도 제한"
    echo "  ✅ 실시간 위협 탐지"
    echo ""
    echo "⚡ 다음 단계:"
    echo "  1. 사용자 계정 생성 및 역할 할당"
    echo "  2. API 키 발급 및 관리"
    echo "  3. 방화벽 규칙 세부 조정"
    echo "  4. 보안 알림 채널 설정"
    echo "  5. 정기 보안 감사 수행"
    echo ""
}

# 에러 처리
trap cleanup EXIT
trap 'error "스크립트 실행 중 오류 발생"; exit 1' ERR

# 메인 함수 실행
main "$@"