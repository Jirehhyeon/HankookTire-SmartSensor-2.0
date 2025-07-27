# 🛠️ 설치 가이드

**SmartTire SmartSensor 2.0 시스템 설치 및 구성**

이 가이드는 SmartTire SmartSensor 2.0 시스템의 완전한 설치 및 구성 과정을 안내합니다.

---

## 📋 목차

1. [사전 요구사항](#-사전-요구사항)
2. [시스템 아키텍처](#-시스템-아키텍처)
3. [설치 계획](#-설치-계획)
4. [기본 설치](#-기본-설치)
5. [고급 설치](#-고급-설치)
6. [설정 및 구성](#-설정-및-구성)
7. [검증 및 테스트](#-검증-및-테스트)
8. [문제 해결](#-문제-해결)

## 🔧 사전 요구사항

### 하드웨어 요구사항

#### 최소 요구사항
```
Kubernetes 클러스터:
├── 마스터 노드: 3개
│   ├── CPU: 4 코어
│   ├── RAM: 8GB
│   └── 디스크: 100GB SSD
├── 워커 노드: 3개 이상
│   ├── CPU: 8 코어
│   ├── RAM: 16GB
│   └── 디스크: 200GB SSD
└── 네트워크: 1Gbps 이상
```

#### 권장 요구사항 (프로덕션)
```
Kubernetes 클러스터:
├── 마스터 노드: 3개
│   ├── CPU: 8 코어
│   ├── RAM: 32GB
│   └── 디스크: 500GB NVMe SSD
├── 워커 노드: 5개 이상
│   ├── CPU: 16 코어
│   ├── RAM: 64GB
│   └── 디스크: 1TB NVMe SSD
├── 스토리지: 고가용성 분산 스토리지
└── 네트워크: 10Gbps 이상
```

### 소프트웨어 요구사항

#### 필수 소프트웨어
```yaml
운영체제:
  - Ubuntu 20.04 LTS 이상
  - CentOS 8 이상
  - RHEL 8 이상

Kubernetes:
  - 버전: 1.20 이상
  - 컨테이너 런타임: Docker 20.10+ 또는 containerd 1.4+
  - CNI 플러그인: Calico, Flannel, 또는 Weave

추가 도구:
  - kubectl: 최신 버전
  - Helm: 3.7 이상
  - Docker: 20.10 이상
  - Git: 2.0 이상
```

#### 선택적 소프트웨어
```yaml
모니터링 도구:
  - Prometheus Operator (권장)
  - Grafana
  - AlertManager

CI/CD 도구:
  - Jenkins 또는 GitLab CI
  - ArgoCD (GitOps)
  - Harbor (이미지 레지스트리)

보안 도구:
  - Falco (런타임 보안)
  - OPA Gatekeeper (정책 관리)
  - Cert-manager (인증서 관리)
```

### 네트워크 요구사항

#### 포트 구성
```yaml
인바운드 포트:
  - 80/tcp: HTTP 웹 인터페이스
  - 443/tcp: HTTPS 웹 인터페이스
  - 1883/tcp: MQTT 브로커
  - 8883/tcp: MQTT over TLS
  - 9090/tcp: Prometheus (옵션)
  - 3000/tcp: Grafana (옵션)

클러스터 내부 포트:
  - 6443/tcp: Kubernetes API 서버
  - 2379-2380/tcp: etcd
  - 10250/tcp: kubelet API
  - 10251/tcp: kube-scheduler
  - 10252/tcp: kube-controller-manager
```

#### DNS 요구사항
```yaml
내부 DNS:
  - cluster.local: Kubernetes 클러스터 DNS
  - *.hankook-smartsensor.svc.cluster.local

외부 DNS:
  - hankook-smartsensor.com
  - api.hankook-smartsensor.com
  - mqtt.hankook-smartsensor.com
  - monitoring.hankook-smartsensor.com
```

## 🏗️ 시스템 아키텍처

### 컴포넌트 배치도

```
┌─────────────────────────────────────────────────────────────┐
│                    Internet Gateway                        │
├─────────────────────────────────────────────────────────────┤
│                    Load Balancer                           │
├─────────────────┬─────────────────┬─────────────────────────┤
│   Web Tier      │   Application   │    Data Tier           │
│                 │   Tier          │                        │
│ ┌─────────────┐ │ ┌─────────────┐ │ ┌─────────────────────┐ │
│ │ Nginx       │ │ │ API Gateway │ │ │ PostgreSQL Cluster  │ │
│ │ Ingress     │ │ │             │ │ │ - Primary           │ │
│ │ Controller  │ │ │ ┌─────────┐ │ │ │ - Secondary         │ │
│ └─────────────┘ │ │ │ API     │ │ │ │ - Read Replicas     │ │
│                 │ │ │ Server  │ │ │ └─────────────────────┘ │
│ ┌─────────────┐ │ │ └─────────┘ │ │                        │
│ │ Web         │ │ │             │ │ ┌─────────────────────┐ │
│ │ Dashboard   │ │ │ ┌─────────┐ │ │ │ Redis Cluster       │ │
│ └─────────────┘ │ │ │ MQTT    │ │ │ │ - Master            │ │
│                 │ │ │ Broker  │ │ │ │ - Slaves            │ │
│                 │ │ └─────────┘ │ │ │ - Sentinel          │ │
│                 │ │             │ │ └─────────────────────┘ │
├─────────────────┼─────────────────┼─────────────────────────┤
│   Security      │   Analytics     │    Monitoring          │
│                 │                 │                        │
│ ┌─────────────┐ │ ┌─────────────┐ │ ┌─────────────────────┐ │
│ │ OAuth2      │ │ │ AI/ML       │ │ │ Prometheus          │ │
│ │ Server      │ │ │ Engine      │ │ │ - Server            │ │
│ └─────────────┘ │ └─────────────┘ │ │ - AlertManager      │ │
│                 │                 │ │ - Node Exporter     │ │
│ ┌─────────────┐ │ ┌─────────────┐ │ └─────────────────────┘ │
│ │ Crypto      │ │ │ Stream      │ │                        │
│ │ Manager     │ │ │ Processing  │ │ ┌─────────────────────┐ │
│ └─────────────┘ │ └─────────────┘ │ │ Grafana             │ │
│                 │                 │ │ - Dashboards        │ │
│ ┌─────────────┐ │                 │ │ - Alerting          │ │
│ │ Network     │ │                 │ └─────────────────────┘ │
│ │ Security    │ │                 │                        │
│ └─────────────┘ │                 │ ┌─────────────────────┐ │
│                 │                 │ │ ELK Stack           │ │
│                 │                 │ │ - Elasticsearch     │ │
│                 │                 │ │ - Logstash          │ │
│                 │                 │ │ - Kibana            │ │
│                 │                 │ └─────────────────────┘ │
└─────────────────┴─────────────────┴─────────────────────────┘
```

### 네임스페이스 구조
```yaml
hankook-smartsensor:     # 주요 애플리케이션
  - api-server
  - web-dashboard
  - sensor-gateway
  - analytics-engine

hankook-security:        # 보안 서비스
  - oauth2-server
  - crypto-manager
  - network-security-manager

monitoring:              # 모니터링 스택
  - prometheus
  - grafana
  - alertmanager
  - elasticsearch
  - logstash
  - kibana

kube-system:            # 시스템 컴포넌트
  - ingress-nginx
  - cert-manager
  - cluster-autoscaler
```

## 📅 설치 계획

### 설치 단계별 계획

#### Phase 1: 기본 인프라 (2-3일)
1. **Kubernetes 클러스터 구축**
2. **네트워킹 및 스토리지 설정**
3. **기본 시스템 컴포넌트 설치**

#### Phase 2: 애플리케이션 배포 (3-4일)
1. **데이터베이스 설치 및 구성**
2. **애플리케이션 서비스 배포**
3. **웹 인터페이스 구성**

#### Phase 3: 보안 시스템 (2-3일)
1. **인증 및 인가 시스템**
2. **암호화 및 키 관리**
3. **네트워크 보안 설정**

#### Phase 4: 모니터링 및 최적화 (2-3일)
1. **모니터링 스택 구축**
2. **알림 시스템 설정**
3. **성능 최적화**

#### Phase 5: 테스트 및 검증 (3-5일)
1. **기능 테스트**
2. **성능 테스트**
3. **보안 테스트**
4. **재해 복구 테스트**

### 롤백 계획
```yaml
체크포인트:
  - checkpoint-1: 기본 인프라 완료
  - checkpoint-2: 애플리케이션 배포 완료
  - checkpoint-3: 보안 시스템 완료
  - checkpoint-4: 모니터링 완료

롤백 절차:
  1. 데이터 백업 확인
  2. 이전 체크포인트로 복원
  3. 서비스 상태 검증
  4. 사용자 접근 복구
```

## 🚀 기본 설치

### 단계 1: 환경 준비

#### Kubernetes 클러스터 확인
```bash
# 클러스터 정보 확인
kubectl cluster-info

# 노드 상태 확인
kubectl get nodes -o wide

# 리소스 사용량 확인
kubectl top nodes
```

#### 네임스페이스 생성
```bash
# 네임스페이스 생성
kubectl create namespace hankook-smartsensor
kubectl create namespace hankook-security
kubectl create namespace monitoring

# 레이블 추가
kubectl label namespace hankook-smartsensor monitoring=enabled
kubectl label namespace hankook-security security=restricted
```

### 단계 2: 저장소 클론 및 설정

```bash
# 프로젝트 클론
git clone https://github.com/hankooktire/smartsensor-2.0.git
cd smartsensor-2.0

# 환경 변수 설정
export NAMESPACE="hankook-smartsensor"
export SECURITY_NAMESPACE="hankook-security"
export MONITORING_NAMESPACE="monitoring"
export CLUSTER_NAME="hankook-production"
export DOMAIN="hankook-smartsensor.com"

# 설정 파일 복사
cp config/env.example config/env.local
```

### 단계 3: 기본 인프라 배포

#### 인프라 설치 스크립트 실행
```bash
cd deployment
chmod +x *.sh

# 기본 인프라 배포
./setup-infrastructure.sh

# 설치 진행 상황 확인
kubectl get pods -A --watch
```

#### 인프라 구성 요소 확인
```bash
# Ingress Controller 확인
kubectl get pods -n ingress-nginx

# 스토리지 클래스 확인
kubectl get storageclass

# 서비스 확인
kubectl get svc -A
```

### 단계 4: 데이터베이스 설치

#### PostgreSQL 클러스터 배포
```bash
# PostgreSQL Operator 설치
kubectl apply -f postgres-operator/

# PostgreSQL 클러스터 생성
kubectl apply -f databases/postgresql-cluster.yaml

# 클러스터 상태 확인
kubectl get postgresql -n hankook-smartsensor
```

#### Redis 클러스터 배포
```bash
# Redis 클러스터 배포
kubectl apply -f databases/redis-cluster.yaml

# Redis 상태 확인
kubectl get pods -n hankook-smartsensor -l app=redis
```

### 단계 5: 애플리케이션 서비스 배포

#### 애플리케이션 스택 배포
```bash
# 애플리케이션 배포
kubectl apply -f applications/

# 배포 상태 확인
kubectl get deployments -n hankook-smartsensor

# 서비스 상태 확인
kubectl get svc -n hankook-smartsensor
```

#### 서비스 준비 상태 대기
```bash
# API 서버 준비 대기
kubectl wait --for=condition=available deployment/api-server -n hankook-smartsensor --timeout=300s

# 웹 대시보드 준비 대기
kubectl wait --for=condition=available deployment/web-dashboard -n hankook-smartsensor --timeout=300s

# 센서 게이트웨이 준비 대기
kubectl wait --for=condition=available deployment/sensor-gateway -n hankook-smartsensor --timeout=300s
```

### 단계 6: 보안 시스템 설치

```bash
cd ../security/scripts

# 보안 시스템 설치
./security-setup.sh

# 보안 서비스 상태 확인
kubectl get pods -n hankook-security
```

### 단계 7: 모니터링 시스템 설치

```bash
cd ../../monitoring/scripts

# 모니터링 시스템 설치
./setup-monitoring.sh

# 모니터링 서비스 상태 확인
kubectl get pods -n monitoring
```

## 🔧 고급 설치

### 고가용성 설정

#### 멀티 마스터 노드 구성
```yaml
# kubeadm-config.yaml
apiVersion: kubeadm.k8s.io/v1beta3
kind: ClusterConfiguration
kubernetesVersion: v1.25.0
controlPlaneEndpoint: "k8s-master-lb.hankook.local:6443"
networking:
  serviceSubnet: "10.96.0.0/12"
  podSubnet: "10.244.0.0/16"
  dnsDomain: "cluster.local"
etcd:
  external:
    endpoints:
    - https://etcd1.hankook.local:2379
    - https://etcd2.hankook.local:2379
    - https://etcd3.hankook.local:2379
```

#### 로드 밸런서 설정
```yaml
# haproxy.cfg
global
    log stdout local0
    daemon

defaults
    mode http
    timeout connect 5000ms
    timeout client 50000ms
    timeout server 50000ms

frontend kubernetes-frontend
    bind *:6443
    mode tcp
    default_backend kubernetes-backend

backend kubernetes-backend
    mode tcp
    balance roundrobin
    server master1 10.0.1.10:6443 check
    server master2 10.0.1.11:6443 check
    server master3 10.0.1.12:6443 check
```

### 스토리지 설정

#### Ceph 클러스터 설치
```bash
# Rook Operator 설치
kubectl apply -f https://raw.githubusercontent.com/rook/rook/release-1.10/deploy/examples/crds.yaml
kubectl apply -f https://raw.githubusercontent.com/rook/rook/release-1.10/deploy/examples/operator.yaml

# Ceph 클러스터 생성
kubectl apply -f storage/ceph-cluster.yaml

# 스토리지 클래스 생성
kubectl apply -f storage/ceph-storageclass.yaml
```

#### NFS 스토리지 설정
```yaml
# nfs-storageclass.yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: nfs-storage
provisioner: kubernetes.io/nfs
parameters:
  server: nfs.hankook.local
  path: /exports/smartsensor
reclaimPolicy: Retain
allowVolumeExpansion: true
```

### 네트워킹 고급 설정

#### Calico 네트워크 정책
```yaml
# network-policy.yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: hankook-smartsensor-policy
  namespace: hankook-smartsensor
spec:
  podSelector: {}
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          name: ingress-nginx
    - namespaceSelector:
        matchLabels:
          name: monitoring
  egress:
  - to:
    - namespaceSelector:
        matchLabels:
          name: hankook-security
    - namespaceSelector:
        matchLabels:
          name: monitoring
  - to: []
    ports:
    - protocol: TCP
      port: 53
    - protocol: UDP
      port: 53
```

### 자동 스케일링 설정

#### Horizontal Pod Autoscaler
```yaml
# api-server-hpa.yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: api-server-hpa
  namespace: hankook-smartsensor
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: api-server
  minReplicas: 3
  maxReplicas: 20
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
```

#### Cluster Autoscaler
```yaml
# cluster-autoscaler.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: cluster-autoscaler
  namespace: kube-system
spec:
  replicas: 1
  selector:
    matchLabels:
      app: cluster-autoscaler
  template:
    metadata:
      labels:
        app: cluster-autoscaler
    spec:
      containers:
      - image: k8s.gcr.io/autoscaling/cluster-autoscaler:v1.25.0
        name: cluster-autoscaler
        command:
        - ./cluster-autoscaler
        - --v=4
        - --stderrthreshold=info
        - --cloud-provider=aws
        - --skip-nodes-with-local-storage=false
        - --expander=least-waste
        - --node-group-auto-discovery=asg:tag=k8s.io/cluster-autoscaler/enabled,k8s.io/cluster-autoscaler/hankook-production
```

## ⚙️ 설정 및 구성

### 애플리케이션 설정

#### API 서버 구성
```yaml
# api-server-config.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: api-server-config
  namespace: hankook-smartsensor
data:
  config.yaml: |
    server:
      port: 8000
      host: "0.0.0.0"
      
    database:
      host: "postgresql-cluster"
      port: 5432
      name: "hankook_sensors"
      user: "api_user"
      
    redis:
      host: "redis-cluster"
      port: 6379
      db: 0
      
    security:
      jwt_secret: "${JWT_SECRET}"
      oauth2_endpoint: "http://oauth2-service.hankook-security.svc.cluster.local:8001"
      
    monitoring:
      prometheus_endpoint: "http://prometheus.monitoring.svc.cluster.local:9090"
      metrics_port: 8080
      
    logging:
      level: "info"
      format: "json"
```

#### MQTT 브로커 구성
```yaml
# mqtt-broker-config.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: mqtt-broker-config
  namespace: hankook-smartsensor
data:
  mosquitto.conf: |
    # Basic Configuration
    port 1883
    listener 8883
    protocol mqtt
    
    # Security
    allow_anonymous false
    password_file /etc/mosquitto/passwords
    acl_file /etc/mosquitto/acl
    
    # Persistence
    persistence true
    persistence_location /mosquitto/data/
    
    # Logging
    log_dest file /mosquitto/log/mosquitto.log
    log_type error
    log_type warning
    log_type notice
    log_type information
    
    # Limits
    max_connections 10000
    max_inflight_messages 100
    max_queued_messages 1000
```

### 데이터베이스 스키마 설정

#### PostgreSQL 초기 스키마
```sql
-- 데이터베이스 생성
CREATE DATABASE hankook_sensors;

-- 사용자 생성
CREATE USER api_user WITH PASSWORD 'secure_password';
CREATE USER readonly_user WITH PASSWORD 'readonly_password';

-- 권한 부여
GRANT CONNECT ON DATABASE hankook_sensors TO api_user;
GRANT CONNECT ON DATABASE hankook_sensors TO readonly_user;

\c hankook_sensors;

-- 스키마 생성
CREATE SCHEMA sensors;
CREATE SCHEMA analytics;
CREATE SCHEMA security;

-- 테이블 생성
CREATE TABLE sensors.vehicles (
    id SERIAL PRIMARY KEY,
    vehicle_id VARCHAR(50) UNIQUE NOT NULL,
    make VARCHAR(50),
    model VARCHAR(50),
    year INTEGER,
    vin VARCHAR(17) UNIQUE,
    registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE sensors.sensor_data (
    id BIGSERIAL PRIMARY KEY,
    vehicle_id VARCHAR(50) REFERENCES sensors.vehicles(vehicle_id),
    sensor_id VARCHAR(50) NOT NULL,
    sensor_type VARCHAR(20) NOT NULL,
    position VARCHAR(20) NOT NULL, -- FL, FR, RL, RR
    value DECIMAL(10,2) NOT NULL,
    unit VARCHAR(10) NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 인덱스 생성
CREATE INDEX idx_sensor_data_vehicle_timestamp ON sensors.sensor_data(vehicle_id, timestamp);
CREATE INDEX idx_sensor_data_sensor_type_timestamp ON sensors.sensor_data(sensor_type, timestamp);
CREATE INDEX idx_sensor_data_timestamp ON sensors.sensor_data(timestamp);

-- 파티셔닝 설정 (월별)
CREATE TABLE sensors.sensor_data_y2024m01 PARTITION OF sensors.sensor_data
FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');
```

### SSL/TLS 인증서 설정

#### Cert-manager 설치
```bash
# Cert-manager 설치
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.10.0/cert-manager.yaml

# ClusterIssuer 생성
kubectl apply -f - <<EOF
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: admin@hankook-smartsensor.com
    privateKeySecretRef:
      name: letsencrypt-prod
    solvers:
    - http01:
        ingress:
          class: nginx
EOF
```

### 백업 및 복구 설정

#### Velero 설치 및 구성
```bash
# Velero 설치
kubectl apply -f https://github.com/vmware-tanzu/velero/releases/download/v1.10.0/velero-v1.10.0-linux-amd64.tar.gz

# 백업 스토리지 설정
velero install \
    --provider aws \
    --plugins velero/velero-plugin-for-aws:v1.6.0 \
    --bucket hankook-smartsensor-backup \
    --secret-file ./credentials-velero \
    --backup-location-config region=ap-northeast-2

# 일일 백업 스케줄 생성
velero create schedule daily-backup --schedule="0 2 * * *" --ttl 720h0m0s
```

## ✅ 검증 및 테스트

### 기능 테스트

#### API 엔드포인트 테스트
```bash
# API 서버 헬스 체크
curl -k https://api.hankook-smartsensor.com/health

# 인증 테스트
curl -X POST https://api.hankook-smartsensor.com/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'

# 센서 데이터 조회 테스트
TOKEN="eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
curl -H "Authorization: Bearer $TOKEN" \
  https://api.hankook-smartsensor.com/api/sensors/data?vehicle_id=HK-2024-001
```

#### 웹 인터페이스 테스트
```bash
# 웹 대시보드 접근 테스트
curl -I https://hankook-smartsensor.com

# JavaScript 로딩 테스트
curl -s https://hankook-smartsensor.com | grep -o '<script[^>]*>' | wc -l

# CSS 로딩 테스트
curl -s https://hankook-smartsensor.com | grep -o '<link[^>]*stylesheet[^>]*>' | wc -l
```

### 성능 테스트

#### 부하 테스트 스크립트
```bash
cd performance/scripts

# 성능 테스트 실행
export CONCURRENT_USERS=100
export TEST_DURATION=300
export API_BASE_URL="https://api.hankook-smartsensor.com"

./performance-suite.sh
```

#### 데이터베이스 성능 테스트
```sql
-- 쿼리 성능 테스트
EXPLAIN ANALYZE SELECT 
    vehicle_id, 
    AVG(value) as avg_pressure,
    COUNT(*) as data_points
FROM sensors.sensor_data 
WHERE sensor_type = 'pressure' 
    AND timestamp >= NOW() - INTERVAL '1 hour'
GROUP BY vehicle_id;

-- 인덱스 효율성 확인
SELECT 
    schemaname,
    tablename,
    indexname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes 
ORDER BY idx_scan DESC;
```

### 보안 테스트

#### 보안 스캔 도구 실행
```bash
# Kubesec 보안 스캔
kubesec scan deployment/applications/api-server.yaml

# Falco 런타임 보안 모니터링
kubectl logs -f -n kube-system -l app=falco

# Pod Security Standards 확인
kubectl get pods -n hankook-smartsensor -o yaml | grep securityContext
```

#### 네트워크 보안 테스트
```bash
# 포트 스캔 테스트
nmap -sS -O target.hankook-smartsensor.com

# SSL/TLS 설정 확인
testssl.sh --quiet --color 3 https://hankook-smartsensor.com

# 방화벽 규칙 테스트
kubectl exec -it network-security-test -- curl -m 5 blocked-site.com
```

### 재해 복구 테스트

#### 장애 시뮬레이션
```bash
# 노드 장애 시뮬레이션
kubectl drain worker-node-1 --ignore-daemonsets --delete-emptydir-data

# Pod 장애 시뮬레이션
kubectl delete pod -n hankook-smartsensor api-server-xxx

# 네트워크 장애 시뮬레이션
kubectl apply -f test/network-partition.yaml
```

#### 백업 복구 테스트
```bash
# 백업 생성 테스트
velero backup create test-backup --include-namespaces hankook-smartsensor

# 복구 테스트
velero restore create test-restore --from-backup test-backup

# 데이터 무결성 확인
kubectl exec -it postgresql-cluster-0 -- psql -U postgres -c "SELECT COUNT(*) FROM sensors.sensor_data;"
```

## 🔧 문제 해결

### 일반적인 설치 문제

#### Pod가 시작되지 않는 경우
```bash
# Pod 상태 확인
kubectl describe pod <pod-name> -n <namespace>

# 로그 확인
kubectl logs <pod-name> -n <namespace>

# 이벤트 확인
kubectl get events -n <namespace> --sort-by=.metadata.creationTimestamp
```

#### 이미지 풀링 실패
```bash
# 이미지 확인
docker pull <image-name>

# 레지스트리 시크릿 확인
kubectl get secrets -n <namespace>

# ImagePullSecrets 설정
kubectl patch serviceaccount default -p '{"imagePullSecrets": [{"name": "regcred"}]}'
```

#### 스토리지 문제
```bash
# PVC 상태 확인
kubectl get pvc -n <namespace>

# StorageClass 확인
kubectl get storageclass

# 볼륨 마운트 문제 확인
kubectl describe pod <pod-name> -n <namespace> | grep -A 10 Volumes
```

### 네트워크 문제

#### 서비스 연결 문제
```bash
# 서비스 엔드포인트 확인
kubectl get endpoints -n <namespace>

# DNS 해결 테스트
kubectl run -it --rm debug --image=busybox --restart=Never -- nslookup <service-name>.<namespace>.svc.cluster.local

# 포트 연결 테스트
kubectl run -it --rm debug --image=busybox --restart=Never -- telnet <service-name> <port>
```

#### Ingress 문제
```bash
# Ingress 상태 확인
kubectl describe ingress -n <namespace>

# Ingress Controller 로그 확인
kubectl logs -n ingress-nginx deployment/ingress-nginx-controller

# SSL 인증서 확인
kubectl describe certificate -n <namespace>
```

### 성능 문제

#### 리소스 부족
```bash
# 노드 리소스 사용량 확인
kubectl top nodes

# Pod 리소스 사용량 확인
kubectl top pods -n <namespace>

# 리소스 제한 조정
kubectl patch deployment <deployment-name> -p '{"spec":{"template":{"spec":{"containers":[{"name":"<container-name>","resources":{"limits":{"memory":"2Gi","cpu":"1000m"}}}]}}}}'
```

#### 데이터베이스 성능 문제
```sql
-- 느린 쿼리 확인
SELECT 
    query,
    calls,
    total_time,
    mean_time
FROM pg_stat_statements 
WHERE total_time > 1000
ORDER BY total_time DESC;

-- 인덱스 미사용 확인
SELECT 
    schemaname,
    tablename,
    seq_scan,
    seq_tup_read,
    idx_scan,
    idx_tup_fetch
FROM pg_stat_user_tables 
WHERE seq_scan > idx_scan 
    AND seq_tup_read > 0;
```

### 보안 문제

#### 인증 실패
```bash
# OAuth2 서버 로그 확인
kubectl logs -n hankook-security deployment/oauth2-server

# JWT 토큰 디코딩
echo "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..." | base64 -d

# 인증서 만료 확인
kubectl get certificates -n <namespace>
```

#### RBAC 권한 문제
```bash
# 권한 확인
kubectl auth can-i <verb> <resource> --as=<user>

# 역할 바인딩 확인
kubectl describe rolebinding -n <namespace>

# 서비스 어카운트 확인
kubectl describe serviceaccount <service-account> -n <namespace>
```

## 📞 지원 및 도움

### 기술 지원 연락처
- **DevOps 팀**: devops@hankook-smartsensor.com
- **보안 팀**: security@hankook-smartsensor.com
- **24/7 지원**: +82-2-1234-5678

### 추가 리소스
- **공식 문서**: https://docs.hankook-smartsensor.com
- **커뮤니티 포럼**: https://forum.hankook-smartsensor.com
- **GitHub 이슈**: https://github.com/hankooktire/smartsensor-2.0/issues

### 교육 및 인증
- **관리자 교육**: 설치 후 필수 교육 과정
- **인증 프로그램**: SmartTire SmartSensor 전문가 인증
- **워크샵**: 정기 기술 워크샵 및 업데이트 세미나

---

**🎉 설치 완료 후 시스템이 정상적으로 작동하는지 확인하고, 추가 구성이나 문제가 있으면 언제든지 연락주세요!**

© 2024 SmartTire SmartSensor 2.0. All rights reserved.