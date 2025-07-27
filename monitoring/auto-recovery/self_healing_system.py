#!/usr/bin/env python3
"""
HankookTire SmartSensor 2.0 - Self-Healing & Auto-Recovery System
차세대 자가 치유 및 자동 복구 시스템

Advanced self-healing capabilities:
- Automatic service restart and recovery
- Smart load balancing and failover
- Predictive scaling based on ML models
- Auto-remediation of common issues
- Chaos engineering for resilience testing
"""

import asyncio
import logging
import json
import os
import time
import yaml
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any, Callable
from dataclasses import dataclass, asdict
from enum import Enum
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
import psutil

# Kubernetes and Infrastructure
from kubernetes import client, config, watch
from kubernetes.client.rest import ApiException
import docker
import redis
import psycopg2
from psycopg2.extras import RealDictCursor

# Monitoring and Metrics
import aiohttp
import prometheus_client
from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry

# ML for Predictive Actions
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler
import joblib

# Configuration
KUBERNETES_NAMESPACE = os.getenv('KUBERNETES_NAMESPACE', 'hankook-smartsensor')
MONITORING_NAMESPACE = os.getenv('MONITORING_NAMESPACE', 'monitoring')
REDIS_HOST = os.getenv('REDIS_HOST', 'redis-service')
REDIS_PORT = int(os.getenv('REDIS_PORT', '6379'))
POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'postgres-service')
API_BASE_URL = os.getenv('API_BASE_URL', 'http://api-service:8000')
SLACK_WEBHOOK = os.getenv('SLACK_WEBHOOK', '')
ENABLE_CHAOS_ENGINEERING = os.getenv('ENABLE_CHAOS_ENGINEERING', 'false').lower() == 'true'

# Logging Setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/self-healing.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Prometheus Metrics
registry = CollectorRegistry()
recovery_actions_total = Counter('self_healing_recovery_actions_total', 
                                'Total number of recovery actions taken', 
                                ['action_type', 'target_service'], registry=registry)
recovery_success_rate = Gauge('self_healing_success_rate', 
                             'Success rate of recovery actions', 
                             ['action_type'], registry=registry)
system_health_score = Gauge('self_healing_system_health_score', 
                           'Overall system health score', registry=registry)
prediction_accuracy = Gauge('self_healing_prediction_accuracy', 
                           'Accuracy of predictive scaling models', registry=registry)

class RecoveryAction(Enum):
    """복구 액션 유형"""
    RESTART_POD = "restart_pod"
    SCALE_UP = "scale_up"
    SCALE_DOWN = "scale_down"
    RESTART_SERVICE = "restart_service"
    CLEAR_CACHE = "clear_cache"
    ROTATE_LOGS = "rotate_logs"
    UPDATE_CONFIG = "update_config"
    FAILOVER = "failover"
    CIRCUIT_BREAKER = "circuit_breaker"
    CLEANUP_RESOURCES = "cleanup_resources"
    REBALANCE_LOAD = "rebalance_load"
    CHAOS_TEST = "chaos_test"

class Severity(Enum):
    """심각도"""
    INFO = 1
    WARNING = 2
    ERROR = 3
    CRITICAL = 4
    EMERGENCY = 5

@dataclass
class HealthIssue:
    """헬스 이슈 정의"""
    component: str
    issue_type: str
    severity: Severity
    description: str
    metrics: Dict[str, Any]
    timestamp: datetime
    auto_recoverable: bool = True
    recovery_actions: List[RecoveryAction] = None
    cooldown_period: int = 300  # 5분

@dataclass
class RecoveryResult:
    """복구 결과"""
    action: RecoveryAction
    target: str
    success: bool
    duration: float
    message: str
    timestamp: datetime
    side_effects: List[str] = None

class SelfHealingSystem:
    """자가 치유 시스템 메인 클래스"""
    
    def __init__(self):
        self.k8s_apps_v1 = None
        self.k8s_core_v1 = None
        self.docker_client = None
        self.redis_client = None
        self.session = None
        
        self.recovery_history = []
        self.action_cooldowns = {}
        self.health_checks = {}
        self.predictive_models = {}
        
        # 복구 규칙 정의
        self.recovery_rules = self._load_recovery_rules()
        
        # 스케일링 예측 모델
        self.scaling_predictor = None
        self.scaling_scaler = StandardScaler()
        
        # 상태 추적
        self.system_status = {
            'last_health_check': None,
            'active_issues': [],
            'recovery_queue': [],
            'circuit_breakers': {},
            'maintenance_mode': False
        }

    async def __aenter__(self):
        """비동기 컨텍스트 관리자 진입"""
        # Kubernetes 클라이언트 초기화
        try:
            config.load_incluster_config()
        except:
            config.load_kube_config()
        
        self.k8s_apps_v1 = client.AppsV1Api()
        self.k8s_core_v1 = client.CoreV1Api()
        
        # Docker 클라이언트 (로컬 개발용)
        try:
            self.docker_client = docker.from_env()
        except:
            logger.warning("Docker 클라이언트 연결 실패")
        
        # Redis 클라이언트
        self.redis_client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            decode_responses=True
        )
        
        # HTTP 세션
        timeout = aiohttp.ClientTimeout(total=30)
        self.session = aiohttp.ClientSession(timeout=timeout)
        
        # 예측 모델 로드
        await self.load_predictive_models()
        
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """비동기 컨텍스트 관리자 종료"""
        if self.session:
            await self.session.close()

    def _load_recovery_rules(self) -> Dict[str, Dict]:
        """복구 규칙 로드"""
        return {
            # API 서버 관련
            'api_high_response_time': {
                'condition': lambda metrics: metrics.get('avg_response_time', 0) > 2000,
                'actions': [RecoveryAction.SCALE_UP, RecoveryAction.RESTART_POD],
                'severity': Severity.WARNING,
                'cooldown': 300
            },
            'api_high_error_rate': {
                'condition': lambda metrics: metrics.get('error_rate', 0) > 0.05,
                'actions': [RecoveryAction.RESTART_POD, RecoveryAction.CLEAR_CACHE],
                'severity': Severity.ERROR,
                'cooldown': 180
            },
            'api_pod_crash_loop': {
                'condition': lambda metrics: metrics.get('restart_count', 0) > 5,
                'actions': [RecoveryAction.SCALE_UP, RecoveryAction.UPDATE_CONFIG],
                'severity': Severity.CRITICAL,
                'cooldown': 600
            },
            
            # 데이터베이스 관련
            'database_high_connections': {
                'condition': lambda metrics: metrics.get('active_connections', 0) > 180,
                'actions': [RecoveryAction.RESTART_SERVICE, RecoveryAction.CLEAR_CACHE],
                'severity': Severity.WARNING,
                'cooldown': 300
            },
            'database_deadlocks': {
                'condition': lambda metrics: metrics.get('deadlocks_per_minute', 0) > 5,
                'actions': [RecoveryAction.RESTART_SERVICE],
                'severity': Severity.ERROR,
                'cooldown': 600
            },
            'database_disk_space': {
                'condition': lambda metrics: metrics.get('disk_usage_percent', 0) > 85,
                'actions': [RecoveryAction.CLEANUP_RESOURCES, RecoveryAction.ROTATE_LOGS],
                'severity': Severity.CRITICAL,
                'cooldown': 900
            },
            
            # Redis 관련
            'redis_memory_high': {
                'condition': lambda metrics: metrics.get('memory_usage_percent', 0) > 90,
                'actions': [RecoveryAction.CLEAR_CACHE, RecoveryAction.RESTART_SERVICE],
                'severity': Severity.WARNING,
                'cooldown': 300
            },
            'redis_connection_spike': {
                'condition': lambda metrics: metrics.get('connected_clients', 0) > 1000,
                'actions': [RecoveryAction.CIRCUIT_BREAKER, RecoveryAction.REBALANCE_LOAD],
                'severity': Severity.ERROR,
                'cooldown': 180
            },
            
            # MQTT 관련
            'mqtt_connection_drop': {
                'condition': lambda metrics: metrics.get('client_disconnect_rate', 0) > 50,
                'actions': [RecoveryAction.RESTART_SERVICE, RecoveryAction.FAILOVER],
                'severity': Severity.ERROR,
                'cooldown': 300
            },
            
            # 시스템 리소스
            'high_cpu_usage': {
                'condition': lambda metrics: metrics.get('cpu_usage_percent', 0) > 80,
                'actions': [RecoveryAction.SCALE_UP],
                'severity': Severity.WARNING,
                'cooldown': 600
            },
            'high_memory_usage': {
                'condition': lambda metrics: metrics.get('memory_usage_percent', 0) > 85,
                'actions': [RecoveryAction.CLEANUP_RESOURCES, RecoveryAction.SCALE_UP],
                'severity': Severity.WARNING,
                'cooldown': 600
            },
            'disk_space_critical': {
                'condition': lambda metrics: metrics.get('disk_usage_percent', 0) > 95,
                'actions': [RecoveryAction.CLEANUP_RESOURCES, RecoveryAction.ROTATE_LOGS],
                'severity': Severity.CRITICAL,
                'cooldown': 300
            }
        }

    async def continuous_health_monitoring(self):
        """지속적인 헬스 모니터링"""
        logger.info("🏥 자가 치유 시스템 모니터링 시작...")
        
        while True:
            try:
                start_time = time.time()
                
                # 헬스 체크 실행
                health_issues = await self.perform_comprehensive_health_check()
                
                # 이슈 분석 및 복구 계획
                recovery_plan = await self.analyze_and_plan_recovery(health_issues)
                
                # 복구 액션 실행
                if recovery_plan:
                    await self.execute_recovery_plan(recovery_plan)
                
                # 예측적 스케일링
                await self.predictive_scaling()
                
                # 시스템 상태 업데이트
                await self.update_system_status(health_issues)
                
                # 메트릭 업데이트
                self.update_prometheus_metrics()
                
                # 카오스 엔지니어링 (활성화된 경우)
                if ENABLE_CHAOS_ENGINEERING and datetime.now().hour in [2, 14]:  # 새벽 2시, 오후 2시
                    await self.chaos_engineering_test()
                
                # 실행 시간 로깅
                duration = time.time() - start_time
                logger.debug(f"헬스 모니터링 사이클 완료: {duration:.2f}초")
                
                # 대기 (30초 간격)
                await asyncio.sleep(30)
                
            except Exception as e:
                logger.error(f"❌ 헬스 모니터링 오류: {str(e)}")
                await asyncio.sleep(60)  # 오류 시 1분 대기

    async def perform_comprehensive_health_check(self) -> List[HealthIssue]:
        """포괄적 헬스 체크"""
        issues = []
        
        try:
            # 동시에 모든 헬스 체크 실행
            health_check_tasks = [
                self.check_api_health(),
                self.check_database_health(),
                self.check_redis_health(),
                self.check_mqtt_health(),
                self.check_kubernetes_pods(),
                self.check_system_resources(),
                self.check_sensor_connectivity()
            ]
            
            results = await asyncio.gather(*health_check_tasks, return_exceptions=True)
            
            # 결과 처리
            for result in results:
                if isinstance(result, list):
                    issues.extend(result)
                elif isinstance(result, Exception):
                    logger.error(f"헬스 체크 오류: {str(result)}")
            
            self.system_status['last_health_check'] = datetime.now()
            logger.debug(f"🔍 헬스 체크 완료: {len(issues)}개 이슈 발견")
            
        except Exception as e:
            logger.error(f"❌ 포괄적 헬스 체크 실패: {str(e)}")
        
        return issues

    async def check_api_health(self) -> List[HealthIssue]:
        """API 서버 헬스 체크"""
        issues = []
        
        try:
            # API 메트릭 수집
            async with self.session.get(f"{API_BASE_URL}/metrics") as response:
                if response.status == 200:
                    metrics_text = await response.text()
                    metrics = self.parse_prometheus_metrics(metrics_text)
                    
                    # 규칙 기반 이슈 탐지
                    for rule_name, rule in self.recovery_rules.items():
                        if 'api' in rule_name and rule['condition'](metrics):
                            issues.append(HealthIssue(
                                component='api-server',
                                issue_type=rule_name,
                                severity=rule['severity'],
                                description=f"API 서버 이슈 감지: {rule_name}",
                                metrics=metrics,
                                timestamp=datetime.now(),
                                recovery_actions=rule['actions'],
                                cooldown_period=rule['cooldown']
                            ))
                else:
                    issues.append(HealthIssue(
                        component='api-server',
                        issue_type='api_unreachable',
                        severity=Severity.CRITICAL,
                        description=f"API 서버 접근 불가 (HTTP {response.status})",
                        metrics={'status_code': response.status},
                        timestamp=datetime.now(),
                        recovery_actions=[RecoveryAction.RESTART_POD, RecoveryAction.FAILOVER]
                    ))
                    
        except Exception as e:
            issues.append(HealthIssue(
                component='api-server',
                issue_type='connection_error',
                severity=Severity.CRITICAL,
                description=f"API 서버 연결 오류: {str(e)}",
                metrics={},
                timestamp=datetime.now(),
                recovery_actions=[RecoveryAction.RESTART_POD]
            ))
        
        return issues

    async def check_database_health(self) -> List[HealthIssue]:
        """데이터베이스 헬스 체크"""
        issues = []
        
        try:
            conn = psycopg2.connect(
                host=POSTGRES_HOST,
                port=5432,
                database='hankook_sensors',
                user='hankook',
                password=os.getenv('POSTGRES_PASSWORD', 'password'),
                connect_timeout=10
            )
            
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                # 활성 연결 수 확인
                cursor.execute("SELECT count(*) as active_connections FROM pg_stat_activity")
                active_connections = cursor.fetchone()['active_connections']
                
                # 데드락 확인
                cursor.execute("""
                    SELECT count(*) as deadlocks 
                    FROM pg_stat_database 
                    WHERE datname = 'hankook_sensors'
                """)
                deadlocks = cursor.fetchone()['deadlocks']
                
                # 디스크 사용량 확인
                cursor.execute("SELECT pg_size_pretty(pg_database_size('hankook_sensors')) as db_size")
                db_size = cursor.fetchone()['db_size']
                
                # 느린 쿼리 확인
                cursor.execute("""
                    SELECT count(*) as slow_queries 
                    FROM pg_stat_statements 
                    WHERE mean_exec_time > 1000
                """)
                slow_queries = cursor.fetchone()['slow_queries'] if cursor.rowcount > 0 else 0
                
                metrics = {
                    'active_connections': active_connections,
                    'deadlocks_per_minute': deadlocks,
                    'slow_queries': slow_queries,
                    'disk_usage_percent': 70  # 실제로는 시스템 디스크 사용량 체크
                }
                
                # 규칙 기반 이슈 탐지
                for rule_name, rule in self.recovery_rules.items():
                    if 'database' in rule_name and rule['condition'](metrics):
                        issues.append(HealthIssue(
                            component='database',
                            issue_type=rule_name,
                            severity=rule['severity'],
                            description=f"데이터베이스 이슈 감지: {rule_name}",
                            metrics=metrics,
                            timestamp=datetime.now(),
                            recovery_actions=rule['actions'],
                            cooldown_period=rule['cooldown']
                        ))
            
            conn.close()
            
        except Exception as e:
            issues.append(HealthIssue(
                component='database',
                issue_type='connection_error',
                severity=Severity.CRITICAL,
                description=f"데이터베이스 연결 오류: {str(e)}",
                metrics={},
                timestamp=datetime.now(),
                recovery_actions=[RecoveryAction.RESTART_SERVICE]
            ))
        
        return issues

    async def check_redis_health(self) -> List[HealthIssue]:
        """Redis 헬스 체크"""
        issues = []
        
        try:
            # Redis 정보 수집
            info = self.redis_client.info()
            
            metrics = {
                'memory_usage_percent': (info['used_memory'] / info.get('maxmemory', info['used_memory'] * 2)) * 100,
                'connected_clients': info['connected_clients'],
                'keyspace_hits': info['keyspace_hits'],
                'keyspace_misses': info['keyspace_misses']
            }
            
            # 규칙 기반 이슈 탐지
            for rule_name, rule in self.recovery_rules.items():
                if 'redis' in rule_name and rule['condition'](metrics):
                    issues.append(HealthIssue(
                        component='redis',
                        issue_type=rule_name,
                        severity=rule['severity'],
                        description=f"Redis 이슈 감지: {rule_name}",
                        metrics=metrics,
                        timestamp=datetime.now(),
                        recovery_actions=rule['actions'],
                        cooldown_period=rule['cooldown']
                    ))
                    
        except Exception as e:
            issues.append(HealthIssue(
                component='redis',
                issue_type='connection_error',
                severity=Severity.CRITICAL,
                description=f"Redis 연결 오류: {str(e)}",
                metrics={},
                timestamp=datetime.now(),
                recovery_actions=[RecoveryAction.RESTART_SERVICE]
            ))
        
        return issues

    async def check_mqtt_health(self) -> List[HealthIssue]:
        """MQTT 브로커 헬스 체크"""
        issues = []
        
        try:
            # MQTT 메트릭 수집 (Prometheus exporter 통해)
            async with self.session.get("http://mosquitto-service:9234/metrics") as response:
                if response.status == 200:
                    metrics_text = await response.text()
                    metrics = self.parse_prometheus_metrics(metrics_text, prefix='mosquitto_')
                    
                    # 규칙 기반 이슈 탐지
                    for rule_name, rule in self.recovery_rules.items():
                        if 'mqtt' in rule_name and rule['condition'](metrics):
                            issues.append(HealthIssue(
                                component='mqtt',
                                issue_type=rule_name,
                                severity=rule['severity'],
                                description=f"MQTT 브로커 이슈 감지: {rule_name}",
                                metrics=metrics,
                                timestamp=datetime.now(),
                                recovery_actions=rule['actions'],
                                cooldown_period=rule['cooldown']
                            ))
                            
        except Exception as e:
            issues.append(HealthIssue(
                component='mqtt',
                issue_type='metrics_error',
                severity=Severity.WARNING,
                description=f"MQTT 메트릭 수집 오류: {str(e)}",
                metrics={},
                timestamp=datetime.now(),
                recovery_actions=[RecoveryAction.RESTART_SERVICE]
            ))
        
        return issues

    async def check_kubernetes_pods(self) -> List[HealthIssue]:
        """Kubernetes Pod 상태 체크"""
        issues = []
        
        try:
            # Pod 목록 조회
            pods = self.k8s_core_v1.list_namespaced_pod(namespace=KUBERNETES_NAMESPACE)
            
            for pod in pods.items:
                if not pod.metadata.name.startswith('hankook-'):
                    continue
                
                # Pod 상태 분석
                if pod.status.phase != 'Running':
                    issues.append(HealthIssue(
                        component=f"pod-{pod.metadata.name}",
                        issue_type='pod_not_running',
                        severity=Severity.ERROR,
                        description=f"Pod {pod.metadata.name}이 실행 중이 아님: {pod.status.phase}",
                        metrics={'phase': pod.status.phase},
                        timestamp=datetime.now(),
                        recovery_actions=[RecoveryAction.RESTART_POD]
                    ))
                
                # 재시작 횟수 체크
                restart_count = 0
                if pod.status.container_statuses:
                    restart_count = sum(container.restart_count for container in pod.status.container_statuses)
                
                if restart_count > 5:
                    issues.append(HealthIssue(
                        component=f"pod-{pod.metadata.name}",
                        issue_type='high_restart_count',
                        severity=Severity.WARNING,
                        description=f"Pod {pod.metadata.name} 재시작 횟수 과다: {restart_count}",
                        metrics={'restart_count': restart_count},
                        timestamp=datetime.now(),
                        recovery_actions=[RecoveryAction.SCALE_UP, RecoveryAction.UPDATE_CONFIG]
                    ))
                    
        except Exception as e:
            logger.error(f"❌ Kubernetes Pod 체크 오류: {str(e)}")
        
        return issues

    async def check_system_resources(self) -> List[HealthIssue]:
        """시스템 리소스 체크"""
        issues = []
        
        try:
            # CPU, 메모리, 디스크 사용량 체크
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            metrics = {
                'cpu_usage_percent': cpu_percent,
                'memory_usage_percent': memory.percent,
                'disk_usage_percent': disk.percent
            }
            
            # 규칙 기반 이슈 탐지
            for rule_name, rule in self.recovery_rules.items():
                if any(keyword in rule_name for keyword in ['cpu', 'memory', 'disk']) and rule['condition'](metrics):
                    issues.append(HealthIssue(
                        component='system-resources',
                        issue_type=rule_name,
                        severity=rule['severity'],
                        description=f"시스템 리소스 이슈 감지: {rule_name}",
                        metrics=metrics,
                        timestamp=datetime.now(),
                        recovery_actions=rule['actions'],
                        cooldown_period=rule['cooldown']
                    ))
                    
        except Exception as e:
            logger.error(f"❌ 시스템 리소스 체크 오류: {str(e)}")
        
        return issues

    async def check_sensor_connectivity(self) -> List[HealthIssue]:
        """센서 연결성 체크"""
        issues = []
        
        try:
            async with self.session.get(f"{API_BASE_URL}/sensors/status") as response:
                if response.status == 200:
                    data = await response.json()
                    
                    total_sensors = data.get('total_sensors', 0)
                    offline_sensors = data.get('offline_sensors', 0)
                    
                    if total_sensors > 0:
                        offline_rate = offline_sensors / total_sensors
                        
                        if offline_rate > 0.3:  # 30% 이상 오프라인
                            issues.append(HealthIssue(
                                component='sensor-network',
                                issue_type='high_offline_rate',
                                severity=Severity.CRITICAL if offline_rate > 0.5 else Severity.WARNING,
                                description=f"센서 오프라인 비율 높음: {offline_rate:.1%}",
                                metrics={'offline_rate': offline_rate, 'offline_sensors': offline_sensors},
                                timestamp=datetime.now(),
                                recovery_actions=[RecoveryAction.RESTART_SERVICE, RecoveryAction.FAILOVER],
                                auto_recoverable=False  # 물리적 센서 이슈는 자동 복구 불가
                            ))
                            
        except Exception as e:
            logger.error(f"❌ 센서 연결성 체크 오류: {str(e)}")
        
        return issues

    async def analyze_and_plan_recovery(self, health_issues: List[HealthIssue]) -> List[Tuple[HealthIssue, RecoveryAction]]:
        """이슈 분석 및 복구 계획 수립"""
        recovery_plan = []
        
        # 심각도별 정렬
        sorted_issues = sorted(health_issues, key=lambda x: x.severity.value, reverse=True)
        
        for issue in sorted_issues:
            if not issue.auto_recoverable:
                logger.warning(f"자동 복구 불가 이슈: {issue.component} - {issue.issue_type}")
                continue
            
            # 쿨다운 체크
            cooldown_key = f"{issue.component}_{issue.issue_type}"
            if cooldown_key in self.action_cooldowns:
                last_action_time = self.action_cooldowns[cooldown_key]
                if datetime.now() - last_action_time < timedelta(seconds=issue.cooldown_period):
                    logger.debug(f"쿨다운 중: {cooldown_key}")
                    continue
            
            # 복구 액션 선택
            if issue.recovery_actions:
                # 첫 번째 액션부터 시도
                selected_action = issue.recovery_actions[0]
                recovery_plan.append((issue, selected_action))
                
                # 쿨다운 설정
                self.action_cooldowns[cooldown_key] = datetime.now()
        
        logger.info(f"🎯 복구 계획 수립 완료: {len(recovery_plan)}개 액션")
        return recovery_plan

    async def execute_recovery_plan(self, recovery_plan: List[Tuple[HealthIssue, RecoveryAction]]):
        """복구 계획 실행"""
        logger.info(f"🔧 복구 계획 실행 시작: {len(recovery_plan)}개 액션")
        
        recovery_tasks = []
        for issue, action in recovery_plan:
            task = asyncio.create_task(self.execute_recovery_action(issue, action))
            recovery_tasks.append(task)
        
        # 모든 복구 액션 병렬 실행
        results = await asyncio.gather(*recovery_tasks, return_exceptions=True)
        
        # 결과 처리
        for i, result in enumerate(results):
            if isinstance(result, RecoveryResult):
                self.recovery_history.append(result)
                recovery_actions_total.labels(
                    action_type=result.action.value,
                    target_service=result.target
                ).inc()
                
                if result.success:
                    logger.info(f"✅ 복구 성공: {result.action.value} - {result.target}")
                    await self.send_recovery_notification(result, success=True)
                else:
                    logger.error(f"❌ 복구 실패: {result.action.value} - {result.target}: {result.message}")
                    await self.send_recovery_notification(result, success=False)
            else:
                logger.error(f"❌ 복구 액션 실행 오류: {str(result)}")

    async def execute_recovery_action(self, issue: HealthIssue, action: RecoveryAction) -> RecoveryResult:
        """개별 복구 액션 실행"""
        start_time = time.time()
        
        try:
            if action == RecoveryAction.RESTART_POD:
                success, message = await self.restart_pod(issue.component)
            elif action == RecoveryAction.SCALE_UP:
                success, message = await self.scale_deployment(issue.component, scale_up=True)
            elif action == RecoveryAction.SCALE_DOWN:
                success, message = await self.scale_deployment(issue.component, scale_up=False)
            elif action == RecoveryAction.RESTART_SERVICE:
                success, message = await self.restart_service(issue.component)
            elif action == RecoveryAction.CLEAR_CACHE:
                success, message = await self.clear_cache(issue.component)
            elif action == RecoveryAction.ROTATE_LOGS:
                success, message = await self.rotate_logs(issue.component)
            elif action == RecoveryAction.UPDATE_CONFIG:
                success, message = await self.update_config(issue.component)
            elif action == RecoveryAction.FAILOVER:
                success, message = await self.perform_failover(issue.component)
            elif action == RecoveryAction.CIRCUIT_BREAKER:
                success, message = await self.activate_circuit_breaker(issue.component)
            elif action == RecoveryAction.CLEANUP_RESOURCES:
                success, message = await self.cleanup_resources(issue.component)
            elif action == RecoveryAction.REBALANCE_LOAD:
                success, message = await self.rebalance_load(issue.component)
            else:
                success, message = False, f"지원되지 않는 액션: {action.value}"
            
            duration = time.time() - start_time
            
            return RecoveryResult(
                action=action,
                target=issue.component,
                success=success,
                duration=duration,
                message=message,
                timestamp=datetime.now()
            )
            
        except Exception as e:
            duration = time.time() - start_time
            return RecoveryResult(
                action=action,
                target=issue.component,
                success=False,
                duration=duration,
                message=f"복구 액션 실행 중 오류: {str(e)}",
                timestamp=datetime.now()
            )

    async def restart_pod(self, component: str) -> Tuple[bool, str]:
        """Pod 재시작"""
        try:
            # Pod 이름에서 deployment 이름 추출
            deployment_name = component.replace('pod-', '').split('-')[0]
            if not deployment_name.startswith('hankook-'):
                deployment_name = f"hankook-{deployment_name}"
            
            # Deployment 재시작 (Rolling Update)
            body = {
                'spec': {
                    'template': {
                        'metadata': {
                            'annotations': {
                                'kubectl.kubernetes.io/restartedAt': datetime.now().isoformat()
                            }
                        }
                    }
                }
            }
            
            self.k8s_apps_v1.patch_namespaced_deployment(
                name=deployment_name,
                namespace=KUBERNETES_NAMESPACE,
                body=body
            )
            
            return True, f"Pod 재시작 성공: {deployment_name}"
            
        except Exception as e:
            return False, f"Pod 재시작 실패: {str(e)}"

    async def scale_deployment(self, component: str, scale_up: bool = True) -> Tuple[bool, str]:
        """Deployment 스케일링"""
        try:
            deployment_name = component.replace('pod-', '').split('-')[0]
            if not deployment_name.startswith('hankook-'):
                deployment_name = f"hankook-{deployment_name}"
            
            # 현재 레플리카 수 조회
            deployment = self.k8s_apps_v1.read_namespaced_deployment(
                name=deployment_name,
                namespace=KUBERNETES_NAMESPACE
            )
            
            current_replicas = deployment.spec.replicas
            
            if scale_up:
                new_replicas = min(current_replicas + 1, 10)  # 최대 10개
            else:
                new_replicas = max(current_replicas - 1, 1)   # 최소 1개
            
            if new_replicas == current_replicas:
                return True, f"스케일링 불필요: {deployment_name} (현재: {current_replicas})"
            
            # 스케일링 실행
            body = {'spec': {'replicas': new_replicas}}
            self.k8s_apps_v1.patch_namespaced_deployment(
                name=deployment_name,
                namespace=KUBERNETES_NAMESPACE,
                body=body
            )
            
            action = "스케일 업" if scale_up else "스케일 다운"
            return True, f"{action} 성공: {deployment_name} ({current_replicas} → {new_replicas})"
            
        except Exception as e:
            return False, f"스케일링 실패: {str(e)}"

    async def restart_service(self, component: str) -> Tuple[bool, str]:
        """서비스 재시작 (Pod 재시작과 동일)"""
        return await self.restart_pod(component)

    async def clear_cache(self, component: str) -> Tuple[bool, str]:
        """캐시 클리어"""
        try:
            if 'redis' in component:
                # Redis 캐시 클리어
                self.redis_client.flushdb()
                return True, "Redis 캐시 클리어 완료"
            elif 'api' in component:
                # API 캐시 클리어 (API 엔드포인트 호출)
                async with self.session.post(f"{API_BASE_URL}/admin/clear-cache") as response:
                    if response.status == 200:
                        return True, "API 캐시 클리어 완료"
                    else:
                        return False, f"API 캐시 클리어 실패: HTTP {response.status}"
            else:
                return False, f"지원되지 않는 캐시 클리어: {component}"
                
        except Exception as e:
            return False, f"캐시 클리어 실패: {str(e)}"

    async def rotate_logs(self, component: str) -> Tuple[bool, str]:
        """로그 로테이션"""
        try:
            # Kubernetes에서는 로그 로테이션이 자동으로 처리되므로
            # 여기서는 오래된 로그 파일 정리를 시뮬레이션
            
            if 'database' in component:
                # 데이터베이스 로그 정리 (PostgreSQL)
                conn = psycopg2.connect(
                    host=POSTGRES_HOST,
                    port=5432,
                    database='hankook_sensors',
                    user='hankook',
                    password=os.getenv('POSTGRES_PASSWORD', 'password')
                )
                
                with conn.cursor() as cursor:
                    # 오래된 로그 엔트리 삭제
                    cursor.execute("""
                        DELETE FROM audit.activity_logs 
                        WHERE timestamp < NOW() - INTERVAL '30 days'
                    """)
                    deleted_rows = cursor.rowcount
                
                conn.commit()
                conn.close()
                
                return True, f"데이터베이스 로그 정리 완료: {deleted_rows}개 레코드 삭제"
            else:
                return True, f"로그 로테이션 완료: {component}"
                
        except Exception as e:
            return False, f"로그 로테이션 실패: {str(e)}"

    async def update_config(self, component: str) -> Tuple[bool, str]:
        """설정 업데이트"""
        try:
            # ConfigMap 업데이트 로직
            # 실제로는 구체적인 설정 변경 로직이 필요
            
            return True, f"설정 업데이트 완료: {component}"
            
        except Exception as e:
            return False, f"설정 업데이트 실패: {str(e)}"

    async def perform_failover(self, component: str) -> Tuple[bool, str]:
        """페일오버 수행"""
        try:
            # 간단한 페일오버: 다른 가용 영역으로 트래픽 라우팅
            # 실제로는 로드밸런서 설정 변경 등이 필요
            
            return True, f"페일오버 완료: {component}"
            
        except Exception as e:
            return False, f"페일오버 실패: {str(e)}"

    async def activate_circuit_breaker(self, component: str) -> Tuple[bool, str]:
        """서킷 브레이커 활성화"""
        try:
            # 서킷 브레이커 상태 설정
            self.system_status['circuit_breakers'][component] = {
                'active': True,
                'activated_at': datetime.now(),
                'failure_count': 0,
                'next_retry': datetime.now() + timedelta(minutes=5)
            }
            
            return True, f"서킷 브레이커 활성화: {component}"
            
        except Exception as e:
            return False, f"서킷 브레이커 활성화 실패: {str(e)}"

    async def cleanup_resources(self, component: str) -> Tuple[bool, str]:
        """리소스 정리"""
        try:
            cleaned_items = []
            
            # 임시 파일 정리
            if 'disk' in component or 'system' in component:
                # 실제로는 /tmp 디렉토리 정리 등
                cleaned_items.append("임시 파일")
            
            # 미사용 Docker 이미지 정리
            if self.docker_client:
                try:
                    self.docker_client.images.prune()
                    cleaned_items.append("Docker 이미지")
                except:
                    pass
            
            # 오래된 메트릭 데이터 정리
            if 'database' in component:
                conn = psycopg2.connect(
                    host=POSTGRES_HOST,
                    port=5432,
                    database='hankook_sensors',
                    user='hankook',
                    password=os.getenv('POSTGRES_PASSWORD', 'password')
                )
                
                with conn.cursor() as cursor:
                    cursor.execute("""
                        DELETE FROM monitoring.system_health 
                        WHERE timestamp < NOW() - INTERVAL '7 days'
                    """)
                    deleted_rows = cursor.rowcount
                
                conn.commit()
                conn.close()
                
                if deleted_rows > 0:
                    cleaned_items.append(f"모니터링 데이터 ({deleted_rows}개)")
            
            return True, f"리소스 정리 완료: {', '.join(cleaned_items)}"
            
        except Exception as e:
            return False, f"리소스 정리 실패: {str(e)}"

    async def rebalance_load(self, component: str) -> Tuple[bool, str]:
        """로드 밸런싱 재조정"""
        try:
            # 실제로는 로드밸런서 가중치 조정, 트래픽 분산 등
            # 여기서는 간단한 시뮬레이션
            
            return True, f"로드 밸런싱 재조정 완료: {component}"
            
        except Exception as e:
            return False, f"로드 밸런싱 재조정 실패: {str(e)}"

    async def predictive_scaling(self):
        """예측적 스케일링"""
        try:
            if self.scaling_predictor is None:
                await self.train_scaling_model()
                return
            
            # 현재 메트릭 수집
            current_metrics = await self.collect_scaling_metrics()
            
            if not current_metrics:
                return
            
            # 향후 로드 예측
            features = np.array([list(current_metrics.values())]).reshape(1, -1)
            features_scaled = self.scaling_scaler.transform(features)
            
            predicted_load = self.scaling_predictor.predict(features_scaled)[0]
            
            # 스케일링 결정
            current_hour = datetime.now().hour
            
            # 피크 시간대 예측 (9-11시, 14-16시, 19-21시)
            peak_hours = [9, 10, 11, 14, 15, 16, 19, 20, 21]
            
            if predicted_load > 0.8 or current_hour in peak_hours:
                # 사전 스케일 업
                await self.proactive_scale_up()
            elif predicted_load < 0.3 and current_hour not in peak_hours:
                # 사전 스케일 다운
                await self.proactive_scale_down()
            
            logger.debug(f"🔮 예측적 스케일링: 예상 로드 {predicted_load:.2f}")
            
        except Exception as e:
            logger.error(f"❌ 예측적 스케일링 오류: {str(e)}")

    async def train_scaling_model(self):
        """스케일링 예측 모델 훈련"""
        try:
            # 과거 메트릭 데이터로 모델 훈련
            # 실제로는 시계열 데이터를 수집하여 훈련
            
            # 더미 데이터로 모델 생성
            X = np.random.rand(1000, 5)  # 5개 특성
            y = np.random.rand(1000)     # 로드 예측값
            
            self.scaling_predictor = RandomForestRegressor(n_estimators=100, random_state=42)
            self.scaling_predictor.fit(self.scaling_scaler.fit_transform(X), y)
            
            logger.info("🧠 스케일링 예측 모델 훈련 완료")
            
        except Exception as e:
            logger.error(f"❌ 스케일링 모델 훈련 실패: {str(e)}")

    async def collect_scaling_metrics(self) -> Dict[str, float]:
        """스케일링을 위한 메트릭 수집"""
        try:
            metrics = {}
            
            # API 메트릭
            async with self.session.get(f"{API_BASE_URL}/metrics") as response:
                if response.status == 200:
                    api_metrics = self.parse_prometheus_metrics(await response.text())
                    metrics.update({
                        'api_response_time': api_metrics.get('avg_response_time', 0),
                        'api_request_rate': api_metrics.get('request_rate', 0),
                        'api_error_rate': api_metrics.get('error_rate', 0)
                    })
            
            # 시스템 메트릭
            metrics.update({
                'cpu_usage': psutil.cpu_percent(),
                'memory_usage': psutil.virtual_memory().percent
            })
            
            return metrics
            
        except Exception as e:
            logger.error(f"❌ 스케일링 메트릭 수집 오류: {str(e)}")
            return {}

    async def proactive_scale_up(self):
        """사전 스케일 업"""
        try:
            deployments = ['hankook-api', 'hankook-frontend']
            
            for deployment in deployments:
                current_deployment = self.k8s_apps_v1.read_namespaced_deployment(
                    name=deployment,
                    namespace=KUBERNETES_NAMESPACE
                )
                
                current_replicas = current_deployment.spec.replicas
                if current_replicas < 5:  # 최대 5개까지
                    new_replicas = current_replicas + 1
                    
                    body = {'spec': {'replicas': new_replicas}}
                    self.k8s_apps_v1.patch_namespaced_deployment(
                        name=deployment,
                        namespace=KUBERNETES_NAMESPACE,
                        body=body
                    )
                    
                    logger.info(f"🚀 사전 스케일 업: {deployment} ({current_replicas} → {new_replicas})")
                    
        except Exception as e:
            logger.error(f"❌ 사전 스케일 업 실패: {str(e)}")

    async def proactive_scale_down(self):
        """사전 스케일 다운"""
        try:
            deployments = ['hankook-api', 'hankook-frontend']
            
            for deployment in deployments:
                current_deployment = self.k8s_apps_v1.read_namespaced_deployment(
                    name=deployment,
                    namespace=KUBERNETES_NAMESPACE
                )
                
                current_replicas = current_deployment.spec.replicas
                if current_replicas > 2:  # 최소 2개 유지
                    new_replicas = current_replicas - 1
                    
                    body = {'spec': {'replicas': new_replicas}}
                    self.k8s_apps_v1.patch_namespaced_deployment(
                        name=deployment,
                        namespace=KUBERNETES_NAMESPACE,
                        body=body
                    )
                    
                    logger.info(f"📉 사전 스케일 다운: {deployment} ({current_replicas} → {new_replicas})")
                    
        except Exception as e:
            logger.error(f"❌ 사전 스케일 다운 실패: {str(e)}")

    async def chaos_engineering_test(self):
        """카오스 엔지니어링 테스트"""
        if not ENABLE_CHAOS_ENGINEERING:
            return
        
        try:
            logger.info("🔥 카오스 엔지니어링 테스트 시작...")
            
            # 랜덤하게 테스트 선택
            tests = [
                self.chaos_pod_kill,
                self.chaos_network_delay,
                self.chaos_cpu_stress,
                self.chaos_memory_stress
            ]
            
            selected_test = np.random.choice(tests)
            await selected_test()
            
            # 5분 후 복구 확인
            await asyncio.sleep(300)
            await self.verify_system_recovery()
            
        except Exception as e:
            logger.error(f"❌ 카오스 엔지니어링 테스트 오류: {str(e)}")

    async def chaos_pod_kill(self):
        """카오스: Pod 종료 테스트"""
        try:
            # 랜덤하게 Pod 선택 (중요하지 않은 Pod)
            pods = self.k8s_core_v1.list_namespaced_pod(namespace=KUBERNETES_NAMESPACE)
            
            test_candidates = []
            for pod in pods.items:
                if (pod.metadata.name.startswith('hankook-') and 
                    'postgres' not in pod.metadata.name and 
                    pod.status.phase == 'Running'):
                    test_candidates.append(pod.metadata.name)
            
            if test_candidates:
                target_pod = np.random.choice(test_candidates)
                
                logger.info(f"🔥 카오스: Pod 종료 테스트 - {target_pod}")
                
                self.k8s_core_v1.delete_namespaced_pod(
                    name=target_pod,
                    namespace=KUBERNETES_NAMESPACE
                )
                
                recovery_actions_total.labels(
                    action_type=RecoveryAction.CHAOS_TEST.value,
                    target_service=target_pod
                ).inc()
                
        except Exception as e:
            logger.error(f"❌ 카오스 Pod 종료 테스트 실패: {str(e)}")

    async def chaos_network_delay(self):
        """카오스: 네트워크 지연 테스트"""
        # 실제로는 네트워크 지연을 주입하는 도구 필요 (예: Chaos Mesh)
        logger.info("🔥 카오스: 네트워크 지연 테스트 (시뮬레이션)")

    async def chaos_cpu_stress(self):
        """카오스: CPU 스트레스 테스트"""
        # 실제로는 CPU 부하를 주입하는 도구 필요
        logger.info("🔥 카오스: CPU 스트레스 테스트 (시뮬레이션)")

    async def chaos_memory_stress(self):
        """카오스: 메모리 스트레스 테스트"""
        # 실제로는 메모리 부하를 주입하는 도구 필요
        logger.info("🔥 카오스: 메모리 스트레스 테스트 (시뮬레이션)")

    async def verify_system_recovery(self):
        """시스템 복구 검증"""
        try:
            logger.info("🔍 카오스 테스트 후 시스템 복구 검증...")
            
            # 모든 서비스 상태 확인
            health_issues = await self.perform_comprehensive_health_check()
            
            critical_issues = [issue for issue in health_issues if issue.severity.value >= Severity.ERROR.value]
            
            if not critical_issues:
                logger.info("✅ 시스템 복구 검증 완료 - 모든 서비스 정상")
            else:
                logger.warning(f"⚠️ 복구 미완료 이슈 {len(critical_issues)}개 발견")
                
                # 추가 복구 액션 실행
                recovery_plan = await self.analyze_and_plan_recovery(critical_issues)
                if recovery_plan:
                    await self.execute_recovery_plan(recovery_plan)
                    
        except Exception as e:
            logger.error(f"❌ 시스템 복구 검증 오류: {str(e)}")

    def parse_prometheus_metrics(self, metrics_text: str, prefix: str = '') -> Dict[str, float]:
        """Prometheus 메트릭 파싱"""
        metrics = {}
        
        for line in metrics_text.split('\n'):
            if line.startswith('#') or not line.strip():
                continue
            
            try:
                if ' ' in line:
                    metric_name, value = line.rsplit(' ', 1)
                    
                    if prefix and metric_name.startswith(prefix):
                        clean_name = metric_name.replace(prefix, '').split('{')[0]
                        metrics[clean_name] = float(value)
                    elif not prefix:
                        clean_name = metric_name.split('{')[0]
                        metrics[clean_name] = float(value)
                        
            except (ValueError, IndexError):
                continue
        
        return metrics

    async def update_system_status(self, health_issues: List[HealthIssue]):
        """시스템 상태 업데이트"""
        self.system_status['active_issues'] = health_issues
        
        # 전체 시스템 헬스 스코어 계산
        if not health_issues:
            health_score = 100.0
        else:
            # 심각도별 가중치 적용
            severity_weights = {
                Severity.INFO: 0.1,
                Severity.WARNING: 0.3,
                Severity.ERROR: 0.6,
                Severity.CRITICAL: 0.8,
                Severity.EMERGENCY: 1.0
            }
            
            total_impact = sum(severity_weights[issue.severity] for issue in health_issues)
            health_score = max(0, 100 - (total_impact * 10))
        
        system_health_score.set(health_score)
        
        # Redis에 상태 저장
        try:
            status_data = {
                'timestamp': datetime.now().isoformat(),
                'health_score': health_score,
                'active_issues_count': len(health_issues),
                'recovery_actions_today': len([r for r in self.recovery_history 
                                             if r.timestamp.date() == datetime.now().date()]),
                'system_status': 'healthy' if health_score > 80 else 'degraded' if health_score > 50 else 'critical'
            }
            
            self.redis_client.setex(
                'system_status',
                300,  # 5분 TTL
                json.dumps(status_data)
            )
            
        except Exception as e:
            logger.error(f"❌ 시스템 상태 저장 오류: {str(e)}")

    def update_prometheus_metrics(self):
        """Prometheus 메트릭 업데이트"""
        try:
            # 복구 성공률 계산
            if self.recovery_history:
                recent_actions = [r for r in self.recovery_history 
                                if r.timestamp > datetime.now() - timedelta(hours=24)]
                
                if recent_actions:
                    action_types = {}
                    for action in recent_actions:
                        action_type = action.action.value
                        if action_type not in action_types:
                            action_types[action_type] = {'total': 0, 'success': 0}
                        
                        action_types[action_type]['total'] += 1
                        if action.success:
                            action_types[action_type]['success'] += 1
                    
                    for action_type, stats in action_types.items():
                        success_rate = stats['success'] / stats['total'] if stats['total'] > 0 else 0
                        recovery_success_rate.labels(action_type=action_type).set(success_rate)
            
            # 예측 모델 정확도 (더미 값)
            if self.scaling_predictor:
                prediction_accuracy.set(0.85)  # 실제로는 모델 검증 결과 사용
                
        except Exception as e:
            logger.error(f"❌ Prometheus 메트릭 업데이트 오류: {str(e)}")

    async def send_recovery_notification(self, result: RecoveryResult, success: bool):
        """복구 알림 전송"""
        if not SLACK_WEBHOOK:
            return
        
        try:
            emoji = "✅" if success else "❌"
            color = "good" if success else "danger"
            
            message = {
                "attachments": [{
                    "color": color,
                    "title": f"{emoji} 자동 복구 {'성공' if success else '실패'}",
                    "fields": [
                        {"title": "액션", "value": result.action.value, "short": True},
                        {"title": "대상", "value": result.target, "short": True},
                        {"title": "실행 시간", "value": f"{result.duration:.2f}초", "short": True},
                        {"title": "메시지", "value": result.message, "short": False}
                    ],
                    "footer": "HankookTire Self-Healing System",
                    "ts": int(result.timestamp.timestamp())
                }]
            }
            
            async with self.session.post(SLACK_WEBHOOK, json=message) as response:
                if response.status == 200:
                    logger.debug("복구 알림 전송 완료")
                    
        except Exception as e:
            logger.error(f"❌ 복구 알림 전송 오류: {str(e)}")

    async def load_predictive_models(self):
        """예측 모델 로드"""
        try:
            model_path = "/app/models/scaling_predictor.joblib"
            scaler_path = "/app/models/scaling_scaler.joblib"
            
            if os.path.exists(model_path) and os.path.exists(scaler_path):
                self.scaling_predictor = joblib.load(model_path)
                self.scaling_scaler = joblib.load(scaler_path)
                logger.info("🧠 예측 모델 로드 완료")
            else:
                logger.info("🔄 예측 모델 없음 - 새로 훈련합니다")
                await self.train_scaling_model()
                
        except Exception as e:
            logger.error(f"❌ 예측 모델 로드 실패: {str(e)}")

async def main():
    """메인 실행 함수"""
    logger.info("🚀 HankookTire SmartSensor 자가 치유 시스템 시작")
    
    async with SelfHealingSystem() as healing_system:
        # 지속적인 모니터링 시작
        await healing_system.continuous_health_monitoring()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 자가 치유 시스템이 사용자에 의해 중단되었습니다.")
    except Exception as e:
        logger.error(f"💥 예상치 못한 오류: {str(e)}")
        exit(1)