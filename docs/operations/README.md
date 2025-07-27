# 🔧 운영 가이드

**HankookTire SmartSensor 2.0 시스템 운영 및 관리**

이 가이드는 HankookTire SmartSensor 2.0 시스템의 일상적인 운영, 관리, 유지보수 방법을 안내합니다.

---

## 📋 목차

1. [운영 개요](#-운영-개요)
2. [일상 운영 작업](#-일상-운영-작업)
3. [시스템 모니터링](#-시스템-모니터링)
4. [성능 관리](#-성능-관리)
5. [백업 및 복구](#-백업-및-복구)
6. [보안 관리](#-보안-관리)
7. [장애 대응](#-장애-대응)
8. [용량 계획](#-용량-계획)

## 🎯 운영 개요

### 운영 팀 구조

#### 역할 및 책임
```yaml
DevOps 엔지니어:
  - 시스템 모니터링 및 알림 관리
  - 배포 및 릴리즈 관리
  - 인프라 자동화 및 스케일링
  - 성능 최적화

SRE (Site Reliability Engineer):
  - 시스템 신뢰성 및 가용성 관리
  - 장애 대응 및 근본 원인 분석
  - 서비스 레벨 목표(SLO) 관리
  - 재해 복구 계획 수립

보안 엔지니어:
  - 보안 정책 수립 및 시행
  - 취약점 분석 및 보안 패치
  - 접근 제어 및 감사
  - 보안 사고 대응

데이터 엔지니어:
  - 데이터 파이프라인 관리
  - 데이터 품질 및 무결성 보장
  - 백업 및 아카이브 관리
  - 분석 및 리포팅 지원
```

### 운영 시간 및 지원

#### 지원 계층
```yaml
Tier 1 (L1) - 기본 지원:
  - 운영시간: 24/7
  - 대응시간: 15분 이내
  - 담당: 운영 센터
  - 범위: 기본 모니터링, 알림 대응, 초기 문제 분류

Tier 2 (L2) - 기술 지원:
  - 운영시간: 평일 09:00-18:00, 주말 대기
  - 대응시간: 30분 이내
  - 담당: DevOps/SRE 팀
  - 범위: 시스템 문제 해결, 성능 분석, 배포 지원

Tier 3 (L3) - 전문가 지원:
  - 운영시간: 평일 09:00-18:00
  - 대응시간: 2시간 이내
  - 담당: 아키텍트, 개발팀
  - 범위: 복잡한 문제 해결, 아키텍처 변경, 긴급 패치
```

### 서비스 레벨 목표 (SLO)

#### 가용성 목표
```yaml
Critical Services (API, Auth):
  - 가용성: 99.9% (월 43분 다운타임)
  - 응답시간: P95 < 200ms, P99 < 500ms
  - 에러율: < 0.1%

Important Services (Dashboard, Analytics):
  - 가용성: 99.5% (월 3.6시간 다운타임)
  - 응답시간: P95 < 1s, P99 < 3s
  - 에러율: < 0.5%

Supporting Services (Monitoring, Logging):
  - 가용성: 99.0% (월 7.2시간 다운타임)
  - 데이터 손실: < 0.01%
  - 복구 시간: < 15분
```

## 📅 일상 운영 작업

### 일일 점검 작업

#### 시스템 상태 점검 (매일 09:00)
```bash
#!/bin/bash
# 일일 시스템 점검 스크립트

echo "🌅 $(date) - 일일 시스템 점검 시작"

# 1. 클러스터 상태 확인
echo "📊 Kubernetes 클러스터 상태:"
kubectl get nodes -o wide
kubectl get pods --all-namespaces | grep -v Running | grep -v Completed

# 2. 리소스 사용량 확인
echo "💻 리소스 사용량:"
kubectl top nodes
kubectl top pods -A --sort-by=memory | head -10

# 3. 저장소 사용량 확인
echo "💾 저장소 사용량:"
kubectl get pvc -A
df -h | grep -E '(8[0-9]|9[0-9])%'

# 4. 주요 서비스 상태
echo "🔍 주요 서비스 Health Check:"
services=(
  "https://api.hankook-smartsensor.com/health"
  "https://hankook-smartsensor.com/health"
  "http://prometheus.monitoring.svc.cluster.local:9090/-/healthy"
)

for service in "${services[@]}"; do
  if curl -s --max-time 10 "$service" > /dev/null; then
    echo "  ✅ $service"
  else
    echo "  ❌ $service"
  fi
done

# 5. 데이터베이스 상태
echo "🗄️ 데이터베이스 연결 확인:"
kubectl exec -n hankook-smartsensor postgresql-cluster-0 -- \
  psql -U postgres -c "SELECT 1;" > /dev/null && echo "  ✅ PostgreSQL" || echo "  ❌ PostgreSQL"

kubectl exec -n hankook-smartsensor redis-cluster-0 -- \
  redis-cli ping | grep PONG > /dev/null && echo "  ✅ Redis" || echo "  ❌ Redis"

# 6. 백업 상태 확인
echo "💾 백업 상태:"
velero backup get | head -5

echo "✅ 일일 점검 완료: $(date)"
```

#### 로그 검토 (매일 10:00)
```bash
#!/bin/bash
# 일일 로그 검토 스크립트

echo "📋 일일 로그 검토 시작: $(date)"

# 1. 에러 로그 수집 (지난 24시간)
echo "❌ 지난 24시간 에러 로그:"
kubectl logs --since=24h -l app=api-server -n hankook-smartsensor | grep -i error | tail -20

# 2. 성능 관련 로그
echo "⚡ 느린 응답 감지:"
kubectl logs --since=24h -l app=api-server -n hankook-smartsensor | \
  grep "response_time" | awk '$NF > 1000' | tail -10

# 3. 보안 관련 로그
echo "🔒 보안 이벤트:"
kubectl logs --since=24h -l app=oauth2-server -n hankook-security | \
  grep -E "(failed|unauthorized|blocked)" | tail -10

# 4. 센서 데이터 품질 확인
echo "📊 센서 데이터 품질:"
kubectl exec -n hankook-smartsensor postgresql-cluster-0 -- \
  psql -U postgres -d hankook_sensors -c "
    SELECT 
      DATE(timestamp) as date,
      COUNT(*) as total_readings,
      COUNT(CASE WHEN value IS NULL THEN 1 END) as null_readings,
      ROUND(AVG(value), 2) as avg_value
    FROM sensors.sensor_data 
    WHERE timestamp >= NOW() - INTERVAL '24 hours'
    GROUP BY DATE(timestamp)
    ORDER BY date DESC
    LIMIT 7;
  "

echo "✅ 로그 검토 완료: $(date)"
```

### 주간 점검 작업

#### 시스템 최적화 (매주 일요일 02:00)
```bash
#!/bin/bash
# 주간 시스템 최적화 스크립트

echo "🔧 주간 시스템 최적화 시작: $(date)"

# 1. 데이터베이스 정리
echo "🗄️ 데이터베이스 최적화:"
kubectl exec -n hankook-smartsensor postgresql-cluster-0 -- \
  psql -U postgres -d hankook_sensors -c "
    -- 오래된 센서 데이터 정리 (90일 이상)
    DELETE FROM sensors.sensor_data 
    WHERE timestamp < NOW() - INTERVAL '90 days';
    
    -- 통계 정보 업데이트
    ANALYZE;
    
    -- 인덱스 재구성
    REINDEX DATABASE hankook_sensors;
  "

# 2. 로그 정리
echo "📋 로그 정리:"
# Elasticsearch 오래된 인덱스 삭제 (30일 이상)
kubectl exec -n monitoring elasticsearch-0 -- \
  curl -X DELETE "localhost:9200/logstash-$(date -d '30 days ago' '+%Y.%m.%d')"

# 3. 이미지 정리
echo "🖼️ Docker 이미지 정리:"
kubectl get nodes -o name | xargs -I {} kubectl debug {} -it --image=alpine -- \
  sh -c "nsenter -t 1 -m -u -n -i -p -- docker system prune -f"

# 4. 메트릭 압축
echo "📊 메트릭 데이터 압축:"
kubectl exec -n monitoring prometheus-0 -- \
  promtool tsdb create-blocks-from-rules --label=prometheus=kube-prometheus-stack-prometheus \
  /prometheus/rules /prometheus/data

echo "✅ 주간 최적화 완료: $(date)"
```

### 월간 점검 작업

#### 보안 감사 (매월 첫째 월요일)
```bash
#!/bin/bash
# 월간 보안 감사 스크립트

echo "🔐 월간 보안 감사 시작: $(date)"

# 1. 인증서 만료 확인
echo "📜 SSL/TLS 인증서 상태:"
kubectl get certificates -A -o custom-columns=\
  "NAMESPACE:.metadata.namespace,NAME:.metadata.name,READY:.status.conditions[0].status,AGE:.metadata.creationTimestamp"

# 2. 권한 검토
echo "👥 RBAC 권한 검토:"
kubectl get clusterrolebindings -o wide | grep -v system:

# 3. 보안 스캔
echo "🔍 보안 취약점 스캔:"
# Trivy를 사용한 이미지 스캔
trivy image --severity HIGH,CRITICAL hankook/api-server:latest

# 4. 네트워크 정책 확인
echo "🌐 네트워크 정책 상태:"
kubectl get networkpolicies -A

# 5. 비밀번호 정책 확인
echo "🔑 사용자 계정 보안 상태:"
kubectl exec -n hankook-security oauth2-server-0 -- \
  python3 -c "
import sys
sys.path.append('/app')
from security_audit import check_user_security
check_user_security()
"

echo "✅ 보안 감사 완료: $(date)"
```

## 📊 시스템 모니터링

### Prometheus 메트릭 설정

#### 주요 모니터링 메트릭
```yaml
# prometheus-rules.yaml
groups:
- name: hankook_smartsensor_alerts
  rules:
  
  # API 서버 메트릭
  - alert: APIHighResponseTime
    expr: histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m])) > 0.5
    for: 2m
    labels:
      severity: warning
      team: backend
    annotations:
      summary: "API 응답 시간 증가"
      description: "API 서버의 95%ile 응답 시간이 {{ $value }}초로 임계값을 초과했습니다."

  - alert: APIErrorRate
    expr: rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m]) > 0.01
    for: 1m
    labels:
      severity: critical
      team: backend
    annotations:
      summary: "API 에러율 증가"
      description: "API 서버의 에러율이 {{ $value }}%로 임계값을 초과했습니다."

  # 데이터베이스 메트릭
  - alert: DatabaseConnectionsHigh
    expr: pg_stat_database_numbackends / pg_settings_max_connections > 0.8
    for: 5m
    labels:
      severity: warning
      team: data
    annotations:
      summary: "데이터베이스 연결 수 높음"
      description: "데이터베이스 연결 수가 최대값의 80%를 초과했습니다."

  - alert: DatabaseSlowQueries
    expr: pg_stat_statements_mean_time_ms > 1000
    for: 2m
    labels:
      severity: warning
      team: data
    annotations:
      summary: "데이터베이스 느린 쿼리 감지"
      description: "평균 쿼리 실행 시간이 {{ $value }}ms로 임계값을 초과했습니다."

  # 센서 데이터 메트릭
  - alert: SensorDataIngestionRate
    expr: rate(sensor_data_received_total[5m]) < 100
    for: 5m
    labels:
      severity: critical
      team: iot
    annotations:
      summary: "센서 데이터 수집 감소"
      description: "센서 데이터 수집율이 {{ $value }}/초로 정상 범위를 벗어났습니다."

  - alert: SensorDataQuality
    expr: sensor_data_error_rate > 0.05
    for: 3m
    labels:
      severity: warning
      team: iot
    annotations:
      summary: "센서 데이터 품질 저하"
      description: "센서 데이터 오류율이 {{ $value }}%로 임계값을 초과했습니다."
```

### Grafana 대시보드

#### 시스템 개요 대시보드
```json
{
  "dashboard": {
    "title": "HankookTire SmartSensor 2.0 - System Overview",
    "panels": [
      {
        "title": "API 요청률",
        "type": "stat",
        "targets": [
          {
            "expr": "sum(rate(http_requests_total[5m]))",
            "legendFormat": "Requests/sec"
          }
        ]
      },
      {
        "title": "응답 시간 분포",
        "type": "heatmap",
        "targets": [
          {
            "expr": "rate(http_request_duration_seconds_bucket[5m])"
          }
        ]
      },
      {
        "title": "활성 차량 수",
        "type": "stat",
        "targets": [
          {
            "expr": "active_vehicles_total"
          }
        ]
      },
      {
        "title": "센서 데이터 수집률",
        "type": "graph",
        "targets": [
          {
            "expr": "rate(sensor_data_received_total[5m])",
            "legendFormat": "Data points/sec"
          }
        ]
      }
    ]
  }
}
```

### 로그 분석

#### ELK 스택 로그 파이프라인
```yaml
# logstash-config.yaml
input {
  beats {
    port => 5044
  }
}

filter {
  if [kubernetes][labels][app] == "api-server" {
    grok {
      match => { 
        "message" => "%{TIMESTAMP_ISO8601:timestamp} %{LOGLEVEL:level} \[%{DATA:thread}\] %{DATA:logger}: %{GREEDYDATA:message}"
      }
    }
    
    if [message] =~ /response_time/ {
      grok {
        match => {
          "message" => "response_time=%{NUMBER:response_time:float}ms"
        }
      }
    }
    
    if [response_time] and [response_time] > 1000 {
      mutate {
        add_tag => ["slow_response"]
      }
    }
  }
  
  if [kubernetes][labels][app] == "sensor-gateway" {
    json {
      source => "message"
    }
    
    if [sensor_data][quality] == "poor" {
      mutate {
        add_tag => ["data_quality_issue"]
      }
    }
  }
}

output {
  elasticsearch {
    hosts => ["elasticsearch-0:9200", "elasticsearch-1:9200"]
    index => "hankook-smartsensor-%{+YYYY.MM.dd}"
  }
}
```

## ⚡ 성능 관리

### 자동 스케일링 설정

#### Horizontal Pod Autoscaler (HPA)
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
  - type: Pods
    pods:
      metric:
        name: http_requests_per_second
      target:
        type: AverageValue
        averageValue: "30"
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
      - type: Percent
        value: 50
        periodSeconds: 60
    scaleUp:
      stabilizationWindowSeconds: 60
      policies:
      - type: Percent
        value: 100
        periodSeconds: 15
      - type: Pods
        value: 4
        periodSeconds: 60
      selectPolicy: Max
```

#### Vertical Pod Autoscaler (VPA)
```yaml
# database-vpa.yaml
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: postgresql-vpa
  namespace: hankook-smartsensor
spec:
  targetRef:
    apiVersion: apps/v1
    kind: StatefulSet
    name: postgresql-cluster
  updatePolicy:
    updateMode: "Auto"
  resourcePolicy:
    containerPolicies:
    - containerName: postgresql
      minAllowed:
        cpu: 500m
        memory: 1Gi
      maxAllowed:
        cpu: 4
        memory: 16Gi
      controlledResources: ["cpu", "memory"]
      controlledValues: RequestsAndLimits
```

### 성능 최적화 작업

#### 데이터베이스 성능 튜닝
```sql
-- PostgreSQL 성능 최적화 쿼리

-- 1. 느린 쿼리 분석
SELECT 
    query,
    calls,
    total_time,
    mean_time,
    (total_time/sum(total_time) OVER()) * 100 AS percentage
FROM pg_stat_statements 
WHERE mean_time > 100
ORDER BY total_time DESC
LIMIT 20;

-- 2. 인덱스 사용률 분석
SELECT 
    schemaname,
    tablename,
    indexname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch,
    pg_size_pretty(pg_relation_size(indexrelid)) AS size
FROM pg_stat_user_indexes
WHERE idx_scan < 100  -- 거의 사용되지 않는 인덱스
ORDER BY pg_relation_size(indexrelid) DESC;

-- 3. 테이블 통계 업데이트
ANALYZE;

-- 4. 자동 VACUUM 설정 최적화
ALTER TABLE sensors.sensor_data SET (
    autovacuum_vacuum_scale_factor = 0.1,
    autovacuum_analyze_scale_factor = 0.05,
    autovacuum_vacuum_cost_delay = 10
);
```

#### 캐시 최적화
```bash
#!/bin/bash
# Redis 캐시 최적화 스크립트

echo "🔄 Redis 캐시 최적화 시작"

# 1. 메모리 사용량 확인
kubectl exec -n hankook-smartsensor redis-cluster-0 -- redis-cli INFO memory

# 2. 키 분석
kubectl exec -n hankook-smartsensor redis-cluster-0 -- redis-cli --bigkeys

# 3. 만료된 키 정리
kubectl exec -n hankook-smartsensor redis-cluster-0 -- redis-cli FLUSHDB

# 4. 캐시 히트율 확인
kubectl exec -n hankook-smartsensor redis-cluster-0 -- redis-cli INFO stats | grep cache

echo "✅ Redis 캐시 최적화 완료"
```

### 성능 모니터링 대시보드

#### 애플리케이션 성능 지표
```yaml
# application-performance.json
{
  "dashboard": {
    "title": "Application Performance Monitoring",
    "panels": [
      {
        "title": "응답 시간 P95/P99",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))",
            "legendFormat": "P95"
          },
          {
            "expr": "histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m]))",
            "legendFormat": "P99"
          }
        ]
      },
      {
        "title": "처리량 (RPS)",
        "targets": [
          {
            "expr": "sum(rate(http_requests_total[5m]))",
            "legendFormat": "Requests/sec"
          }
        ]
      },
      {
        "title": "에러율",
        "targets": [
          {
            "expr": "rate(http_requests_total{status=~\"5..\"}[5m]) / rate(http_requests_total[5m]) * 100",
            "legendFormat": "Error rate %"
          }
        ]
      }
    ]
  }
}
```

## 💾 백업 및 복구

### 백업 전략

#### 데이터 백업 스케줄
```yaml
# velero-backup-schedule.yaml
apiVersion: velero.io/v1
kind: Schedule
metadata:
  name: hankook-smartsensor-backup
  namespace: velero
spec:
  schedule: "0 2 * * *"  # 매일 02:00
  template:
    metadata:
      labels:
        backup-type: daily
    spec:
      includedNamespaces:
      - hankook-smartsensor
      - hankook-security
      - monitoring
      excludedResources:
      - events
      - events.events.k8s.io
      storageLocation: default
      volumeSnapshotLocations:
      - default
      ttl: 720h0m0s  # 30일 보관
```

#### 데이터베이스 백업
```bash
#!/bin/bash
# PostgreSQL 백업 스크립트

BACKUP_DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backups/postgresql"
RETENTION_DAYS=30

echo "📦 PostgreSQL 백업 시작: $BACKUP_DATE"

# 1. 데이터베이스 덤프
kubectl exec -n hankook-smartsensor postgresql-cluster-0 -- \
  pg_dumpall -U postgres | gzip > "$BACKUP_DIR/postgresql_backup_$BACKUP_DATE.sql.gz"

# 2. WAL 파일 백업
kubectl exec -n hankook-smartsensor postgresql-cluster-0 -- \
  tar -czf - /var/lib/postgresql/data/pg_wal/ > "$BACKUP_DIR/wal_backup_$BACKUP_DATE.tar.gz"

# 3. 설정 파일 백업
kubectl get configmap postgresql-config -n hankook-smartsensor -o yaml > \
  "$BACKUP_DIR/postgresql_config_$BACKUP_DATE.yaml"

# 4. 오래된 백업 정리
find "$BACKUP_DIR" -name "*.gz" -mtime +$RETENTION_DAYS -delete

# 5. 백업 검증
if [ -f "$BACKUP_DIR/postgresql_backup_$BACKUP_DATE.sql.gz" ]; then
  echo "✅ PostgreSQL 백업 완료: postgresql_backup_$BACKUP_DATE.sql.gz"
else
  echo "❌ PostgreSQL 백업 실패"
  exit 1
fi

# 6. 클라우드 스토리지에 업로드
aws s3 cp "$BACKUP_DIR/postgresql_backup_$BACKUP_DATE.sql.gz" \
  s3://hankook-smartsensor-backups/postgresql/

echo "📤 백업 파일 클라우드 업로드 완료"
```

### 재해 복구 절차

#### 전체 시스템 복구
```bash
#!/bin/bash
# 재해 복구 스크립트

BACKUP_DATE=${1:-latest}
echo "🚑 재해 복구 시작: $BACKUP_DATE"

# 1. 클러스터 상태 확인
if ! kubectl cluster-info > /dev/null 2>&1; then
  echo "❌ Kubernetes 클러스터에 연결할 수 없습니다"
  exit 1
fi

# 2. 네임스페이스 재생성
kubectl create namespace hankook-smartsensor --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace hankook-security --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f -

# 3. Velero를 사용한 애플리케이션 복구
if [ "$BACKUP_DATE" = "latest" ]; then
  BACKUP_NAME=$(velero backup get | grep Completed | head -1 | awk '{print $1}')
else
  BACKUP_NAME="hankook-smartsensor-backup-$BACKUP_DATE"
fi

echo "📦 백업에서 복구 중: $BACKUP_NAME"
velero restore create --from-backup $BACKUP_NAME --wait

# 4. 데이터베이스 복구
echo "🗄️ 데이터베이스 복구 중..."
kubectl apply -f deployment/databases/postgresql-cluster.yaml

# PostgreSQL 준비 대기
kubectl wait --for=condition=ready pod/postgresql-cluster-0 -n hankook-smartsensor --timeout=300s

# 백업된 데이터 복원
aws s3 cp s3://hankook-smartsensor-backups/postgresql/postgresql_backup_$BACKUP_DATE.sql.gz /tmp/
gunzip /tmp/postgresql_backup_$BACKUP_DATE.sql.gz

kubectl exec -i -n hankook-smartsensor postgresql-cluster-0 -- \
  psql -U postgres < /tmp/postgresql_backup_$BACKUP_DATE.sql

# 5. 서비스 상태 확인
echo "🔍 서비스 상태 확인 중..."
kubectl get pods -A | grep -v Running | grep -v Completed

# 6. 기능 테스트
echo "🧪 기능 테스트 실행 중..."
curl -f https://api.hankook-smartsensor.com/health || echo "❌ API 서버 테스트 실패"
curl -f https://hankook-smartsensor.com || echo "❌ 웹 대시보드 테스트 실패"

echo "✅ 재해 복구 완료: $(date)"
```

### 백업 검증

#### 정기 백업 테스트
```bash
#!/bin/bash
# 백업 검증 스크립트 (매주 실행)

echo "🔍 백업 검증 시작: $(date)"

# 1. 최신 백업 파일 확인
LATEST_BACKUP=$(ls -t /backups/postgresql/postgresql_backup_*.sql.gz | head -1)
if [ -z "$LATEST_BACKUP" ]; then
  echo "❌ 백업 파일을 찾을 수 없습니다"
  exit 1
fi

echo "📦 검증할 백업: $LATEST_BACKUP"

# 2. 테스트 환경에 복원
TEST_NAMESPACE="backup-test-$(date +%s)"
kubectl create namespace $TEST_NAMESPACE

# 테스트용 PostgreSQL 인스턴스 생성
kubectl apply -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: postgres-test
  namespace: $TEST_NAMESPACE
spec:
  replicas: 1
  selector:
    matchLabels:
      app: postgres-test
  template:
    metadata:
      labels:
        app: postgres-test
    spec:
      containers:
      - name: postgres
        image: postgres:13
        env:
        - name: POSTGRES_PASSWORD
          value: testpassword
        - name: PGDATA
          value: /var/lib/postgresql/data/pgdata
        volumeMounts:
        - name: postgres-storage
          mountPath: /var/lib/postgresql/data
      volumes:
      - name: postgres-storage
        emptyDir: {}
EOF

# Pod 준비 대기
kubectl wait --for=condition=ready pod -l app=postgres-test -n $TEST_NAMESPACE --timeout=300s

# 3. 백업 데이터 복원 테스트
echo "🔄 백업 데이터 복원 테스트 중..."
gunzip -c "$LATEST_BACKUP" | kubectl exec -i -n $TEST_NAMESPACE \
  deployment/postgres-test -- psql -U postgres

# 4. 데이터 무결성 확인
RECORD_COUNT=$(kubectl exec -n $TEST_NAMESPACE deployment/postgres-test -- \
  psql -U postgres -d hankook_sensors -t -c "SELECT COUNT(*) FROM sensors.sensor_data;")

echo "📊 복원된 레코드 수: $RECORD_COUNT"

if [ "$RECORD_COUNT" -gt 0 ]; then
  echo "✅ 백업 검증 성공"
else
  echo "❌ 백업 검증 실패: 데이터가 없습니다"
fi

# 5. 정리
kubectl delete namespace $TEST_NAMESPACE

echo "🏁 백업 검증 완료: $(date)"
```

## 🔒 보안 관리

### 보안 정책 관리

#### Pod Security Standards
```yaml
# pod-security-policy.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: hankook-smartsensor
  labels:
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/audit: restricted
    pod-security.kubernetes.io/warn: restricted
---
apiVersion: v1
kind: Namespace
metadata:
  name: hankook-security
  labels:
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/audit: restricted
    pod-security.kubernetes.io/warn: restricted
```

#### Network Policies
```yaml
# network-policies.yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-all
  namespace: hankook-smartsensor
spec:
  podSelector: {}
  policyTypes:
  - Ingress
  - Egress
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-api-server
  namespace: hankook-smartsensor
spec:
  podSelector:
    matchLabels:
      app: api-server
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          name: ingress-nginx
    - podSelector:
        matchLabels:
          app: web-dashboard
    ports:
    - protocol: TCP
      port: 8000
  egress:
  - to:
    - podSelector:
        matchLabels:
          app: postgresql
    ports:
    - protocol: TCP
      port: 5432
  - to:
    - podSelector:
        matchLabels:
          app: redis
    ports:
    - protocol: TCP
      port: 6379
```

### 취약점 관리

#### 정기 보안 스캔
```bash
#!/bin/bash
# 보안 스캔 스크립트

echo "🔍 정기 보안 스캔 시작: $(date)"

# 1. 컨테이너 이미지 취약점 스캔
IMAGES=(
  "hankook/api-server:latest"
  "hankook/web-dashboard:latest"
  "hankook/sensor-gateway:latest"
  "hankook/analytics-engine:latest"
)

for image in "${IMAGES[@]}"; do
  echo "🖼️ 이미지 스캔 중: $image"
  trivy image --severity HIGH,CRITICAL --format json $image > "scan_results_$(echo $image | tr '/:' '_').json"
done

# 2. Kubernetes 클러스터 보안 스캔
echo "☸️ Kubernetes 클러스터 스캔 중..."
kube-bench run --targets master,node --outputfile kube-bench-results.json --json

# 3. 네트워크 보안 스캔
echo "🌐 네트워크 보안 스캔 중..."
nmap -sS -O hankook-smartsensor.com > network-scan-results.txt

# 4. 설정 보안 스캔
echo "⚙️ 설정 보안 스캔 중..."
# Falco를 사용한 런타임 보안 모니터링
kubectl logs -n kube-system -l app=falco --since=24h | grep -i "warning\|error" > falco-alerts.log

# 5. 결과 분석 및 리포트 생성
echo "📋 보안 스캔 리포트 생성 중..."
python3 security_report_generator.py \
  --trivy-results scan_results_*.json \
  --kube-bench kube-bench-results.json \
  --network-scan network-scan-results.txt \
  --falco-alerts falco-alerts.log \
  --output security-report-$(date +%Y%m%d).html

echo "✅ 보안 스캔 완료. 리포트: security-report-$(date +%Y%m%d).html"
```

### 액세스 관리

#### 사용자 액세스 검토
```bash
#!/bin/bash
# 사용자 액세스 검토 스크립트

echo "👥 사용자 액세스 검토 시작: $(date)"

# 1. 활성 사용자 목록
echo "📋 활성 사용자 목록:"
kubectl get rolebindings,clusterrolebindings -A -o wide | \
  grep -v system: | awk '{print $1, $3, $4}' | sort | uniq

# 2. 권한 매트릭스 생성
echo "🔐 권한 매트릭스:"
users=(admin operator viewer)
for user in "${users[@]}"; do
  echo "사용자: $user"
  kubectl auth can-i --list --as=$user | head -10
done

# 3. 마지막 로그인 확인
echo "🕐 마지막 로그인 시간:"
kubectl logs -n hankook-security oauth2-server-0 --since=720h | \
  grep "login_success" | tail -20

# 4. 비활성 계정 확인
echo "😴 비활성 계정 (90일 이상 미사용):"
python3 -c "
import json
import datetime
from kubernetes import client, config

config.load_incluster_config()
v1 = client.CoreV1Api()

# 사용자별 마지막 활동 시간 조회
# (실제 구현에서는 audit 로그 분석)
inactive_users = []
cutoff_date = datetime.datetime.now() - datetime.timedelta(days=90)

# 결과 출력
for user in inactive_users:
    print(f'{user[\"username\"]} - 마지막 활동: {user[\"last_activity\"]}')
"

echo "✅ 사용자 액세스 검토 완료: $(date)"
```

## 🚨 장애 대응

### 장애 대응 절차

#### 인시던트 대응 플레이북
```yaml
# incident-response-playbook.yaml
incident_levels:
  P1_Critical:
    description: "서비스 완전 중단 또는 심각한 보안 침해"
    response_time: "15분 이내"
    escalation_time: "30분"
    team: ["L1", "L2", "L3", "Management"]
    
  P2_High:
    description: "주요 기능 장애 또는 성능 심각한 저하"
    response_time: "30분 이내"
    escalation_time: "1시간"
    team: ["L1", "L2"]
    
  P3_Medium:
    description: "일부 기능 장애 또는 성능 저하"
    response_time: "2시간 이내"
    escalation_time: "4시간"
    team: ["L1", "L2"]
    
  P4_Low:
    description: "경미한 문제 또는 개선 사항"
    response_time: "24시간 이내"
    escalation_time: "48시간"
    team: ["L1"]

response_procedures:
  step1_detect:
    - "모니터링 시스템 알림 확인"
    - "서비스 상태 페이지 업데이트"
    - "초기 영향 범위 평가"
    
  step2_assess:
    - "장애 원인 초기 분석"
    - "비즈니스 영향도 평가"
    - "우선순위 결정"
    
  step3_mitigate:
    - "즉시 완화 조치 실행"
    - "트래픽 우회 또는 서비스 격리"
    - "백업 시스템 활성화"
    
  step4_resolve:
    - "근본 원인 분석"
    - "영구 수정 사항 적용"
    - "서비스 정상화 확인"
    
  step5_communicate:
    - "상태 업데이트 공지"
    - "이해관계자 커뮤니케이션"
    - "고객 및 사용자 공지"
    
  step6_postmortem:
    - "포스트모템 회의 진행"
    - "개선 사항 도출"
    - "액션 플랜 수립"
```

#### 자동 장애 복구 스크립트
```bash
#!/bin/bash
# 자동 장애 복구 스크립트

ALERT_TYPE=${1:-"unknown"}
ALERT_SEVERITY=${2:-"warning"}

echo "🚨 장애 감지 - 타입: $ALERT_TYPE, 심각도: $ALERT_SEVERITY"

case $ALERT_TYPE in
  "pod_crash_loop")
    echo "🔄 Pod CrashLoopBackOff 복구 중..."
    # 최근 재시작된 Pod 확인
    POD_NAME=$(kubectl get pods -A --field-selector=status.phase=Failed -o name | head -1)
    if [ -n "$POD_NAME" ]; then
      kubectl delete $POD_NAME
      echo "✅ 실패한 Pod 재시작: $POD_NAME"
    fi
    ;;
    
  "high_memory_usage")
    echo "💾 메모리 사용량 증가 대응 중..."
    # 메모리 사용량이 높은 Pod 식별
    kubectl top pods -A --sort-by=memory | head -10
    
    # HPA 스케일 업 강제 실행
    kubectl patch hpa api-server-hpa -p '{"spec":{"minReplicas":5}}'
    echo "✅ HPA 최소 레플리카 증가"
    ;;
    
  "database_connection_limit")
    echo "🗄️ 데이터베이스 연결 한계 대응 중..."
    # 유휴 연결 정리
    kubectl exec -n hankook-smartsensor postgresql-cluster-0 -- \
      psql -U postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'idle' AND query_start < now() - interval '10 minutes';"
    echo "✅ 유휴 데이터베이스 연결 정리 완료"
    ;;
    
  "disk_space_low")
    echo "💾 디스크 공간 부족 대응 중..."
    # 로그 파일 정리
    kubectl get pods -A -o name | xargs -I {} kubectl exec {} -- find /var/log -name "*.log" -mtime +7 -delete 2>/dev/null || true
    
    # 임시 파일 정리
    kubectl get pods -A -o name | xargs -I {} kubectl exec {} -- find /tmp -type f -mtime +1 -delete 2>/dev/null || true
    echo "✅ 디스크 공간 정리 완료"
    ;;
    
  "ssl_certificate_expiring")
    echo "📜 SSL 인증서 만료 임박 대응 중..."
    # Cert-manager를 통한 인증서 갱신 강제 실행
    kubectl annotate certificate --all cert-manager.io/issue-temporary-certificate=true
    echo "✅ SSL 인증서 갱신 요청 완료"
    ;;
    
  *)
    echo "⚠️ 알 수 없는 장애 유형: $ALERT_TYPE"
    echo "수동 대응이 필요합니다."
    ;;
esac

# 복구 후 상태 확인
sleep 30
echo "🔍 복구 후 시스템 상태 확인:"
kubectl get pods -A | grep -v Running | grep -v Completed || echo "모든 Pod가 정상 상태입니다"

echo "🏁 자동 복구 완료: $(date)"
```

### 포스트모템 프로세스

#### 포스트모템 템플릿
```markdown
# 인시던트 포스트모템

## 기본 정보
- **인시던트 ID**: INC-2024-001
- **발생 일시**: 2024-01-26 14:30 KST
- **해결 일시**: 2024-01-26 16:45 KST
- **총 영향 시간**: 2시간 15분
- **심각도**: P2 (High)
- **담당자**: DevOps 팀

## 인시던트 요약
API 서버의 메모리 누수로 인한 서비스 응답 지연 및 일부 요청 실패

## 타임라인
- **14:30** - Prometheus 알림으로 높은 응답 시간 감지
- **14:35** - L1 팀 초기 대응 시작
- **14:45** - L2 팀 에스컬레이션
- **15:00** - 메모리 누수 원인 식별
- **15:30** - 애플리케이션 재시작 결정
- **15:45** - 롤링 업데이트 시작
- **16:15** - 모든 인스턴스 교체 완료
- **16:30** - 서비스 정상화 확인
- **16:45** - 인시던트 종료 선언

## 근본 원인
배치 처리 작업에서 대량의 센서 데이터 처리 시 메모리 해제가 제대로 이루어지지 않아 메모리 누수 발생

## 영향 범위
- **사용자 영향**: 약 500명의 활성 사용자
- **서비스 영향**: API 응답 시간 500ms → 3000ms 증가
- **데이터 영향**: 없음 (모든 데이터 정상 처리)
- **비즈니스 영향**: 실시간 모니터링 지연

## 대응 조치
### 즉시 대응
1. API 서버 인스턴스 수 증가 (3 → 6)
2. 로드 밸런서 헬스 체크 간격 단축
3. 메모리 사용량 높은 인스턴스 우선 재시작

### 근본적 해결
1. 배치 처리 로직에서 메모리 해제 코드 추가
2. 메모리 프로파일링 도구 적용
3. 가비지 컬렉션 튜닝

## 향후 개선 사항
1. **예방 조치**
   - 메모리 사용량 알림 임계값 조정 (70% → 60%)
   - 자동 메모리 프로파일링 도구 도입
   - 배치 작업 메모리 사용량 모니터링 강화

2. **감지 개선**
   - 메모리 누수 패턴 탐지 알고리즘 구현
   - 애플리케이션별 세분화된 모니터링

3. **대응 개선**
   - 자동 인스턴스 재시작 정책 수립
   - 장애 대응 플레이북 업데이트

## 액션 아이템
| 항목 | 담당자 | 완료 목표일 | 상태 |
|------|--------|-------------|------|
| 메모리 누수 수정 코드 배포 | 개발팀 | 2024-01-28 | 진행중 |
| 모니터링 임계값 조정 | DevOps팀 | 2024-01-27 | 완료 |
| 자동 재시작 정책 수립 | SRE팀 | 2024-02-05 | 계획중 |

## 교훈
1. 메모리 사용량 증가는 점진적이므로 조기 감지가 중요
2. 배치 작업의 리소스 사용 패턴을 별도로 모니터링 필요
3. 자동 복구 메커니즘의 중요성 재확인
```

## 📈 용량 계획

### 리소스 사용량 분석

#### 용량 계획 스크립트
```bash
#!/bin/bash
# 용량 계획 및 예측 스크립트

echo "📊 용량 계획 분석 시작: $(date)"

# 1. 현재 리소스 사용량 수집
echo "💻 현재 리소스 사용량:"
kubectl top nodes
kubectl top pods -A --sort-by=memory | head -20

# 2. 히스토리 데이터 분석 (Prometheus 쿼리)
echo "📈 리소스 사용량 트렌드 (지난 30일):"
PROM_URL="http://prometheus.monitoring.svc.cluster.local:9090"

# CPU 사용량 트렌드
curl -s "${PROM_URL}/api/v1/query_range?query=100-(avg(rate(node_cpu_seconds_total{mode=\"idle\"}[5m]))*100)&start=$(date -d '30 days ago' +%s)&end=$(date +%s)&step=3600" | \
  jq -r '.data.result[0].values[] | "\(.[0]) \(.[1])"' > cpu_usage_30days.txt

# 메모리 사용량 트렌드  
curl -s "${PROM_URL}/api/v1/query_range?query=(1-(node_memory_MemAvailable_bytes/node_memory_MemTotal_bytes))*100&start=$(date -d '30 days ago' +%s)&end=$(date +%s)&step=3600" | \
  jq -r '.data.result[0].values[] | "\(.[0]) \(.[1])"' > memory_usage_30days.txt

# 3. 성장률 계산
echo "📈 리소스 사용량 성장률:"
python3 << EOF
import numpy as np
from datetime import datetime, timedelta

# CPU 사용량 분석
with open('cpu_usage_30days.txt', 'r') as f:
    cpu_data = [float(line.split()[1]) for line in f.readlines()]

if cpu_data:
    cpu_trend = np.polyfit(range(len(cpu_data)), cpu_data, 1)[0]
    print(f"CPU 사용량 일일 증가율: {cpu_trend:.3f}%")
    
    # 6개월 예측
    current_avg = np.mean(cpu_data[-7:])  # 최근 7일 평균
    predicted_6m = current_avg + (cpu_trend * 180)
    print(f"현재 평균 CPU 사용률: {current_avg:.1f}%")
    print(f"6개월 후 예상 CPU 사용률: {predicted_6m:.1f}%")

# 메모리 사용량 분석
with open('memory_usage_30days.txt', 'r') as f:
    memory_data = [float(line.split()[1]) for line in f.readlines()]

if memory_data:
    memory_trend = np.polyfit(range(len(memory_data)), memory_data, 1)[0]
    print(f"메모리 사용량 일일 증가율: {memory_trend:.3f}%")
    
    current_avg = np.mean(memory_data[-7:])
    predicted_6m = current_avg + (memory_trend * 180)
    print(f"현재 평균 메모리 사용률: {current_avg:.1f}%")
    print(f"6개월 후 예상 메모리 사용률: {predicted_6m:.1f}%")
EOF

# 4. 스토리지 사용량 분석
echo "💾 스토리지 사용량 분석:"
kubectl exec -n hankook-smartsensor postgresql-cluster-0 -- \
  psql -U postgres -d hankook_sensors -c "
    SELECT 
      schemaname,
      tablename,
      pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size,
      pg_total_relation_size(schemaname||'.'||tablename) as size_bytes
    FROM pg_tables 
    WHERE schemaname NOT IN ('information_schema', 'pg_catalog')
    ORDER BY size_bytes DESC;
  "

# 5. 센서 데이터 증가율 분석
echo "📊 센서 데이터 증가율:"
kubectl exec -n hankook-smartsensor postgresql-cluster-0 -- \
  psql -U postgres -d hankook_sensors -c "
    SELECT 
      DATE(timestamp) as date,
      COUNT(*) as daily_records,
      AVG(COUNT(*)) OVER (ORDER BY DATE(timestamp) ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) as rolling_7day_avg
    FROM sensors.sensor_data 
    WHERE timestamp >= NOW() - INTERVAL '30 days'
    GROUP BY DATE(timestamp)
    ORDER BY date DESC
    LIMIT 10;
  "

# 6. 용량 계획 권고사항 생성
echo "📋 용량 계획 권고사항:"
python3 << EOF
import json

# 임계값 설정
CPU_THRESHOLD = 70
MEMORY_THRESHOLD = 80
STORAGE_THRESHOLD = 80

recommendations = []

# CPU 권고사항
if predicted_6m > CPU_THRESHOLD:
    recommendations.append({
        "resource": "CPU",
        "action": "노드 추가 또는 인스턴스 타입 업그레이드",
        "timeline": "3-4개월 내",
        "urgency": "high" if predicted_6m > 85 else "medium"
    })

# 메모리 권고사항  
if predicted_6m > MEMORY_THRESHOLD:
    recommendations.append({
        "resource": "Memory", 
        "action": "메모리 증설 또는 워커 노드 추가",
        "timeline": "2-3개월 내",
        "urgency": "high" if predicted_6m > 90 else "medium"
    })

# 권고사항 출력
for rec in recommendations:
    print(f"⚠️ {rec['resource']}: {rec['action']} ({rec['timeline']})")

if not recommendations:
    print("✅ 현재 용량으로 6개월 안정적 운영 가능")
EOF

echo "✅ 용량 계획 분석 완료: $(date)"
```

### 확장 계획

#### 클러스터 확장 전략
```yaml
# cluster-scaling-strategy.yaml
scaling_triggers:
  scale_out:  # 노드 추가
    cpu_threshold: 70%
    memory_threshold: 80% 
    duration: 15분
    
  scale_up:   # 인스턴스 타입 업그레이드
    cpu_threshold: 85%
    memory_threshold: 90%
    duration: 30분

node_groups:
  general:
    instance_type: m5.xlarge
    min_size: 3
    max_size: 10
    target_capacity: 5
    
  memory_optimized:
    instance_type: r5.xlarge  
    min_size: 0
    max_size: 5
    target_capacity: 2
    
  compute_optimized:
    instance_type: c5.xlarge
    min_size: 0
    max_size: 3
    target_capacity: 1

storage_scaling:
  postgresql:
    current_size: 500GB
    growth_rate: 10GB/month
    next_resize: 1TB
    resize_trigger: 80%
    
  elasticsearch:
    current_size: 200GB
    growth_rate: 5GB/month
    retention_policy: 30days
    hot_tier: 50GB
    warm_tier: 150GB
```

---

**🎯 체계적인 운영 관리를 통해 안정적이고 효율적인 시스템을 유지하세요!**

© 2024 HankookTire SmartSensor 2.0. All rights reserved.