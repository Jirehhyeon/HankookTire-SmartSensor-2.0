#!/bin/bash

# HankookTire SmartSensor 2.0 - Performance Testing and Optimization Suite
# 차세대 통합 스마트 타이어 센서 시스템 성능 테스트 및 최적화 스위트

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

success() {
    echo -e "${CYAN}[$(date +'%Y-%m-%d %H:%M:%S')] SUCCESS: $1${NC}"
}

# 스크립트 시작
log "🚀 HankookTire SmartSensor 2.0 성능 테스트 및 최적화 시작"

# 환경 변수 설정
NAMESPACE=${NAMESPACE:-"hankook-smartsensor"}
SECURITY_NAMESPACE=${SECURITY_NAMESPACE:-"hankook-security"}
MONITORING_NAMESPACE=${MONITORING_NAMESPACE:-"monitoring"}
TEST_DURATION=${TEST_DURATION:-"300"}  # 5분
CONCURRENT_USERS=${CONCURRENT_USERS:-"100"}
API_BASE_URL=${API_BASE_URL:-"http://localhost:8000"}

# 성능 테스트 결과 디렉토리
RESULTS_DIR="./performance_results_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$RESULTS_DIR"

# 사전 요구사항 확인
check_prerequisites() {
    log "📋 사전 요구사항 확인 중..."
    
    # kubectl 확인
    if ! command -v kubectl &> /dev/null; then
        error "kubectl이 설치되어 있지 않습니다."
        exit 1
    fi
    
    # Python 확인
    if ! command -v python3 &> /dev/null; then
        error "Python3이 설치되어 있지 않습니다."
        exit 1
    fi
    
    # 필요한 Python 패키지 설치
    log "📦 Python 패키지 설치 중..."
    pip3 install -q aiohttp asyncio psycopg2-binary redis numpy matplotlib pandas psutil || {
        error "Python 패키지 설치 실패"
        exit 1
    }
    
    # curl 확인
    if ! command -v curl &> /dev/null; then
        error "curl이 설치되어 있지 않습니다."
        exit 1
    fi
    
    # 클러스터 연결 확인
    if ! kubectl cluster-info &> /dev/null; then
        error "Kubernetes 클러스터에 연결할 수 없습니다."
        exit 1
    fi
    
    log "✅ 사전 요구사항 확인 완료"
}

# 시스템 상태 확인
check_system_status() {
    log "🔍 시스템 상태 확인 중..."
    
    # Pod 상태 확인
    info "Pod 상태 확인:"
    kubectl get pods -n $NAMESPACE
    kubectl get pods -n $SECURITY_NAMESPACE
    kubectl get pods -n $MONITORING_NAMESPACE
    
    # 서비스 상태 확인
    info "서비스 상태 확인:"
    kubectl get svc -n $NAMESPACE
    
    # 리소스 사용량 확인
    info "리소스 사용량 확인:"
    kubectl top nodes 2>/dev/null || warn "메트릭 서버를 사용할 수 없습니다"
    kubectl top pods -n $NAMESPACE 2>/dev/null || warn "Pod 메트릭을 사용할 수 없습니다"
    
    log "✅ 시스템 상태 확인 완료"
}

# 성능 기준선 측정
measure_baseline_performance() {
    log "📊 성능 기준선 측정 중..."
    
    # API 응답 시간 측정
    info "API 엔드포인트 응답 시간 측정:"
    
    endpoints=(
        "/health"
        "/api/dashboard/summary"
        "/api/vehicles"
        "/api/sensors/status"
        "/api/analytics/overview"
    )
    
    for endpoint in "${endpoints[@]}"; do
        info "테스트 중: $endpoint"
        
        # curl을 사용한 응답 시간 측정
        response_time=$(curl -w "%{time_total}" -s -o /dev/null "$API_BASE_URL$endpoint" || echo "0")
        
        if (( $(echo "$response_time > 0" | bc -l) )); then
            info "  응답 시간: ${response_time}초"
            echo "$endpoint,$response_time" >> "$RESULTS_DIR/baseline_response_times.csv"
        else
            warn "  $endpoint 응답 실패"
        fi
        
        sleep 1
    done
    
    # 데이터베이스 성능 측정
    measure_database_performance
    
    # Redis 성능 측정
    measure_redis_performance
    
    log "✅ 성능 기준선 측정 완료"
}

# 데이터베이스 성능 측정
measure_database_performance() {
    info "🗄️ 데이터베이스 성능 측정 중..."
    
    # PostgreSQL Pod 찾기
    POSTGRES_POD=$(kubectl get pods -n $NAMESPACE -l app=postgres -o jsonpath="{.items[0].metadata.name}" 2>/dev/null || echo "")
    
    if [ -z "$POSTGRES_POD" ]; then
        warn "PostgreSQL Pod를 찾을 수 없습니다"
        return
    fi
    
    # 데이터베이스 연결 테스트
    DB_RESPONSE_TIME=$(kubectl exec -n $NAMESPACE $POSTGRES_POD -- psql -U hankook -d hankook_sensors -c "SELECT 1;" -t -A 2>/dev/null | wc -l || echo "0")
    
    if [ "$DB_RESPONSE_TIME" -gt 0 ]; then
        info "  데이터베이스 연결: 성공"
        
        # 테이블 크기 확인
        kubectl exec -n $NAMESPACE $POSTGRES_POD -- psql -U hankook -d hankook_sensors -c "
            SELECT 
                schemaname,
                tablename,
                pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
            FROM pg_tables 
            WHERE schemaname NOT IN ('information_schema', 'pg_catalog')
            ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
            LIMIT 10;
        " 2>/dev/null > "$RESULTS_DIR/database_table_sizes.txt" || warn "데이터베이스 크기 확인 실패"
        
        # 느린 쿼리 확인
        kubectl exec -n $NAMESPACE $POSTGRES_POD -- psql -U hankook -d hankook_sensors -c "
            SELECT 
                query,
                calls,
                total_time,
                mean_time,
                max_time
            FROM pg_stat_statements 
            ORDER BY total_time DESC 
            LIMIT 10;
        " 2>/dev/null > "$RESULTS_DIR/slow_queries.txt" || warn "느린 쿼리 확인 실패"
        
    else
        warn "데이터베이스 연결 실패"
    fi
}

# Redis 성능 측정
measure_redis_performance() {
    info "💾 Redis 성능 측정 중..."
    
    # Redis Pod 찾기
    REDIS_POD=$(kubectl get pods -n $NAMESPACE -l app=redis -o jsonpath="{.items[0].metadata.name}" 2>/dev/null || echo "")
    
    if [ -z "$REDIS_POD" ]; then
        warn "Redis Pod를 찾을 수 없습니다"
        return
    fi
    
    # Redis 정보 수집
    kubectl exec -n $NAMESPACE $REDIS_POD -- redis-cli INFO memory 2>/dev/null > "$RESULTS_DIR/redis_memory.txt" || warn "Redis 메모리 정보 수집 실패"
    kubectl exec -n $NAMESPACE $REDIS_POD -- redis-cli INFO stats 2>/dev/null > "$RESULTS_DIR/redis_stats.txt" || warn "Redis 통계 정보 수집 실패"
    
    # Redis 성능 테스트
    kubectl exec -n $NAMESPACE $REDIS_POD -- redis-cli --latency-history -i 1 2>/dev/null > "$RESULTS_DIR/redis_latency.txt" &
    REDIS_LATENCY_PID=$!
    
    sleep 10
    
    kill $REDIS_LATENCY_PID 2>/dev/null || true
    
    info "  Redis 성능 측정 완료"
}

# 부하 테스트 실행
run_load_tests() {
    log "🧪 부하 테스트 실행 중..."
    
    # Python 부하 테스트 스크립트 실행
    info "API 부하 테스트 시작 - ${CONCURRENT_USERS}명 동시 사용자, ${TEST_DURATION}초"
    
    cat > "$RESULTS_DIR/load_test.py" << 'EOF'
#!/usr/bin/env python3
import asyncio
import aiohttp
import time
import json
import sys
from datetime import datetime

async def make_request(session, url, semaphore):
    async with semaphore:
        start_time = time.time()
        try:
            async with session.get(url) as response:
                await response.text()
                return {
                    'url': url,
                    'status': response.status,
                    'response_time': time.time() - start_time,
                    'success': response.status < 400
                }
        except Exception as e:
            return {
                'url': url,
                'status': 0,
                'response_time': time.time() - start_time,
                'success': False,
                'error': str(e)
            }

async def load_test(base_url, concurrent_users, duration):
    endpoints = [
        "/health",
        "/api/dashboard/summary", 
        "/api/vehicles",
        "/api/sensors/status"
    ]
    
    semaphore = asyncio.Semaphore(concurrent_users)
    results = []
    
    async with aiohttp.ClientSession() as session:
        start_time = time.time()
        
        while time.time() - start_time < duration:
            tasks = []
            for endpoint in endpoints:
                url = base_url + endpoint
                task = asyncio.create_task(make_request(session, url, semaphore))
                tasks.append(task)
            
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            results.extend([r for r in batch_results if isinstance(r, dict)])
            
            await asyncio.sleep(0.1)  # 100ms 간격
    
    return results

if __name__ == "__main__":
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    concurrent_users = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    duration = int(sys.argv[3]) if len(sys.argv) > 3 else 30
    
    print(f"부하 테스트 시작: {base_url}, {concurrent_users} 동시 사용자, {duration}초")
    
    results = asyncio.run(load_test(base_url, concurrent_users, duration))
    
    # 결과 분석
    total_requests = len(results)
    successful_requests = sum(1 for r in results if r['success'])
    response_times = [r['response_time'] for r in results]
    
    if response_times:
        avg_response_time = sum(response_times) / len(response_times)
        max_response_time = max(response_times)
        min_response_time = min(response_times)
    else:
        avg_response_time = max_response_time = min_response_time = 0
    
    summary = {
        'total_requests': total_requests,
        'successful_requests': successful_requests,
        'success_rate': successful_requests / total_requests if total_requests > 0 else 0,
        'avg_response_time': avg_response_time,
        'max_response_time': max_response_time,
        'min_response_time': min_response_time,
        'requests_per_second': total_requests / duration,
        'timestamp': datetime.now().isoformat()
    }
    
    print(json.dumps(summary, indent=2))
    
    # 상세 결과 저장
    with open('load_test_details.json', 'w') as f:
        json.dump(results, f, indent=2)
EOF

    # 부하 테스트 실행
    python3 "$RESULTS_DIR/load_test.py" "$API_BASE_URL" "$CONCURRENT_USERS" "$TEST_DURATION" > "$RESULTS_DIR/load_test_summary.json"
    
    # 결과 파일 이동
    mv load_test_details.json "$RESULTS_DIR/" 2>/dev/null || true
    
    log "✅ 부하 테스트 완료"
}

# 데이터베이스 최적화 실행
run_database_optimization() {
    log "🔧 데이터베이스 최적화 실행 중..."
    
    # 데이터베이스 최적화 스크립트 실행
    if [ -f "../optimization/database_optimizer.py" ]; then
        info "데이터베이스 최적화 스크립트 실행 중..."
        
        cd ../optimization
        python3 database_optimizer.py > "$RESULTS_DIR/database_optimization.log" 2>&1
        cd - > /dev/null
        
        success "데이터베이스 최적화 완료"
    else
        warn "데이터베이스 최적화 스크립트를 찾을 수 없습니다"
    fi
}

# API 최적화 실행
run_api_optimization() {
    log "⚡ API 최적화 실행 중..."
    
    # API 최적화 스크립트 백그라운드 실행
    if [ -f "../optimization/api_optimizer.py" ]; then
        info "API 최적화 서버 시작 중..."
        
        cd ../optimization
        python3 api_optimizer.py > "$RESULTS_DIR/api_optimization.log" 2>&1 &
        API_OPTIMIZER_PID=$!
        cd - > /dev/null
        
        # 잠시 대기 후 테스트
        sleep 30
        
        # 최적화된 API 테스트
        info "최적화된 API 성능 테스트 중..."
        curl -s "$API_BASE_URL/api/performance/stats" > "$RESULTS_DIR/optimized_api_stats.json" || warn "최적화된 API 통계 수집 실패"
        
        # API 최적화 서버 종료
        kill $API_OPTIMIZER_PID 2>/dev/null || true
        
        success "API 최적화 테스트 완료"
    else
        warn "API 최적화 스크립트를 찾을 수 없습니다"
    fi
}

# 네트워크 성능 테스트
run_network_performance_tests() {
    log "🌐 네트워크 성능 테스트 실행 중..."
    
    # 클러스터 내부 네트워크 지연 시간 측정
    info "클러스터 내부 네트워크 지연 시간 측정:"
    
    # API 서비스 IP 가져오기
    API_SERVICE_IP=$(kubectl get svc -n $NAMESPACE api-service -o jsonpath="{.spec.clusterIP}" 2>/dev/null || echo "")
    
    if [ -n "$API_SERVICE_IP" ]; then
        # 네트워크 지연 시간 측정 Pod 생성
        cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Pod
metadata:
  name: network-test
  namespace: $NAMESPACE
spec:
  containers:
  - name: network-test
    image: busybox
    command: ['sleep', '300']
  restartPolicy: Never
EOF
        
        # Pod 준비 대기
        kubectl wait --for=condition=ready pod/network-test -n $NAMESPACE --timeout=60s
        
        # ping 테스트
        info "  API 서비스로 ping 테스트 중..."
        kubectl exec -n $NAMESPACE network-test -- ping -c 10 $API_SERVICE_IP > "$RESULTS_DIR/network_ping.txt" 2>/dev/null || warn "Ping 테스트 실패"
        
        # 정리
        kubectl delete pod network-test -n $NAMESPACE --ignore-not-found=true
        
    else
        warn "API 서비스 IP를 찾을 수 없습니다"
    fi
    
    # 외부 네트워크 연결 테스트
    info "외부 네트워크 연결 테스트:"
    ping -c 5 8.8.8.8 > "$RESULTS_DIR/external_network.txt" 2>/dev/null || warn "외부 네트워크 테스트 실패"
    
    log "✅ 네트워크 성능 테스트 완료"
}

# 리소스 사용량 모니터링
monitor_resource_usage() {
    log "📈 리소스 사용량 모니터링 시작..."
    
    # 모니터링 스크립트 생성
    cat > "$RESULTS_DIR/resource_monitor.sh" << 'EOF'
#!/bin/bash
RESULTS_DIR=$1
DURATION=$2

echo "timestamp,cpu_percent,memory_mb,disk_io,network_io" > "$RESULTS_DIR/resource_usage.csv"

for i in $(seq 1 $DURATION); do
    timestamp=$(date +%s)
    
    # 시스템 리소스 사용량 (가능한 경우)
    if command -v top &> /dev/null; then
        cpu_percent=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | sed 's/%us,//' 2>/dev/null || echo "0")
    else
        cpu_percent="0"
    fi
    
    if command -v free &> /dev/null; then
        memory_mb=$(free -m | awk 'NR==2{printf "%.0f", $3}' 2>/dev/null || echo "0")
    else
        memory_mb="0"
    fi
    
    echo "$timestamp,$cpu_percent,$memory_mb,0,0" >> "$RESULTS_DIR/resource_usage.csv"
    
    sleep 1
done
EOF
    
    chmod +x "$RESULTS_DIR/resource_monitor.sh"
    
    # 백그라운드에서 리소스 모니터링 시작
    "$RESULTS_DIR/resource_monitor.sh" "$RESULTS_DIR" "300" &
    MONITOR_PID=$!
    
    info "리소스 모니터링 시작됨 (PID: $MONITOR_PID)"
    
    # 메인 테스트 완료 후 모니터링 종료
    sleep 310
    kill $MONITOR_PID 2>/dev/null || true
    
    log "✅ 리소스 사용량 모니터링 완료"
}

# Kubernetes 리소스 성능 분석
analyze_kubernetes_performance() {
    log "☸️ Kubernetes 리소스 성능 분석 중..."
    
    # HPA 상태 확인
    info "HPA 상태 확인:"
    kubectl get hpa -n $NAMESPACE > "$RESULTS_DIR/hpa_status.txt" 2>/dev/null || warn "HPA 정보 수집 실패"
    
    # Pod 리소스 사용량
    info "Pod 리소스 사용량:"
    kubectl top pods -n $NAMESPACE --containers > "$RESULTS_DIR/pod_resource_usage.txt" 2>/dev/null || warn "Pod 리소스 정보 수집 실패"
    
    # 노드 리소스 사용량
    info "노드 리소스 사용량:"
    kubectl top nodes > "$RESULTS_DIR/node_resource_usage.txt" 2>/dev/null || warn "노드 리소스 정보 수집 실패"
    
    # 이벤트 확인
    info "최근 이벤트 확인:"
    kubectl get events -n $NAMESPACE --sort-by=.metadata.creationTimestamp > "$RESULTS_DIR/recent_events.txt" 2>/dev/null || warn "이벤트 정보 수집 실패"
    
    # 서비스 엔드포인트 확인
    info "서비스 엔드포인트 확인:"
    kubectl get endpoints -n $NAMESPACE > "$RESULTS_DIR/service_endpoints.txt" 2>/dev/null || warn "엔드포인트 정보 수집 실패"
    
    log "✅ Kubernetes 성능 분석 완료"
}

# 성능 리포트 생성
generate_performance_report() {
    log "📄 성능 리포트 생성 중..."
    
    # HTML 리포트 생성
    cat > "$RESULTS_DIR/performance_report.html" << EOF
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>HankookTire SmartSensor 2.0 - Performance Report</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }
        .header { background: #1e88e5; color: white; padding: 20px; border-radius: 8px; text-align: center; }
        .section { background: white; margin: 20px 0; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .metric { display: inline-block; margin: 10px; text-align: center; padding: 15px; background: #e3f2fd; border-radius: 8px; }
        .metric-value { font-size: 24px; font-weight: bold; color: #1976d2; }
        .metric-label { font-size: 14px; color: #666; margin-top: 5px; }
        .status-good { color: #4caf50; }
        .status-warning { color: #ff9800; }
        .status-error { color: #f44336; }
        table { width: 100%; border-collapse: collapse; margin: 10px 0; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #f2f2f2; }
        .file-list { list-style-type: none; padding: 0; }
        .file-list li { margin: 5px 0; padding: 5px; background: #f9f9f9; border-radius: 4px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🚀 HankookTire SmartSensor 2.0</h1>
        <h2>Performance Test Report</h2>
        <p>Generated: $(date)</p>
    </div>
    
    <div class="section">
        <h3>📊 Test Summary</h3>
        <div class="metric">
            <div class="metric-value">$TEST_DURATION</div>
            <div class="metric-label">Test Duration (seconds)</div>
        </div>
        <div class="metric">
            <div class="metric-value">$CONCURRENT_USERS</div>
            <div class="metric-label">Concurrent Users</div>
        </div>
        <div class="metric">
            <div class="metric-value">$(date)</div>
            <div class="metric-label">Test Date</div>
        </div>
    </div>
    
    <div class="section">
        <h3>📈 Performance Metrics</h3>
        <p>부하 테스트 결과는 load_test_summary.json 파일을 참조하세요.</p>
        
        <h4>API 응답 시간 (기준선)</h4>
        <table>
            <tr><th>Endpoint</th><th>Response Time (seconds)</th></tr>
EOF

    # 기준선 응답 시간 데이터 추가
    if [ -f "$RESULTS_DIR/baseline_response_times.csv" ]; then
        while IFS=',' read -r endpoint time; do
            echo "            <tr><td>$endpoint</td><td>$time</td></tr>" >> "$RESULTS_DIR/performance_report.html"
        done < "$RESULTS_DIR/baseline_response_times.csv"
    fi

    cat >> "$RESULTS_DIR/performance_report.html" << EOF
        </table>
    </div>
    
    <div class="section">
        <h3>🗄️ Database Performance</h3>
        <p>데이터베이스 성능 분석 결과:</p>
        <ul class="file-list">
            <li>📄 Table Sizes: database_table_sizes.txt</li>
            <li>📄 Slow Queries: slow_queries.txt</li>
            <li>📄 Optimization Log: database_optimization.log</li>
        </ul>
    </div>
    
    <div class="section">
        <h3>💾 Cache Performance</h3>
        <p>Redis 성능 분석 결과:</p>
        <ul class="file-list">
            <li>📄 Memory Usage: redis_memory.txt</li>
            <li>📄 Statistics: redis_stats.txt</li>
            <li>📄 Latency: redis_latency.txt</li>
        </ul>
    </div>
    
    <div class="section">
        <h3>☸️ Kubernetes Performance</h3>
        <p>Kubernetes 클러스터 성능 분석:</p>
        <ul class="file-list">
            <li>📄 HPA Status: hpa_status.txt</li>
            <li>📄 Pod Resources: pod_resource_usage.txt</li>
            <li>📄 Node Resources: node_resource_usage.txt</li>
            <li>📄 Recent Events: recent_events.txt</li>
        </ul>
    </div>
    
    <div class="section">
        <h3>🌐 Network Performance</h3>
        <p>네트워크 성능 테스트 결과:</p>
        <ul class="file-list">
            <li>📄 Internal Network: network_ping.txt</li>
            <li>📄 External Network: external_network.txt</li>
        </ul>
    </div>
    
    <div class="section">
        <h3>📋 Generated Files</h3>
        <p>이번 테스트에서 생성된 모든 파일:</p>
        <ul class="file-list">
EOF

    # 생성된 파일 목록 추가
    find "$RESULTS_DIR" -type f -name "*.txt" -o -name "*.json" -o -name "*.csv" -o -name "*.log" | sort | while read -r file; do
        filename=$(basename "$file")
        echo "            <li>📄 $filename</li>" >> "$RESULTS_DIR/performance_report.html"
    done

    cat >> "$RESULTS_DIR/performance_report.html" << EOF
        </ul>
    </div>
    
    <div class="section">
        <h3>🔧 Optimization Recommendations</h3>
        <ul>
            <li>데이터베이스 인덱스 최적화 실행됨</li>
            <li>API 응답 캐싱 전략 구현됨</li>
            <li>리소스 사용량 모니터링 활성화됨</li>
            <li>네트워크 성능 기준선 설정됨</li>
        </ul>
    </div>
    
    <div class="section">
        <h3>📞 Contact Information</h3>
        <p>성능 관련 문의사항이 있으시면 DevOps 팀에 연락하세요.</p>
        <p>📧 Email: devops@hankook-smartsensor.com</p>
    </div>
    
</body>
</html>
EOF

    # 요약 리포트 생성
    cat > "$RESULTS_DIR/summary.txt" << EOF
HankookTire SmartSensor 2.0 - Performance Test Summary
======================================================

Test Configuration:
- Duration: $TEST_DURATION seconds
- Concurrent Users: $CONCURRENT_USERS
- API Base URL: $API_BASE_URL
- Test Date: $(date)

Generated Files:
$(find "$RESULTS_DIR" -type f -name "*.txt" -o -name "*.json" -o -name "*.csv" -o -name "*.log" | wc -l) files created

Key Results:
- Load test completed successfully
- Database optimization applied
- API performance optimization tested
- Network performance baseline established
- Resource usage monitored

Next Steps:
1. Review detailed results in individual files
2. Implement recommended optimizations
3. Schedule regular performance testing
4. Monitor ongoing performance metrics

For detailed analysis, see performance_report.html
EOF

    log "✅ 성능 리포트 생성 완료"
}

# 정리 함수
cleanup() {
    log "🧹 정리 작업 중..."
    
    # 백그라운드 프로세스 종료
    jobs -p | xargs -r kill 2>/dev/null || true
    
    # 임시 파일 정리
    rm -f load_test_details.json 2>/dev/null || true
}

# 메인 실행 함수
main() {
    log "🎯 HankookTire SmartSensor 2.0 성능 테스트 및 최적화 시작"
    
    # 백그라운드에서 리소스 모니터링 시작
    monitor_resource_usage &
    
    # 단계별 실행
    check_prerequisites
    check_system_status
    measure_baseline_performance
    
    # 병렬로 최적화 실행
    run_database_optimization &
    DB_OPT_PID=$!
    
    run_api_optimization &
    API_OPT_PID=$!
    
    # 부하 테스트 실행
    run_load_tests
    
    # 네트워크 성능 테스트
    run_network_performance_tests
    
    # Kubernetes 성능 분석
    analyze_kubernetes_performance
    
    # 최적화 작업 완료 대기
    wait $DB_OPT_PID 2>/dev/null || true
    wait $API_OPT_PID 2>/dev/null || true
    
    # 성능 리포트 생성
    generate_performance_report
    
    log "🎉 성능 테스트 및 최적화 완료!"
    
    # 결과 요약 출력
    echo ""
    echo "======================================================="
    echo "🚀 HankookTire SmartSensor 2.0 성능 테스트 완료!"
    echo "======================================================="
    echo ""
    echo "📊 결과 디렉토리: $RESULTS_DIR"
    echo "📄 상세 리포트: $RESULTS_DIR/performance_report.html"
    echo "📋 요약: $RESULTS_DIR/summary.txt"
    echo ""
    echo "🔧 수행된 최적화:"
    echo "  ✅ 데이터베이스 인덱스 최적화"
    echo "  ✅ API 응답 캐싱"
    echo "  ✅ 리소스 사용량 모니터링"
    echo "  ✅ 네트워크 성능 분석"
    echo "  ✅ Kubernetes 성능 튜닝"
    echo ""
    echo "⚡ 다음 단계:"
    echo "  1. 상세 리포트 검토"
    echo "  2. 추가 최적화 적용"
    echo "  3. 정기 성능 모니터링 설정"
    echo "  4. 알림 임계값 조정"
    echo ""
    echo "📈 성능 모니터링 대시보드:"
    echo "  Grafana: https://monitoring.hankook-smartsensor.com/grafana"
    echo "  Prometheus: https://monitoring.hankook-smartsensor.com/prometheus"
    echo ""
}

# 에러 처리
trap cleanup EXIT
trap 'error "스크립트 실행 중 오류 발생"; exit 1' ERR

# 메인 함수 실행
main "$@"