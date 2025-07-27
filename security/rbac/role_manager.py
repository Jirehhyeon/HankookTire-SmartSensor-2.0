#!/usr/bin/env python3
"""
HankookTire SmartSensor 2.0 - Role-Based Access Control (RBAC) Manager
차세대 통합 스마트 타이어 센서 시스템 역할 기반 접근 제어

RBAC 시스템 구현
- 세분화된 권한 관리
- 동적 역할 할당
- 리소스 레벨 접근 제어
- 권한 상속 및 위임
- 감사 로깅
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple, Union
from dataclasses import dataclass, asdict
from enum import Enum
import psycopg2
from psycopg2.extras import RealDictCursor
import redis
from functools import wraps

# 설정
POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'postgres-service')
POSTGRES_PORT = int(os.getenv('POSTGRES_PORT', '5432'))
POSTGRES_DB = os.getenv('POSTGRES_DB', 'smarttire_sensors')
POSTGRES_USER = os.getenv('POSTGRES_USER', 'smarttire')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'password')

REDIS_HOST = os.getenv('REDIS_HOST', 'redis-service')
REDIS_PORT = int(os.getenv('REDIS_PORT', '6379'))
REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', '')

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class Permission(Enum):
    """권한 정의"""
    # 센서 관련 권한
    SENSOR_READ = "sensor:read"
    SENSOR_WRITE = "sensor:write"
    SENSOR_DELETE = "sensor:delete"
    SENSOR_CONFIGURE = "sensor:configure"
    SENSOR_FIRMWARE_UPDATE = "sensor:firmware_update"
    
    # TPMS 관련 권한
    TPMS_READ = "tpms:read"
    TPMS_WRITE = "tpms:write"
    TPMS_DELETE = "tpms:delete"
    TPMS_CALIBRATE = "tpms:calibrate"
    TPMS_ALERT_MANAGE = "tpms:alert_manage"
    
    # 차량 관련 권한
    VEHICLE_READ = "vehicle:read"
    VEHICLE_WRITE = "vehicle:write"
    VEHICLE_DELETE = "vehicle:delete"
    VEHICLE_ASSIGN_SENSOR = "vehicle:assign_sensor"
    
    # 데이터 관련 권한
    DATA_READ = "data:read"
    DATA_EXPORT = "data:export"
    DATA_DELETE = "data:delete"
    DATA_ANALYTICS = "data:analytics"
    DATA_ARCHIVE = "data:archive"
    
    # 사용자 관리 권한
    USER_READ = "user:read"
    USER_WRITE = "user:write"
    USER_DELETE = "user:delete"
    USER_ROLE_ASSIGN = "user:role_assign"
    USER_PASSWORD_RESET = "user:password_reset"
    
    # 시스템 관리 권한
    SYSTEM_CONFIG = "system:config"
    SYSTEM_MONITOR = "system:monitor"
    SYSTEM_BACKUP = "system:backup"
    SYSTEM_MAINTENANCE = "system:maintenance"
    
    # API 관련 권한
    API_KEY_CREATE = "api:key_create"
    API_KEY_REVOKE = "api:key_revoke"
    API_RATE_LIMIT_BYPASS = "api:rate_limit_bypass"
    
    # 보안 권한
    SECURITY_AUDIT = "security:audit"
    SECURITY_CONFIG = "security:config"
    SECURITY_INCIDENT_MANAGE = "security:incident_manage"
    
    # 보고서 권한
    REPORT_VIEW = "report:view"
    REPORT_CREATE = "report:create"
    REPORT_SCHEDULE = "report:schedule"
    REPORT_ADMIN = "report:admin"

class ResourceType(Enum):
    """리소스 타입"""
    SENSOR = "sensor"
    TPMS = "tpms"
    VEHICLE = "vehicle"
    USER = "user"
    SYSTEM = "system"
    DATA = "data"
    REPORT = "report"
    API = "api"

class Action(Enum):
    """액션 타입"""
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    EXECUTE = "execute"
    CONFIGURE = "configure"
    EXPORT = "export"
    IMPORT = "import"

@dataclass
class Role:
    """역할 모델"""
    id: int
    name: str
    description: str
    permissions: List[Permission]
    is_system_role: bool = False
    created_at: datetime = None
    updated_at: datetime = None

@dataclass
class ResourcePermission:
    """리소스별 권한"""
    user_id: int
    resource_type: ResourceType
    resource_id: Optional[str]  # None이면 모든 리소스
    permissions: List[Permission]
    granted_by: int
    granted_at: datetime
    expires_at: Optional[datetime] = None

@dataclass
class AccessRequest:
    """접근 요청"""
    user_id: int
    resource_type: ResourceType
    resource_id: Optional[str]
    action: Action
    context: Dict = None

@dataclass
class AuditLog:
    """감사 로그"""
    id: Optional[int]
    user_id: int
    action: str
    resource_type: str
    resource_id: Optional[str]
    result: str  # allowed, denied
    reason: str
    ip_address: str
    user_agent: str
    timestamp: datetime = None

class RoleManager:
    """역할 관리자"""
    
    def __init__(self):
        self.redis_client = None
        self._permission_cache = {}
        self._role_cache = {}
        
    async def initialize(self):
        """초기화"""
        # Redis 연결
        self.redis_client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            password=REDIS_PASSWORD if REDIS_PASSWORD else None,
            decode_responses=True
        )
        
        # 테이블 생성
        await self.create_rbac_tables()
        
        # 기본 역할 생성
        await self.create_default_roles()
        
    async def create_rbac_tables(self):
        """RBAC 테이블 생성"""
        conn = psycopg2.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            database=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD
        )
        
        try:
            with conn.cursor() as cursor:
                # 역할 테이블
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS auth.roles (
                        id SERIAL PRIMARY KEY,
                        name VARCHAR(50) UNIQUE NOT NULL,
                        description TEXT,
                        permissions JSONB NOT NULL,
                        is_system_role BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # 사용자-역할 매핑 테이블
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS auth.user_roles (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER REFERENCES auth.users(id) ON DELETE CASCADE,
                        role_id INTEGER REFERENCES auth.roles(id) ON DELETE CASCADE,
                        assigned_by INTEGER REFERENCES auth.users(id),
                        assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        expires_at TIMESTAMP,
                        UNIQUE(user_id, role_id)
                    )
                """)
                
                # 리소스별 권한 테이블
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS auth.resource_permissions (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER REFERENCES auth.users(id) ON DELETE CASCADE,
                        resource_type VARCHAR(20) NOT NULL,
                        resource_id TEXT,
                        permissions JSONB NOT NULL,
                        granted_by INTEGER REFERENCES auth.users(id),
                        granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        expires_at TIMESTAMP
                    )
                """)
                
                # 접근 감사 로그 테이블
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS auth.access_audit_logs (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER REFERENCES auth.users(id),
                        action VARCHAR(50) NOT NULL,
                        resource_type VARCHAR(20) NOT NULL,
                        resource_id TEXT,
                        result VARCHAR(10) NOT NULL,
                        reason TEXT,
                        ip_address INET,
                        user_agent TEXT,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # 인덱스 생성
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_roles_user_id ON auth.user_roles(user_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_resource_permissions_user_id ON auth.resource_permissions(user_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_resource_permissions_resource ON auth.resource_permissions(resource_type, resource_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_access_audit_logs_user_id ON auth.access_audit_logs(user_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_access_audit_logs_timestamp ON auth.access_audit_logs(timestamp)")
                
            conn.commit()
            logger.info("✅ RBAC 테이블 생성 완료")
            
        except Exception as e:
            logger.error(f"❌ RBAC 테이블 생성 실패: {str(e)}")
            conn.rollback()
            raise
        finally:
            conn.close()

    async def create_default_roles(self):
        """기본 역할 생성"""
        default_roles = [
            {
                "name": "super_admin",
                "description": "시스템 최고 관리자 - 모든 권한",
                "permissions": [p.value for p in Permission],
                "is_system_role": True
            },
            {
                "name": "admin",
                "description": "시스템 관리자 - 대부분 권한",
                "permissions": [
                    Permission.SENSOR_READ.value, Permission.SENSOR_WRITE.value, Permission.SENSOR_CONFIGURE.value,
                    Permission.TPMS_READ.value, Permission.TPMS_WRITE.value, Permission.TPMS_CALIBRATE.value,
                    Permission.VEHICLE_READ.value, Permission.VEHICLE_WRITE.value, Permission.VEHICLE_ASSIGN_SENSOR.value,
                    Permission.DATA_READ.value, Permission.DATA_EXPORT.value, Permission.DATA_ANALYTICS.value,
                    Permission.USER_READ.value, Permission.USER_WRITE.value, Permission.USER_ROLE_ASSIGN.value,
                    Permission.SYSTEM_CONFIG.value, Permission.SYSTEM_MONITOR.value,
                    Permission.REPORT_VIEW.value, Permission.REPORT_CREATE.value, Permission.REPORT_SCHEDULE.value
                ],
                "is_system_role": True
            },
            {
                "name": "engineer",
                "description": "엔지니어 - 기술적 관리 권한",
                "permissions": [
                    Permission.SENSOR_READ.value, Permission.SENSOR_WRITE.value, Permission.SENSOR_CONFIGURE.value, Permission.SENSOR_FIRMWARE_UPDATE.value,
                    Permission.TPMS_READ.value, Permission.TPMS_WRITE.value, Permission.TPMS_CALIBRATE.value,
                    Permission.VEHICLE_READ.value, Permission.VEHICLE_ASSIGN_SENSOR.value,
                    Permission.DATA_READ.value, Permission.DATA_EXPORT.value, Permission.DATA_ANALYTICS.value,
                    Permission.SYSTEM_MONITOR.value,
                    Permission.REPORT_VIEW.value, Permission.REPORT_CREATE.value
                ],
                "is_system_role": True
            },
            {
                "name": "operator",
                "description": "운영자 - 일상적 운영 권한",
                "permissions": [
                    Permission.SENSOR_READ.value, Permission.SENSOR_WRITE.value,
                    Permission.TPMS_READ.value, Permission.TPMS_WRITE.value,
                    Permission.VEHICLE_READ.value, Permission.VEHICLE_WRITE.value,
                    Permission.DATA_READ.value,
                    Permission.REPORT_VIEW.value
                ],
                "is_system_role": True
            },
            {
                "name": "viewer",
                "description": "조회자 - 읽기 전용 권한",
                "permissions": [
                    Permission.SENSOR_READ.value,
                    Permission.TPMS_READ.value,
                    Permission.VEHICLE_READ.value,
                    Permission.DATA_READ.value,
                    Permission.REPORT_VIEW.value
                ],
                "is_system_role": True
            },
            {
                "name": "api_client",
                "description": "API 클라이언트 - API 접근 권한",
                "permissions": [
                    Permission.SENSOR_READ.value, Permission.SENSOR_WRITE.value,
                    Permission.TPMS_READ.value, Permission.TPMS_WRITE.value,
                    Permission.DATA_READ.value
                ],
                "is_system_role": True
            },
            {
                "name": "sensor_device",
                "description": "센서 디바이스 - 센서 데이터 전송 권한",
                "permissions": [
                    Permission.SENSOR_WRITE.value,
                    Permission.TPMS_WRITE.value
                ],
                "is_system_role": True
            }
        ]
        
        conn = psycopg2.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            database=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD
        )
        
        try:
            with conn.cursor() as cursor:
                for role_data in default_roles:
                    cursor.execute("""
                        INSERT INTO auth.roles (name, description, permissions, is_system_role)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (name) DO UPDATE SET
                            description = EXCLUDED.description,
                            permissions = EXCLUDED.permissions,
                            updated_at = CURRENT_TIMESTAMP
                    """, (
                        role_data["name"],
                        role_data["description"],
                        json.dumps(role_data["permissions"]),
                        role_data["is_system_role"]
                    ))
                    
            conn.commit()
            logger.info("✅ 기본 역할 생성 완료")
            
        except Exception as e:
            logger.error(f"❌ 기본 역할 생성 실패: {str(e)}")
            conn.rollback()
            raise
        finally:
            conn.close()

    async def get_user_permissions(self, user_id: int) -> Set[Permission]:
        """사용자의 모든 권한 조회"""
        cache_key = f"user_permissions:{user_id}"
        
        # 캐시 확인
        try:
            cached = self.redis_client.get(cache_key)
            if cached:
                permission_strings = json.loads(cached)
                return {Permission(p) for p in permission_strings}
        except:
            pass
        
        permissions = set()
        
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
                # 역할 기반 권한 조회
                cursor.execute("""
                    SELECT r.permissions
                    FROM auth.user_roles ur
                    JOIN auth.roles r ON ur.role_id = r.id
                    WHERE ur.user_id = %s 
                      AND (ur.expires_at IS NULL OR ur.expires_at > CURRENT_TIMESTAMP)
                """, (user_id,))
                
                role_permissions = cursor.fetchall()
                for row in role_permissions:
                    role_perms = json.loads(row['permissions']) if isinstance(row['permissions'], str) else row['permissions']
                    permissions.update(Permission(p) for p in role_perms)
                
                # 리소스별 직접 권한 조회
                cursor.execute("""
                    SELECT permissions
                    FROM auth.resource_permissions
                    WHERE user_id = %s 
                      AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
                """, (user_id,))
                
                resource_permissions = cursor.fetchall()
                for row in resource_permissions:
                    resource_perms = json.loads(row['permissions']) if isinstance(row['permissions'], str) else row['permissions']
                    permissions.update(Permission(p) for p in resource_perms)
            
            # 캐시 저장 (5분)
            try:
                permission_strings = [p.value for p in permissions]
                self.redis_client.setex(cache_key, 300, json.dumps(permission_strings))
            except:
                pass
            
            return permissions
            
        except Exception as e:
            logger.error(f"❌ 사용자 권한 조회 실패: {str(e)}")
            return set()
        finally:
            conn.close()

    async def check_permission(self, request: AccessRequest, ip_address: str = "", user_agent: str = "") -> bool:
        """권한 확인"""
        try:
            user_permissions = await self.get_user_permissions(request.user_id)
            
            # 권한 매핑
            required_permission = self._get_required_permission(request.resource_type, request.action)
            
            has_permission = required_permission in user_permissions
            
            # 감사 로그 기록
            await self.log_access_attempt(
                user_id=request.user_id,
                action=f"{request.resource_type.value}:{request.action.value}",
                resource_type=request.resource_type.value,
                resource_id=request.resource_id,
                result="allowed" if has_permission else "denied",
                reason="permission_check",
                ip_address=ip_address,
                user_agent=user_agent
            )
            
            return has_permission
            
        except Exception as e:
            logger.error(f"❌ 권한 확인 실패: {str(e)}")
            return False

    def _get_required_permission(self, resource_type: ResourceType, action: Action) -> Permission:
        """리소스 타입과 액션에 따른 필요 권한 반환"""
        permission_map = {
            (ResourceType.SENSOR, Action.READ): Permission.SENSOR_READ,
            (ResourceType.SENSOR, Action.CREATE): Permission.SENSOR_WRITE,
            (ResourceType.SENSOR, Action.UPDATE): Permission.SENSOR_WRITE,
            (ResourceType.SENSOR, Action.DELETE): Permission.SENSOR_DELETE,
            (ResourceType.SENSOR, Action.CONFIGURE): Permission.SENSOR_CONFIGURE,
            
            (ResourceType.TPMS, Action.READ): Permission.TPMS_READ,
            (ResourceType.TPMS, Action.CREATE): Permission.TPMS_WRITE,
            (ResourceType.TPMS, Action.UPDATE): Permission.TPMS_WRITE,
            (ResourceType.TPMS, Action.DELETE): Permission.TPMS_DELETE,
            
            (ResourceType.VEHICLE, Action.READ): Permission.VEHICLE_READ,
            (ResourceType.VEHICLE, Action.CREATE): Permission.VEHICLE_WRITE,
            (ResourceType.VEHICLE, Action.UPDATE): Permission.VEHICLE_WRITE,
            (ResourceType.VEHICLE, Action.DELETE): Permission.VEHICLE_DELETE,
            
            (ResourceType.DATA, Action.READ): Permission.DATA_READ,
            (ResourceType.DATA, Action.EXPORT): Permission.DATA_EXPORT,
            (ResourceType.DATA, Action.DELETE): Permission.DATA_DELETE,
            
            (ResourceType.USER, Action.READ): Permission.USER_READ,
            (ResourceType.USER, Action.CREATE): Permission.USER_WRITE,
            (ResourceType.USER, Action.UPDATE): Permission.USER_WRITE,
            (ResourceType.USER, Action.DELETE): Permission.USER_DELETE,
            
            (ResourceType.SYSTEM, Action.READ): Permission.SYSTEM_MONITOR,
            (ResourceType.SYSTEM, Action.CONFIGURE): Permission.SYSTEM_CONFIG,
            
            (ResourceType.REPORT, Action.READ): Permission.REPORT_VIEW,
            (ResourceType.REPORT, Action.CREATE): Permission.REPORT_CREATE,
        }
        
        return permission_map.get((resource_type, action), Permission.SENSOR_READ)

    async def assign_role_to_user(self, user_id: int, role_name: str, assigned_by: int, expires_at: Optional[datetime] = None):
        """사용자에게 역할 할당"""
        conn = psycopg2.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            database=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD
        )
        
        try:
            with conn.cursor() as cursor:
                # 역할 ID 조회
                cursor.execute("SELECT id FROM auth.roles WHERE name = %s", (role_name,))
                role_result = cursor.fetchone()
                
                if not role_result:
                    raise ValueError(f"Role not found: {role_name}")
                
                role_id = role_result[0]
                
                # 역할 할당
                cursor.execute("""
                    INSERT INTO auth.user_roles (user_id, role_id, assigned_by, expires_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (user_id, role_id) DO UPDATE SET
                        assigned_by = EXCLUDED.assigned_by,
                        assigned_at = CURRENT_TIMESTAMP,
                        expires_at = EXCLUDED.expires_at
                """, (user_id, role_id, assigned_by, expires_at))
                
            conn.commit()
            
            # 캐시 무효화
            try:
                self.redis_client.delete(f"user_permissions:{user_id}")
            except:
                pass
            
            logger.info(f"✅ 역할 할당 완료: 사용자 {user_id}에게 {role_name} 역할 할당")
            
        except Exception as e:
            logger.error(f"❌ 역할 할당 실패: {str(e)}")
            conn.rollback()
            raise
        finally:
            conn.close()

    async def revoke_role_from_user(self, user_id: int, role_name: str):
        """사용자에서 역할 제거"""
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
                    DELETE FROM auth.user_roles
                    WHERE user_id = %s 
                      AND role_id = (SELECT id FROM auth.roles WHERE name = %s)
                """, (user_id, role_name))
                
            conn.commit()
            
            # 캐시 무효화
            try:
                self.redis_client.delete(f"user_permissions:{user_id}")
            except:
                pass
            
            logger.info(f"✅ 역할 제거 완료: 사용자 {user_id}에서 {role_name} 역할 제거")
            
        except Exception as e:
            logger.error(f"❌ 역할 제거 실패: {str(e)}")
            conn.rollback()
            raise
        finally:
            conn.close()

    async def grant_resource_permission(self, user_id: int, resource_type: ResourceType, resource_id: Optional[str], 
                                      permissions: List[Permission], granted_by: int, expires_at: Optional[datetime] = None):
        """리소스별 권한 부여"""
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
                    INSERT INTO auth.resource_permissions 
                    (user_id, resource_type, resource_id, permissions, granted_by, expires_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    user_id,
                    resource_type.value,
                    resource_id,
                    json.dumps([p.value for p in permissions]),
                    granted_by,
                    expires_at
                ))
                
            conn.commit()
            
            # 캐시 무효화
            try:
                self.redis_client.delete(f"user_permissions:{user_id}")
            except:
                pass
            
            logger.info(f"✅ 리소스 권한 부여 완료: 사용자 {user_id}")
            
        except Exception as e:
            logger.error(f"❌ 리소스 권한 부여 실패: {str(e)}")
            conn.rollback()
            raise
        finally:
            conn.close()

    async def log_access_attempt(self, user_id: int, action: str, resource_type: str, resource_id: Optional[str],
                               result: str, reason: str, ip_address: str, user_agent: str):
        """접근 시도 로깅"""
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
                    INSERT INTO auth.access_audit_logs 
                    (user_id, action, resource_type, resource_id, result, reason, ip_address, user_agent)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (user_id, action, resource_type, resource_id, result, reason, ip_address, user_agent))
                
            conn.commit()
            
        except Exception as e:
            logger.error(f"❌ 접근 로그 기록 실패: {str(e)}")
        finally:
            conn.close()

# 데코레이터
def require_permission(resource_type: ResourceType, action: Action):
    """권한 확인 데코레이터"""
    def decorator(func):
        @wraps(func)
        async def wrapper(request, *args, **kwargs):
            if 'user' not in request:
                raise web.HTTPUnauthorized(reason="Authentication required")
            
            user = request['user']
            role_manager = request.app.get('role_manager')
            
            if not role_manager:
                raise web.HTTPInternalServerError(reason="Role manager not available")
            
            # 리소스 ID 추출 (URL 파라미터에서)
            resource_id = request.match_info.get('id') or request.query.get('id')
            
            access_request = AccessRequest(
                user_id=user['id'],
                resource_type=resource_type,
                resource_id=resource_id,
                action=action,
                context={"endpoint": request.path}
            )
            
            has_permission = await role_manager.check_permission(
                access_request,
                ip_address=request.remote,
                user_agent=request.headers.get('User-Agent', '')
            )
            
            if not has_permission:
                raise web.HTTPForbidden(reason="Insufficient permissions")
            
            return await func(request, *args, **kwargs)
        return wrapper
    return decorator

def require_role(*required_roles):
    """역할 확인 데코레이터"""
    def decorator(func):
        @wraps(func)
        async def wrapper(request, *args, **kwargs):
            if 'user' not in request:
                raise web.HTTPUnauthorized(reason="Authentication required")
            
            user = request['user']
            user_role = user.get('role')
            
            if user_role not in required_roles:
                raise web.HTTPForbidden(reason="Insufficient role")
            
            return await func(request, *args, **kwargs)
        return wrapper
    return decorator

async def main():
    """테스트 실행"""
    role_manager = RoleManager()
    await role_manager.initialize()
    
    # 테스트 사용자에게 역할 할당
    await role_manager.assign_role_to_user(1, "admin", 1)
    
    # 권한 확인
    request = AccessRequest(
        user_id=1,
        resource_type=ResourceType.SENSOR,
        resource_id="sensor_001",
        action=Action.READ
    )
    
    has_permission = await role_manager.check_permission(request)
    logger.info(f"권한 확인 결과: {has_permission}")

if __name__ == "__main__":
    asyncio.run(main())