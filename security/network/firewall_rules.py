#!/usr/bin/env python3
"""
HankookTire SmartSensor 2.0 - Network Security & Firewall Manager
차세대 통합 스마트 타이어 센서 시스템 네트워크 보안 관리자

네트워크 보안 규칙 관리
- 방화벽 규칙 자동 생성
- 침입 탐지 시스템 (IDS)
- DDoS 방어
- 네트워크 트래픽 분석
- 지역별 접근 제어
- API 속도 제한
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple, Union
from dataclasses import dataclass, asdict
from enum import Enum
from ipaddress import ip_address, ip_network, IPv4Address, IPv4Network
import psycopg2
from psycopg2.extras import RealDictCursor
import redis
import re
from collections import defaultdict, deque
import geoip2.database
import geoip2.errors

# 설정
POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'postgres-service')
POSTGRES_PORT = int(os.getenv('POSTGRES_PORT', '5432'))
POSTGRES_DB = os.getenv('POSTGRES_DB', 'smarttire_sensors')
POSTGRES_USER = os.getenv('POSTGRES_USER', 'smarttire')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'password')

REDIS_HOST = os.getenv('REDIS_HOST', 'redis-service')
REDIS_PORT = int(os.getenv('REDIS_PORT', '6379'))
REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', '')

# 보안 설정
DEFAULT_RATE_LIMIT = int(os.getenv('DEFAULT_RATE_LIMIT', '100'))
RATE_LIMIT_WINDOW = int(os.getenv('RATE_LIMIT_WINDOW', '3600'))
MAX_FAILED_ATTEMPTS = int(os.getenv('MAX_FAILED_ATTEMPTS', '5'))
BAN_DURATION = int(os.getenv('BAN_DURATION', '3600'))
GEOIP_DB_PATH = os.getenv('GEOIP_DB_PATH', '/opt/geoip/GeoLite2-Country.mmdb')

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class RuleAction(Enum):
    """방화벽 규칙 액션"""
    ALLOW = "allow"
    DENY = "deny"
    DROP = "drop"
    LIMIT = "limit"
    LOG = "log"

class TrafficType(Enum):
    """트래픽 타입"""
    HTTP = "http"
    HTTPS = "https"
    MQTT = "mqtt"
    WEBSOCKET = "websocket"
    API = "api"
    SSH = "ssh"
    ICMP = "icmp"
    DNS = "dns"

class ThreatLevel(Enum):
    """위협 수준"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class SecurityEventType(Enum):
    """보안 이벤트 타입"""
    INTRUSION_ATTEMPT = "intrusion_attempt"
    DDOS_ATTACK = "ddos_attack"
    BRUTE_FORCE = "brute_force"
    SUSPICIOUS_TRAFFIC = "suspicious_traffic"
    MALFORMED_REQUEST = "malformed_request"
    UNAUTHORIZED_ACCESS = "unauthorized_access"
    RATE_LIMIT_VIOLATION = "rate_limit_violation"
    GEO_BLOCKING = "geo_blocking"
    IP_REPUTATION = "ip_reputation"

@dataclass
class FirewallRule:
    """방화벽 규칙"""
    id: Optional[int]
    name: str
    description: str
    source_ip: Optional[str]  # CIDR 표기법
    destination_ip: Optional[str]
    source_port: Optional[int]
    destination_port: Optional[int]
    protocol: str  # tcp, udp, icmp
    action: RuleAction
    priority: int
    is_active: bool = True
    created_at: datetime = None
    updated_at: datetime = None

@dataclass
class SecurityEvent:
    """보안 이벤트"""
    id: Optional[int]
    event_type: SecurityEventType
    source_ip: str
    destination_ip: str
    source_port: Optional[int]
    destination_port: Optional[int]
    protocol: str
    threat_level: ThreatLevel
    details: Dict
    is_blocked: bool
    timestamp: datetime = None

@dataclass
class TrafficAnalysis:
    """트래픽 분석 결과"""
    ip_address: str
    request_count: int
    data_volume: int
    unique_endpoints: int
    error_rate: float
    avg_response_time: float
    suspicious_patterns: List[str]
    risk_score: float
    timestamp: datetime

class NetworkSecurityManager:
    """네트워크 보안 관리자"""
    
    def __init__(self):
        self.redis_client = None
        self.geoip_reader = None
        self.traffic_cache = defaultdict(lambda: deque(maxlen=1000))
        self.blocked_ips = set()
        
        # 기본 방화벽 규칙
        self.default_rules = [
            # 내부 네트워크 허용
            ("Allow Internal 10.x", "10.0.0.0/8", None, "tcp", RuleAction.ALLOW, 100),
            ("Allow Internal 172.x", "172.16.0.0/12", None, "tcp", RuleAction.ALLOW, 100),
            ("Allow Internal 192.x", "192.168.0.0/16", None, "tcp", RuleAction.ALLOW, 100),
            
            # 서비스별 규칙
            ("Allow HTTP", None, 80, "tcp", RuleAction.ALLOW, 200),
            ("Allow HTTPS", None, 443, "tcp", RuleAction.ALLOW, 200),
            ("Allow MQTT", None, 1883, "tcp", RuleAction.ALLOW, 200),
            ("Allow MQTT Secure", None, 8883, "tcp", RuleAction.ALLOW, 200),
            
            # 위험한 포트 차단
            ("Block Telnet", None, 23, "tcp", RuleAction.DENY, 50),
            ("Block FTP", None, 21, "tcp", RuleAction.DENY, 50),
            ("Block SMB", None, 445, "tcp", RuleAction.DENY, 50),
            ("Block RDP", None, 3389, "tcp", RuleAction.DENY, 50),
            
            # 기본 차단
            ("Default Deny", None, None, "tcp", RuleAction.DENY, 1),
        ]
        
        # 알려진 악성 IP 패턴
        self.malicious_patterns = [
            r'\.onion$',  # Tor 출구 노드
            r'^169\.254\.',  # Link-local
            r'^0\.',  # 잘못된 IP
            r'^224\.',  # 멀티캐스트
        ]
        
        # 허용된 국가 코드
        self.allowed_countries = {'KR', 'US', 'JP', 'DE', 'GB', 'CA', 'AU', 'SG'}
        
    async def initialize(self):
        """초기화"""
        # Redis 연결
        self.redis_client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            password=REDIS_PASSWORD if REDIS_PASSWORD else None,
            decode_responses=True
        )
        
        # GeoIP 데이터베이스 로드
        try:
            if os.path.exists(GEOIP_DB_PATH):
                self.geoip_reader = geoip2.database.Reader(GEOIP_DB_PATH)
                logger.info("✅ GeoIP 데이터베이스 로드 완료")
            else:
                logger.warning("⚠️ GeoIP 데이터베이스 파일을 찾을 수 없습니다")
        except Exception as e:
            logger.error(f"❌ GeoIP 데이터베이스 로드 실패: {str(e)}")
        
        # 테이블 생성
        await self.create_security_tables()
        
        # 기본 규칙 생성
        await self.initialize_default_rules()
        
        # 차단된 IP 로드
        await self.load_blocked_ips()

    async def create_security_tables(self):
        """보안 테이블 생성"""
        conn = psycopg2.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            database=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD
        )
        
        try:
            with conn.cursor() as cursor:
                # 방화벽 규칙 테이블
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS security.firewall_rules (
                        id SERIAL PRIMARY KEY,
                        name VARCHAR(100) NOT NULL,
                        description TEXT,
                        source_ip CIDR,
                        destination_ip CIDR,
                        source_port INTEGER,
                        destination_port INTEGER,
                        protocol VARCHAR(10) NOT NULL,
                        action VARCHAR(10) NOT NULL,
                        priority INTEGER NOT NULL,
                        is_active BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # 보안 이벤트 테이블
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS security.security_events (
                        id SERIAL PRIMARY KEY,
                        event_type VARCHAR(30) NOT NULL,
                        source_ip INET NOT NULL,
                        destination_ip INET,
                        source_port INTEGER,
                        destination_port INTEGER,
                        protocol VARCHAR(10),
                        threat_level VARCHAR(10) NOT NULL,
                        details JSONB,
                        is_blocked BOOLEAN DEFAULT FALSE,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # 차단된 IP 테이블
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS security.blocked_ips (
                        id SERIAL PRIMARY KEY,
                        ip_address INET UNIQUE NOT NULL,
                        reason VARCHAR(100) NOT NULL,
                        blocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        expires_at TIMESTAMP,
                        is_permanent BOOLEAN DEFAULT FALSE,
                        block_count INTEGER DEFAULT 1
                    )
                """)
                
                # 트래픽 분석 테이블
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS security.traffic_analysis (
                        id SERIAL PRIMARY KEY,
                        ip_address INET NOT NULL,
                        request_count INTEGER NOT NULL,
                        data_volume BIGINT NOT NULL,
                        unique_endpoints INTEGER NOT NULL,
                        error_rate FLOAT NOT NULL,
                        avg_response_time FLOAT NOT NULL,
                        suspicious_patterns JSONB,
                        risk_score FLOAT NOT NULL,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # IP 평판 테이블
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS security.ip_reputation (
                        id SERIAL PRIMARY KEY,
                        ip_address INET UNIQUE NOT NULL,
                        reputation_score FLOAT NOT NULL,
                        country_code CHAR(2),
                        is_malicious BOOLEAN DEFAULT FALSE,
                        last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        metadata JSONB
                    )
                """)
                
                # 인덱스 생성
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_firewall_rules_priority ON security.firewall_rules(priority DESC)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_security_events_timestamp ON security.security_events(timestamp DESC)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_security_events_source_ip ON security.security_events(source_ip)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_blocked_ips_ip ON security.blocked_ips(ip_address)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_traffic_analysis_ip ON security.traffic_analysis(ip_address)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_traffic_analysis_timestamp ON security.traffic_analysis(timestamp)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_ip_reputation_ip ON security.ip_reputation(ip_address)")
                
            conn.commit()
            logger.info("✅ 보안 테이블 생성 완료")
            
        except Exception as e:
            logger.error(f"❌ 보안 테이블 생성 실패: {str(e)}")
            conn.rollback()
            raise
        finally:
            conn.close()

    async def initialize_default_rules(self):
        """기본 방화벽 규칙 생성"""
        conn = psycopg2.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            database=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD
        )
        
        try:
            with conn.cursor() as cursor:
                for name, source_ip, dest_port, protocol, action, priority in self.default_rules:
                    cursor.execute("""
                        INSERT INTO security.firewall_rules 
                        (name, description, source_ip, destination_port, protocol, action, priority)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT DO NOTHING
                    """, (
                        name,
                        f"Default rule: {name}",
                        source_ip,
                        dest_port,
                        protocol,
                        action.value,
                        priority
                    ))
                    
            conn.commit()
            logger.info("✅ 기본 방화벽 규칙 생성 완료")
            
        except Exception as e:
            logger.error(f"❌ 기본 방화벽 규칙 생성 실패: {str(e)}")
            conn.rollback()
            raise
        finally:
            conn.close()

    async def load_blocked_ips(self):
        """차단된 IP 목록 로드"""
        conn = psycopg2.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            database=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            cursor_factory=RealDictCursor
        )
        
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT ip_address FROM security.blocked_ips 
                    WHERE is_permanent = TRUE 
                       OR expires_at > CURRENT_TIMESTAMP
                """)
                
                blocked_ips = cursor.fetchall()
                
            self.blocked_ips = {str(row['ip_address']) for row in blocked_ips}
            logger.info(f"✅ 차단된 IP {len(self.blocked_ips)}개 로드 완료")
            
        except Exception as e:
            logger.error(f"❌ 차단된 IP 로드 실패: {str(e)}")
        finally:
            conn.close()

    async def check_ip_access(self, ip: str, port: int, protocol: str = "tcp") -> Tuple[bool, str]:
        """IP 접근 권한 확인"""
        try:
            # 차단된 IP 확인
            if ip in self.blocked_ips:
                await self.log_security_event(
                    SecurityEventType.UNAUTHORIZED_ACCESS,
                    ip, None, None, port, protocol,
                    ThreatLevel.HIGH,
                    {"reason": "blocked_ip"},
                    True
                )
                return False, "IP blocked"
            
            # 악성 패턴 확인
            if self.is_malicious_ip(ip):
                await self.block_ip(ip, "Malicious IP pattern", timedelta(hours=24))
                return False, "Malicious IP pattern"
            
            # 지역별 차단 확인
            if not await self.check_geo_access(ip):
                await self.log_security_event(
                    SecurityEventType.GEO_BLOCKING,
                    ip, None, None, port, protocol,
                    ThreatLevel.MEDIUM,
                    {"reason": "geo_blocking"},
                    True
                )
                return False, "Geographic restriction"
            
            # 방화벽 규칙 확인
            allowed, rule_name = await self.check_firewall_rules(ip, port, protocol)
            if not allowed:
                await self.log_security_event(
                    SecurityEventType.UNAUTHORIZED_ACCESS,
                    ip, None, None, port, protocol,
                    ThreatLevel.MEDIUM,
                    {"reason": "firewall_rule", "rule": rule_name},
                    True
                )
                return False, f"Blocked by rule: {rule_name}"
            
            # 속도 제한 확인
            if not await self.check_rate_limit(ip):
                await self.log_security_event(
                    SecurityEventType.RATE_LIMIT_VIOLATION,
                    ip, None, None, port, protocol,
                    ThreatLevel.MEDIUM,
                    {"reason": "rate_limit"},
                    True
                )
                return False, "Rate limit exceeded"
            
            return True, "Access allowed"
            
        except Exception as e:
            logger.error(f"❌ IP 접근 확인 실패: {str(e)}")
            return False, "Internal error"

    def is_malicious_ip(self, ip: str) -> bool:
        """악성 IP 패턴 확인"""
        for pattern in self.malicious_patterns:
            if re.search(pattern, ip):
                return True
        return False

    async def check_geo_access(self, ip: str) -> bool:
        """지역별 접근 제어"""
        if not self.geoip_reader:
            return True  # GeoIP 없으면 허용
        
        try:
            response = self.geoip_reader.country(ip)
            country_code = response.country.iso_code
            
            # IP 평판 정보 업데이트
            await self.update_ip_reputation(ip, country_code)
            
            return country_code in self.allowed_countries
            
        except geoip2.errors.AddressNotFoundError:
            logger.warning(f"⚠️ IP 지역 정보 없음: {ip}")
            return True  # 정보 없으면 허용
        except Exception as e:
            logger.error(f"❌ 지역 확인 실패: {str(e)}")
            return True

    async def check_firewall_rules(self, ip: str, port: int, protocol: str) -> Tuple[bool, str]:
        """방화벽 규칙 확인"""
        conn = psycopg2.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            database=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            cursor_factory=RealDictCursor
        )
        
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT name, action FROM security.firewall_rules 
                    WHERE is_active = TRUE
                      AND (source_ip IS NULL OR %s::inet <<= source_ip)
                      AND (destination_port IS NULL OR destination_port = %s)
                      AND protocol = %s
                    ORDER BY priority DESC
                    LIMIT 1
                """, (ip, port, protocol))
                
                rule = cursor.fetchone()
                
            if rule:
                action = RuleAction(rule['action'])
                if action in [RuleAction.ALLOW]:
                    return True, rule['name']
                else:
                    return False, rule['name']
            
            return False, "Default deny"
            
        except Exception as e:
            logger.error(f"❌ 방화벽 규칙 확인 실패: {str(e)}")
            return False, "Error checking rules"
        finally:
            conn.close()

    async def check_rate_limit(self, ip: str, limit: int = DEFAULT_RATE_LIMIT, window: int = RATE_LIMIT_WINDOW) -> bool:
        """속도 제한 확인"""
        try:
            key = f"rate_limit:{ip}"
            current = self.redis_client.get(key)
            
            if current is None:
                self.redis_client.setex(key, window, 1)
                return True
            elif int(current) < limit:
                self.redis_client.incr(key)
                return True
            else:
                return False
                
        except Exception as e:
            logger.error(f"❌ 속도 제한 확인 실패: {str(e)}")
            return True  # Redis 오류 시 허용

    async def analyze_traffic_pattern(self, ip: str, endpoint: str, response_time: float, status_code: int, data_size: int):
        """트래픽 패턴 분석"""
        try:
            # 트래픽 정보 저장
            traffic_info = {
                'endpoint': endpoint,
                'response_time': response_time,
                'status_code': status_code,
                'data_size': data_size,
                'timestamp': time.time()
            }
            
            self.traffic_cache[ip].append(traffic_info)
            
            # 분석을 위한 데이터 수집 (최근 1시간)
            current_time = time.time()
            hour_ago = current_time - 3600
            
            recent_traffic = [
                t for t in self.traffic_cache[ip] 
                if t['timestamp'] > hour_ago
            ]
            
            if len(recent_traffic) < 10:  # 충분한 데이터가 없으면 분석 안함
                return
            
            # 분석 수행
            analysis = await self.perform_traffic_analysis(ip, recent_traffic)
            
            # 위험 점수가 높으면 추가 조치
            if analysis.risk_score > 0.8:
                await self.handle_suspicious_traffic(ip, analysis)
                
        except Exception as e:
            logger.error(f"❌ 트래픽 패턴 분석 실패: {str(e)}")

    async def perform_traffic_analysis(self, ip: str, traffic_data: List[Dict]) -> TrafficAnalysis:
        """트래픽 분석 수행"""
        request_count = len(traffic_data)
        data_volume = sum(t['data_size'] for t in traffic_data)
        unique_endpoints = len(set(t['endpoint'] for t in traffic_data))
        
        # 오류율 계산
        error_count = sum(1 for t in traffic_data if t['status_code'] >= 400)
        error_rate = error_count / request_count if request_count > 0 else 0
        
        # 평균 응답 시간
        avg_response_time = sum(t['response_time'] for t in traffic_data) / request_count
        
        # 의심스러운 패턴 탐지
        suspicious_patterns = []
        
        # 1. 높은 요청 빈도
        if request_count > 1000:
            suspicious_patterns.append("high_request_frequency")
        
        # 2. 높은 오류율
        if error_rate > 0.5:
            suspicious_patterns.append("high_error_rate")
        
        # 3. 비정상적인 엔드포인트 탐색
        if unique_endpoints > 100:
            suspicious_patterns.append("endpoint_scanning")
        
        # 4. 비정상적인 응답 시간
        if avg_response_time > 5.0:
            suspicious_patterns.append("slow_response_pattern")
        
        # 위험 점수 계산
        risk_score = self.calculate_risk_score(
            request_count, error_rate, unique_endpoints, suspicious_patterns
        )
        
        analysis = TrafficAnalysis(
            ip_address=ip,
            request_count=request_count,
            data_volume=data_volume,
            unique_endpoints=unique_endpoints,
            error_rate=error_rate,
            avg_response_time=avg_response_time,
            suspicious_patterns=suspicious_patterns,
            risk_score=risk_score,
            timestamp=datetime.utcnow()
        )
        
        # 분석 결과 저장
        await self.store_traffic_analysis(analysis)
        
        return analysis

    def calculate_risk_score(self, request_count: int, error_rate: float, unique_endpoints: int, patterns: List[str]) -> float:
        """위험 점수 계산"""
        score = 0.0
        
        # 요청 빈도 점수 (0-0.3)
        if request_count > 10000:
            score += 0.3
        elif request_count > 5000:
            score += 0.2
        elif request_count > 1000:
            score += 0.1
        
        # 오류율 점수 (0-0.3)
        if error_rate > 0.8:
            score += 0.3
        elif error_rate > 0.5:
            score += 0.2
        elif error_rate > 0.3:
            score += 0.1
        
        # 엔드포인트 탐색 점수 (0-0.2)
        if unique_endpoints > 200:
            score += 0.2
        elif unique_endpoints > 100:
            score += 0.1
        
        # 패턴 점수 (0-0.2)
        score += len(patterns) * 0.05
        
        return min(score, 1.0)

    async def handle_suspicious_traffic(self, ip: str, analysis: TrafficAnalysis):
        """의심스러운 트래픽 처리"""
        try:
            # 보안 이벤트 로깅
            await self.log_security_event(
                SecurityEventType.SUSPICIOUS_TRAFFIC,
                ip, None, None, None, "tcp",
                ThreatLevel.HIGH,
                {
                    "risk_score": analysis.risk_score,
                    "patterns": analysis.suspicious_patterns,
                    "request_count": analysis.request_count,
                    "error_rate": analysis.error_rate
                },
                False
            )
            
            # 위험 점수에 따른 대응
            if analysis.risk_score > 0.9:
                # 즉시 차단
                await self.block_ip(ip, "High risk traffic pattern", timedelta(hours=24))
                logger.warning(f"🚨 높은 위험 점수로 IP 차단: {ip} (점수: {analysis.risk_score})")
                
            elif analysis.risk_score > 0.8:
                # 단기 차단
                await self.block_ip(ip, "Suspicious traffic pattern", timedelta(hours=1))
                logger.warning(f"⚠️ 의심스러운 패턴으로 IP 임시 차단: {ip} (점수: {analysis.risk_score})")
                
        except Exception as e:
            logger.error(f"❌ 의심스러운 트래픽 처리 실패: {str(e)}")

    async def block_ip(self, ip: str, reason: str, duration: Optional[timedelta] = None):
        """IP 차단"""
        conn = psycopg2.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            database=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD
        )
        
        try:
            expires_at = datetime.utcnow() + duration if duration else None
            is_permanent = duration is None
            
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO security.blocked_ips (ip_address, reason, expires_at, is_permanent)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (ip_address) DO UPDATE SET
                        reason = EXCLUDED.reason,
                        blocked_at = CURRENT_TIMESTAMP,
                        expires_at = EXCLUDED.expires_at,
                        is_permanent = EXCLUDED.is_permanent,
                        block_count = security.blocked_ips.block_count + 1
                """, (ip, reason, expires_at, is_permanent))
                
            conn.commit()
            
            # 메모리 캐시 업데이트
            self.blocked_ips.add(ip)
            
            # Redis 캐시 업데이트
            if duration:
                self.redis_client.setex(f"blocked_ip:{ip}", int(duration.total_seconds()), reason)
            else:
                self.redis_client.set(f"blocked_ip:{ip}", reason)
            
            logger.info(f"🚫 IP 차단 완료: {ip} (이유: {reason})")
            
        except Exception as e:
            logger.error(f"❌ IP 차단 실패: {str(e)}")
            conn.rollback()
            raise
        finally:
            conn.close()

    async def unblock_ip(self, ip: str):
        """IP 차단 해제"""
        conn = psycopg2.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            database=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD
        )
        
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    DELETE FROM security.blocked_ips WHERE ip_address = %s
                """, (ip,))
                
            conn.commit()
            
            # 메모리 캐시 업데이트
            self.blocked_ips.discard(ip)
            
            # Redis 캐시 업데이트
            self.redis_client.delete(f"blocked_ip:{ip}")
            
            logger.info(f"✅ IP 차단 해제 완료: {ip}")
            
        except Exception as e:
            logger.error(f"❌ IP 차단 해제 실패: {str(e)}")
            conn.rollback()
            raise
        finally:
            conn.close()

    async def update_ip_reputation(self, ip: str, country_code: str):
        """IP 평판 정보 업데이트"""
        conn = psycopg2.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            database=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD
        )
        
        try:
            # 기본 평판 점수 계산
            reputation_score = 0.5  # 중립
            
            # 허용된 국가면 점수 증가
            if country_code in self.allowed_countries:
                reputation_score += 0.3
            
            # 악성 패턴이면 점수 감소
            if self.is_malicious_ip(ip):
                reputation_score -= 0.4
                is_malicious = True
            else:
                is_malicious = False
            
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO security.ip_reputation 
                    (ip_address, reputation_score, country_code, is_malicious, metadata)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (ip_address) DO UPDATE SET
                        reputation_score = EXCLUDED.reputation_score,
                        country_code = EXCLUDED.country_code,
                        is_malicious = EXCLUDED.is_malicious,
                        last_seen = CURRENT_TIMESTAMP,
                        metadata = EXCLUDED.metadata
                """, (
                    ip,
                    reputation_score,
                    country_code,
                    is_malicious,
                    json.dumps({"last_update": datetime.utcnow().isoformat()})
                ))
                
            conn.commit()
            
        except Exception as e:
            logger.error(f"❌ IP 평판 업데이트 실패: {str(e)}")
            conn.rollback()
        finally:
            conn.close()

    async def store_traffic_analysis(self, analysis: TrafficAnalysis):
        """트래픽 분석 결과 저장"""
        conn = psycopg2.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            database=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD
        )
        
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO security.traffic_analysis 
                    (ip_address, request_count, data_volume, unique_endpoints, 
                     error_rate, avg_response_time, suspicious_patterns, risk_score)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    analysis.ip_address,
                    analysis.request_count,
                    analysis.data_volume,
                    analysis.unique_endpoints,
                    analysis.error_rate,
                    analysis.avg_response_time,
                    json.dumps(analysis.suspicious_patterns),
                    analysis.risk_score
                ))
                
            conn.commit()
            
        except Exception as e:
            logger.error(f"❌ 트래픽 분석 저장 실패: {str(e)}")
            conn.rollback()
        finally:
            conn.close()

    async def log_security_event(self, event_type: SecurityEventType, source_ip: str, dest_ip: Optional[str],
                                source_port: Optional[int], dest_port: Optional[int], protocol: str,
                                threat_level: ThreatLevel, details: Dict, is_blocked: bool):
        """보안 이벤트 로깅"""
        conn = psycopg2.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            database=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD
        )
        
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO security.security_events 
                    (event_type, source_ip, destination_ip, source_port, destination_port, 
                     protocol, threat_level, details, is_blocked)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    event_type.value,
                    source_ip,
                    dest_ip,
                    source_port,
                    dest_port,
                    protocol,
                    threat_level.value,
                    json.dumps(details),
                    is_blocked
                ))
                
            conn.commit()
            
        except Exception as e:
            logger.error(f"❌ 보안 이벤트 로깅 실패: {str(e)}")
        finally:
            conn.close()

    async def cleanup_expired_blocks(self):
        """만료된 차단 해제"""
        conn = psycopg2.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            database=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            cursor_factory=RealDictCursor
        )
        
        try:
            with conn.cursor() as cursor:
                # 만료된 차단 조회
                cursor.execute("""
                    SELECT ip_address FROM security.blocked_ips 
                    WHERE expires_at < CURRENT_TIMESTAMP AND is_permanent = FALSE
                """)
                
                expired_ips = cursor.fetchall()
                
                # 만료된 차단 삭제
                cursor.execute("""
                    DELETE FROM security.blocked_ips 
                    WHERE expires_at < CURRENT_TIMESTAMP AND is_permanent = FALSE
                """)
                
            conn.commit()
            
            # 메모리 캐시에서 제거
            for row in expired_ips:
                ip = str(row['ip_address'])
                self.blocked_ips.discard(ip)
                self.redis_client.delete(f"blocked_ip:{ip}")
            
            if expired_ips:
                logger.info(f"✅ 만료된 차단 {len(expired_ips)}개 해제 완료")
                
        except Exception as e:
            logger.error(f"❌ 만료된 차단 정리 실패: {str(e)}")
            conn.rollback()
        finally:
            conn.close()

    async def get_security_dashboard_data(self) -> Dict:
        """보안 대시보드 데이터 조회"""
        conn = psycopg2.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            database=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            cursor_factory=RealDictCursor
        )
        
        try:
            dashboard_data = {}
            
            with conn.cursor() as cursor:
                # 차단된 IP 수
                cursor.execute("SELECT COUNT(*) as count FROM security.blocked_ips")
                dashboard_data['blocked_ips'] = cursor.fetchone()['count']
                
                # 최근 24시간 보안 이벤트 수
                cursor.execute("""
                    SELECT COUNT(*) as count FROM security.security_events 
                    WHERE timestamp > CURRENT_TIMESTAMP - INTERVAL '24 hours'
                """)
                dashboard_data['recent_events'] = cursor.fetchone()['count']
                
                # 위협 수준별 이벤트 분포
                cursor.execute("""
                    SELECT threat_level, COUNT(*) as count 
                    FROM security.security_events 
                    WHERE timestamp > CURRENT_TIMESTAMP - INTERVAL '24 hours'
                    GROUP BY threat_level
                """)
                dashboard_data['threat_distribution'] = {
                    row['threat_level']: row['count'] 
                    for row in cursor.fetchall()
                }
                
                # 상위 공격자 IP
                cursor.execute("""
                    SELECT source_ip, COUNT(*) as count 
                    FROM security.security_events 
                    WHERE timestamp > CURRENT_TIMESTAMP - INTERVAL '24 hours'
                      AND is_blocked = TRUE
                    GROUP BY source_ip 
                    ORDER BY count DESC 
                    LIMIT 10
                """)
                dashboard_data['top_attackers'] = [
                    {"ip": str(row['source_ip']), "count": row['count']}
                    for row in cursor.fetchall()
                ]
                
            return dashboard_data
            
        except Exception as e:
            logger.error(f"❌ 보안 대시보드 데이터 조회 실패: {str(e)}")
            return {}
        finally:
            conn.close()

async def main():
    """테스트 실행"""
    security_manager = NetworkSecurityManager()
    await security_manager.initialize()
    
    # 테스트 IP 접근 확인
    test_ip = "192.168.1.100"
    allowed, reason = await security_manager.check_ip_access(test_ip, 443, "tcp")
    logger.info(f"IP {test_ip} 접근 결과: {allowed} - {reason}")
    
    # 대시보드 데이터 조회
    dashboard = await security_manager.get_security_dashboard_data()
    logger.info(f"보안 대시보드: {dashboard}")

if __name__ == "__main__":
    asyncio.run(main())