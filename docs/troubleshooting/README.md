# 🔧 문제 해결 가이드

**HankookTire SmartSensor 2.0 시스템 문제 해결**

이 가이드는 HankookTire SmartSensor 2.0 시스템에서 발생할 수 있는 일반적인 문제들의 해결 방법을 제공합니다.

---

## 📋 목차

1. [일반적인 문제](#-일반적인-문제)
2. [시스템 성능 문제](#-시스템-성능-문제)
3. [네트워크 연결 문제](#-네트워크-연결-문제)
4. [데이터베이스 문제](#-데이터베이스-문제)
5. [보안 관련 문제](#-보안-관련-문제)
6. [모니터링 문제](#-모니터링-문제)
7. [진단 도구](#-진단-도구)
8. [고급 문제 해결](#-고급-문제-해결)

## ⚠️ 일반적인 문제

### 서비스 접속 불가

#### 증상
- 웹 대시보드에 접속할 수 없음
- API 호출이 응답하지 않음
- "연결할 수 없습니다" 오류 메시지

#### 진단 단계
```bash
# 1. 서비스 상태 확인
kubectl get pods -n hankook-smartsensor
kubectl get svc -n hankook-smartsensor

# 2. 네트워크 연결 테스트
curl -I https://hankook-smartsensor.com
curl -I https://api.hankook-smartsensor.com/health

# 3. DNS 해결 확인
nslookup hankook-smartsensor.com
dig +short hankook-smartsensor.com

# 4. 인그레스 상태 확인
kubectl get ingress -n hankook-smartsensor
kubectl describe ingress hankook-smartsensor-ingress -n hankook-smartsensor
```

#### 해결 방법

**Step 1: Pod 상태 확인 및 복구**
```bash
# 실패한 Pod 확인
kubectl get pods -n hankook-smartsensor | grep -v Running

# Pod 로그 확인
kubectl logs <pod-name> -n hankook-smartsensor

# Pod 재시작
kubectl delete pod <pod-name> -n hankook-smartsensor

# Deployment 재시작
kubectl rollout restart deployment/<deployment-name> -n hankook-smartsensor
```

**Step 2: 서비스 및 인그레스 복구**
```bash
# 서비스 엔드포인트 확인
kubectl get endpoints -n hankook-smartsensor

# 인그레스 컨트롤러 확인
kubectl get pods -n ingress-nginx
kubectl logs -n ingress-nginx deployment/ingress-nginx-controller

# 인그레스 재적용
kubectl apply -f deployment/ingress.yaml
```

**Step 3: DNS 및 인증서 문제 해결**
```bash
# 인증서 상태 확인
kubectl get certificates -n hankook-smartsensor
kubectl describe certificate <cert-name> -n hankook-smartsensor

# Let's Encrypt 인증서 갱신 강제 실행
kubectl annotate certificate <cert-name> cert-manager.io/issue-temporary-certificate=true

# DNS 캐시 플러시
sudo systemctl flush-dns
# 또는 Windows에서: ipconfig /flushdns
```

### 로그인 실패

#### 증상
- 올바른 자격 증명으로도 로그인 실패
- "인증 실패" 오류 메시지
- 토큰 만료 오류

#### 진단 및 해결
```bash
# 1. OAuth2 서버 상태 확인
kubectl get pods -n hankook-security -l app=oauth2-server
kubectl logs -n hankook-security deployment/oauth2-server

# 2. 데이터베이스 연결 확인
kubectl exec -n hankook-security oauth2-server-0 -- \
  python3 -c "
import psycopg2
try:
    conn = psycopg2.connect(
        host='postgresql-cluster', 
        database='hankook_sensors', 
        user='oauth_user'
    )
    print('✅ 데이터베이스 연결 성공')
except Exception as e:
    print(f'❌ 데이터베이스 연결 실패: {e}')
"

# 3. JWT 토큰 검증
kubectl get secret jwt-secrets -n hankook-security -o yaml

# 4. 사용자 계정 확인
kubectl exec -n hankook-smartsensor postgresql-cluster-0 -- \
  psql -U postgres -d hankook_sensors -c "
    SELECT username, email, status, last_login 
    FROM auth.users 
    WHERE username = 'your_username';
  "
```

### 센서 데이터 수신 안됨

#### 증상
- 실시간 센서 데이터가 표시되지 않음
- 차량 상태가 "오프라인"으로 표시
- 대시보드에 데이터 없음

#### 진단 단계
```bash
# 1. MQTT 브로커 상태 확인
kubectl get pods -n hankook-smartsensor -l app=mqtt-broker
kubectl logs -n hankook-smartsensor deployment/mqtt-broker

# 2. 센서 게이트웨이 상태 확인
kubectl get pods -n hankook-smartsensor -l app=sensor-gateway
kubectl logs -n hankook-smartsensor deployment/sensor-gateway

# 3. 데이터베이스 최근 데이터 확인
kubectl exec -n hankook-smartsensor postgresql-cluster-0 -- \
  psql -U postgres -d hankook_sensors -c "
    SELECT 
      vehicle_id,
      sensor_type,
      COUNT(*) as readings,
      MAX(timestamp) as last_reading
    FROM sensors.sensor_data 
    WHERE timestamp >= NOW() - INTERVAL '1 hour'
    GROUP BY vehicle_id, sensor_type
    ORDER BY last_reading DESC
    LIMIT 20;
  "

# 4. MQTT 연결 테스트
kubectl run mqtt-test --rm -i --restart=Never --image=eclipse-mosquitto:2.0 -- \
  mosquitto_sub -h mqtt-broker.hankook-smartsensor.svc.cluster.local -t "hankook/smartsensor/+/+/data" -v
```

#### 해결 방법

**Step 1: MQTT 브로커 문제 해결**
```bash
# MQTT 브로커 재시작
kubectl rollout restart deployment/mqtt-broker -n hankook-smartsensor

# MQTT 설정 확인
kubectl get configmap mqtt-broker-config -n hankook-smartsensor -o yaml

# 포트 포워딩을 통한 직접 테스트
kubectl port-forward -n hankook-smartsensor svc/mqtt-broker 1883:1883 &
mosquitto_pub -h localhost -t "test/topic" -m "test message"
```

**Step 2: 센서 게이트웨이 복구**
```bash
# 센서 게이트웨이 로그 상세 확인
kubectl logs -n hankook-smartsensor deployment/sensor-gateway --previous

# 환경 변수 확인
kubectl describe deployment sensor-gateway -n hankook-smartsensor

# 리소스 사용량 확인
kubectl top pods -n hankook-smartsensor -l app=sensor-gateway
```

**Step 3: 디바이스 연결 확인**
```bash
# 디바이스별 연결 상태 확인
kubectl exec -n hankook-smartsensor redis-cluster-0 -- \
  redis-cli KEYS "device:*:status"

# 연결된 디바이스 목록
kubectl exec -n hankook-smartsensor redis-cluster-0 -- \
  redis-cli SMEMBERS "connected_devices"
```

## ⚡ 시스템 성능 문제

### 높은 응답 시간

#### 증상
- API 응답 시간이 1초 이상
- 웹 대시보드 로딩 지연
- 타임아웃 오류 발생

#### 진단 도구
```bash
#!/bin/bash
# 성능 진단 스크립트

echo "🔍 성능 진단 시작: $(date)"

# 1. API 응답 시간 측정
echo "⏱️ API 응답 시간 측정:"
endpoints=(
  "https://api.hankook-smartsensor.com/health"
  "https://api.hankook-smartsensor.com/api/vehicles"
  "https://api.hankook-smartsensor.com/api/sensors/status"
)

for endpoint in "${endpoints[@]}"; do
  response_time=$(curl -w "%{time_total}" -s -o /dev/null "$endpoint")
  echo "  $endpoint: ${response_time}s"
done

# 2. 리소스 사용률 확인
echo "💻 리소스 사용률:"
kubectl top nodes
kubectl top pods -A --sort-by=cpu | head -10

# 3. 데이터베이스 성능 확인
echo "🗄️ 데이터베이스 성능:"
kubectl exec -n hankook-smartsensor postgresql-cluster-0 -- \
  psql -U postgres -d hankook_sensors -c "
    SELECT 
      query,
      calls,
      total_time,
      mean_time
    FROM pg_stat_statements 
    WHERE mean_time > 100
    ORDER BY total_time DESC
    LIMIT 10;
  "

# 4. 캐시 히트율 확인
echo "💾 캐시 성능:"
kubectl exec -n hankook-smartsensor redis-cluster-0 -- \
  redis-cli INFO stats | grep cache

echo "✅ 성능 진단 완료"
```

#### 최적화 방법

**API 서버 최적화**
```bash
# 1. 인스턴스 수 증가
kubectl scale deployment api-server --replicas=6 -n hankook-smartsensor

# 2. 리소스 할당 증가
kubectl patch deployment api-server -n hankook-smartsensor -p '
{
  "spec": {
    "template": {
      "spec": {
        "containers": [
          {
            "name": "api-server",
            "resources": {
              "requests": {
                "cpu": "500m",
                "memory": "1Gi"
              },
              "limits": {
                "cpu": "2000m", 
                "memory": "4Gi"
              }
            }
          }
        ]
      }
    }
  }
}'

# 3. JVM 튜닝 (Java 애플리케이션인 경우)
kubectl patch deployment api-server -n hankook-smartsensor -p '
{
  "spec": {
    "template": {
      "spec": {
        "containers": [
          {
            "name": "api-server",
            "env": [
              {
                "name": "JAVA_OPTS",
                "value": "-Xms2g -Xmx4g -XX:+UseG1GC -XX:MaxGCPauseMillis=200"
              }
            ]
          }
        ]
      }
    }
  }
}'
```

**데이터베이스 최적화**
```sql
-- PostgreSQL 성능 튜닝

-- 1. 느린 쿼리 최적화
EXPLAIN ANALYZE SELECT 
    vehicle_id, 
    AVG(value) 
FROM sensors.sensor_data 
WHERE timestamp >= NOW() - INTERVAL '1 hour'
GROUP BY vehicle_id;

-- 2. 인덱스 추가
CREATE INDEX CONCURRENTLY idx_sensor_data_vehicle_timestamp 
ON sensors.sensor_data (vehicle_id, timestamp DESC);

-- 3. 테이블 파티셔닝 확인
SELECT 
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
FROM pg_tables 
WHERE tablename LIKE 'sensor_data%'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- 4. 통계 정보 업데이트
ANALYZE sensors.sensor_data;

-- 5. 자동 VACUUM 설정 최적화
ALTER TABLE sensors.sensor_data SET (
  autovacuum_vacuum_scale_factor = 0.1,
  autovacuum_analyze_scale_factor = 0.05
);
```

### 메모리 부족

#### 증상
- Pod가 OOMKilled 상태
- 시스템 응답 느림
- 스왑 사용량 증가

#### 진단 및 해결
```bash
# 1. 메모리 사용량 분석
kubectl top pods -A --sort-by=memory
kubectl describe node <node-name> | grep -A 5 "Allocated resources"

# 2. OOM 발생 Pod 확인
kubectl get events --sort-by=.metadata.creationTimestamp | grep OOMKilled

# 3. 메모리 리소스 한계 확인
kubectl describe pod <pod-name> -n <namespace> | grep -A 10 "Limits\|Requests"

# 4. 메모리 누수 감지
kubectl exec -n hankook-smartsensor <pod-name> -- \
  ps aux --sort=-%mem | head -10

# 해결 방법: 메모리 한계 증가
kubectl patch deployment <deployment-name> -n <namespace> -p '
{
  "spec": {
    "template": {
      "spec": {
        "containers": [
          {
            "name": "<container-name>",
            "resources": {
              "requests": {
                "memory": "2Gi"
              },
              "limits": {
                "memory": "8Gi"
              }
            }
          }
        ]
      }
    }
  }
}'
```

## 🌐 네트워크 연결 문제

### Service Discovery 문제

#### 증상
- 서비스 간 통신 실패
- "Service not found" 오류
- DNS 해결 실패

#### 진단 및 해결
```bash
# 1. DNS 해결 테스트
kubectl run dns-test --rm -i --restart=Never --image=busybox -- \
  nslookup api-server.hankook-smartsensor.svc.cluster.local

# 2. 서비스 엔드포인트 확인
kubectl get endpoints -n hankook-smartsensor

# 3. CoreDNS 상태 확인
kubectl get pods -n kube-system -l k8s-app=kube-dns
kubectl logs -n kube-system deployment/coredns

# 4. 네트워크 정책 확인
kubectl get networkpolicies -A

# 해결 방법: CoreDNS 재시작
kubectl rollout restart deployment/coredns -n kube-system

# 서비스 재생성
kubectl delete svc api-server -n hankook-smartsensor
kubectl apply -f deployment/applications/api-server.yaml
```

### TLS/SSL 인증서 문제

#### 증상
- HTTPS 연결 실패
- "인증서 유효하지 않음" 오류
- Mixed content 경고

#### 진단 및 해결
```bash
# 1. 인증서 상태 확인
kubectl get certificates -n hankook-smartsensor
kubectl describe certificate hankook-smartsensor-tls -n hankook-smartsensor

# 2. 인증서 만료일 확인
openssl s_client -connect hankook-smartsensor.com:443 -servername hankook-smartsensor.com < /dev/null 2>/dev/null | \
  openssl x509 -noout -dates

# 3. Let's Encrypt ACME Challenge 확인
kubectl get challenges -A

# 4. Cert-manager 로그 확인
kubectl logs -n cert-manager deployment/cert-manager

# 해결 방법: 인증서 갱신 강제 실행
kubectl annotate certificate hankook-smartsensor-tls cert-manager.io/issue-temporary-certificate=true

# 또는 인증서 삭제 후 재생성
kubectl delete certificate hankook-smartsensor-tls -n hankook-smartsensor
kubectl apply -f deployment/certificates/tls-certificate.yaml
```

### 로드 밸런서 문제

#### 증상
- 일부 요청만 실패
- 로드 밸런싱 불균형
- 503 Service Unavailable 오류

#### 진단 및 해결
```bash
# 1. 인그레스 컨트롤러 상태 확인
kubectl get pods -n ingress-nginx -l app.kubernetes.io/component=controller
kubectl logs -n ingress-nginx deployment/ingress-nginx-controller --tail=100

# 2. 백엔드 서비스 헬스 체크
kubectl get endpoints api-server -n hankook-smartsensor
curl -I http://api-server.hankook-smartsensor.svc.cluster.local:8000/health

# 3. 인그레스 설정 확인
kubectl describe ingress hankook-smartsensor-ingress -n hankook-smartsensor

# 해결 방법: 헬스 체크 경로 수정
kubectl patch ingress hankook-smartsensor-ingress -n hankook-smartsensor --type='json' -p='[
  {
    "op": "add",
    "path": "/metadata/annotations/nginx.ingress.kubernetes.io~1backend-protocol",
    "value": "HTTP"
  },
  {
    "op": "add", 
    "path": "/metadata/annotations/nginx.ingress.kubernetes.io~1health-check-path",
    "value": "/health"
  }
]'
```

## 🗄️ 데이터베이스 문제

### 연결 한계 초과

#### 증상
- "Too many connections" 오류
- 새로운 연결 생성 실패
- 애플리케이션 응답 없음

#### 진단 및 해결
```bash
# 1. 현재 연결 수 확인
kubectl exec -n hankook-smartsensor postgresql-cluster-0 -- \
  psql -U postgres -c "
    SELECT 
      count(*) as total_connections,
      count(*) filter (where state = 'active') as active_connections,
      count(*) filter (where state = 'idle') as idle_connections
    FROM pg_stat_activity;
  "

# 2. 최대 연결 수 확인
kubectl exec -n hankook-smartsensor postgresql-cluster-0 -- \
  psql -U postgres -c "SHOW max_connections;"

# 3. 연결별 쿼리 확인
kubectl exec -n hankook-smartsensor postgresql-cluster-0 -- \
  psql -U postgres -c "
    SELECT 
      pid,
      usename,
      application_name,
      client_addr,
      state,
      query_start,
      query
    FROM pg_stat_activity 
    WHERE state = 'active'
    ORDER BY query_start;
  "

# 해결 방법: 유휴 연결 정리
kubectl exec -n hankook-smartsensor postgresql-cluster-0 -- \
  psql -U postgres -c "
    SELECT pg_terminate_backend(pid) 
    FROM pg_stat_activity 
    WHERE state = 'idle' 
      AND query_start < now() - interval '10 minutes'
      AND usename != 'postgres';
  "

# max_connections 설정 증가
kubectl patch postgresql postgresql-cluster -n hankook-smartsensor --type='json' -p='[
  {
    "op": "replace",
    "path": "/spec/postgresql/parameters/max_connections",
    "value": "200"
  }
]'
```

### 성능 저하

#### 증상
- 쿼리 실행 시간 증가
- 높은 CPU 사용률
- 잠금 대기 시간 증가

#### 진단 및 최적화
```sql
-- 1. 느린 쿼리 식별
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

-- 2. 블로킹 쿼리 확인
SELECT 
  bl.pid AS blocked_pid,
  bl.usename AS blocked_user,
  bl.query AS blocked_query,
  ka.pid AS blocking_pid,
  ka.usename AS blocking_user,
  ka.query AS blocking_query
FROM pg_stat_activity bl
JOIN pg_stat_activity ka ON bl.wait_event_type = 'Lock' 
WHERE bl.wait_event_type = 'Lock'
  AND bl.pid != ka.pid;

-- 3. 인덱스 사용률 분석
SELECT 
  schemaname,
  tablename,
  indexname,
  idx_scan,
  idx_tup_read,
  idx_tup_fetch
FROM pg_stat_user_indexes
WHERE idx_scan < 100  -- 사용되지 않는 인덱스
ORDER BY pg_relation_size(indexrelid) DESC;

-- 4. 테이블 통계 업데이트
ANALYZE;

-- 5. 불필요한 인덱스 제거
DROP INDEX CONCURRENTLY IF EXISTS unused_index_name;

-- 6. 필요한 인덱스 추가
CREATE INDEX CONCURRENTLY idx_sensor_data_vehicle_timestamp 
ON sensors.sensor_data (vehicle_id, timestamp DESC)
WHERE timestamp >= NOW() - INTERVAL '30 days';
```

### 백업 및 복구 문제

#### 백업 실패
```bash
# 1. 백업 프로세스 상태 확인
kubectl get cronjobs -n hankook-smartsensor
kubectl get jobs -n hankook-smartsensor

# 2. 백업 로그 확인
kubectl logs job/postgresql-backup-$(date +%Y%m%d) -n hankook-smartsensor

# 3. 디스크 공간 확인
kubectl exec -n hankook-smartsensor postgresql-cluster-0 -- df -h

# 4. 백업 수동 실행
kubectl create job postgresql-backup-manual --from=cronjob/postgresql-backup -n hankook-smartsensor
```

#### 복구 테스트
```bash
# 1. 테스트 환경에서 복구 실행
kubectl create namespace backup-test
kubectl apply -f deployment/databases/postgresql-test.yaml -n backup-test

# 2. 백업 파일 복원
BACKUP_FILE="postgresql_backup_20240126.sql.gz"
gunzip -c /backups/postgresql/$BACKUP_FILE | \
  kubectl exec -i -n backup-test postgresql-test-0 -- \
  psql -U postgres

# 3. 데이터 무결성 검증
kubectl exec -n backup-test postgresql-test-0 -- \
  psql -U postgres -d hankook_sensors -c "
    SELECT 
      'sensor_data' as table_name,
      COUNT(*) as record_count,
      MIN(timestamp) as earliest_data,
      MAX(timestamp) as latest_data
    FROM sensors.sensor_data;
  "
```

## 🔐 보안 관련 문제

### 인증 토큰 문제

#### 증상
- "Invalid token" 오류
- 토큰 만료 후 자동 갱신 실패
- 403 Forbidden 오류

#### 진단 및 해결
```bash
# 1. JWT 토큰 검증
TOKEN="eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
echo $TOKEN | cut -d. -f2 | base64 -d | jq .

# 2. OAuth2 서버 상태 확인
kubectl get pods -n hankook-security -l app=oauth2-server
kubectl logs -n hankook-security deployment/oauth2-server --tail=50

# 3. 토큰 시크릿 확인
kubectl get secret jwt-secrets -n hankook-security -o yaml

# 4. 시간 동기화 확인
kubectl exec -n hankook-security oauth2-server-0 -- date

# 해결 방법: 토큰 갱신
curl -X POST https://api.hankook-smartsensor.com/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{
    "refresh_token": "your_refresh_token_here",
    "grant_type": "refresh_token"
  }'
```

### RBAC 권한 문제

#### 증상
- "Permission denied" 오류
- 특정 기능에 접근할 수 없음
- API 호출이 403 오류 반환

#### 진단 및 해결
```bash
# 1. 사용자 권한 확인
kubectl auth can-i get pods --as=user@company.com
kubectl auth can-i "*" --as=user@company.com

# 2. 역할 바인딩 확인
kubectl get rolebindings,clusterrolebindings -A | grep user@company.com

# 3. 서비스 어카운트 권한 확인
kubectl describe serviceaccount api-server -n hankook-smartsensor

# 해결 방법: 권한 추가
kubectl create rolebinding user-access \
  --clusterrole=view \
  --user=user@company.com \
  --namespace=hankook-smartsensor
```

### 네트워크 보안 정책 문제

#### 증상
- 서비스 간 통신 차단
- "Connection refused" 오류
- 예상하지 못한 트래픽 차단

#### 진단 및 해결
```bash
# 1. 네트워크 정책 확인
kubectl get networkpolicies -A
kubectl describe networkpolicy default-deny -n hankook-smartsensor

# 2. 통신 테스트
kubectl run network-test --rm -i --restart=Never --image=busybox -- \
  wget -qO- --timeout=5 http://api-server.hankook-smartsensor.svc.cluster.local:8000/health

# 3. 방화벽 규칙 확인
kubectl logs -n hankook-security deployment/network-security-manager

# 해결 방법: 임시 정책 완화
kubectl patch networkpolicy default-deny -n hankook-smartsensor -p '
{
  "spec": {
    "egress": [
      {
        "to": [],
        "ports": [
          {
            "protocol": "TCP",
            "port": 53
          },
          {
            "protocol": "UDP", 
            "port": 53
          }
        ]
      }
    ]
  }
}'
```

## 📊 모니터링 문제

### Prometheus 메트릭 수집 실패

#### 증상
- Grafana 대시보드에 데이터 없음
- "No data" 메시지 표시
- 알림이 작동하지 않음

#### 진단 및 해결
```bash
# 1. Prometheus 상태 확인
kubectl get pods -n monitoring -l app=prometheus
kubectl logs -n monitoring prometheus-0

# 2. ServiceMonitor 확인
kubectl get servicemonitors -n monitoring
kubectl describe servicemonitor hankook-smartsensor-monitor -n monitoring

# 3. 메트릭 엔드포인트 테스트
kubectl port-forward -n hankook-smartsensor svc/api-server 8080:8080 &
curl http://localhost:8080/metrics

# 4. Prometheus 설정 확인
kubectl exec -n monitoring prometheus-0 -- \
  promtool config check /etc/prometheus/prometheus.yml

# 해결 방법: ServiceMonitor 재생성
kubectl delete servicemonitor hankook-smartsensor-monitor -n monitoring
kubectl apply -f monitoring/servicemonitors/
```

### Grafana 대시보드 문제

#### 증상
- 대시보드가 로드되지 않음
- 패널에 오류 메시지 표시
- 데이터 소스 연결 실패

#### 진단 및 해결
```bash
# 1. Grafana 상태 확인
kubectl get pods -n monitoring -l app=grafana
kubectl logs -n monitoring deployment/grafana

# 2. 데이터 소스 연결 테스트
kubectl port-forward -n monitoring svc/grafana 3000:3000 &
# 브라우저에서 http://localhost:3000 접속하여 데이터 소스 테스트

# 3. 대시보드 JSON 유효성 확인
kubectl get configmap grafana-dashboards -n monitoring -o yaml

# 해결 방법: Grafana 재시작
kubectl rollout restart deployment/grafana -n monitoring

# 대시보드 재로드
kubectl delete configmap grafana-dashboards -n monitoring
kubectl apply -f monitoring/dashboards/
```

### AlertManager 알림 문제

#### 증상
- 알림이 전송되지 않음
- 이메일이나 Slack 메시지 수신 안됨
- 알림 규칙이 트리거되지 않음

#### 진단 및 해결
```bash
# 1. AlertManager 상태 확인
kubectl get pods -n monitoring -l app=alertmanager
kubectl logs -n monitoring alertmanager-0

# 2. 알림 규칙 확인
kubectl get prometheusrules -n monitoring
kubectl describe prometheusrule hankook-smartsensor-alerts -n monitoring

# 3. AlertManager 설정 확인
kubectl get secret alertmanager-config -n monitoring -o yaml

# 4. 알림 테스트
curl -X POST http://alertmanager.monitoring.svc.cluster.local:9093/api/v1/alerts \
  -H "Content-Type: application/json" \
  -d '[
    {
      "labels": {
        "alertname": "TestAlert",
        "severity": "warning"
      },
      "annotations": {
        "summary": "Test alert message"
      }
    }
  ]'

# 해결 방법: 설정 업데이트
kubectl patch secret alertmanager-config -n monitoring -p '
{
  "data": {
    "alertmanager.yml": "'$(cat alertmanager.yml | base64 -w 0)'"
  }
}'
```

## 🛠️ 진단 도구

### 종합 진단 스크립트

```bash
#!/bin/bash
# 시스템 종합 진단 스크립트

echo "🔍 HankookTire SmartSensor 2.0 시스템 진단 시작"
echo "================================================="

# 1. 클러스터 기본 상태
echo "☸️ Kubernetes 클러스터 상태:"
kubectl cluster-info
kubectl get nodes -o wide

# 2. 네임스페이스별 Pod 상태
echo "📦 Pod 상태 확인:"
namespaces=("hankook-smartsensor" "hankook-security" "monitoring")
for ns in "${namespaces[@]}"; do
  echo "  Namespace: $ns"
  kubectl get pods -n $ns | grep -v Running | grep -v Completed || echo "    ✅ 모든 Pod 정상"
done

# 3. 서비스 Health Check
echo "🏥 서비스 Health Check:"
services=(
  "https://hankook-smartsensor.com/health"
  "https://api.hankook-smartsensor.com/health"
)

for service in "${services[@]}"; do
  if curl -sf --max-time 10 "$service" > /dev/null; then
    echo "  ✅ $service"
  else
    echo "  ❌ $service"
  fi
done

# 4. 데이터베이스 연결 테스트
echo "🗄️ 데이터베이스 연결 테스트:"
kubectl exec -n hankook-smartsensor postgresql-cluster-0 -- \
  psql -U postgres -c "SELECT 1;" > /dev/null && \
  echo "  ✅ PostgreSQL 연결 성공" || \
  echo "  ❌ PostgreSQL 연결 실패"

# 5. 리소스 사용량 확인
echo "💻 리소스 사용량:"
kubectl top nodes 2>/dev/null || echo "  ⚠️ 메트릭 서버를 사용할 수 없습니다"

# 6. 스토리지 상태
echo "💾 스토리지 상태:"
kubectl get pvc -A | grep -v Bound || echo "  ✅ 모든 PVC 정상"

# 7. 인증서 만료 확인
echo "📜 SSL 인증서 상태:"
kubectl get certificates -A -o custom-columns=\
"NAME:.metadata.name,NAMESPACE:.metadata.namespace,READY:.status.conditions[0].status"

# 8. 최근 이벤트 확인
echo "📅 최근 이벤트 (경고/오류):"
kubectl get events -A --field-selector type=Warning --sort-by=.metadata.creationTimestamp | tail -5

echo "================================================="
echo "✅ 시스템 진단 완료: $(date)"
```

### 로그 수집 스크립트

```bash
#!/bin/bash
# 로그 수집 스크립트

LOG_DIR="troubleshooting_logs_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$LOG_DIR"

echo "📋 로그 수집 시작: $LOG_DIR"

# 1. 클러스터 정보
kubectl cluster-info > "$LOG_DIR/cluster-info.txt"
kubectl get nodes -o wide > "$LOG_DIR/nodes.txt"
kubectl get pods -A -o wide > "$LOG_DIR/all-pods.txt"

# 2. 애플리케이션 로그
namespaces=("hankook-smartsensor" "hankook-security" "monitoring")
for ns in "${namespaces[@]}"; do
  mkdir -p "$LOG_DIR/$ns"
  
  # Pod 로그 수집
  kubectl get pods -n $ns -o name | while read pod; do
    pod_name=$(echo $pod | cut -d/ -f2)
    kubectl logs $pod -n $ns --previous --tail=1000 > "$LOG_DIR/$ns/${pod_name}-previous.log" 2>/dev/null || true
    kubectl logs $pod -n $ns --tail=1000 > "$LOG_DIR/$ns/${pod_name}.log" 2>/dev/null || true
  done
  
  # 리소스 상태
  kubectl describe pods -n $ns > "$LOG_DIR/$ns/pod-descriptions.txt"
  kubectl get events -n $ns --sort-by=.metadata.creationTimestamp > "$LOG_DIR/$ns/events.txt"
done

# 3. 설정 파일
kubectl get configmaps -A -o yaml > "$LOG_DIR/configmaps.yaml"
kubectl get secrets -A -o yaml > "$LOG_DIR/secrets.yaml"

# 4. 네트워크 정보
kubectl get ingress -A -o yaml > "$LOG_DIR/ingress.yaml"
kubectl get services -A -o wide > "$LOG_DIR/services.txt"
kubectl get networkpolicies -A -o yaml > "$LOG_DIR/networkpolicies.yaml"

# 5. 압축
tar -czf "${LOG_DIR}.tar.gz" "$LOG_DIR"
rm -rf "$LOG_DIR"

echo "✅ 로그 수집 완료: ${LOG_DIR}.tar.gz"
echo "📧 기술 지원팀에 이 파일을 전송하세요"
```

## 🚀 고급 문제 해결

### 메모리 누수 분석

```bash
#!/bin/bash
# 메모리 누수 분석 스크립트

POD_NAME=${1:-"api-server"}
NAMESPACE=${2:-"hankook-smartsensor"}

echo "🔍 메모리 누수 분석: $POD_NAME"

# 1. 현재 메모리 사용량
kubectl top pod $POD_NAME -n $NAMESPACE

# 2. 메모리 사용량 히스토리 (Prometheus)
kubectl port-forward -n monitoring svc/prometheus 9090:9090 &
PROM_PID=$!

sleep 5

# 지난 6시간 메모리 사용량 쿼리
curl -s "http://localhost:9090/api/v1/query_range?query=container_memory_usage_bytes{pod=\"$POD_NAME\"}&start=$(date -d '6 hours ago' +%s)&end=$(date +%s)&step=300" | \
  jq -r '.data.result[0].values[] | "\(.[0]) \(.[1])"' > memory_usage.txt

kill $PROM_PID

# 3. 메모리 사용량 트렌드 분석
python3 << EOF
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime

# 데이터 로드
times = []
values = []

with open('memory_usage.txt', 'r') as f:
    for line in f:
        timestamp, value = line.strip().split()
        times.append(datetime.fromtimestamp(float(timestamp)))
        values.append(float(value) / 1024 / 1024)  # MB로 변환

if times:
    # 트렌드 계산
    x = np.arange(len(values))
    z = np.polyfit(x, values, 1)
    trend = z[0]
    
    print(f"메모리 사용량 트렌드: {trend:.2f} MB/시간")
    
    if trend > 10:  # 시간당 10MB 이상 증가
        print("⚠️ 메모리 누수 의심")
    else:
        print("✅ 메모리 사용량 정상")
        
    # 그래프 생성
    plt.figure(figsize=(12, 6))
    plt.plot(times, values, label='메모리 사용량')
    plt.plot(times, np.polyval(z, x), '--r', label=f'트렌드 (기울기: {trend:.2f})')
    plt.xlabel('시간')
    plt.ylabel('메모리 사용량 (MB)')
    plt.title(f'{POD_NAME} 메모리 사용량 분석')
    plt.legend()
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig('memory_analysis.png')
    print("📊 그래프 저장: memory_analysis.png")
EOF

# 4. JVM 메모리 덤프 (Java 애플리케이션인 경우)
kubectl exec -n $NAMESPACE $POD_NAME -- \
  jcmd 1 GC.run_finalization 2>/dev/null || echo "Java 애플리케이션이 아니거나 JVM 명령 사용 불가"

echo "✅ 메모리 누수 분석 완료"
```

### 네트워크 패킷 분석

```bash
#!/bin/bash
# 네트워크 패킷 분석

NODE_NAME=${1:-$(kubectl get nodes -o name | head -1 | cut -d/ -f2)}
POD_NAME=${2:-"api-server"}
NAMESPACE=${3:-"hankook-smartsensor"}

echo "🌐 네트워크 패킷 분석: $POD_NAME on $NODE_NAME"

# 1. Pod의 네트워크 인터페이스 확인
POD_IP=$(kubectl get pod $POD_NAME -n $NAMESPACE -o jsonpath='{.status.podIP}')
echo "Pod IP: $POD_IP"

# 2. 노드에서 tcpdump 실행
kubectl debug node/$NODE_NAME -it --image=nicolaka/netshoot -- \
  tcpdump -i any host $POD_IP -w /tmp/packet_capture.pcap -c 1000

# 3. 패킷 캡처 파일 분석
kubectl debug node/$NODE_NAME -it --image=nicolaka/netshoot -- \
  tshark -r /tmp/packet_capture.pcap -T fields -e frame.time -e ip.src -e ip.dst -e tcp.port

echo "✅ 네트워크 패킷 분석 완료"
```

### 성능 프로파일링

```bash
#!/bin/bash
# 애플리케이션 성능 프로파일링

POD_NAME=${1:-"api-server"}
NAMESPACE=${2:-"hankook-smartsensor"}
DURATION=${3:-60}  # 초

echo "⚡ 성능 프로파일링: $POD_NAME ($DURATION초)"

# 1. CPU 프로파일링 (Java 애플리케이션)
kubectl exec -n $NAMESPACE $POD_NAME -- \
  timeout $DURATION jstack 1 > cpu_profile.txt 2>/dev/null || \
  echo "Java 프로파일링 불가 - 다른 방법 시도"

# 2. 시스템 리소스 모니터링
kubectl exec -n $NAMESPACE $POD_NAME -- \
  top -b -n $(($DURATION/5)) -d 5 > system_profile.txt &

# 3. 네트워크 통계
kubectl exec -n $NAMESPACE $POD_NAME -- \
  netstat -s > network_stats_before.txt

sleep $DURATION

kubectl exec -n $NAMESPACE $POD_NAME -- \
  netstat -s > network_stats_after.txt

# 4. 결과 분석
echo "📊 프로파일링 결과 분석:"
echo "CPU 사용량 히스토리:"
kubectl exec -n $NAMESPACE $POD_NAME -- \
  awk '/^%Cpu/ {print $2}' system_profile.txt | \
  sed 's/%us,//' | sort -n | tail -5

echo "메모리 사용량 히스토리:"  
kubectl exec -n $NAMESPACE $POD_NAME -- \
  awk '/^KiB Mem/ {print $8}' system_profile.txt | \
  sed 's/free//' | sort -n | head -5

echo "✅ 성능 프로파일링 완료"
```

## 📞 지원 요청

### 기술 지원 연락처

**긴급 상황 (24/7)**
- 전화: +82-2-1234-5678
- 이메일: emergency@hankook-smartsensor.com
- Slack: #emergency-support

**일반 기술 지원**
- 이메일: support@hankook-smartsensor.com
- 티켓 시스템: https://support.hankook-smartsensor.com
- 커뮤니티: https://forum.hankook-smartsensor.com

### 지원 요청 시 필요 정보

1. **시스템 정보**
   - Kubernetes 버전
   - 노드 구성 및 리소스
   - 네트워크 설정

2. **문제 상황**
   - 발생 시간 및 빈도
   - 오류 메시지
   - 재현 단계

3. **로그 및 진단 데이터**
   - 종합 진단 스크립트 결과
   - 로그 수집 스크립트 출력
   - 관련 스크린샷

4. **영향 범위**
   - 영향받는 사용자 수
   - 비즈니스 임팩트
   - 긴급도

---

**🛠️ 문제를 신속하게 해결하여 시스템을 안정적으로 유지하세요!**

© 2024 HankookTire SmartSensor 2.0. All rights reserved.