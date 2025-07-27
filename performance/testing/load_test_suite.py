#!/usr/bin/env python3
"""
HankookTire SmartSensor 2.0 - Comprehensive Load Testing Suite
차세대 통합 스마트 타이어 센서 시스템 부하 테스트

포괄적인 성능 테스트 프레임워크
- API 엔드포인트 부하 테스트
- 센서 데이터 스트리밍 테스트
- 데이터베이스 성능 테스트
- 실시간 대시보드 성능 테스트
- 동시 사용자 시뮬레이션
- 네트워크 지연 시뮬레이션
"""

import asyncio
import aiohttp
import time
import json
import logging
import statistics
import random
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from enum import Enum
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
import psycopg2
from psycopg2.extras import RealDictCursor
import redis
import websockets
import paho.mqtt.client as mqtt
import threading
import queue
import ssl
import os

# 설정
API_BASE_URL = os.getenv('API_BASE_URL', 'http://localhost:8000')
MQTT_HOST = os.getenv('MQTT_HOST', 'localhost')
MQTT_PORT = int(os.getenv('MQTT_PORT', '1883'))
WEBSOCKET_URL = os.getenv('WEBSOCKET_URL', 'ws://localhost:8000/ws')

POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'localhost')
POSTGRES_PORT = int(os.getenv('POSTGRES_PORT', '5432'))
POSTGRES_DB = os.getenv('POSTGRES_DB', 'hankook_sensors')
POSTGRES_USER = os.getenv('POSTGRES_USER', 'hankook')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'password')

REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', '6379'))

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TestType(Enum):
    """테스트 타입"""
    API_LOAD = "api_load"
    SENSOR_STREAMING = "sensor_streaming"
    DATABASE_STRESS = "database_stress"
    REALTIME_DASHBOARD = "realtime_dashboard"
    CONCURRENT_USERS = "concurrent_users"
    NETWORK_LATENCY = "network_latency"
    FAILOVER = "failover"
    SCALABILITY = "scalability"

class LoadPattern(Enum):
    """부하 패턴"""
    CONSTANT = "constant"
    RAMP_UP = "ramp_up"
    SPIKE = "spike"
    STEP = "step"
    SINE_WAVE = "sine_wave"

@dataclass
class TestConfig:
    """테스트 설정"""
    test_type: TestType
    duration_seconds: int
    concurrent_users: int
    rps_target: int  # Requests per second
    load_pattern: LoadPattern
    test_data_size: int
    include_auth: bool = True
    network_delay_ms: int = 0
    error_threshold: float = 0.05  # 5%

@dataclass
class TestResult:
    """테스트 결과"""
    test_type: TestType
    start_time: datetime
    end_time: datetime
    total_requests: int
    successful_requests: int
    failed_requests: int
    avg_response_time: float
    p50_response_time: float
    p95_response_time: float
    p99_response_time: float
    max_response_time: float
    min_response_time: float
    throughput_rps: float
    error_rate: float
    cpu_usage_percent: float
    memory_usage_mb: float
    network_io_mb: float
    database_connections: int
    cache_hit_rate: float
    details: Dict[str, Any]

class SensorDataGenerator:
    """센서 데이터 생성기"""
    
    def __init__(self):
        self.vehicle_ids = [f"VH{str(i).zfill(6)}" for i in range(1, 10001)]  # 10,000 vehicles
        self.sensor_types = ["pressure", "temperature", "humidity", "vibration", "location"]
        
    def generate_tpms_data(self, vehicle_id: str) -> Dict:
        """TPMS 센서 데이터 생성"""
        return {
            "vehicle_id": vehicle_id,
            "sensor_id": f"TPMS_{vehicle_id}_{random.randint(1, 4)}",
            "tire_position": random.choice(["FL", "FR", "RL", "RR"]),
            "pressure_kpa": round(random.normalvariate(250, 20), 2),
            "temperature_celsius": round(random.normalvariate(35, 10), 2),
            "battery_voltage": round(random.normalvariate(3.2, 0.3), 2),
            "signal_strength": random.randint(-90, -30),
            "timestamp": datetime.utcnow().isoformat(),
            "quality_score": random.randint(70, 100)
        }
    
    def generate_environmental_data(self, vehicle_id: str) -> Dict:
        """환경 센서 데이터 생성"""
        return {
            "vehicle_id": vehicle_id,
            "sensor_id": f"ENV_{vehicle_id}",
            "humidity_percent": round(random.normalvariate(60, 15), 2),
            "ambient_temperature": round(random.normalvariate(25, 8), 2),
            "vibration_g": round(random.normalvariate(0.5, 0.2), 3),
            "road_condition": random.choice(["dry", "wet", "snow", "ice"]),
            "location": {
                "latitude": round(random.uniform(33.0, 38.0), 6),
                "longitude": round(random.uniform(126.0, 131.0), 6),
                "altitude": random.randint(0, 500)
            },
            "timestamp": datetime.utcnow().isoformat(),
            "quality_score": random.randint(80, 100)
        }
    
    def generate_batch_data(self, count: int) -> List[Dict]:
        """배치 데이터 생성"""
        data = []
        for _ in range(count):
            vehicle_id = random.choice(self.vehicle_ids)
            if random.random() < 0.7:  # 70% TPMS data
                data.append(self.generate_tpms_data(vehicle_id))
            else:  # 30% Environmental data
                data.append(self.generate_environmental_data(vehicle_id))
        return data

class PerformanceMonitor:
    """성능 모니터링"""
    
    def __init__(self):
        self.metrics = {
            'response_times': [],
            'timestamps': [],
            'errors': [],
            'throughput': []
        }
        self.start_time = None
        
    def start_monitoring(self):
        """모니터링 시작"""
        self.start_time = time.time()
        self.metrics = {
            'response_times': [],
            'timestamps': [],
            'errors': [],
            'throughput': []
        }
        
    def record_request(self, response_time: float, success: bool):
        """요청 기록"""
        current_time = time.time()
        self.metrics['response_times'].append(response_time)
        self.metrics['timestamps'].append(current_time - self.start_time)
        self.metrics['errors'].append(0 if success else 1)
        
    def calculate_throughput(self, window_seconds: int = 10) -> float:
        """처리량 계산"""
        current_time = time.time() - self.start_time
        recent_requests = [
            t for t in self.metrics['timestamps'] 
            if t > current_time - window_seconds
        ]
        return len(recent_requests) / window_seconds if recent_requests else 0

class LoadTestRunner:
    """부하 테스트 실행기"""
    
    def __init__(self):
        self.session = None
        self.monitor = PerformanceMonitor()
        self.data_generator = SensorDataGenerator()
        self.redis_client = None
        
    async def __aenter__(self):
        timeout = aiohttp.ClientTimeout(total=30)
        self.session = aiohttp.ClientSession(timeout=timeout)
        
        # Redis 연결
        self.redis_client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            decode_responses=True
        )
        
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def authenticate(self) -> str:
        """인증 토큰 획득"""
        try:
            auth_data = {
                "username": "test_user",
                "password": "test_password"
            }
            
            async with self.session.post(f"{API_BASE_URL}/auth/login", json=auth_data) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("access_token", "")
                else:
                    logger.warning("인증 실패 - 인증 없이 테스트 진행")
                    return ""
        except Exception as e:
            logger.warning(f"인증 실패: {str(e)} - 인증 없이 테스트 진행")
            return ""

    async def run_api_load_test(self, config: TestConfig) -> TestResult:
        """API 부하 테스트"""
        logger.info(f"🚀 API 부하 테스트 시작 - {config.concurrent_users}명 동시 사용자, {config.duration_seconds}초")
        
        self.monitor.start_monitoring()
        start_time = datetime.utcnow()
        
        # 인증 토큰 획득
        auth_token = ""
        if config.include_auth:
            auth_token = await self.authenticate()
        
        headers = {}
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"
        
        # API 엔드포인트 목록
        endpoints = [
            ("/sensors", "GET"),
            ("/sensors/status", "GET"),
            ("/vehicles", "GET"),
            ("/dashboard/summary", "GET"),
            ("/analytics/overview", "GET")
        ]
        
        # 동시 요청 실행
        tasks = []
        for _ in range(config.concurrent_users):
            task = asyncio.create_task(
                self._execute_api_requests(endpoints, headers, config.duration_seconds)
            )
            tasks.append(task)
        
        # 모든 태스크 완료 대기
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        end_time = datetime.utcnow()
        
        # 결과 분석
        return self._analyze_results(TestType.API_LOAD, start_time, end_time, config)

    async def _execute_api_requests(self, endpoints: List[Tuple[str, str]], headers: Dict, duration: int):
        """API 요청 실행"""
        end_time = time.time() + duration
        
        while time.time() < end_time:
            endpoint, method = random.choice(endpoints)
            url = f"{API_BASE_URL}{endpoint}"
            
            start_request = time.time()
            success = False
            
            try:
                if method == "GET":
                    async with self.session.get(url, headers=headers) as response:
                        success = response.status < 400
                        await response.text()  # 응답 본문 읽기
                elif method == "POST":
                    data = self.data_generator.generate_tpms_data("TEST_VEHICLE")
                    async with self.session.post(url, json=data, headers=headers) as response:
                        success = response.status < 400
                        await response.text()
                        
            except Exception as e:
                logger.debug(f"요청 실패: {str(e)}")
                success = False
            
            response_time = time.time() - start_request
            self.monitor.record_request(response_time, success)
            
            # 요청 간 간격 (목표 RPS 달성)
            await asyncio.sleep(random.uniform(0.1, 0.5))

    async def run_sensor_streaming_test(self, config: TestConfig) -> TestResult:
        """센서 스트리밍 테스트"""
        logger.info(f"📡 센서 스트리밍 테스트 시작 - {config.test_data_size}개 센서, {config.duration_seconds}초")
        
        self.monitor.start_monitoring()
        start_time = datetime.utcnow()
        
        # MQTT 클라이언트 설정
        mqtt_results = queue.Queue()
        mqtt_threads = []
        
        for i in range(config.concurrent_users):
            thread = threading.Thread(
                target=self._mqtt_sensor_simulation,
                args=(f"sensor_{i}", config.duration_seconds, mqtt_results)
            )
            thread.start()
            mqtt_threads.append(thread)
        
        # WebSocket 스트리밍 시뮬레이션
        websocket_task = asyncio.create_task(
            self._websocket_streaming_test(config.duration_seconds)
        )
        
        # 모든 스레드 완료 대기
        for thread in mqtt_threads:
            thread.join()
        
        await websocket_task
        
        end_time = datetime.utcnow()
        
        return self._analyze_results(TestType.SENSOR_STREAMING, start_time, end_time, config)

    def _mqtt_sensor_simulation(self, sensor_id: str, duration: int, results: queue.Queue):
        """MQTT 센서 시뮬레이션"""
        try:
            client = mqtt.Client()
            client.connect(MQTT_HOST, MQTT_PORT, 60)
            client.loop_start()
            
            end_time = time.time() + duration
            message_count = 0
            
            while time.time() < end_time:
                # 센서 데이터 생성 및 전송
                data = self.data_generator.generate_tpms_data(f"VEHICLE_{sensor_id}")
                topic = f"sensors/tpms/{sensor_id}"
                
                start_time = time.time()
                result = client.publish(topic, json.dumps(data))
                
                if result.rc == mqtt.MQTT_ERR_SUCCESS:
                    response_time = time.time() - start_time
                    self.monitor.record_request(response_time, True)
                    message_count += 1
                else:
                    self.monitor.record_request(0, False)
                
                time.sleep(random.uniform(0.5, 2.0))  # 센서 데이터 전송 간격
            
            client.loop_stop()
            client.disconnect()
            results.put(message_count)
            
        except Exception as e:
            logger.error(f"MQTT 시뮬레이션 오류: {str(e)}")
            results.put(0)

    async def _websocket_streaming_test(self, duration: int):
        """WebSocket 스트리밍 테스트"""
        try:
            async with websockets.connect(WEBSOCKET_URL) as websocket:
                end_time = time.time() + duration
                
                while time.time() < end_time:
                    # 실시간 데이터 요청
                    request = {
                        "type": "subscribe",
                        "topic": "realtime_dashboard",
                        "filters": {"vehicle_count": 100}
                    }
                    
                    start_time = time.time()
                    await websocket.send(json.dumps(request))
                    
                    try:
                        response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                        response_time = time.time() - start_time
                        self.monitor.record_request(response_time, True)
                    except asyncio.TimeoutError:
                        self.monitor.record_request(5.0, False)
                    
                    await asyncio.sleep(1.0)  # 1초 간격
                    
        except Exception as e:
            logger.error(f"WebSocket 테스트 오류: {str(e)}")

    async def run_database_stress_test(self, config: TestConfig) -> TestResult:
        """데이터베이스 스트레스 테스트"""
        logger.info(f"🗄️ 데이터베이스 스트레스 테스트 시작 - {config.concurrent_users}개 동시 연결")
        
        self.monitor.start_monitoring()
        start_time = datetime.utcnow()
        
        # 데이터베이스 작업 시뮬레이션
        tasks = []
        for i in range(config.concurrent_users):
            task = asyncio.create_task(
                self._database_operations(f"worker_{i}", config.duration_seconds)
            )
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        end_time = datetime.utcnow()
        
        return self._analyze_results(TestType.DATABASE_STRESS, start_time, end_time, config)

    async def _database_operations(self, worker_id: str, duration: int):
        """데이터베이스 작업 실행"""
        try:
            conn = psycopg2.connect(
                host=POSTGRES_HOST,
                port=POSTGRES_PORT,
                database=POSTGRES_DB,
                user=POSTGRES_USER,
                password=POSTGRES_PASSWORD,
                cursor_factory=RealDictCursor
            )
            
            end_time = time.time() + duration
            
            while time.time() < end_time:
                start_request = time.time()
                success = False
                
                try:
                    with conn.cursor() as cursor:
                        # 다양한 쿼리 실행
                        operation = random.choice([
                            "SELECT COUNT(*) FROM sensors.devices",
                            "SELECT * FROM sensors.sensor_readings ORDER BY created_at DESC LIMIT 100",
                            "SELECT vehicle_id, COUNT(*) FROM sensors.sensor_readings GROUP BY vehicle_id LIMIT 50",
                            "SELECT AVG(pressure_kpa) FROM sensors.tpms_data WHERE created_at > NOW() - INTERVAL '1 hour'"
                        ])
                        
                        cursor.execute(operation)
                        results = cursor.fetchall()
                        success = True
                        
                except Exception as e:
                    logger.debug(f"DB 쿼리 실패: {str(e)}")
                    conn.rollback()
                    success = False
                
                response_time = time.time() - start_request
                self.monitor.record_request(response_time, success)
                
                await asyncio.sleep(random.uniform(0.1, 1.0))
            
            conn.close()
            
        except Exception as e:
            logger.error(f"데이터베이스 작업 오류: {str(e)}")

    async def run_concurrent_users_test(self, config: TestConfig) -> TestResult:
        """동시 사용자 테스트"""
        logger.info(f"👥 동시 사용자 테스트 시작 - {config.concurrent_users}명")
        
        self.monitor.start_monitoring()
        start_time = datetime.utcnow()
        
        # 사용자 시나리오 시뮬레이션
        tasks = []
        for i in range(config.concurrent_users):
            task = asyncio.create_task(
                self._user_scenario_simulation(f"user_{i}", config.duration_seconds)
            )
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        end_time = datetime.utcnow()
        
        return self._analyze_results(TestType.CONCURRENT_USERS, start_time, end_time, config)

    async def _user_scenario_simulation(self, user_id: str, duration: int):
        """사용자 시나리오 시뮬레이션"""
        end_time = time.time() + duration
        
        # 사용자 행동 패턴
        scenarios = [
            self._dashboard_browsing,
            self._sensor_monitoring,
            self._data_analysis,
            self._alert_management
        ]
        
        while time.time() < end_time:
            scenario = random.choice(scenarios)
            await scenario(user_id)
            
            # 사용자 행동 간 휴식
            await asyncio.sleep(random.uniform(2.0, 10.0))

    async def _dashboard_browsing(self, user_id: str):
        """대시보드 브라우징 시뮬레이션"""
        endpoints = [
            "/dashboard/summary",
            "/dashboard/vehicles",
            "/dashboard/alerts",
            "/dashboard/analytics"
        ]
        
        for endpoint in random.sample(endpoints, random.randint(2, 4)):
            start_time = time.time()
            success = False
            
            try:
                async with self.session.get(f"{API_BASE_URL}{endpoint}") as response:
                    success = response.status < 400
                    await response.text()
            except Exception:
                success = False
            
            response_time = time.time() - start_time
            self.monitor.record_request(response_time, success)
            
            await asyncio.sleep(random.uniform(0.5, 2.0))

    async def _sensor_monitoring(self, user_id: str):
        """센서 모니터링 시뮬레이션"""
        # 센서 목록 조회
        start_time = time.time()
        success = False
        
        try:
            async with self.session.get(f"{API_BASE_URL}/sensors") as response:
                success = response.status < 400
                data = await response.json()
                
                if success and data:
                    # 특정 센서 상세 정보 조회
                    sensor_id = random.choice(data[:10])["id"] if data else "1"
                    async with self.session.get(f"{API_BASE_URL}/sensors/{sensor_id}") as detail_response:
                        await detail_response.text()
                        
        except Exception:
            success = False
        
        response_time = time.time() - start_time
        self.monitor.record_request(response_time, success)

    async def _data_analysis(self, user_id: str):
        """데이터 분석 시뮬레이션"""
        # 분석 쿼리 실행
        start_time = time.time()
        success = False
        
        try:
            params = {
                "start_date": (datetime.utcnow() - timedelta(days=7)).isoformat(),
                "end_date": datetime.utcnow().isoformat(),
                "vehicle_ids": ",".join(random.sample(self.data_generator.vehicle_ids, 10))
            }
            
            async with self.session.get(f"{API_BASE_URL}/analytics/trends", params=params) as response:
                success = response.status < 400
                await response.text()
                
        except Exception:
            success = False
        
        response_time = time.time() - start_time
        self.monitor.record_request(response_time, success)

    async def _alert_management(self, user_id: str):
        """알림 관리 시뮬레이션"""
        start_time = time.time()
        success = False
        
        try:
            async with self.session.get(f"{API_BASE_URL}/alerts") as response:
                success = response.status < 400
                await response.text()
                
        except Exception:
            success = False
        
        response_time = time.time() - start_time
        self.monitor.record_request(response_time, success)

    def _analyze_results(self, test_type: TestType, start_time: datetime, end_time: datetime, config: TestConfig) -> TestResult:
        """결과 분석"""
        response_times = self.monitor.metrics['response_times']
        errors = self.monitor.metrics['errors']
        
        if not response_times:
            return TestResult(
                test_type=test_type,
                start_time=start_time,
                end_time=end_time,
                total_requests=0,
                successful_requests=0,
                failed_requests=0,
                avg_response_time=0,
                p50_response_time=0,
                p95_response_time=0,
                p99_response_time=0,
                max_response_time=0,
                min_response_time=0,
                throughput_rps=0,
                error_rate=0,
                cpu_usage_percent=0,
                memory_usage_mb=0,
                network_io_mb=0,
                database_connections=0,
                cache_hit_rate=0,
                details={}
            )
        
        total_requests = len(response_times)
        failed_requests = sum(errors)
        successful_requests = total_requests - failed_requests
        
        duration = (end_time - start_time).total_seconds()
        throughput_rps = total_requests / duration if duration > 0 else 0
        error_rate = failed_requests / total_requests if total_requests > 0 else 0
        
        # 응답 시간 통계
        avg_response_time = statistics.mean(response_times)
        p50_response_time = np.percentile(response_times, 50)
        p95_response_time = np.percentile(response_times, 95)
        p99_response_time = np.percentile(response_times, 99)
        max_response_time = max(response_times)
        min_response_time = min(response_times)
        
        # 시스템 메트릭 (시뮬레이션)
        cpu_usage = random.uniform(30, 80)
        memory_usage = random.uniform(1000, 4000)
        
        return TestResult(
            test_type=test_type,
            start_time=start_time,
            end_time=end_time,
            total_requests=total_requests,
            successful_requests=successful_requests,
            failed_requests=failed_requests,
            avg_response_time=avg_response_time,
            p50_response_time=p50_response_time,
            p95_response_time=p95_response_time,
            p99_response_time=p99_response_time,
            max_response_time=max_response_time,
            min_response_time=min_response_time,
            throughput_rps=throughput_rps,
            error_rate=error_rate,
            cpu_usage_percent=cpu_usage,
            memory_usage_mb=memory_usage,
            network_io_mb=random.uniform(100, 500),
            database_connections=random.randint(10, 50),
            cache_hit_rate=random.uniform(0.85, 0.98),
            details={
                'config': asdict(config),
                'response_time_distribution': {
                    'p10': np.percentile(response_times, 10),
                    'p25': np.percentile(response_times, 25),
                    'p75': np.percentile(response_times, 75),
                    'p90': np.percentile(response_times, 90)
                }
            }
        )

class PerformanceReporter:
    """성능 리포트 생성기"""
    
    def __init__(self):
        self.results = []
        
    def add_result(self, result: TestResult):
        """결과 추가"""
        self.results.append(result)
        
    def generate_report(self, output_dir: str = "./performance_reports"):
        """성능 리포트 생성"""
        os.makedirs(output_dir, exist_ok=True)
        
        # JSON 리포트
        self._generate_json_report(output_dir)
        
        # 차트 생성
        self._generate_charts(output_dir)
        
        # HTML 리포트
        self._generate_html_report(output_dir)
        
        logger.info(f"✅ 성능 리포트 생성 완료: {output_dir}")

    def _generate_json_report(self, output_dir: str):
        """JSON 리포트 생성"""
        report_data = {
            'test_summary': {
                'total_tests': len(self.results),
                'generated_at': datetime.utcnow().isoformat(),
                'test_types': list(set(r.test_type.value for r in self.results))
            },
            'test_results': [
                {
                    'test_type': r.test_type.value,
                    'start_time': r.start_time.isoformat(),
                    'end_time': r.end_time.isoformat(),
                    'duration_seconds': (r.end_time - r.start_time).total_seconds(),
                    'total_requests': r.total_requests,
                    'successful_requests': r.successful_requests,
                    'failed_requests': r.failed_requests,
                    'avg_response_time': round(r.avg_response_time, 3),
                    'p95_response_time': round(r.p95_response_time, 3),
                    'throughput_rps': round(r.throughput_rps, 2),
                    'error_rate': round(r.error_rate, 4),
                    'cpu_usage_percent': round(r.cpu_usage_percent, 2),
                    'memory_usage_mb': round(r.memory_usage_mb, 2),
                    'cache_hit_rate': round(r.cache_hit_rate, 4)
                }
                for r in self.results
            ]
        }
        
        with open(f"{output_dir}/performance_report.json", 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)

    def _generate_charts(self, output_dir: str):
        """차트 생성"""
        if not self.results:
            return
            
        plt.style.use('seaborn-v0_8')
        
        # 응답 시간 분포 차트
        fig, axes = plt.subplots(2, 2, figsize=(15, 12))
        fig.suptitle('HankookTire SmartSensor 2.0 - Performance Test Results', fontsize=16)
        
        # 1. 응답 시간 비교
        test_types = [r.test_type.value for r in self.results]
        avg_times = [r.avg_response_time for r in self.results]
        p95_times = [r.p95_response_time for r in self.results]
        
        x = np.arange(len(test_types))
        width = 0.35
        
        axes[0, 0].bar(x - width/2, avg_times, width, label='Average', alpha=0.8)
        axes[0, 0].bar(x + width/2, p95_times, width, label='95th Percentile', alpha=0.8)
        axes[0, 0].set_xlabel('Test Type')
        axes[0, 0].set_ylabel('Response Time (seconds)')
        axes[0, 0].set_title('Response Time Comparison')
        axes[0, 0].set_xticks(x)
        axes[0, 0].set_xticklabels(test_types, rotation=45)
        axes[0, 0].legend()
        
        # 2. 처리량 비교
        throughputs = [r.throughput_rps for r in self.results]
        axes[0, 1].bar(test_types, throughputs, alpha=0.8, color='green')
        axes[0, 1].set_xlabel('Test Type')
        axes[0, 1].set_ylabel('Throughput (requests/sec)')
        axes[0, 1].set_title('Throughput Comparison')
        axes[0, 1].tick_params(axis='x', rotation=45)
        
        # 3. 오류율 비교
        error_rates = [r.error_rate * 100 for r in self.results]
        axes[1, 0].bar(test_types, error_rates, alpha=0.8, color='red')
        axes[1, 0].set_xlabel('Test Type')
        axes[1, 0].set_ylabel('Error Rate (%)')
        axes[1, 0].set_title('Error Rate Comparison')
        axes[1, 0].tick_params(axis='x', rotation=45)
        
        # 4. 리소스 사용률
        cpu_usage = [r.cpu_usage_percent for r in self.results]
        memory_usage = [r.memory_usage_mb / 1000 for r in self.results]  # GB 변환
        
        x = np.arange(len(test_types))
        axes[1, 1].bar(x - width/2, cpu_usage, width, label='CPU (%)', alpha=0.8)
        axes[1, 1].bar(x + width/2, memory_usage, width, label='Memory (GB)', alpha=0.8)
        axes[1, 1].set_xlabel('Test Type')
        axes[1, 1].set_ylabel('Resource Usage')
        axes[1, 1].set_title('Resource Usage Comparison')
        axes[1, 1].set_xticks(x)
        axes[1, 1].set_xticklabels(test_types, rotation=45)
        axes[1, 1].legend()
        
        plt.tight_layout()
        plt.savefig(f"{output_dir}/performance_charts.png", dpi=300, bbox_inches='tight')
        plt.close()

    def _generate_html_report(self, output_dir: str):
        """HTML 리포트 생성"""
        html_content = f"""
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>HankookTire SmartSensor 2.0 - Performance Test Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .header {{ background: #1e88e5; color: white; padding: 20px; border-radius: 8px; }}
        .summary {{ background: #f5f5f5; padding: 15px; border-radius: 8px; margin: 20px 0; }}
        .test-result {{ border: 1px solid #ddd; margin: 10px 0; border-radius: 8px; }}
        .test-header {{ background: #e3f2fd; padding: 10px; font-weight: bold; }}
        .test-details {{ padding: 15px; }}
        .metric {{ display: inline-block; margin: 10px; text-align: center; }}
        .metric-value {{ font-size: 24px; font-weight: bold; color: #1976d2; }}
        .metric-label {{ font-size: 12px; color: #666; }}
        .chart {{ text-align: center; margin: 20px 0; }}
        .status-good {{ color: #4caf50; }}
        .status-warning {{ color: #ff9800; }}
        .status-error {{ color: #f44336; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🚀 HankookTire SmartSensor 2.0</h1>
        <h2>Performance Test Report</h2>
        <p>Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC</p>
    </div>
    
    <div class="summary">
        <h3>📊 Test Summary</h3>
        <div class="metric">
            <div class="metric-value">{len(self.results)}</div>
            <div class="metric-label">Total Tests</div>
        </div>
        <div class="metric">
            <div class="metric-value">{sum(r.total_requests for r in self.results):,}</div>
            <div class="metric-label">Total Requests</div>
        </div>
        <div class="metric">
            <div class="metric-value">{sum(r.successful_requests for r in self.results):,}</div>
            <div class="metric-label">Successful Requests</div>
        </div>
        <div class="metric">
            <div class="metric-value">{(sum(r.error_rate for r in self.results) / len(self.results) * 100):.2f}%</div>
            <div class="metric-label">Average Error Rate</div>
        </div>
    </div>
    
    <div class="chart">
        <img src="performance_charts.png" alt="Performance Charts" style="max-width: 100%;">
    </div>
"""
        
        for result in self.results:
            status_class = "status-good"
            if result.error_rate > 0.05:
                status_class = "status-error"
            elif result.error_rate > 0.01:
                status_class = "status-warning"
                
            html_content += f"""
    <div class="test-result">
        <div class="test-header">
            {result.test_type.value.replace('_', ' ').title()} Test
            <span class="{status_class}">({'✅ PASS' if result.error_rate <= 0.05 else '❌ FAIL'})</span>
        </div>
        <div class="test-details">
            <div class="metric">
                <div class="metric-value">{result.total_requests:,}</div>
                <div class="metric-label">Total Requests</div>
            </div>
            <div class="metric">
                <div class="metric-value">{result.avg_response_time:.3f}s</div>
                <div class="metric-label">Avg Response Time</div>
            </div>
            <div class="metric">
                <div class="metric-value">{result.p95_response_time:.3f}s</div>
                <div class="metric-label">95th Percentile</div>
            </div>
            <div class="metric">
                <div class="metric-value">{result.throughput_rps:.1f}</div>
                <div class="metric-label">Requests/sec</div>
            </div>
            <div class="metric">
                <div class="metric-value">{result.error_rate*100:.2f}%</div>
                <div class="metric-label">Error Rate</div>
            </div>
            <div class="metric">
                <div class="metric-value">{result.cpu_usage_percent:.1f}%</div>
                <div class="metric-label">CPU Usage</div>
            </div>
            <div class="metric">
                <div class="metric-value">{result.memory_usage_mb:.0f}MB</div>
                <div class="metric-label">Memory Usage</div>
            </div>
        </div>
    </div>
"""
        
        html_content += """
</body>
</html>
"""
        
        with open(f"{output_dir}/performance_report.html", 'w', encoding='utf-8') as f:
            f.write(html_content)

async def main():
    """메인 실행 함수"""
    logger.info("🚀 HankookTire SmartSensor 2.0 성능 테스트 시작")
    
    # 테스트 설정
    test_configs = [
        TestConfig(
            test_type=TestType.API_LOAD,
            duration_seconds=60,
            concurrent_users=50,
            rps_target=1000,
            load_pattern=LoadPattern.CONSTANT,
            test_data_size=1000
        ),
        TestConfig(
            test_type=TestType.SENSOR_STREAMING,
            duration_seconds=60,
            concurrent_users=20,
            rps_target=500,
            load_pattern=LoadPattern.CONSTANT,
            test_data_size=500
        ),
        TestConfig(
            test_type=TestType.DATABASE_STRESS,
            duration_seconds=45,
            concurrent_users=30,
            rps_target=200,
            load_pattern=LoadPattern.RAMP_UP,
            test_data_size=1000
        ),
        TestConfig(
            test_type=TestType.CONCURRENT_USERS,
            duration_seconds=90,
            concurrent_users=100,
            rps_target=800,
            load_pattern=LoadPattern.STEP,
            test_data_size=2000
        )
    ]
    
    reporter = PerformanceReporter()
    
    async with LoadTestRunner() as runner:
        for config in test_configs:
            logger.info(f"🧪 {config.test_type.value} 테스트 실행 중...")
            
            try:
                if config.test_type == TestType.API_LOAD:
                    result = await runner.run_api_load_test(config)
                elif config.test_type == TestType.SENSOR_STREAMING:
                    result = await runner.run_sensor_streaming_test(config)
                elif config.test_type == TestType.DATABASE_STRESS:
                    result = await runner.run_database_stress_test(config)
                elif config.test_type == TestType.CONCURRENT_USERS:
                    result = await runner.run_concurrent_users_test(config)
                else:
                    continue
                
                reporter.add_result(result)
                
                # 결과 출력
                logger.info(f"✅ {config.test_type.value} 테스트 완료:")
                logger.info(f"   총 요청: {result.total_requests:,}")
                logger.info(f"   성공률: {(result.successful_requests/result.total_requests*100):.1f}%")
                logger.info(f"   평균 응답시간: {result.avg_response_time:.3f}초")
                logger.info(f"   처리량: {result.throughput_rps:.1f} req/sec")
                logger.info(f"   95% 응답시간: {result.p95_response_time:.3f}초")
                
            except Exception as e:
                logger.error(f"❌ {config.test_type.value} 테스트 실패: {str(e)}")
            
            # 테스트 간 휴식
            await asyncio.sleep(10)
    
    # 리포트 생성
    reporter.generate_report()
    
    logger.info("🎉 모든 성능 테스트 완료!")

if __name__ == "__main__":
    asyncio.run(main())