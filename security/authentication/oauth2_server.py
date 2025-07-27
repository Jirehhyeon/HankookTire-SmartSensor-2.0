#!/usr/bin/env python3
"""
HankookTire SmartSensor 2.0 - OAuth2 Authentication Server
차세대 통합 스마트 타이어 센서 시스템 인증 서버

JWT 기반 OAuth2 인증 서버 구현
- JWT 토큰 발급 및 검증
- 역할 기반 접근 제어 (RBAC)
- 다중 인증 요소 (MFA) 지원
- API 키 관리
- 보안 이벤트 로깅
"""

import asyncio
import aiohttp
import jwt
import bcrypt
import secrets
import hashlib
import pyotp
import qrcode
import io
import base64
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Union
from dataclasses import dataclass, asdict
from enum import Enum
import json
import logging
import os
import redis
import psycopg2
from psycopg2.extras import RealDictCursor
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from aiohttp import web, web_middlewares
from aiohttp.web_exceptions import HTTPUnauthorized, HTTPForbidden, HTTPBadRequest
import time
import re
from ipaddress import ip_address, ip_network

# 설정
JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', secrets.token_hex(32))
JWT_ALGORITHM = 'HS256'
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 30
JWT_REFRESH_TOKEN_EXPIRE_DAYS = 30

POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'postgres-service')
POSTGRES_PORT = int(os.getenv('POSTGRES_PORT', '5432'))
POSTGRES_DB = os.getenv('POSTGRES_DB', 'smarttire_sensors')
POSTGRES_USER = os.getenv('POSTGRES_USER', 'smarttire')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'password')

REDIS_HOST = os.getenv('REDIS_HOST', 'redis-service')
REDIS_PORT = int(os.getenv('REDIS_PORT', '6379'))
REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', '')

RATE_LIMIT_REQUESTS = int(os.getenv('RATE_LIMIT_REQUESTS', '100'))
RATE_LIMIT_WINDOW = int(os.getenv('RATE_LIMIT_WINDOW', '3600'))  # 1시간

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class UserRole(Enum):
    """사용자 역할 정의"""
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    ENGINEER = "engineer"
    OPERATOR = "operator"
    VIEWER = "viewer"
    API_CLIENT = "api_client"
    SENSOR_DEVICE = "sensor_device"

class AuthenticationMethod(Enum):
    """인증 방법"""
    PASSWORD = "password"
    API_KEY = "api_key"
    DEVICE_CERTIFICATE = "device_certificate"
    MFA_TOTP = "mfa_totp"

class SecurityEventType(Enum):
    """보안 이벤트 타입"""
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILURE = "login_failure"
    TOKEN_ISSUED = "token_issued"
    TOKEN_REFRESHED = "token_refreshed"
    TOKEN_REVOKED = "token_revoked"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    MFA_ENABLED = "mfa_enabled"
    MFA_DISABLED = "mfa_disabled"
    PASSWORD_CHANGED = "password_changed"
    API_KEY_CREATED = "api_key_created"
    API_KEY_REVOKED = "api_key_revoked"

@dataclass
class User:
    """사용자 모델"""
    id: int
    username: str
    email: str
    password_hash: str
    role: UserRole
    is_active: bool = True
    mfa_enabled: bool = False
    mfa_secret: Optional[str] = None
    created_at: datetime = None
    last_login: Optional[datetime] = None
    login_attempts: int = 0
    locked_until: Optional[datetime] = None

@dataclass
class APIKey:
    """API 키 모델"""
    id: int
    key_hash: str
    name: str
    user_id: int
    permissions: List[str]
    is_active: bool = True
    expires_at: Optional[datetime] = None
    created_at: datetime = None
    last_used: Optional[datetime] = None

@dataclass
class SecurityEvent:
    """보안 이벤트 모델"""
    id: Optional[int]
    event_type: SecurityEventType
    user_id: Optional[int]
    ip_address: str
    user_agent: str
    details: Dict
    timestamp: datetime = None

class SecurityManager:
    """보안 관리자 클래스"""
    
    def __init__(self):
        self.redis_client = None
        self.db_pool = None
        
    async def initialize(self):
        """초기화"""
        # Redis 연결
        self.redis_client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            password=REDIS_PASSWORD if REDIS_PASSWORD else None,
            decode_responses=True
        )
        
        # 데이터베이스 테이블 생성
        await self.create_security_tables()
        
    async def create_security_tables(self):
        """보안 관련 테이블 생성"""
        conn = psycopg2.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            database=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD
        )
        
        try:
            with conn.cursor() as cursor:
                # 사용자 테이블
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS auth.users (
                        id SERIAL PRIMARY KEY,
                        username VARCHAR(50) UNIQUE NOT NULL,
                        email VARCHAR(255) UNIQUE NOT NULL,
                        password_hash TEXT NOT NULL,
                        role VARCHAR(20) NOT NULL,
                        is_active BOOLEAN DEFAULT TRUE,
                        mfa_enabled BOOLEAN DEFAULT FALSE,
                        mfa_secret TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_login TIMESTAMP,
                        login_attempts INTEGER DEFAULT 0,
                        locked_until TIMESTAMP
                    )
                """)
                
                # API 키 테이블
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS auth.api_keys (
                        id SERIAL PRIMARY KEY,
                        key_hash TEXT UNIQUE NOT NULL,
                        name VARCHAR(100) NOT NULL,
                        user_id INTEGER REFERENCES auth.users(id),
                        permissions JSONB NOT NULL,
                        is_active BOOLEAN DEFAULT TRUE,
                        expires_at TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_used TIMESTAMP
                    )
                """)
                
                # 보안 이벤트 테이블
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS auth.security_events (
                        id SERIAL PRIMARY KEY,
                        event_type VARCHAR(50) NOT NULL,
                        user_id INTEGER REFERENCES auth.users(id),
                        ip_address INET NOT NULL,
                        user_agent TEXT,
                        details JSONB NOT NULL,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # 토큰 블랙리스트 테이블
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS auth.token_blacklist (
                        id SERIAL PRIMARY KEY,
                        token_jti VARCHAR(36) UNIQUE NOT NULL,
                        expires_at TIMESTAMP NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # 인덱스 생성
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_security_events_timestamp ON auth.security_events(timestamp)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_security_events_user_id ON auth.security_events(user_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_user_id ON auth.api_keys(user_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_token_blacklist_jti ON auth.token_blacklist(token_jti)")
                
            conn.commit()
            logger.info("✅ 보안 테이블 생성 완료")
            
        except Exception as e:
            logger.error(f"❌ 보안 테이블 생성 실패: {str(e)}")
            conn.rollback()
            raise
        finally:
            conn.close()

    def hash_password(self, password: str) -> str:
        """비밀번호 해시화"""
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

    def verify_password(self, password: str, hashed: str) -> bool:
        """비밀번호 검증"""
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

    def generate_api_key(self) -> str:
        """API 키 생성"""
        return f"hks_{secrets.token_urlsafe(32)}"

    def hash_api_key(self, api_key: str) -> str:
        """API 키 해시화"""
        return hashlib.sha256(api_key.encode()).hexdigest()

    def generate_mfa_secret(self) -> str:
        """MFA 시크릿 생성"""
        return pyotp.random_base32()

    def generate_mfa_qr_code(self, username: str, secret: str) -> str:
        """MFA QR 코드 생성"""
        totp_uri = pyotp.totp.TOTP(secret).provisioning_uri(
            name=username,
            issuer_name="HankookTire SmartSensor"
        )
        
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(totp_uri)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        
        return base64.b64encode(buffer.getvalue()).decode()

    def verify_mfa_token(self, secret: str, token: str) -> bool:
        """MFA 토큰 검증"""
        totp = pyotp.TOTP(secret)
        return totp.verify(token, valid_window=1)

    async def create_user(self, username: str, email: str, password: str, role: UserRole) -> User:
        """사용자 생성"""
        conn = psycopg2.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            database=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            cursor_factory=RealDictCursor
        )
        
        try:
            password_hash = self.hash_password(password)
            
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO auth.users (username, email, password_hash, role)
                    VALUES (%s, %s, %s, %s)
                    RETURNING *
                """, (username, email, password_hash, role.value))
                
                user_data = cursor.fetchone()
                
            conn.commit()
            
            user = User(
                id=user_data['id'],
                username=user_data['username'],
                email=user_data['email'],
                password_hash=user_data['password_hash'],
                role=UserRole(user_data['role']),
                is_active=user_data['is_active'],
                mfa_enabled=user_data['mfa_enabled'],
                mfa_secret=user_data['mfa_secret'],
                created_at=user_data['created_at'],
                last_login=user_data['last_login'],
                login_attempts=user_data['login_attempts'],
                locked_until=user_data['locked_until']
            )
            
            logger.info(f"✅ 사용자 생성 완료: {username}")
            return user
            
        except Exception as e:
            logger.error(f"❌ 사용자 생성 실패: {str(e)}")
            conn.rollback()
            raise
        finally:
            conn.close()

    async def get_user_by_username(self, username: str) -> Optional[User]:
        """사용자명으로 사용자 조회"""
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
                    SELECT * FROM auth.users WHERE username = %s AND is_active = TRUE
                """, (username,))
                
                user_data = cursor.fetchone()
                
            if not user_data:
                return None
                
            return User(
                id=user_data['id'],
                username=user_data['username'],
                email=user_data['email'],
                password_hash=user_data['password_hash'],
                role=UserRole(user_data['role']),
                is_active=user_data['is_active'],
                mfa_enabled=user_data['mfa_enabled'],
                mfa_secret=user_data['mfa_secret'],
                created_at=user_data['created_at'],
                last_login=user_data['last_login'],
                login_attempts=user_data['login_attempts'],
                locked_until=user_data['locked_until']
            )
            
        except Exception as e:
            logger.error(f"❌ 사용자 조회 실패: {str(e)}")
            raise
        finally:
            conn.close()

    async def create_api_key(self, user_id: int, name: str, permissions: List[str], expires_at: Optional[datetime] = None) -> str:
        """API 키 생성"""
        api_key = self.generate_api_key()
        key_hash = self.hash_api_key(api_key)
        
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
                    INSERT INTO auth.api_keys (key_hash, name, user_id, permissions, expires_at)
                    VALUES (%s, %s, %s, %s, %s)
                """, (key_hash, name, user_id, json.dumps(permissions), expires_at))
                
            conn.commit()
            logger.info(f"✅ API 키 생성 완료: {name}")
            return api_key
            
        except Exception as e:
            logger.error(f"❌ API 키 생성 실패: {str(e)}")
            conn.rollback()
            raise
        finally:
            conn.close()

    async def log_security_event(self, event: SecurityEvent):
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
                    INSERT INTO auth.security_events (event_type, user_id, ip_address, user_agent, details)
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    event.event_type.value,
                    event.user_id,
                    event.ip_address,
                    event.user_agent,
                    json.dumps(event.details)
                ))
                
            conn.commit()
            
        except Exception as e:
            logger.error(f"❌ 보안 이벤트 로깅 실패: {str(e)}")
        finally:
            conn.close()

    async def check_rate_limit(self, identifier: str, window: int = RATE_LIMIT_WINDOW, limit: int = RATE_LIMIT_REQUESTS) -> bool:
        """요청 속도 제한 확인"""
        try:
            key = f"rate_limit:{identifier}"
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

    def generate_jwt_token(self, user: User, token_type: str = "access") -> str:
        """JWT 토큰 생성"""
        now = datetime.utcnow()
        
        if token_type == "access":
            expire = now + timedelta(minutes=JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
        else:  # refresh
            expire = now + timedelta(days=JWT_REFRESH_TOKEN_EXPIRE_DAYS)
        
        payload = {
            "sub": str(user.id),
            "username": user.username,
            "role": user.role.value,
            "type": token_type,
            "iat": now.timestamp(),
            "exp": expire.timestamp(),
            "jti": secrets.token_hex(16)
        }
        
        return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

    def verify_jwt_token(self, token: str) -> Dict:
        """JWT 토큰 검증"""
        try:
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
            
            # 토큰 블랙리스트 확인
            if self.is_token_blacklisted(payload.get('jti')):
                raise jwt.InvalidTokenError("Token is blacklisted")
                
            return payload
            
        except jwt.ExpiredSignatureError:
            raise HTTPUnauthorized(reason="Token expired")
        except jwt.InvalidTokenError:
            raise HTTPUnauthorized(reason="Invalid token")

    def is_token_blacklisted(self, jti: str) -> bool:
        """토큰 블랙리스트 확인"""
        try:
            return bool(self.redis_client.get(f"blacklist:{jti}"))
        except:
            return False

    async def revoke_token(self, jti: str, expires_at: datetime):
        """토큰 취소"""
        try:
            # Redis에 블랙리스트 추가
            ttl = int((expires_at - datetime.utcnow()).total_seconds())
            if ttl > 0:
                self.redis_client.setex(f"blacklist:{jti}", ttl, "1")
                
            # 데이터베이스에도 기록
            conn = psycopg2.connect(
                host=POSTGRES_HOST,
                port=POSTGRES_PORT,
                database=POSTGRES_DB,
                user=POSTGRES_USER,
                password=POSTGRES_PASSWORD
            )
            
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO auth.token_blacklist (token_jti, expires_at)
                    VALUES (%s, %s)
                    ON CONFLICT (token_jti) DO NOTHING
                """, (jti, expires_at))
                
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"❌ 토큰 취소 실패: {str(e)}")

class AuthHandler:
    """인증 핸들러"""
    
    def __init__(self, security_manager: SecurityManager):
        self.security_manager = security_manager

    async def login(self, request):
        """로그인"""
        try:
            data = await request.json()
            username = data.get('username')
            password = data.get('password')
            mfa_token = data.get('mfa_token')
            
            if not username or not password:
                raise HTTPBadRequest(reason="Username and password required")
            
            # 클라이언트 정보
            ip_address = request.remote
            user_agent = request.headers.get('User-Agent', '')
            
            # 속도 제한 확인
            if not await self.security_manager.check_rate_limit(f"login:{ip_address}"):
                await self.security_manager.log_security_event(SecurityEvent(
                    id=None,
                    event_type=SecurityEventType.RATE_LIMIT_EXCEEDED,
                    user_id=None,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    details={"action": "login"}
                ))
                raise HTTPForbidden(reason="Rate limit exceeded")
            
            # 사용자 조회
            user = await self.security_manager.get_user_by_username(username)
            if not user:
                await self.security_manager.log_security_event(SecurityEvent(
                    id=None,
                    event_type=SecurityEventType.LOGIN_FAILURE,
                    user_id=None,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    details={"reason": "user_not_found", "username": username}
                ))
                raise HTTPUnauthorized(reason="Invalid credentials")
            
            # 계정 잠금 확인
            if user.locked_until and user.locked_until > datetime.utcnow():
                await self.security_manager.log_security_event(SecurityEvent(
                    id=None,
                    event_type=SecurityEventType.LOGIN_FAILURE,
                    user_id=user.id,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    details={"reason": "account_locked"}
                ))
                raise HTTPForbidden(reason="Account locked")
            
            # 비밀번호 검증
            if not self.security_manager.verify_password(password, user.password_hash):
                await self.security_manager.log_security_event(SecurityEvent(
                    id=None,
                    event_type=SecurityEventType.LOGIN_FAILURE,
                    user_id=user.id,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    details={"reason": "invalid_password"}
                ))
                raise HTTPUnauthorized(reason="Invalid credentials")
            
            # MFA 확인
            if user.mfa_enabled:
                if not mfa_token:
                    raise HTTPBadRequest(reason="MFA token required")
                    
                if not self.security_manager.verify_mfa_token(user.mfa_secret, mfa_token):
                    await self.security_manager.log_security_event(SecurityEvent(
                        id=None,
                        event_type=SecurityEventType.LOGIN_FAILURE,
                        user_id=user.id,
                        ip_address=ip_address,
                        user_agent=user_agent,
                        details={"reason": "invalid_mfa_token"}
                    ))
                    raise HTTPUnauthorized(reason="Invalid MFA token")
            
            # 토큰 생성
            access_token = self.security_manager.generate_jwt_token(user, "access")
            refresh_token = self.security_manager.generate_jwt_token(user, "refresh")
            
            # 성공 로깅
            await self.security_manager.log_security_event(SecurityEvent(
                id=None,
                event_type=SecurityEventType.LOGIN_SUCCESS,
                user_id=user.id,
                ip_address=ip_address,
                user_agent=user_agent,
                details={"method": "password"}
            ))
            
            return web.json_response({
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer",
                "expires_in": JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "role": user.role.value,
                    "mfa_enabled": user.mfa_enabled
                }
            })
            
        except web.HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ 로그인 처리 실패: {str(e)}")
            raise web.HTTPInternalServerError(reason="Internal server error")

    async def refresh_token(self, request):
        """토큰 갱신"""
        try:
            data = await request.json()
            refresh_token = data.get('refresh_token')
            
            if not refresh_token:
                raise HTTPBadRequest(reason="Refresh token required")
            
            # 토큰 검증
            payload = self.security_manager.verify_jwt_token(refresh_token)
            
            if payload.get('type') != 'refresh':
                raise HTTPUnauthorized(reason="Invalid token type")
            
            # 사용자 조회
            user = await self.security_manager.get_user_by_username(payload.get('username'))
            if not user or not user.is_active:
                raise HTTPUnauthorized(reason="User not found or inactive")
            
            # 새 토큰 생성
            new_access_token = self.security_manager.generate_jwt_token(user, "access")
            
            # 로깅
            await self.security_manager.log_security_event(SecurityEvent(
                id=None,
                event_type=SecurityEventType.TOKEN_REFRESHED,
                user_id=user.id,
                ip_address=request.remote,
                user_agent=request.headers.get('User-Agent', ''),
                details={}
            ))
            
            return web.json_response({
                "access_token": new_access_token,
                "token_type": "bearer",
                "expires_in": JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
            })
            
        except web.HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ 토큰 갱신 실패: {str(e)}")
            raise web.HTTPInternalServerError(reason="Internal server error")

    async def logout(self, request):
        """로그아웃"""
        try:
            # Authorization 헤더에서 토큰 추출
            auth_header = request.headers.get('Authorization', '')
            if not auth_header.startswith('Bearer '):
                raise HTTPBadRequest(reason="Invalid authorization header")
            
            token = auth_header[7:]  # "Bearer " 제거
            payload = self.security_manager.verify_jwt_token(token)
            
            # 토큰 취소
            exp_timestamp = payload.get('exp')
            if exp_timestamp:
                expires_at = datetime.utcfromtimestamp(exp_timestamp)
                await self.security_manager.revoke_token(payload.get('jti'), expires_at)
            
            # 로깅
            await self.security_manager.log_security_event(SecurityEvent(
                id=None,
                event_type=SecurityEventType.TOKEN_REVOKED,
                user_id=int(payload.get('sub')),
                ip_address=request.remote,
                user_agent=request.headers.get('User-Agent', ''),
                details={"reason": "logout"}
            ))
            
            return web.json_response({"message": "Successfully logged out"})
            
        except web.HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ 로그아웃 처리 실패: {str(e)}")
            raise web.HTTPInternalServerError(reason="Internal server error")

# 미들웨어
async def auth_middleware(request, handler):
    """인증 미들웨어"""
    # 인증이 필요 없는 경로
    public_paths = ['/auth/login', '/auth/refresh', '/health', '/docs']
    
    if request.path in public_paths or request.path.startswith('/auth/'):
        return await handler(request)
    
    # Authorization 헤더 확인
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        raise HTTPUnauthorized(reason="Missing or invalid authorization header")
    
    token = auth_header[7:]  # "Bearer " 제거
    
    try:
        security_manager = request.app['security_manager']
        payload = security_manager.verify_jwt_token(token)
        
        # 요청에 사용자 정보 추가
        request['user'] = {
            'id': int(payload.get('sub')),
            'username': payload.get('username'),
            'role': payload.get('role')
        }
        
        return await handler(request)
        
    except Exception as e:
        logger.error(f"❌ 인증 미들웨어 오류: {str(e)}")
        raise HTTPUnauthorized(reason="Invalid token")

async def create_app():
    """애플리케이션 생성"""
    app = web.Application(middlewares=[auth_middleware])
    
    # 보안 관리자 초기화
    security_manager = SecurityManager()
    await security_manager.initialize()
    app['security_manager'] = security_manager
    
    # 인증 핸들러
    auth_handler = AuthHandler(security_manager)
    
    # 라우트 설정
    app.router.add_post('/auth/login', auth_handler.login)
    app.router.add_post('/auth/refresh', auth_handler.refresh_token)
    app.router.add_post('/auth/logout', auth_handler.logout)
    
    # 헬스체크
    async def health_check(request):
        return web.json_response({"status": "healthy", "service": "auth-server"})
    
    app.router.add_get('/health', health_check)
    
    return app

async def main():
    """메인 실행 함수"""
    app = await create_app()
    
    # 서버 시작
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8001)
    
    logger.info("🔐 HankookTire OAuth2 Authentication Server 시작 - Port 8001")
    await site.start()
    
    try:
        await asyncio.Future()  # 무한 대기
    except KeyboardInterrupt:
        logger.info("👋 인증 서버 종료 중...")
    finally:
        await runner.cleanup()

if __name__ == "__main__":
    asyncio.run(main())