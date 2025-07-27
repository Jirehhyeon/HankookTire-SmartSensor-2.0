#!/usr/bin/env python3
"""
HankookTire SmartSensor 2.0 - Database Performance Optimizer
차세대 통합 스마트 타이어 센서 시스템 데이터베이스 최적화

데이터베이스 성능 최적화 도구
- 쿼리 성능 분석 및 최적화
- 인덱스 자동 생성 및 관리
- 파티셔닝 전략 구현
- 연결 풀 최적화
- 캐싱 전략 구현
- 데이터 아카이빙
"""

import asyncio
import psycopg2
from psycopg2.extras import RealDictCursor
import redis
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from enum import Enum
import statistics
import threading
from concurrent.futures import ThreadPoolExecutor
import os

# 설정
POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'localhost')
POSTGRES_PORT = int(os.getenv('POSTGRES_PORT', '5432'))
POSTGRES_DB = os.getenv('POSTGRES_DB', 'smarttire_sensors')
POSTGRES_USER = os.getenv('POSTGRES_USER', 'smarttire')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'password')

REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', '6379'))
REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', '')

# 최적화 설정
SLOW_QUERY_THRESHOLD = float(os.getenv('SLOW_QUERY_THRESHOLD', '1.0'))  # 1초
INDEX_USAGE_THRESHOLD = float(os.getenv('INDEX_USAGE_THRESHOLD', '0.1'))  # 10%
CACHE_TTL_SECONDS = int(os.getenv('CACHE_TTL_SECONDS', '300'))  # 5분
PARTITION_SIZE_MB = int(os.getenv('PARTITION_SIZE_MB', '1000'))  # 1GB

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class OptimizationType(Enum):
    """최적화 타입"""
    INDEX_CREATION = "index_creation"
    QUERY_OPTIMIZATION = "query_optimization"
    PARTITIONING = "partitioning"
    CACHING = "caching"
    CONNECTION_POOLING = "connection_pooling"
    ARCHIVING = "archiving"
    VACUUM_ANALYZE = "vacuum_analyze"

class QueryType(Enum):
    """쿼리 타입"""
    SELECT = "select"
    INSERT = "insert"
    UPDATE = "update"
    DELETE = "delete"
    AGGREGATE = "aggregate"

@dataclass
class QueryAnalysis:
    """쿼리 분석 결과"""
    query_text: str
    query_type: QueryType
    execution_time_ms: float
    rows_examined: int
    rows_returned: int
    index_usage: List[str]
    table_scans: int
    cpu_cost: float
    io_cost: float
    optimization_suggestions: List[str]
    timestamp: datetime

@dataclass
class IndexRecommendation:
    """인덱스 추천"""
    table_name: str
    column_names: List[str]
    index_type: str  # btree, hash, gin, gist
    expected_improvement: float
    usage_frequency: int
    size_estimate_mb: float
    creation_time_estimate: int

@dataclass
class PartitionStrategy:
    """파티셔닝 전략"""
    table_name: str
    partition_key: str
    partition_type: str  # range, list, hash
    partition_interval: str
    retention_period: int
    expected_performance_gain: float

class DatabaseOptimizer:
    """데이터베이스 최적화 관리자"""
    
    def __init__(self):
        self.redis_client = None
        self.connection_pool = None
        self.query_stats = {}
        self.optimization_history = []
        
    async def initialize(self):
        """초기화"""
        # Redis 연결
        self.redis_client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            password=REDIS_PASSWORD if REDIS_PASSWORD else None,
            decode_responses=True
        )
        
        # 연결 풀 초기화
        self.connection_pool = psycopg2.pool.ThreadedConnectionPool(
            5, 20,  # min, max connections
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            database=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD
        )
        
        # 성능 모니터링 테이블 생성
        await self.create_performance_tables()
        
        # 기본 최적화 실행
        await self.apply_baseline_optimizations()
        
        logger.info("✅ 데이터베이스 최적화 관리자 초기화 완료")

    async def create_performance_tables(self):
        """성능 모니터링 테이블 생성"""
        conn = self.get_connection()
        
        try:
            with conn.cursor() as cursor:
                # 쿼리 성능 로그 테이블
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS performance.query_performance (
                        id SERIAL PRIMARY KEY,
                        query_hash VARCHAR(64) NOT NULL,
                        query_text TEXT NOT NULL,
                        query_type VARCHAR(20) NOT NULL,
                        execution_time_ms FLOAT NOT NULL,
                        rows_examined INTEGER,
                        rows_returned INTEGER,
                        index_usage JSONB,
                        table_scans INTEGER DEFAULT 0,
                        cpu_cost FLOAT,
                        io_cost FLOAT,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # 인덱스 사용 통계 테이블
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS performance.index_usage_stats (
                        id SERIAL PRIMARY KEY,
                        schema_name VARCHAR(64) NOT NULL,
                        table_name VARCHAR(64) NOT NULL,
                        index_name VARCHAR(64) NOT NULL,
                        scans INTEGER DEFAULT 0,
                        tuples_read INTEGER DEFAULT 0,
                        tuples_fetched INTEGER DEFAULT 0,
                        last_used TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(schema_name, table_name, index_name)
                    )
                """)
                
                # 테이블 크기 통계 테이블
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS performance.table_size_stats (
                        id SERIAL PRIMARY KEY,
                        schema_name VARCHAR(64) NOT NULL,
                        table_name VARCHAR(64) NOT NULL,
                        size_bytes BIGINT NOT NULL,
                        row_count BIGINT,
                        avg_row_size INTEGER,
                        last_vacuum TIMESTAMP,
                        last_analyze TIMESTAMP,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # 최적화 이력 테이블
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS performance.optimization_history (
                        id SERIAL PRIMARY KEY,
                        optimization_type VARCHAR(30) NOT NULL,
                        target_object VARCHAR(100) NOT NULL,
                        action_taken TEXT NOT NULL,
                        before_metrics JSONB,
                        after_metrics JSONB,
                        performance_gain FLOAT,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # 인덱스 생성
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_query_performance_hash ON performance.query_performance(query_hash)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_query_performance_timestamp ON performance.query_performance(timestamp)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_index_usage_table ON performance.index_usage_stats(schema_name, table_name)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_table_size_stats_table ON performance.table_size_stats(schema_name, table_name)")
                
            conn.commit()
            logger.info("✅ 성능 모니터링 테이블 생성 완료")
            
        except Exception as e:
            logger.error(f"❌ 성능 테이블 생성 실패: {str(e)}")
            conn.rollback()
            raise
        finally:
            self.return_connection(conn)

    def get_connection(self):
        """연결 풀에서 연결 획득"""
        return self.connection_pool.getconn()
        
    def return_connection(self, conn):
        """연결 풀에 연결 반환"""
        self.connection_pool.putconn(conn)

    async def apply_baseline_optimizations(self):
        """기본 최적화 적용"""
        logger.info("🔧 기본 최적화 적용 중...")
        
        conn = self.get_connection()
        
        try:
            with conn.cursor() as cursor:
                # PostgreSQL 설정 최적화
                optimizations = [
                    # 메모리 설정
                    "SET shared_buffers = '256MB'",
                    "SET effective_cache_size = '1GB'",
                    "SET work_mem = '16MB'",
                    "SET maintenance_work_mem = '64MB'",
                    
                    # 연결 설정
                    "SET max_connections = 200",
                    "SET tcp_keepalives_idle = 600",
                    "SET tcp_keepalives_interval = 30",
                    
                    # 쓰기 성능 최적화
                    "SET wal_buffers = '16MB'",
                    "SET checkpoint_completion_target = 0.9",
                    "SET checkpoint_timeout = '10min'",
                    
                    # 쿼리 성능 최적화
                    "SET random_page_cost = 1.1",
                    "SET cpu_tuple_cost = 0.01",
                    "SET cpu_index_tuple_cost = 0.005",
                    
                    # 통계 수집 활성화
                    "SET track_activities = on",
                    "SET track_counts = on",
                    "SET track_io_timing = on",
                    "SET track_functions = 'all'"
                ]
                
                for optimization in optimizations:
                    try:
                        cursor.execute(optimization)
                        logger.debug(f"✅ 적용: {optimization}")
                    except Exception as e:
                        logger.warning(f"⚠️ 설정 적용 실패: {optimization} - {str(e)}")
                
            conn.commit()
            
            # 기본 인덱스 생성
            await self.create_essential_indexes()
            
            logger.info("✅ 기본 최적화 적용 완료")
            
        except Exception as e:
            logger.error(f"❌ 기본 최적화 적용 실패: {str(e)}")
            conn.rollback()
        finally:
            self.return_connection(conn)

    async def create_essential_indexes(self):
        """필수 인덱스 생성"""
        logger.info("📊 필수 인덱스 생성 중...")
        
        essential_indexes = [
            # 센서 데이터 인덱스
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_sensor_readings_timestamp ON sensors.sensor_readings(created_at)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_sensor_readings_device_id ON sensors.sensor_readings(device_id)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_sensor_readings_vehicle_timestamp ON sensors.sensor_readings(vehicle_id, created_at)",
            
            # TPMS 데이터 인덱스
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_tpms_data_timestamp ON sensors.tpms_data(created_at)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_tpms_data_vehicle_tire ON sensors.tpms_data(vehicle_id, tire_position)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_tpms_data_pressure ON sensors.tpms_data(pressure_kpa) WHERE pressure_kpa < 200",
            
            # 차량 데이터 인덱스
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_vehicles_status ON sensors.vehicles(status)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_vehicles_location ON sensors.vehicles USING GIST(location)",
            
            # 알림 데이터 인덱스
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_alerts_timestamp ON alerts.alert_events(created_at)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_alerts_severity ON alerts.alert_events(severity)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_alerts_vehicle_id ON alerts.alert_events(vehicle_id)",
            
            # 사용자 인증 인덱스
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_users_email ON auth.users(email)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_security_events_timestamp ON auth.security_events(timestamp)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_security_events_source_ip ON auth.security_events(source_ip)",
            
            # 복합 인덱스
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_sensor_readings_composite ON sensors.sensor_readings(device_id, created_at, sensor_type)",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_tpms_alerts_composite ON sensors.tpms_data(vehicle_id, created_at) WHERE pressure_kpa < 200 OR temperature_celsius > 80"
        ]
        
        conn = self.get_connection()
        
        try:
            with conn.cursor() as cursor:
                for index_sql in essential_indexes:
                    try:
                        start_time = time.time()
                        cursor.execute(index_sql)
                        execution_time = time.time() - start_time
                        
                        index_name = index_sql.split('IF NOT EXISTS ')[1].split(' ON')[0]
                        logger.info(f"✅ 인덱스 생성 완료: {index_name} ({execution_time:.2f}초)")
                        
                    except Exception as e:
                        logger.warning(f"⚠️ 인덱스 생성 실패: {str(e)}")
                
            conn.commit()
            
        except Exception as e:
            logger.error(f"❌ 필수 인덱스 생성 실패: {str(e)}")
            conn.rollback()
        finally:
            self.return_connection(conn)

    async def analyze_query_performance(self, days: int = 7) -> List[QueryAnalysis]:
        """쿼리 성능 분석"""
        logger.info(f"🔍 최근 {days}일간 쿼리 성능 분석 중...")
        
        conn = self.get_connection()
        
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                # 느린 쿼리 조회
                cursor.execute("""
                    SELECT 
                        query,
                        calls,
                        total_time,
                        mean_time,
                        max_time,
                        min_time,
                        rows,
                        shared_blks_hit,
                        shared_blks_read,
                        shared_blks_dirtied,
                        temp_blks_read,
                        temp_blks_written
                    FROM pg_stat_statements 
                    WHERE mean_time > %s
                    ORDER BY total_time DESC
                    LIMIT 50
                """, (SLOW_QUERY_THRESHOLD * 1000,))  # 밀리초 변환
                
                slow_queries = cursor.fetchall()
                
                analyses = []
                for query_stat in slow_queries:
                    analysis = await self._analyze_single_query(query_stat)
                    analyses.append(analysis)
                
                # 분석 결과 저장
                await self._save_query_analyses(analyses)
                
                logger.info(f"✅ {len(analyses)}개 쿼리 분석 완료")
                return analyses
                
        except Exception as e:
            logger.error(f"❌ 쿼리 성능 분석 실패: {str(e)}")
            return []
        finally:
            self.return_connection(conn)

    async def _analyze_single_query(self, query_stat: Dict) -> QueryAnalysis:
        """단일 쿼리 분석"""
        query_text = query_stat['query']
        
        # 쿼리 타입 감지
        query_type = QueryType.SELECT
        if query_text.upper().strip().startswith('INSERT'):
            query_type = QueryType.INSERT
        elif query_text.upper().strip().startswith('UPDATE'):
            query_type = QueryType.UPDATE
        elif query_text.upper().strip().startswith('DELETE'):
            query_type = QueryType.DELETE
        elif any(keyword in query_text.upper() for keyword in ['COUNT', 'SUM', 'AVG', 'GROUP BY']):
            query_type = QueryType.AGGREGATE
        
        # 최적화 제안 생성
        suggestions = await self._generate_optimization_suggestions(query_stat)
        
        return QueryAnalysis(
            query_text=query_text,
            query_type=query_type,
            execution_time_ms=query_stat['mean_time'],
            rows_examined=query_stat.get('rows', 0),
            rows_returned=query_stat.get('rows', 0),
            index_usage=[],  # pg_stat_statements에서는 직접 제공되지 않음
            table_scans=query_stat.get('shared_blks_read', 0),
            cpu_cost=query_stat['total_time'],
            io_cost=query_stat.get('shared_blks_read', 0) * 0.1,
            optimization_suggestions=suggestions,
            timestamp=datetime.utcnow()
        )

    async def _generate_optimization_suggestions(self, query_stat: Dict) -> List[str]:
        """최적화 제안 생성"""
        suggestions = []
        
        query_text = query_stat['query'].upper()
        
        # 인덱스 제안
        if query_stat.get('shared_blks_read', 0) > 1000:
            suggestions.append("높은 디스크 I/O 감지 - 적절한 인덱스 생성 고려")
        
        if 'WHERE' in query_text and 'INDEX' not in query_text:
            suggestions.append("WHERE 절의 컬럼에 인덱스 생성 고려")
        
        if 'ORDER BY' in query_text:
            suggestions.append("ORDER BY 절의 컬럼에 인덱스 생성 고려")
        
        if 'GROUP BY' in query_text:
            suggestions.append("GROUP BY 절의 컬럼에 인덱스 생성 고려")
        
        # 쿼리 구조 제안
        if 'SELECT *' in query_text:
            suggestions.append("필요한 컬럼만 선택하여 성능 향상")
        
        if query_stat['mean_time'] > 5000:  # 5초 이상
            suggestions.append("쿼리가 매우 느림 - 쿼리 재작성 또는 데이터 파티셔닝 고려")
        
        if query_stat.get('temp_blks_written', 0) > 0:
            suggestions.append("임시 파일 사용 감지 - work_mem 증가 또는 쿼리 최적화 필요")
        
        return suggestions

    async def recommend_indexes(self) -> List[IndexRecommendation]:
        """인덱스 추천"""
        logger.info("📊 인덱스 추천 분석 중...")
        
        conn = self.get_connection()
        recommendations = []
        
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                # 테이블별 스캔 통계 조회
                cursor.execute("""
                    SELECT 
                        schemaname,
                        tablename,
                        seq_scan,
                        seq_tup_read,
                        idx_scan,
                        idx_tup_fetch,
                        n_tup_ins,
                        n_tup_upd,
                        n_tup_del
                    FROM pg_stat_user_tables
                    WHERE seq_scan > 1000 OR (seq_scan > idx_scan AND seq_scan > 10)
                    ORDER BY seq_scan DESC
                """)
                
                tables_needing_indexes = cursor.fetchall()
                
                for table_stat in tables_needing_indexes:
                    # 테이블의 컬럼 분석
                    table_name = f"{table_stat['schemaname']}.{table_stat['tablename']}"
                    
                    # WHERE 절에서 자주 사용되는 컬럼 찾기
                    frequent_columns = await self._find_frequent_where_columns(table_name)
                    
                    for column in frequent_columns:
                        recommendation = IndexRecommendation(
                            table_name=table_name,
                            column_names=[column],
                            index_type="btree",
                            expected_improvement=self._calculate_expected_improvement(table_stat),
                            usage_frequency=table_stat['seq_scan'],
                            size_estimate_mb=self._estimate_index_size(table_name, [column]),
                            creation_time_estimate=self._estimate_creation_time(table_name)
                        )
                        recommendations.append(recommendation)
                
                logger.info(f"✅ {len(recommendations)}개 인덱스 추천 생성")
                return recommendations
                
        except Exception as e:
            logger.error(f"❌ 인덱스 추천 실패: {str(e)}")
            return []
        finally:
            self.return_connection(conn)

    async def _find_frequent_where_columns(self, table_name: str) -> List[str]:
        """WHERE 절에서 자주 사용되는 컬럼 찾기"""
        # 실제 구현에서는 pg_stat_statements를 분석하여
        # 해당 테이블에 대한 쿼리들의 WHERE 절을 파싱해야 함
        # 여기서는 일반적으로 자주 사용되는 컬럼들을 반환
        
        common_columns = {
            'sensors.sensor_readings': ['created_at', 'device_id', 'vehicle_id'],
            'sensors.tpms_data': ['created_at', 'vehicle_id', 'tire_position'],
            'sensors.vehicles': ['status', 'created_at'],
            'alerts.alert_events': ['created_at', 'severity', 'vehicle_id'],
            'auth.users': ['email', 'username'],
            'auth.security_events': ['timestamp', 'source_ip']
        }
        
        return common_columns.get(table_name, ['id', 'created_at'])

    def _calculate_expected_improvement(self, table_stat: Dict) -> float:
        """예상 성능 향상 계산"""
        seq_scan = table_stat['seq_scan']
        idx_scan = table_stat.get('idx_scan', 0)
        
        if seq_scan > 0:
            # 시퀀셜 스캔 비율이 높을수록 인덱스로 인한 개선 효과가 큼
            improvement = min(90.0, (seq_scan / (seq_scan + idx_scan + 1)) * 100)
            return improvement
        
        return 0.0

    def _estimate_index_size(self, table_name: str, columns: List[str]) -> float:
        """인덱스 크기 예상"""
        # 간단한 추정식 (실제로는 테이블 크기와 컬럼 타입을 고려해야 함)
        base_size = 10.0  # MB
        column_factor = len(columns) * 2.0
        return base_size + column_factor

    def _estimate_creation_time(self, table_name: str) -> int:
        """인덱스 생성 시간 예상 (초)"""
        # 테이블 크기에 따른 대략적인 생성 시간
        # 실제로는 테이블 크기를 조회해야 함
        return 30  # 30초 기본값

    async def create_recommended_indexes(self, recommendations: List[IndexRecommendation]) -> List[str]:
        """추천된 인덱스 생성"""
        logger.info(f"🔨 {len(recommendations)}개 추천 인덱스 생성 중...")
        
        created_indexes = []
        conn = self.get_connection()
        
        try:
            with conn.cursor() as cursor:
                for rec in recommendations:
                    if rec.expected_improvement > 20.0:  # 20% 이상 개선 예상시만 생성
                        index_name = f"idx_{rec.table_name.split('.')[-1]}_{('_'.join(rec.column_names))}"
                        columns_str = ', '.join(rec.column_names)
                        
                        create_sql = f"""
                            CREATE INDEX CONCURRENTLY IF NOT EXISTS {index_name}
                            ON {rec.table_name} ({columns_str})
                        """
                        
                        try:
                            start_time = time.time()
                            cursor.execute(create_sql)
                            execution_time = time.time() - start_time
                            
                            created_indexes.append(index_name)
                            
                            # 최적화 이력 기록
                            await self._record_optimization(
                                OptimizationType.INDEX_CREATION,
                                rec.table_name,
                                f"Created index {index_name}",
                                {},
                                {"index_name": index_name, "execution_time": execution_time},
                                rec.expected_improvement
                            )
                            
                            logger.info(f"✅ 인덱스 생성 완료: {index_name} ({execution_time:.2f}초)")
                            
                        except Exception as e:
                            logger.warning(f"⚠️ 인덱스 생성 실패: {index_name} - {str(e)}")
            
            conn.commit()
            
        except Exception as e:
            logger.error(f"❌ 인덱스 생성 실패: {str(e)}")
            conn.rollback()
        finally:
            self.return_connection(conn)
        
        return created_indexes

    async def implement_partitioning(self, strategy: PartitionStrategy) -> bool:
        """파티셔닝 구현"""
        logger.info(f"🗂️ 테이블 파티셔닝 구현 중: {strategy.table_name}")
        
        conn = self.get_connection()
        
        try:
            with conn.cursor() as cursor:
                # 기존 테이블 백업
                backup_table = f"{strategy.table_name}_backup_{int(time.time())}"
                
                cursor.execute(f"""
                    CREATE TABLE {backup_table} AS 
                    SELECT * FROM {strategy.table_name}
                """)
                
                # 파티션 테이블 생성
                if strategy.partition_type == "range":
                    await self._create_range_partitions(cursor, strategy)
                elif strategy.partition_type == "hash":
                    await self._create_hash_partitions(cursor, strategy)
                
                # 데이터 마이그레이션
                await self._migrate_data_to_partitions(cursor, strategy, backup_table)
                
                # 최적화 이력 기록
                await self._record_optimization(
                    OptimizationType.PARTITIONING,
                    strategy.table_name,
                    f"Implemented {strategy.partition_type} partitioning on {strategy.partition_key}",
                    {"backup_table": backup_table},
                    {"partition_strategy": asdict(strategy)},
                    strategy.expected_performance_gain
                )
                
            conn.commit()
            logger.info(f"✅ 파티셔닝 구현 완료: {strategy.table_name}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 파티셔닝 구현 실패: {str(e)}")
            conn.rollback()
            return False
        finally:
            self.return_connection(conn)

    async def _create_range_partitions(self, cursor, strategy: PartitionStrategy):
        """범위 파티션 생성"""
        # 예: 날짜 기반 월별 파티션
        if strategy.partition_key == 'created_at':
            # 현재 월부터 6개월 후까지 파티션 생성
            for i in range(7):
                partition_date = datetime.utcnow() + timedelta(days=30*i)
                partition_name = f"{strategy.table_name}_{partition_date.strftime('%Y_%m')}"
                
                start_date = partition_date.replace(day=1)
                if i < 6:
                    end_date = (start_date + timedelta(days=32)).replace(day=1)
                else:
                    end_date = start_date + timedelta(days=365)  # 마지막 파티션은 1년 후
                
                cursor.execute(f"""
                    CREATE TABLE {partition_name} PARTITION OF {strategy.table_name}
                    FOR VALUES FROM ('{start_date.isoformat()}') TO ('{end_date.isoformat()}')
                """)

    async def _create_hash_partitions(self, cursor, strategy: PartitionStrategy):
        """해시 파티션 생성"""
        # 해시 파티션 4개 생성
        for i in range(4):
            partition_name = f"{strategy.table_name}_hash_{i}"
            cursor.execute(f"""
                CREATE TABLE {partition_name} PARTITION OF {strategy.table_name}
                FOR VALUES WITH (modulus 4, remainder {i})
            """)

    async def _migrate_data_to_partitions(self, cursor, strategy: PartitionStrategy, backup_table: str):
        """파티션으로 데이터 마이그레이션"""
        # 백업 테이블에서 새 파티션 테이블로 데이터 복사
        cursor.execute(f"""
            INSERT INTO {strategy.table_name} 
            SELECT * FROM {backup_table}
        """)

    async def setup_caching_strategy(self) -> Dict[str, Any]:
        """캐싱 전략 설정"""
        logger.info("🗄️ 캐싱 전략 설정 중...")
        
        # 자주 조회되는 쿼리들을 캐시에 저장
        cache_strategies = {
            'dashboard_summary': {
                'ttl': 60,  # 1분
                'refresh_interval': 30
            },
            'vehicle_status': {
                'ttl': 30,  # 30초
                'refresh_interval': 15
            },
            'sensor_aggregates': {
                'ttl': 300,  # 5분
                'refresh_interval': 120
            },
            'alert_counts': {
                'ttl': 120,  # 2분
                'refresh_interval': 60
            }
        }
        
        # Redis에 캐싱 전략 저장
        for key, strategy in cache_strategies.items():
            cache_key = f"cache_strategy:{key}"
            self.redis_client.hset(cache_key, mapping=strategy)
            self.redis_client.expire(cache_key, 86400)  # 24시간
        
        # 캐시 워밍업
        await self._warm_up_cache()
        
        logger.info("✅ 캐싱 전략 설정 완료")
        return cache_strategies

    async def _warm_up_cache(self):
        """캐시 워밍업"""
        logger.info("🔥 캐시 워밍업 중...")
        
        warmup_queries = [
            ("dashboard_summary", "SELECT COUNT(*) as total_vehicles, COUNT(CASE WHEN status = 'active' THEN 1 END) as active_vehicles FROM sensors.vehicles"),
            ("recent_alerts", "SELECT COUNT(*) FROM alerts.alert_events WHERE created_at > NOW() - INTERVAL '1 hour'"),
            ("sensor_counts", "SELECT COUNT(*) FROM sensors.sensor_readings WHERE created_at > NOW() - INTERVAL '1 hour'")
        ]
        
        conn = self.get_connection()
        
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                for cache_key, query in warmup_queries:
                    try:
                        cursor.execute(query)
                        result = cursor.fetchall()
                        
                        # Redis에 결과 캐시
                        self.redis_client.setex(
                            f"cache:{cache_key}",
                            CACHE_TTL_SECONDS,
                            json.dumps(result, default=str)
                        )
                        
                        logger.debug(f"✅ 캐시 워밍업: {cache_key}")
                        
                    except Exception as e:
                        logger.warning(f"⚠️ 캐시 워밍업 실패: {cache_key} - {str(e)}")
                        
        except Exception as e:
            logger.error(f"❌ 캐시 워밍업 실패: {str(e)}")
        finally:
            self.return_connection(conn)

    async def run_maintenance_tasks(self):
        """정기 유지보수 작업"""
        logger.info("🧹 데이터베이스 유지보수 작업 실행 중...")
        
        conn = self.get_connection()
        
        try:
            with conn.cursor() as cursor:
                # VACUUM ANALYZE 실행
                tables_to_maintain = [
                    'sensors.sensor_readings',
                    'sensors.tpms_data',
                    'alerts.alert_events',
                    'auth.security_events'
                ]
                
                for table in tables_to_maintain:
                    try:
                        start_time = time.time()
                        cursor.execute(f"VACUUM ANALYZE {table}")
                        execution_time = time.time() - start_time
                        
                        logger.info(f"✅ VACUUM ANALYZE 완료: {table} ({execution_time:.2f}초)")
                        
                        # 최적화 이력 기록
                        await self._record_optimization(
                            OptimizationType.VACUUM_ANALYZE,
                            table,
                            "VACUUM ANALYZE executed",
                            {},
                            {"execution_time": execution_time},
                            5.0  # 5% 성능 향상 예상
                        )
                        
                    except Exception as e:
                        logger.warning(f"⚠️ VACUUM ANALYZE 실패: {table} - {str(e)}")
                
                # 통계 정보 업데이트
                cursor.execute("ANALYZE")
                
            conn.commit()
            
        except Exception as e:
            logger.error(f"❌ 유지보수 작업 실패: {str(e)}")
            conn.rollback()
        finally:
            self.return_connection(conn)

    async def _record_optimization(self, opt_type: OptimizationType, target: str, action: str,
                                 before_metrics: Dict, after_metrics: Dict, performance_gain: float):
        """최적화 이력 기록"""
        conn = self.get_connection()
        
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO performance.optimization_history 
                    (optimization_type, target_object, action_taken, before_metrics, after_metrics, performance_gain)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    opt_type.value,
                    target,
                    action,
                    json.dumps(before_metrics),
                    json.dumps(after_metrics),
                    performance_gain
                ))
                
            conn.commit()
            
        except Exception as e:
            logger.error(f"❌ 최적화 이력 기록 실패: {str(e)}")
            conn.rollback()
        finally:
            self.return_connection(conn)

    async def generate_performance_report(self) -> Dict[str, Any]:
        """성능 리포트 생성"""
        logger.info("📊 데이터베이스 성능 리포트 생성 중...")
        
        conn = self.get_connection()
        
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                report = {
                    'generated_at': datetime.utcnow().isoformat(),
                    'database_size': {},
                    'query_performance': {},
                    'index_usage': {},
                    'optimization_history': [],
                    'recommendations': []
                }
                
                # 데이터베이스 크기 정보
                cursor.execute("""
                    SELECT 
                        pg_size_pretty(pg_database_size(current_database())) as database_size,
                        pg_size_pretty(sum(pg_total_relation_size(c.oid))) as tables_size
                    FROM pg_class c
                    LEFT JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname NOT IN ('information_schema', 'pg_catalog', 'pg_toast')
                      AND c.relkind = 'r'
                """)
                
                size_info = cursor.fetchone()
                report['database_size'] = dict(size_info) if size_info else {}
                
                # 상위 느린 쿼리
                cursor.execute("""
                    SELECT 
                        query,
                        calls,
                        total_time,
                        mean_time,
                        max_time
                    FROM pg_stat_statements 
                    ORDER BY total_time DESC 
                    LIMIT 10
                """)
                
                slow_queries = cursor.fetchall()
                report['query_performance']['slow_queries'] = [dict(q) for q in slow_queries]
                
                # 인덱스 사용률
                cursor.execute("""
                    SELECT 
                        schemaname,
                        tablename,
                        indexname,
                        idx_scan,
                        idx_tup_read,
                        idx_tup_fetch
                    FROM pg_stat_user_indexes
                    ORDER BY idx_scan DESC
                    LIMIT 20
                """)
                
                index_stats = cursor.fetchall()
                report['index_usage'] = [dict(idx) for idx in index_stats]
                
                # 최근 최적화 이력
                cursor.execute("""
                    SELECT *
                    FROM performance.optimization_history
                    ORDER BY timestamp DESC
                    LIMIT 20
                """)
                
                optimization_history = cursor.fetchall()
                report['optimization_history'] = [dict(opt) for opt in optimization_history]
                
                return report
                
        except Exception as e:
            logger.error(f"❌ 성능 리포트 생성 실패: {str(e)}")
            return {}
        finally:
            self.return_connection(conn)

async def main():
    """메인 실행 함수"""
    logger.info("🚀 HankookTire SmartSensor 2.0 데이터베이스 최적화 시작")
    
    optimizer = DatabaseOptimizer()
    await optimizer.initialize()
    
    # 쿼리 성능 분석
    query_analyses = await optimizer.analyze_query_performance()
    logger.info(f"📊 분석된 쿼리 수: {len(query_analyses)}")
    
    # 인덱스 추천 및 생성
    recommendations = await optimizer.recommend_indexes()
    if recommendations:
        created_indexes = await optimizer.create_recommended_indexes(recommendations)
        logger.info(f"🔨 생성된 인덱스 수: {len(created_indexes)}")
    
    # 캐싱 전략 설정
    cache_strategies = await optimizer.setup_caching_strategy()
    logger.info(f"🗄️ 설정된 캐시 전략 수: {len(cache_strategies)}")
    
    # 유지보수 작업
    await optimizer.run_maintenance_tasks()
    
    # 성능 리포트 생성
    report = await optimizer.generate_performance_report()
    
    # 리포트 저장
    with open('database_performance_report.json', 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)
    
    logger.info("🎉 데이터베이스 최적화 완료!")
    logger.info("📄 상세 리포트: database_performance_report.json")

if __name__ == "__main__":
    asyncio.run(main())