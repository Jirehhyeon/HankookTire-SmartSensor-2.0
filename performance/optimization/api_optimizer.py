#!/usr/bin/env python3
"""
HankookTire SmartSensor 2.0 - API Performance Optimizer
차세대 통합 스마트 타이어 센서 시스템 API 성능 최적화

API 성능 최적화 도구
- 응답 시간 최적화
- 동시성 처리 개선
- 캐싱 전략 구현
- 압축 및 직렬화 최적화
- 비동기 처리 최적화
- API 속도 제한 최적화
"""

import asyncio
import aiohttp
from aiohttp import web, web_middlewares
import aioredis
import json
import logging
import time
import gzip
import pickle
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any, Callable
from dataclasses import dataclass, asdict
from enum import Enum
import statistics
import threading
from concurrent.futures import ThreadPoolExecutor
import uvloop
import orjson
import msgpack
from functools import wraps, lru_cache
import hashlib
import psutil
import os

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class CacheStrategy(Enum):
    """캐시 전략"""
    NO_CACHE = "no_cache"
    MEMORY_CACHE = "memory_cache"
    REDIS_CACHE = "redis_cache"
    HYBRID_CACHE = "hybrid_cache"
    WRITE_THROUGH = "write_through"
    WRITE_BEHIND = "write_behind"

class CompressionType(Enum):
    """압축 타입"""
    NONE = "none"
    GZIP = "gzip"
    BROTLI = "brotli"
    LZ4 = "lz4"

class SerializationType(Enum):
    """직렬화 타입"""
    JSON = "json"
    ORJSON = "orjson"
    MSGPACK = "msgpack"
    PICKLE = "pickle"

@dataclass
class PerformanceMetrics:
    """성능 메트릭"""
    endpoint: str
    method: str
    response_time_ms: float
    memory_usage_mb: float
    cpu_usage_percent: float
    cache_hit: bool
    compression_ratio: float
    request_size_bytes: int
    response_size_bytes: int
    concurrent_requests: int
    timestamp: datetime

@dataclass
class OptimizationConfig:
    """최적화 설정"""
    cache_strategy: CacheStrategy
    cache_ttl_seconds: int
    compression_type: CompressionType
    compression_threshold: int  # bytes
    serialization_type: SerializationType
    max_concurrent_requests: int
    request_timeout_seconds: int
    enable_async_processing: bool
    enable_response_streaming: bool

class CacheManager:
    """캐시 관리자"""
    
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_url = redis_url
        self.redis = None
        self.memory_cache = {}
        self.cache_stats = {
            'hits': 0,
            'misses': 0,
            'sets': 0,
            'deletes': 0
        }
        
    async def initialize(self):
        """초기화"""
        try:
            self.redis = aioredis.from_url(self.redis_url)
            await self.redis.ping()
            logger.info("✅ Redis 연결 성공")
        except Exception as e:
            logger.warning(f"⚠️ Redis 연결 실패: {str(e)} - 메모리 캐시만 사용")
            self.redis = None
    
    async def get(self, key: str, strategy: CacheStrategy = CacheStrategy.HYBRID_CACHE) -> Optional[Any]:
        """캐시에서 값 조회"""
        try:
            if strategy == CacheStrategy.NO_CACHE:
                return None
            
            # 메모리 캐시 확인
            if strategy in [CacheStrategy.MEMORY_CACHE, CacheStrategy.HYBRID_CACHE]:
                if key in self.memory_cache:
                    self.cache_stats['hits'] += 1
                    return self.memory_cache[key]['data']
            
            # Redis 캐시 확인
            if self.redis and strategy in [CacheStrategy.REDIS_CACHE, CacheStrategy.HYBRID_CACHE]:
                data = await self.redis.get(key)
                if data:
                    self.cache_stats['hits'] += 1
                    return orjson.loads(data)
            
            self.cache_stats['misses'] += 1
            return None
            
        except Exception as e:
            logger.error(f"❌ 캐시 조회 실패: {str(e)}")
            self.cache_stats['misses'] += 1
            return None
    
    async def set(self, key: str, value: Any, ttl: int = 300, 
                 strategy: CacheStrategy = CacheStrategy.HYBRID_CACHE):
        """캐시에 값 저장"""
        try:
            if strategy == CacheStrategy.NO_CACHE:
                return
            
            # 메모리 캐시 저장
            if strategy in [CacheStrategy.MEMORY_CACHE, CacheStrategy.HYBRID_CACHE]:
                self.memory_cache[key] = {
                    'data': value,
                    'expires_at': time.time() + ttl
                }
                
                # 메모리 캐시 크기 제한 (1000개)
                if len(self.memory_cache) > 1000:
                    oldest_key = min(self.memory_cache.keys(), 
                                   key=lambda k: self.memory_cache[k]['expires_at'])
                    del self.memory_cache[oldest_key]
            
            # Redis 캐시 저장
            if self.redis and strategy in [CacheStrategy.REDIS_CACHE, CacheStrategy.HYBRID_CACHE]:
                await self.redis.setex(key, ttl, orjson.dumps(value))
            
            self.cache_stats['sets'] += 1
            
        except Exception as e:
            logger.error(f"❌ 캐시 저장 실패: {str(e)}")
    
    async def delete(self, key: str, strategy: CacheStrategy = CacheStrategy.HYBRID_CACHE):
        """캐시에서 값 삭제"""
        try:
            # 메모리 캐시 삭제
            if strategy in [CacheStrategy.MEMORY_CACHE, CacheStrategy.HYBRID_CACHE]:
                if key in self.memory_cache:
                    del self.memory_cache[key]
            
            # Redis 캐시 삭제
            if self.redis and strategy in [CacheStrategy.REDIS_CACHE, CacheStrategy.HYBRID_CACHE]:
                await self.redis.delete(key)
            
            self.cache_stats['deletes'] += 1
            
        except Exception as e:
            logger.error(f"❌ 캐시 삭제 실패: {str(e)}")
    
    def get_stats(self) -> Dict[str, Any]:
        """캐시 통계 조회"""
        total_requests = self.cache_stats['hits'] + self.cache_stats['misses']
        hit_rate = self.cache_stats['hits'] / total_requests if total_requests > 0 else 0
        
        return {
            **self.cache_stats,
            'hit_rate': hit_rate,
            'memory_cache_size': len(self.memory_cache)
        }

class CompressionManager:
    """압축 관리자"""
    
    @staticmethod
    def compress(data: bytes, compression_type: CompressionType) -> Tuple[bytes, float]:
        """데이터 압축"""
        original_size = len(data)
        
        if compression_type == CompressionType.NONE:
            return data, 1.0
        
        try:
            if compression_type == CompressionType.GZIP:
                compressed = gzip.compress(data)
            else:
                # 다른 압축 알고리즘들 (실제 구현에서는 적절한 라이브러리 사용)
                compressed = gzip.compress(data)  # 기본값으로 gzip 사용
            
            compression_ratio = len(compressed) / original_size if original_size > 0 else 1.0
            return compressed, compression_ratio
            
        except Exception as e:
            logger.error(f"❌ 압축 실패: {str(e)}")
            return data, 1.0
    
    @staticmethod
    def decompress(data: bytes, compression_type: CompressionType) -> bytes:
        """데이터 압축 해제"""
        if compression_type == CompressionType.NONE:
            return data
        
        try:
            if compression_type == CompressionType.GZIP:
                return gzip.decompress(data)
            else:
                return gzip.decompress(data)  # 기본값으로 gzip 사용
                
        except Exception as e:
            logger.error(f"❌ 압축 해제 실패: {str(e)}")
            return data

class SerializationManager:
    """직렬화 관리자"""
    
    @staticmethod
    def serialize(data: Any, serialization_type: SerializationType) -> bytes:
        """데이터 직렬화"""
        try:
            if serialization_type == SerializationType.JSON:
                return json.dumps(data, default=str).encode('utf-8')
            elif serialization_type == SerializationType.ORJSON:
                return orjson.dumps(data)
            elif serialization_type == SerializationType.MSGPACK:
                return msgpack.packb(data)
            elif serialization_type == SerializationType.PICKLE:
                return pickle.dumps(data)
            else:
                return orjson.dumps(data)  # 기본값
                
        except Exception as e:
            logger.error(f"❌ 직렬화 실패: {str(e)}")
            return b'{}'
    
    @staticmethod
    def deserialize(data: bytes, serialization_type: SerializationType) -> Any:
        """데이터 역직렬화"""
        try:
            if serialization_type == SerializationType.JSON:
                return json.loads(data.decode('utf-8'))
            elif serialization_type == SerializationType.ORJSON:
                return orjson.loads(data)
            elif serialization_type == SerializationType.MSGPACK:
                return msgpack.unpackb(data)
            elif serialization_type == SerializationType.PICKLE:
                return pickle.loads(data)
            else:
                return orjson.loads(data)  # 기본값
                
        except Exception as e:
            logger.error(f"❌ 역직렬화 실패: {str(e)}")
            return {}

class PerformanceMonitor:
    """성능 모니터"""
    
    def __init__(self):
        self.metrics = []
        self.active_requests = 0
        self.request_lock = threading.Lock()
        
    def start_request(self) -> str:
        """요청 시작 기록"""
        with self.request_lock:
            self.active_requests += 1
            request_id = f"req_{int(time.time() * 1000)}_{self.active_requests}"
            return request_id
    
    def end_request(self):
        """요청 종료 기록"""
        with self.request_lock:
            self.active_requests = max(0, self.active_requests - 1)
    
    def record_metric(self, metric: PerformanceMetrics):
        """메트릭 기록"""
        self.metrics.append(metric)
        
        # 메트릭 개수 제한 (최근 10000개만 유지)
        if len(self.metrics) > 10000:
            self.metrics = self.metrics[-5000:]
    
    def get_stats(self, last_minutes: int = 5) -> Dict[str, Any]:
        """통계 조회"""
        cutoff_time = datetime.utcnow() - timedelta(minutes=last_minutes)
        recent_metrics = [m for m in self.metrics if m.timestamp > cutoff_time]
        
        if not recent_metrics:
            return {}
        
        response_times = [m.response_time_ms for m in recent_metrics]
        memory_usage = [m.memory_usage_mb for m in recent_metrics]
        cache_hits = sum(1 for m in recent_metrics if m.cache_hit)
        
        return {
            'total_requests': len(recent_metrics),
            'active_requests': self.active_requests,
            'avg_response_time_ms': statistics.mean(response_times),
            'p95_response_time_ms': statistics.quantiles(response_times, n=20)[18] if len(response_times) > 20 else max(response_times),
            'p99_response_time_ms': statistics.quantiles(response_times, n=100)[98] if len(response_times) > 100 else max(response_times),
            'avg_memory_usage_mb': statistics.mean(memory_usage),
            'cache_hit_rate': cache_hits / len(recent_metrics),
            'requests_per_minute': len(recent_metrics) / last_minutes
        }

class APIOptimizer:
    """API 최적화 관리자"""
    
    def __init__(self):
        self.cache_manager = CacheManager()
        self.performance_monitor = PerformanceMonitor()
        self.optimization_configs = {}
        self.executor = ThreadPoolExecutor(max_workers=10)
        
    async def initialize(self):
        """초기화"""
        await self.cache_manager.initialize()
        
        # 기본 최적화 설정
        default_config = OptimizationConfig(
            cache_strategy=CacheStrategy.HYBRID_CACHE,
            cache_ttl_seconds=300,
            compression_type=CompressionType.GZIP,
            compression_threshold=1024,  # 1KB
            serialization_type=SerializationType.ORJSON,
            max_concurrent_requests=100,
            request_timeout_seconds=30,
            enable_async_processing=True,
            enable_response_streaming=False
        )
        
        self.optimization_configs['default'] = default_config
        
        logger.info("✅ API 최적화 관리자 초기화 완료")

    def optimized_endpoint(self, cache_key: Optional[str] = None, 
                          config_name: str = 'default'):
        """최적화된 엔드포인트 데코레이터"""
        def decorator(func: Callable):
            @wraps(func)
            async def wrapper(request: web.Request):
                start_time = time.time()
                request_id = self.performance_monitor.start_request()
                
                config = self.optimization_configs.get(config_name, self.optimization_configs['default'])
                
                try:
                    # 캐시 확인
                    if cache_key:
                        cache_data = await self._get_cached_response(request, cache_key, config)
                        if cache_data:
                            return await self._create_optimized_response(
                                cache_data, config, start_time, request_id, 
                                request.path, request.method, True
                            )
                    
                    # 실제 처리 실행
                    if config.enable_async_processing:
                        response_data = await func(request)
                    else:
                        response_data = await asyncio.get_event_loop().run_in_executor(
                            self.executor, lambda: asyncio.run(func(request))
                        )
                    
                    # 캐시 저장
                    if cache_key:
                        await self._cache_response(request, cache_key, response_data, config)
                    
                    return await self._create_optimized_response(
                        response_data, config, start_time, request_id,
                        request.path, request.method, False
                    )
                    
                except Exception as e:
                    logger.error(f"❌ API 처리 오류: {str(e)}")
                    return web.json_response(
                        {'error': 'Internal server error'}, 
                        status=500
                    )
                finally:
                    self.performance_monitor.end_request()
                    
            return wrapper
        return decorator

    async def _get_cached_response(self, request: web.Request, cache_key: str, 
                                 config: OptimizationConfig) -> Optional[Any]:
        """캐시된 응답 조회"""
        full_cache_key = self._build_cache_key(request, cache_key)
        return await self.cache_manager.get(full_cache_key, config.cache_strategy)

    async def _cache_response(self, request: web.Request, cache_key: str, 
                            response_data: Any, config: OptimizationConfig):
        """응답 캐시 저장"""
        full_cache_key = self._build_cache_key(request, cache_key)
        await self.cache_manager.set(
            full_cache_key, response_data, 
            config.cache_ttl_seconds, config.cache_strategy
        )

    def _build_cache_key(self, request: web.Request, base_key: str) -> str:
        """캐시 키 생성"""
        # 요청 파라미터를 포함한 캐시 키 생성
        params = dict(request.query)
        params_str = json.dumps(params, sort_keys=True)
        cache_key = f"{base_key}:{request.path}:{hashlib.md5(params_str.encode()).hexdigest()}"
        return cache_key

    async def _create_optimized_response(self, data: Any, config: OptimizationConfig,
                                       start_time: float, request_id: str,
                                       path: str, method: str, cache_hit: bool) -> web.Response:
        """최적화된 응답 생성"""
        # 직렬화
        serialized_data = SerializationManager.serialize(data, config.serialization_type)
        
        # 압축 (임계값 이상일 때만)
        compressed_data = serialized_data
        compression_ratio = 1.0
        content_encoding = None
        
        if len(serialized_data) > config.compression_threshold:
            compressed_data, compression_ratio = CompressionManager.compress(
                serialized_data, config.compression_type
            )
            if config.compression_type == CompressionType.GZIP:
                content_encoding = 'gzip'
        
        # 응답 헤더 설정
        headers = {
            'Content-Type': 'application/json',
            'X-Request-ID': request_id,
            'X-Cache-Hit': str(cache_hit),
            'X-Compression-Ratio': f"{compression_ratio:.3f}"
        }
        
        if content_encoding:
            headers['Content-Encoding'] = content_encoding
        
        # 성능 메트릭 기록
        end_time = time.time()
        response_time_ms = (end_time - start_time) * 1000
        
        process = psutil.Process()
        memory_usage_mb = process.memory_info().rss / 1024 / 1024
        cpu_usage_percent = process.cpu_percent()
        
        metric = PerformanceMetrics(
            endpoint=path,
            method=method,
            response_time_ms=response_time_ms,
            memory_usage_mb=memory_usage_mb,
            cpu_usage_percent=cpu_usage_percent,
            cache_hit=cache_hit,
            compression_ratio=compression_ratio,
            request_size_bytes=0,  # 요청 크기는 별도 측정 필요
            response_size_bytes=len(compressed_data),
            concurrent_requests=self.performance_monitor.active_requests,
            timestamp=datetime.utcnow()
        )
        
        self.performance_monitor.record_metric(metric)
        
        return web.Response(
            body=compressed_data,
            headers=headers,
            status=200
        )

    def add_optimization_config(self, name: str, config: OptimizationConfig):
        """최적화 설정 추가"""
        self.optimization_configs[name] = config
        logger.info(f"✅ 최적화 설정 추가: {name}")

    async def optimize_database_queries(self, query_func: Callable, 
                                      cache_key: str, ttl: int = 300):
        """데이터베이스 쿼리 최적화"""
        # 캐시 확인
        cached_result = await self.cache_manager.get(cache_key)
        if cached_result:
            return cached_result
        
        # 쿼리 실행
        start_time = time.time()
        result = await query_func()
        execution_time = time.time() - start_time
        
        # 결과 캐시 저장 (실행 시간이 긴 쿼리만)
        if execution_time > 0.1:  # 100ms 이상
            await self.cache_manager.set(cache_key, result, ttl)
        
        return result

    async def batch_process_requests(self, requests: List[Dict], 
                                   process_func: Callable) -> List[Any]:
        """요청 배치 처리"""
        batch_size = 50  # 배치 크기
        results = []
        
        for i in range(0, len(requests), batch_size):
            batch = requests[i:i + batch_size]
            
            # 배치 내 요청들을 병렬 처리
            tasks = [process_func(req) for req in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            results.extend(batch_results)
        
        return results

    async def precompute_expensive_operations(self):
        """비용이 많이 드는 연산 사전 계산"""
        logger.info("🔄 비용이 많이 드는 연산 사전 계산 중...")
        
        precompute_tasks = [
            ('dashboard_summary', self._precompute_dashboard_summary),
            ('vehicle_statistics', self._precompute_vehicle_statistics),
            ('sensor_aggregates', self._precompute_sensor_aggregates),
            ('alert_summaries', self._precompute_alert_summaries)
        ]
        
        for cache_key, compute_func in precompute_tasks:
            try:
                result = await compute_func()
                await self.cache_manager.set(cache_key, result, 3600)  # 1시간 캐시
                logger.info(f"✅ 사전 계산 완료: {cache_key}")
            except Exception as e:
                logger.error(f"❌ 사전 계산 실패: {cache_key} - {str(e)}")

    async def _precompute_dashboard_summary(self) -> Dict[str, Any]:
        """대시보드 요약 사전 계산"""
        # 실제 구현에서는 데이터베이스 쿼리 실행
        return {
            'total_vehicles': 10000,
            'active_vehicles': 8500,
            'total_sensors': 40000,
            'active_sensors': 38000,
            'recent_alerts': 45,
            'critical_alerts': 3,
            'last_updated': datetime.utcnow().isoformat()
        }

    async def _precompute_vehicle_statistics(self) -> Dict[str, Any]:
        """차량 통계 사전 계산"""
        return {
            'by_status': {
                'active': 8500,
                'inactive': 1200,
                'maintenance': 300
            },
            'by_region': {
                'seoul': 3000,
                'busan': 1500,
                'incheon': 1200,
                'daegu': 1000,
                'others': 3300
            },
            'last_updated': datetime.utcnow().isoformat()
        }

    async def _precompute_sensor_aggregates(self) -> Dict[str, Any]:
        """센서 집계 사전 계산"""
        return {
            'average_pressure': 245.5,
            'average_temperature': 34.2,
            'data_points_today': 1250000,
            'quality_score': 97.8,
            'last_updated': datetime.utcnow().isoformat()
        }

    async def _precompute_alert_summaries(self) -> Dict[str, Any]:
        """알림 요약 사전 계산"""
        return {
            'today': {
                'total': 245,
                'critical': 8,
                'warning': 67,
                'info': 170
            },
            'this_week': {
                'total': 1680,
                'critical': 45,
                'warning': 456,
                'info': 1179
            },
            'last_updated': datetime.utcnow().isoformat()
        }

    async def get_performance_report(self) -> Dict[str, Any]:
        """성능 리포트 생성"""
        performance_stats = self.performance_monitor.get_stats()
        cache_stats = self.cache_manager.get_stats()
        
        return {
            'generated_at': datetime.utcnow().isoformat(),
            'performance': performance_stats,
            'cache': cache_stats,
            'optimization_configs': {
                name: asdict(config) 
                for name, config in self.optimization_configs.items()
            }
        }

class RateLimiter:
    """API 속도 제한기"""
    
    def __init__(self, redis_client):
        self.redis = redis_client
        
    async def is_allowed(self, key: str, limit: int, window: int) -> Tuple[bool, Dict[str, int]]:
        """속도 제한 확인"""
        try:
            current_time = int(time.time())
            window_start = current_time - window
            
            # Redis에서 현재 윈도우의 요청 수 확인
            pipe = self.redis.pipeline()
            pipe.zremrangebyscore(key, 0, window_start)
            pipe.zcard(key)
            pipe.zadd(key, {str(current_time): current_time})
            pipe.expire(key, window)
            
            results = await pipe.execute()
            current_requests = results[1]
            
            allowed = current_requests < limit
            remaining = max(0, limit - current_requests - 1)
            
            return allowed, {
                'limit': limit,
                'remaining': remaining,
                'reset_time': current_time + window
            }
            
        except Exception as e:
            logger.error(f"❌ 속도 제한 확인 실패: {str(e)}")
            return True, {'limit': limit, 'remaining': limit - 1, 'reset_time': int(time.time()) + window}

# 미들웨어
async def performance_middleware(request: web.Request, handler):
    """성능 모니터링 미들웨어"""
    start_time = time.time()
    
    try:
        response = await handler(request)
        
        # 성능 메트릭 헤더 추가
        response.headers['X-Response-Time'] = f"{(time.time() - start_time) * 1000:.2f}ms"
        response.headers['X-Timestamp'] = str(int(time.time()))
        
        return response
        
    except Exception as e:
        logger.error(f"❌ 요청 처리 오류: {str(e)}")
        raise

async def compression_middleware(request: web.Request, handler):
    """압축 미들웨어"""
    response = await handler(request)
    
    # Accept-Encoding 헤더 확인
    accept_encoding = request.headers.get('Accept-Encoding', '')
    
    if 'gzip' in accept_encoding and len(response.body) > 1024:
        compressed_body = gzip.compress(response.body)
        response.body = compressed_body
        response.headers['Content-Encoding'] = 'gzip'
        response.headers['Content-Length'] = str(len(compressed_body))
    
    return response

async def cache_middleware(request: web.Request, handler):
    """캐시 미들웨어"""
    # GET 요청에 대해서만 캐시 적용
    if request.method != 'GET':
        return await handler(request)
    
    # 캐시 헤더 설정
    response = await handler(request)
    
    if response.status == 200:
        response.headers['Cache-Control'] = 'public, max-age=300'
        response.headers['ETag'] = hashlib.md5(response.body).hexdigest()
    
    return response

# 최적화된 API 예제
async def create_optimized_app(optimizer: APIOptimizer):
    """최적화된 애플리케이션 생성"""
    app = web.Application(middlewares=[
        performance_middleware,
        compression_middleware,
        cache_middleware
    ])
    
    # 최적화된 엔드포인트들
    @optimizer.optimized_endpoint(cache_key='dashboard_summary')
    async def dashboard_summary(request: web.Request):
        """대시보드 요약 (캐시됨)"""
        return await optimizer._precompute_dashboard_summary()
    
    @optimizer.optimized_endpoint(cache_key='vehicle_list')
    async def vehicle_list(request: web.Request):
        """차량 목록 (캐시됨)"""
        # 실제 구현에서는 데이터베이스 쿼리
        vehicles = [
            {'id': i, 'status': 'active', 'location': f'Location {i}'}
            for i in range(1, 101)
        ]
        return {'vehicles': vehicles, 'total': len(vehicles)}
    
    @optimizer.optimized_endpoint()
    async def sensor_data(request: web.Request):
        """센서 데이터 (캐시 없음)"""
        vehicle_id = request.query.get('vehicle_id')
        if not vehicle_id:
            return {'error': 'vehicle_id required'}
        
        # 실시간 센서 데이터 (캐시하지 않음)
        return {
            'vehicle_id': vehicle_id,
            'sensors': [
                {'type': 'pressure', 'value': 245.5, 'unit': 'kPa'},
                {'type': 'temperature', 'value': 34.2, 'unit': '°C'}
            ],
            'timestamp': datetime.utcnow().isoformat()
        }
    
    async def performance_stats(request: web.Request):
        """성능 통계"""
        report = await optimizer.get_performance_report()
        return web.json_response(report)
    
    # 라우트 등록
    app.router.add_get('/api/dashboard/summary', dashboard_summary)
    app.router.add_get('/api/vehicles', vehicle_list)
    app.router.add_get('/api/sensors/data', sensor_data)
    app.router.add_get('/api/performance/stats', performance_stats)
    
    return app

async def main():
    """메인 실행 함수"""
    logger.info("🚀 HankookTire SmartSensor 2.0 API 최적화 시작")
    
    # uvloop 사용 (성능 향상)
    if hasattr(uvloop, 'install'):
        uvloop.install()
    
    # API 최적화 관리자 초기화
    optimizer = APIOptimizer()
    await optimizer.initialize()
    
    # 사전 계산 실행
    await optimizer.precompute_expensive_operations()
    
    # 최적화된 애플리케이션 생성
    app = await create_optimized_app(optimizer)
    
    # 서버 시작
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8000)
    
    logger.info("🌐 최적화된 API 서버 시작 - Port 8000")
    await site.start()
    
    try:
        # 성능 모니터링 루프
        while True:
            await asyncio.sleep(60)  # 1분마다
            
            # 성능 리포트 생성
            report = await optimizer.get_performance_report()
            
            logger.info(f"📊 성능 통계:")
            if 'performance' in report:
                perf = report['performance']
                logger.info(f"   활성 요청: {perf.get('active_requests', 0)}")
                logger.info(f"   분당 요청: {perf.get('requests_per_minute', 0):.1f}")
                logger.info(f"   평균 응답시간: {perf.get('avg_response_time_ms', 0):.2f}ms")
                logger.info(f"   캐시 적중률: {perf.get('cache_hit_rate', 0):.2%}")
            
            # 사전 계산 갱신
            await optimizer.precompute_expensive_operations()
            
    except KeyboardInterrupt:
        logger.info("👋 API 서버 종료 중...")
    finally:
        await runner.cleanup()

if __name__ == "__main__":
    asyncio.run(main())