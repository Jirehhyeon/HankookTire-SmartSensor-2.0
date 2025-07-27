#!/usr/bin/env python3
"""
HankookTire SmartSensor 2.0 - System Health Check Script
차세대 통합 스마트 타이어 센서 시스템 헬스체크

This script performs comprehensive health checks on all system components
and sends alerts via multiple channels (Slack, Email, Webhook).
"""

import asyncio
import aiohttp
import psycopg2
import redis
import json
import logging
import time
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import smtplib
from email.mime.text import MimeText
from email.mime.multipart import MimeMultipart

# 설정
POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'postgres-service')
POSTGRES_PORT = int(os.getenv('POSTGRES_PORT', '5432'))
POSTGRES_DB = os.getenv('POSTGRES_DB', 'smarttire_sensors')
POSTGRES_USER = os.getenv('POSTGRES_USER', 'smarttire')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'password')

REDIS_HOST = os.getenv('REDIS_HOST', 'redis-service')
REDIS_PORT = int(os.getenv('REDIS_PORT', '6379'))
REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', '')

API_BASE_URL = os.getenv('API_BASE_URL', 'http://api-service:8000')
MQTT_HOST = os.getenv('MQTT_HOST', 'mosquitto-service')
MQTT_PORT = int(os.getenv('MQTT_PORT', '1883'))

SLACK_WEBHOOK_URL = os.getenv('SLACK_WEBHOOK_URL', '')
EMAIL_SMTP_SERVER = os.getenv('EMAIL_SMTP_SERVER', 'smtp.gmail.com')
EMAIL_SMTP_PORT = int(os.getenv('EMAIL_SMTP_PORT', '587'))
EMAIL_USERNAME = os.getenv('EMAIL_USERNAME', '')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD', '')
ALERT_EMAIL_TO = os.getenv('ALERT_EMAIL_TO', 'ops@smarttire-smartsensor.com')

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/health-check.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class HealthStatus(Enum):
    """헬스체크 상태"""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"

@dataclass
class HealthCheckResult:
    """헬스체크 결과"""
    component: str
    status: HealthStatus
    message: str
    response_time_ms: float
    details: Dict = None
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()

class HealthChecker:
    """시스템 헬스체크 메인 클래스"""
    
    def __init__(self):
        self.results: List[HealthCheckResult] = []
        self.session: Optional[aiohttp.ClientSession] = None
        
    async def __aenter__(self):
        timeout = aiohttp.ClientTimeout(total=30)
        self.session = aiohttp.ClientSession(timeout=timeout)
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def check_api_health(self) -> HealthCheckResult:
        """API 서버 헬스체크"""
        start_time = time.time()
        
        try:
            async with self.session.get(f"{API_BASE_URL}/health") as response:
                response_time = (time.time() - start_time) * 1000
                
                if response.status == 200:
                    data = await response.json()
                    
                    if response_time > 2000:  # 2초 이상
                        status = HealthStatus.WARNING
                        message = f"API 응답 시간이 느림 ({response_time:.0f}ms)"
                    else:
                        status = HealthStatus.HEALTHY
                        message = "API 서버 정상"
                        
                    return HealthCheckResult(
                        component="API Server",
                        status=status,
                        message=message,
                        response_time_ms=response_time,
                        details=data
                    )
                else:
                    return HealthCheckResult(
                        component="API Server",
                        status=HealthStatus.CRITICAL,
                        message=f"API 서버 응답 오류 (HTTP {response.status})",
                        response_time_ms=response_time
                    )
                    
        except asyncio.TimeoutError:
            return HealthCheckResult(
                component="API Server",
                status=HealthStatus.CRITICAL,
                message="API 서버 응답 시간 초과",
                response_time_ms=30000
            )
        except Exception as e:
            return HealthCheckResult(
                component="API Server",
                status=HealthStatus.CRITICAL,
                message=f"API 서버 연결 실패: {str(e)}",
                response_time_ms=0
            )

    def check_database_health(self) -> HealthCheckResult:
        """PostgreSQL 데이터베이스 헬스체크"""
        start_time = time.time()
        
        try:
            conn = psycopg2.connect(
                host=POSTGRES_HOST,
                port=POSTGRES_PORT,
                database=POSTGRES_DB,
                user=POSTGRES_USER,
                password=POSTGRES_PASSWORD,
                connect_timeout=10
            )
            
            with conn.cursor() as cursor:
                # 기본 연결 테스트
                cursor.execute("SELECT 1")
                
                # 센서 데이터 테이블 상태 확인
                cursor.execute("""
                    SELECT COUNT(*) as total_sensors,
                           COUNT(CASE WHEN last_seen > NOW() - INTERVAL '1 hour' THEN 1 END) as active_sensors
                    FROM sensors.devices
                """)
                
                total_sensors, active_sensors = cursor.fetchone()
                
                # 최근 데이터 확인
                cursor.execute("""
                    SELECT COUNT(*) 
                    FROM sensors.sensor_readings 
                    WHERE created_at > NOW() - INTERVAL '5 minutes'
                """)
                
                recent_readings = cursor.fetchone()[0]
                
                # 데이터베이스 크기 확인
                cursor.execute("""
                    SELECT pg_size_pretty(pg_database_size(%s))
                """, (POSTGRES_DB,))
                
                db_size = cursor.fetchone()[0]
                
            conn.close()
            response_time = (time.time() - start_time) * 1000
            
            # 상태 평가
            if active_sensors / max(total_sensors, 1) < 0.8:  # 80% 미만 활성
                status = HealthStatus.WARNING
                message = f"활성 센서 비율 낮음 ({active_sensors}/{total_sensors})"
            elif recent_readings < 10:  # 최근 5분간 데이터 10개 미만
                status = HealthStatus.WARNING
                message = "최근 센서 데이터 수집량 부족"
            else:
                status = HealthStatus.HEALTHY
                message = "데이터베이스 정상"
                
            return HealthCheckResult(
                component="PostgreSQL Database",
                status=status,
                message=message,
                response_time_ms=response_time,
                details={
                    "total_sensors": total_sensors,
                    "active_sensors": active_sensors,
                    "recent_readings": recent_readings,
                    "database_size": db_size
                }
            )
            
        except Exception as e:
            return HealthCheckResult(
                component="PostgreSQL Database",
                status=HealthStatus.CRITICAL,
                message=f"데이터베이스 연결 실패: {str(e)}",
                response_time_ms=0
            )

    def check_redis_health(self) -> HealthCheckResult:
        """Redis 캐시 헬스체크"""
        start_time = time.time()
        
        try:
            r = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                password=REDIS_PASSWORD if REDIS_PASSWORD else None,
                socket_timeout=10,
                decode_responses=True
            )
            
            # 기본 연결 테스트
            r.ping()
            
            # 메모리 사용량 확인
            info = r.info('memory')
            used_memory = info['used_memory']
            max_memory = info.get('maxmemory', 0)
            
            # 키 개수 확인
            db_info = r.info('keyspace')
            total_keys = sum([db_info[db].get('keys', 0) for db in db_info if db.startswith('db')])
            
            response_time = (time.time() - start_time) * 1000
            
            # 상태 평가
            if max_memory > 0 and (used_memory / max_memory) > 0.9:  # 90% 이상 사용
                status = HealthStatus.WARNING
                message = f"Redis 메모리 사용량 높음 ({used_memory/max_memory*100:.1f}%)"
            else:
                status = HealthStatus.HEALTHY
                message = "Redis 캐시 정상"
                
            return HealthCheckResult(
                component="Redis Cache",
                status=status,
                message=message,
                response_time_ms=response_time,
                details={
                    "used_memory_mb": used_memory // (1024*1024),
                    "max_memory_mb": max_memory // (1024*1024) if max_memory > 0 else "unlimited",
                    "total_keys": total_keys,
                    "connected_clients": info.get('connected_clients', 0)
                }
            )
            
        except Exception as e:
            return HealthCheckResult(
                component="Redis Cache",
                status=HealthStatus.CRITICAL,
                message=f"Redis 연결 실패: {str(e)}",
                response_time_ms=0
            )

    async def check_mqtt_health(self) -> HealthCheckResult:
        """MQTT 브로커 헬스체크"""
        start_time = time.time()
        
        try:
            # MQTT 브로커 포트 연결 테스트
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(MQTT_HOST, MQTT_PORT),
                timeout=10
            )
            
            writer.close()
            await writer.wait_closed()
            
            response_time = (time.time() - start_time) * 1000
            
            # Prometheus 메트릭을 통한 추가 정보 수집 (선택사항)
            try:
                async with self.session.get(f"http://{MQTT_HOST}:9234/metrics") as response:
                    if response.status == 200:
                        metrics_text = await response.text()
                        # 간단한 메트릭 파싱 (실제로는 prometheus client 사용 권장)
                        connected_clients = 0
                        for line in metrics_text.split('\n'):
                            if line.startswith('mosquitto_connected_clients'):
                                connected_clients = int(line.split()[-1])
                                break
                    else:
                        connected_clients = -1
            except:
                connected_clients = -1
                
            return HealthCheckResult(
                component="MQTT Broker",
                status=HealthStatus.HEALTHY,
                message="MQTT 브로커 정상",
                response_time_ms=response_time,
                details={
                    "connected_clients": connected_clients if connected_clients >= 0 else "unknown"
                }
            )
            
        except asyncio.TimeoutError:
            return HealthCheckResult(
                component="MQTT Broker",
                status=HealthStatus.CRITICAL,
                message="MQTT 브로커 연결 시간 초과",
                response_time_ms=10000
            )
        except Exception as e:
            return HealthCheckResult(
                component="MQTT Broker",
                status=HealthStatus.CRITICAL,
                message=f"MQTT 브로커 연결 실패: {str(e)}",
                response_time_ms=0
            )

    async def check_sensor_connectivity(self) -> HealthCheckResult:
        """센서 연결성 헬스체크"""
        start_time = time.time()
        
        try:
            # API를 통한 센서 상태 확인
            async with self.session.get(f"{API_BASE_URL}/sensors/status") as response:
                response_time = (time.time() - start_time) * 1000
                
                if response.status == 200:
                    data = await response.json()
                    
                    total_sensors = data.get('total_sensors', 0)
                    online_sensors = data.get('online_sensors', 0)
                    offline_sensors = data.get('offline_sensors', 0)
                    
                    if total_sensors == 0:
                        status = HealthStatus.WARNING
                        message = "등록된 센서가 없음"
                    elif offline_sensors / max(total_sensors, 1) > 0.2:  # 20% 이상 오프라인
                        status = HealthStatus.WARNING
                        message = f"오프라인 센서 비율 높음 ({offline_sensors}/{total_sensors})"
                    elif offline_sensors / max(total_sensors, 1) > 0.5:  # 50% 이상 오프라인
                        status = HealthStatus.CRITICAL
                        message = f"대량 센서 오프라인 ({offline_sensors}/{total_sensors})"
                    else:
                        status = HealthStatus.HEALTHY
                        message = f"센서 연결 정상 ({online_sensors}/{total_sensors})"
                        
                    return HealthCheckResult(
                        component="Sensor Connectivity",
                        status=status,
                        message=message,
                        response_time_ms=response_time,
                        details={
                            "total_sensors": total_sensors,
                            "online_sensors": online_sensors,
                            "offline_sensors": offline_sensors,
                            "online_percentage": (online_sensors / max(total_sensors, 1)) * 100
                        }
                    )
                else:
                    return HealthCheckResult(
                        component="Sensor Connectivity",
                        status=HealthStatus.CRITICAL,
                        message=f"센서 상태 API 오류 (HTTP {response.status})",
                        response_time_ms=response_time
                    )
                    
        except Exception as e:
            return HealthCheckResult(
                component="Sensor Connectivity",
                status=HealthStatus.CRITICAL,
                message=f"센서 상태 확인 실패: {str(e)}",
                response_time_ms=0
            )

    async def run_all_checks(self) -> List[HealthCheckResult]:
        """모든 헬스체크 실행"""
        logger.info("🔍 시스템 헬스체크 시작...")
        
        # 비동기 헬스체크
        async_checks = [
            self.check_api_health(),
            self.check_mqtt_health(),
            self.check_sensor_connectivity()
        ]
        
        # 동기 헬스체크 (별도 실행)
        sync_results = [
            self.check_database_health(),
            self.check_redis_health()
        ]
        
        # 비동기 체크 실행
        async_results = await asyncio.gather(*async_checks, return_exceptions=True)
        
        # 예외 처리
        processed_results = []
        for i, result in enumerate(async_results):
            if isinstance(result, Exception):
                component_names = ["API Server", "MQTT Broker", "Sensor Connectivity"]
                processed_results.append(HealthCheckResult(
                    component=component_names[i],
                    status=HealthStatus.CRITICAL,
                    message=f"헬스체크 실행 중 오류: {str(result)}",
                    response_time_ms=0
                ))
            else:
                processed_results.append(result)
        
        # 모든 결과 합치기
        self.results = processed_results + sync_results
        
        logger.info(f"✅ 헬스체크 완료 - 총 {len(self.results)}개 컴포넌트")
        return self.results

    def get_overall_status(self) -> HealthStatus:
        """전체 시스템 상태 평가"""
        if not self.results:
            return HealthStatus.UNKNOWN
            
        statuses = [result.status for result in self.results]
        
        if HealthStatus.CRITICAL in statuses:
            return HealthStatus.CRITICAL
        elif HealthStatus.WARNING in statuses:
            return HealthStatus.WARNING
        else:
            return HealthStatus.HEALTHY

    async def send_slack_alert(self, overall_status: HealthStatus):
        """Slack 알림 전송"""
        if not SLACK_WEBHOOK_URL:
            return
            
        try:
            # 상태별 이모지 및 색상
            status_config = {
                HealthStatus.HEALTHY: {"emoji": "🟢", "color": "good"},
                HealthStatus.WARNING: {"emoji": "🟡", "color": "warning"},
                HealthStatus.CRITICAL: {"emoji": "🔴", "color": "danger"},
                HealthStatus.UNKNOWN: {"emoji": "⚪", "color": "#808080"}
            }
            
            config = status_config[overall_status]
            
            # Slack 메시지 구성
            fields = []
            for result in self.results:
                status_emoji = status_config[result.status]["emoji"]
                fields.append({
                    "title": result.component,
                    "value": f"{status_emoji} {result.message} ({result.response_time_ms:.0f}ms)",
                    "short": True
                })
            
            payload = {
                "username": "HankookTire HealthCheck Bot",
                "icon_emoji": ":health:",
                "attachments": [{
                    "color": config["color"],
                    "title": f"{config['emoji']} HankookTire SmartSensor 2.0 - System Health Report",
                    "text": f"전체 시스템 상태: *{overall_status.value.upper()}*",
                    "fields": fields,
                    "footer": "HankookTire SmartSensor 2.0",
                    "ts": int(time.time())
                }]
            }
            
            async with self.session.post(SLACK_WEBHOOK_URL, json=payload) as response:
                if response.status == 200:
                    logger.info("✅ Slack 알림 전송 완료")
                else:
                    logger.error(f"❌ Slack 알림 전송 실패: HTTP {response.status}")
                    
        except Exception as e:
            logger.error(f"❌ Slack 알림 전송 중 오류: {str(e)}")

    def send_email_alert(self, overall_status: HealthStatus):
        """이메일 알림 전송"""
        if not all([EMAIL_USERNAME, EMAIL_PASSWORD, ALERT_EMAIL_TO]):
            return
            
        try:
            # 이메일 내용 구성
            subject = f"🚨 HankookTire SmartSensor Health Alert - {overall_status.value.upper()}"
            
            html_body = f"""
            <html>
            <body>
                <h2>🚀 HankookTire SmartSensor 2.0 - Health Check Report</h2>
                <p><strong>전체 시스템 상태: {overall_status.value.upper()}</strong></p>
                <p><strong>점검 시간:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S KST')}</p>
                
                <h3>컴포넌트별 상태</h3>
                <table border="1" cellpadding="5" cellspacing="0">
                    <tr style="background-color: #f0f0f0;">
                        <th>컴포넌트</th>
                        <th>상태</th>
                        <th>메시지</th>
                        <th>응답시간</th>
                    </tr>
            """
            
            for result in self.results:
                status_color = {
                    HealthStatus.HEALTHY: "green",
                    HealthStatus.WARNING: "orange", 
                    HealthStatus.CRITICAL: "red",
                    HealthStatus.UNKNOWN: "gray"
                }[result.status]
                
                html_body += f"""
                    <tr>
                        <td>{result.component}</td>
                        <td style="color: {status_color}; font-weight: bold;">{result.status.value.upper()}</td>
                        <td>{result.message}</td>
                        <td>{result.response_time_ms:.0f}ms</td>
                    </tr>
                """
            
            html_body += """
                </table>
                <br>
                <p><em>이 메시지는 HankookTire SmartSensor 2.0 자동 모니터링 시스템에서 발송되었습니다.</em></p>
            </body>
            </html>
            """
            
            # 이메일 전송
            msg = MimeMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = EMAIL_USERNAME
            msg['To'] = ALERT_EMAIL_TO
            
            html_part = MimeText(html_body, 'html')
            msg.attach(html_part)
            
            server = smtplib.SMTP(EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT)
            server.starttls()
            server.login(EMAIL_USERNAME, EMAIL_PASSWORD)
            server.send_message(msg)
            server.quit()
            
            logger.info("✅ 이메일 알림 전송 완료")
            
        except Exception as e:
            logger.error(f"❌ 이메일 알림 전송 중 오류: {str(e)}")

    def save_results_to_file(self):
        """결과를 JSON 파일로 저장"""
        try:
            results_data = {
                "timestamp": datetime.now().isoformat(),
                "overall_status": self.get_overall_status().value,
                "results": [
                    {
                        **asdict(result),
                        "timestamp": result.timestamp.isoformat(),
                        "status": result.status.value
                    }
                    for result in self.results
                ]
            }
            
            with open('/var/log/health-check-results.json', 'w', encoding='utf-8') as f:
                json.dump(results_data, f, ensure_ascii=False, indent=2)
                
            logger.info("✅ 헬스체크 결과 파일 저장 완료")
            
        except Exception as e:
            logger.error(f"❌ 결과 파일 저장 중 오류: {str(e)}")

async def main():
    """메인 실행 함수"""
    logger.info("🚀 HankookTire SmartSensor 2.0 Health Check 시작")
    
    async with HealthChecker() as checker:
        # 모든 헬스체크 실행
        results = await checker.run_all_checks()
        
        # 전체 상태 평가
        overall_status = checker.get_overall_status()
        
        # 결과 출력
        logger.info("=" * 60)
        logger.info(f"🏥 전체 시스템 상태: {overall_status.value.upper()}")
        logger.info("=" * 60)
        
        for result in results:
            status_emoji = {
                HealthStatus.HEALTHY: "🟢",
                HealthStatus.WARNING: "🟡", 
                HealthStatus.CRITICAL: "🔴",
                HealthStatus.UNKNOWN: "⚪"
            }[result.status]
            
            logger.info(f"{status_emoji} {result.component}: {result.message} ({result.response_time_ms:.0f}ms)")
            
            if result.details:
                for key, value in result.details.items():
                    logger.info(f"    {key}: {value}")
        
        # 결과 저장
        checker.save_results_to_file()
        
        # 알림 전송 (WARNING 이상인 경우만)
        if overall_status in [HealthStatus.WARNING, HealthStatus.CRITICAL]:
            await checker.send_slack_alert(overall_status)
            checker.send_email_alert(overall_status)
        
        logger.info("✅ 헬스체크 완료")
        
        # 상태에 따른 종료 코드 반환
        exit_codes = {
            HealthStatus.HEALTHY: 0,
            HealthStatus.WARNING: 1,
            HealthStatus.CRITICAL: 2,
            HealthStatus.UNKNOWN: 3
        }
        
        return exit_codes[overall_status]

if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        exit(exit_code)
    except KeyboardInterrupt:
        logger.info("👋 헬스체크가 사용자에 의해 중단되었습니다.")
        exit(130)
    except Exception as e:
        logger.error(f"💥 헬스체크 실행 중 예상치 못한 오류: {str(e)}")
        exit(4)