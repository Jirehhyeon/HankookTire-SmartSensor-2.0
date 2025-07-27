# 🚀 SmartTire SmartSensor 2.0 - Kubernetes 배포 가이드

## 📋 목차
1. [사전 요구사항](#사전-요구사항)
2. [배포 준비](#배포-준비)
3. [보안 설정](#보안-설정)
4. [순차적 배포](#순차적-배포)
5. [모니터링 설정](#모니터링-설정)
6. [검증 및 테스트](#검증-및-테스트)
7. [운영 및 유지보수](#운영-및-유지보수)
8. [문제 해결](#문제-해결)

## 🔧 사전 요구사항

### Kubernetes 클러스터
- **Kubernetes 버전**: 1.25+ 권장
- **노드 수**: 최소 3개 (Master 1개, Worker 2개 이상)
- **리소스 요구사항**:
  - CPU: 최소 8 cores (권장 16 cores)
  - Memory: 최소 16GB (권장 32GB)
  - Storage: 최소 500GB SSD

### 필수 도구 설치
```bash
# kubectl 설치 확인
kubectl version --client

# kustomize 설치 확인
kustomize version

# helm 설치 (선택사항)
helm version
```

### 스토리지 클래스 준비
```bash
# 스토리지 클래스 확인
kubectl get storageclass

# 필요한 스토리지 클래스:
# - fast-ssd: 고성능 SSD (데이터베이스용)
# - standard: 표준 스토리지 (로그, 백업용)
```

## 🛠️ 배포 준비

### 1. 소스 코드 클론
```bash
git clone https://github.com/hankook/smartsensor-2.0.git
cd smartsensor-2.0/deployment/kubernetes
```

### 2. 환경 변수 설정
```bash
# 환경 설정 파일 생성
cp .env.example .env

# 환경 변수 편집
vim .env
```

### 3. 도커 이미지 빌드 및 푸시
```bash
# API 서버 이미지 빌드
cd ../../backend
docker build -t hankook/smartsensor-api:2.0.0 .
docker push hankook/smartsensor-api:2.0.0

# 프론트엔드 이미지 빌드
cd ../frontend
docker build -t hankook/smartsensor-frontend:2.0.0 .
docker push hankook/smartsensor-frontend:2.0.0
```

## 🔐 보안 설정

### 1. Secrets 생성 (중요!)
```bash
# ⚠️ secrets.yaml 파일의 기본값들을 실제 보안 값으로 변경
# 실제 운영환경에서는 다음과 같이 생성:

# 데이터베이스 자격증명
kubectl create secret generic database-credentials \
  --from-literal=username='hankook' \
  --from-literal=password='강력한패스워드123!' \
  --from-literal=url='postgresql://hankook:강력한패스워드123!@postgres-service:5432/hankook_sensors' \
  -n hankook-smartsensor

# Redis 자격증명
kubectl create secret generic redis-credentials \
  --from-literal=password='Redis강력한패스워드456!' \
  -n hankook-smartsensor

# MQTT 자격증명
kubectl create secret generic mosquitto-credentials \
  --from-literal=username='hankook' \
  --from-literal=password='MQTT강력한패스워드789!' \
  -n hankook-smartsensor

# Grafana 자격증명
kubectl create secret generic grafana-credentials \
  --from-literal=admin-password='Grafana관리자패스워드!' \
  -n hankook-smartsensor
```

### 2. TLS 인증서 설정
```bash
# Let's Encrypt Cert-Manager 설치 (선택사항)
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.0/cert-manager.yaml

# 또는 기존 인증서 사용
kubectl create secret tls hankook-smartsensor-tls \
  --cert=path/to/certificate.crt \
  --key=path/to/private.key \
  -n hankook-smartsensor
```

## 🚀 순차적 배포

### 1단계: 네임스페이스 및 기본 설정
```bash
# 네임스페이스 생성
kubectl apply -f namespace.yaml

# 네임스페이스 확인
kubectl get namespace hankook-smartsensor
```

### 2단계: 데이터베이스 배포
```bash
# PostgreSQL 배포
kubectl apply -f database-deployment.yaml

# 배포 상태 확인
kubectl get pods -n hankook-smartsensor -l app=postgres
kubectl logs -n hankook-smartsensor -l app=postgres

# 데이터베이스 준비 상태 확인
kubectl wait --for=condition=ready pod -l app=postgres -n hankook-smartsensor --timeout=300s
```

### 3단계: 캐시 및 메시징 서비스
```bash
# Redis 배포
kubectl apply -f redis-deployment.yaml

# MQTT 브로커 배포
kubectl apply -f mqtt-deployment.yaml

# 서비스 상태 확인
kubectl get pods -n hankook-smartsensor -l component=cache
kubectl get pods -n hankook-smartsensor -l component=mqtt-broker
```

### 4단계: 애플리케이션 서비스
```bash
# API 서버 배포
kubectl apply -f api-deployment.yaml

# 배포 상태 확인
kubectl get deployment -n hankook-smartsensor hankook-api
kubectl rollout status deployment/hankook-api -n hankook-smartsensor
```

### 5단계: 웹 인터페이스 및 라우팅
```bash
# 프론트엔드 및 Ingress 배포
kubectl apply -f ingress-nginx.yaml

# Ingress 상태 확인
kubectl get ingress -n hankook-smartsensor
```

### 6단계: 모니터링 스택
```bash
# Prometheus, Grafana, Node Exporter 배포
kubectl apply -f monitoring-stack.yaml

# 모니터링 서비스 확인
kubectl get pods -n hankook-smartsensor -l component=monitoring
```

## 📊 모니터링 설정

### Grafana 대시보드 접속
```bash
# Grafana 서비스 포트포워딩
kubectl port-forward -n hankook-smartsensor svc/grafana-service 3000:3000

# 브라우저에서 http://localhost:3000 접속
# 기본 로그인: admin / (secrets.yaml에서 설정한 패스워드)
```

### Prometheus 접속
```bash
# Prometheus 포트포워딩
kubectl port-forward -n hankook-smartsensor svc/prometheus-service 9090:9090

# 브라우저에서 http://localhost:9090 접속
```

### 대시보드 설정
1. Grafana에서 Prometheus 데이터소스 추가
2. 사전 정의된 대시보드 임포트
3. 알림 규칙 설정

## ✅ 검증 및 테스트

### 1. 서비스 상태 확인
```bash
# 모든 Pod 상태 확인
kubectl get pods -n hankook-smartsensor

# 서비스 상태 확인
kubectl get services -n hankook-smartsensor

# PVC 상태 확인
kubectl get pvc -n hankook-smartsensor
```

### 2. API 테스트
```bash
# API 헬스체크
curl -k https://api.hankook-smartsensor.com/health

# 웹소켓 연결 테스트
curl -k -H "Connection: Upgrade" -H "Upgrade: websocket" \
  https://api.hankook-smartsensor.com/ws
```

### 3. 데이터베이스 연결 테스트
```bash
# PostgreSQL 포트포워딩
kubectl port-forward -n hankook-smartsensor svc/postgres-service 5432:5432

# 데이터베이스 연결 테스트
psql -h localhost -p 5432 -U hankook -d hankook_sensors -c "SELECT version();"
```

### 4. MQTT 브로커 테스트
```bash
# MQTT 포트포워딩
kubectl port-forward -n hankook-smartsensor svc/mosquitto-service 1883:1883

# MQTT 클라이언트로 테스트
mosquitto_pub -h localhost -p 1883 -t test/topic -m "Hello SmartTire!"
mosquitto_sub -h localhost -p 1883 -t test/topic
```

## 🔧 운영 및 유지보수

### 로그 모니터링
```bash
# API 서버 로그 확인
kubectl logs -n hankook-smartsensor -l app=hankook-api -f

# 전체 시스템 로그 스트리밍
kubectl logs -n hankook-smartsensor --all-containers=true -f
```

### 스케일링
```bash
# API 서버 스케일 아웃
kubectl scale deployment hankook-api --replicas=5 -n hankook-smartsensor

# HPA 상태 확인
kubectl get hpa -n hankook-smartsensor
```

### 업데이트 배포
```bash
# 롤링 업데이트
kubectl set image deployment/hankook-api \
  api=hankook/smartsensor-api:2.0.1 \
  -n hankook-smartsensor

# 롤백
kubectl rollout undo deployment/hankook-api -n hankook-smartsensor
```

### 백업
```bash
# 데이터베이스 백업
kubectl exec -n hankook-smartsensor postgres-0 -- \
  pg_dump -U hankook hankook_sensors > backup_$(date +%Y%m%d_%H%M%S).sql

# PVC 스냅샷 (CSI 드라이버 지원 시)
kubectl create volumesnapshot postgres-snapshot \
  --volumesnapshotclass=csi-snapshot-class \
  --source-name=postgres-storage-postgres-0 \
  -n hankook-smartsensor
```

## 🐛 문제 해결

### 일반적인 문제들

#### Pod가 Pending 상태
```bash
# 리소스 부족 확인
kubectl describe pod <pod-name> -n hankook-smartsensor
kubectl top nodes
kubectl top pods -n hankook-smartsensor
```

#### ImagePullBackOff 오류
```bash
# 이미지 확인
kubectl describe pod <pod-name> -n hankook-smartsensor

# 이미지 레지스트리 자격증명 확인
kubectl get secrets -n hankook-smartsensor
```

#### PVC 마운트 실패
```bash
# 스토리지 클래스 확인
kubectl get storageclass
kubectl describe pvc <pvc-name> -n hankook-smartsensor
```

#### 네트워크 연결 문제
```bash
# 서비스 엔드포인트 확인
kubectl get endpoints -n hankook-smartsensor

# 네트워크 정책 확인
kubectl get networkpolicy -n hankook-smartsensor
```

### 디버깅 도구
```bash
# 문제 해결용 busybox Pod 실행
kubectl run debug-pod --image=busybox --rm -it --restart=Never \
  -n hankook-smartsensor -- sh

# 클러스터 내부에서 서비스 테스트
nslookup postgres-service.hankook-smartsensor.svc.cluster.local
wget -O- http://api-service:8000/health
```

## 📞 지원 및 문의

- **기술 지원**: tech-support@hankook-smartsensor.com
- **문서**: https://docs.hankook-smartsensor.com
- **이슈 트래킹**: https://github.com/hankook/smartsensor-2.0/issues

---

## 🎯 성능 최적화 팁

1. **리소스 요청/제한 튜닝**: 실제 사용량에 맞게 조정
2. **HPA 설정**: CPU/메모리 기반 자동 스케일링
3. **노드 어피니티**: 워크로드별 적절한 노드 배치
4. **PDB 설정**: 서비스 가용성 보장
5. **모니터링**: Prometheus/Grafana 메트릭 활용

## 🔒 보안 체크리스트

- [ ] 모든 기본 패스워드 변경
- [ ] TLS 인증서 적용
- [ ] RBAC 정책 설정
- [ ] 네트워크 정책 구성
- [ ] Pod 보안 정책 적용
- [ ] Secret 로테이션 계획
- [ ] 취약점 스캔 정기 실행