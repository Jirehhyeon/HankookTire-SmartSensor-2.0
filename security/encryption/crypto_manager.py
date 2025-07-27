#!/usr/bin/env python3
"""
HankookTire SmartSensor 2.0 - Cryptographic Manager
차세대 통합 스마트 타이어 센서 시스템 암호화 관리자

데이터 암호화 및 보안 통신 관리
- AES-256 데이터 암호화
- RSA 키 교환
- TLS/SSL 인증서 관리
- 하드웨어 보안 모듈 (HSM) 연동
- 키 순환 및 관리
- 디지털 서명 및 검증
"""

import asyncio
import os
import secrets
import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Union
from dataclasses import dataclass, asdict
from enum import Enum
import base64
import hmac

# 암호화 라이브러리
from cryptography.hazmat.primitives import hashes, serialization, padding
from cryptography.hazmat.primitives.asymmetric import rsa, padding as asym_padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from cryptography.hazmat.backends import default_backend
from cryptography.x509 import load_pem_x509_certificate, CertificateBuilder, Name, NameAttribute
from cryptography.x509.oid import NameOID, ExtensionOID
from cryptography import x509
import psycopg2
from psycopg2.extras import RealDictCursor
import redis

# 설정
POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'postgres-service')
POSTGRES_PORT = int(os.getenv('POSTGRES_PORT', '5432'))
POSTGRES_DB = os.getenv('POSTGRES_DB', 'smarttire_sensors')
POSTGRES_USER = os.getenv('POSTGRES_USER', 'smarttire')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'password')

REDIS_HOST = os.getenv('REDIS_HOST', 'redis-service')
REDIS_PORT = int(os.getenv('REDIS_PORT', '6379'))
REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', '')

# 암호화 설정
MASTER_KEY = os.getenv('MASTER_KEY', secrets.token_hex(32))
KEY_ROTATION_DAYS = int(os.getenv('KEY_ROTATION_DAYS', '90'))
HSM_ENABLED = os.getenv('HSM_ENABLED', 'false').lower() == 'true'

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class KeyType(Enum):
    """키 타입"""
    MASTER_KEY = "master_key"
    DATA_ENCRYPTION_KEY = "data_encryption_key"
    KEY_ENCRYPTION_KEY = "key_encryption_key"
    SIGNING_KEY = "signing_key"
    TLS_CERTIFICATE = "tls_certificate"
    DEVICE_CERTIFICATE = "device_certificate"

class EncryptionAlgorithm(Enum):
    """암호화 알고리즘"""
    AES_256_GCM = "aes_256_gcm"
    AES_256_CBC = "aes_256_cbc"
    RSA_2048 = "rsa_2048"
    RSA_4096 = "rsa_4096"
    ECDSA_P256 = "ecdsa_p256"
    ECDSA_P384 = "ecdsa_p384"

class KeyStatus(Enum):
    """키 상태"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    EXPIRED = "expired"
    REVOKED = "revoked"
    PENDING_ROTATION = "pending_rotation"

@dataclass
class CryptoKey:
    """암호화 키 모델"""
    id: Optional[int]
    key_id: str
    key_type: KeyType
    algorithm: EncryptionAlgorithm
    key_data: bytes
    iv: Optional[bytes]
    status: KeyStatus
    created_at: datetime
    expires_at: Optional[datetime]
    rotated_from: Optional[str]
    metadata: Dict = None

@dataclass
class EncryptedData:
    """암호화된 데이터"""
    ciphertext: bytes
    iv: bytes
    tag: Optional[bytes]
    key_id: str
    algorithm: EncryptionAlgorithm
    timestamp: datetime

@dataclass
class DigitalSignature:
    """디지털 서명"""
    signature: bytes
    algorithm: str
    key_id: str
    timestamp: datetime

class CryptoManager:
    """암호화 관리자"""
    
    def __init__(self):
        self.redis_client = None
        self.master_key = MASTER_KEY.encode() if isinstance(MASTER_KEY, str) else MASTER_KEY
        self._key_cache = {}
        
    async def initialize(self):
        """초기화"""
        # Redis 연결
        self.redis_client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            password=REDIS_PASSWORD if REDIS_PASSWORD else None,
            decode_responses=False  # 바이너리 데이터 처리
        )
        
        # 테이블 생성
        await self.create_crypto_tables()
        
        # 마스터 키 검증
        await self.verify_master_key()
        
        # 기본 키 생성
        await self.initialize_default_keys()

    async def create_crypto_tables(self):
        """암호화 관련 테이블 생성"""
        conn = psycopg2.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            database=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD
        )
        
        try:
            with conn.cursor() as cursor:
                # 암호화 키 테이블
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS security.crypto_keys (
                        id SERIAL PRIMARY KEY,
                        key_id VARCHAR(64) UNIQUE NOT NULL,
                        key_type VARCHAR(30) NOT NULL,
                        algorithm VARCHAR(20) NOT NULL,
                        key_data BYTEA NOT NULL,
                        iv BYTEA,
                        status VARCHAR(20) DEFAULT 'active',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        expires_at TIMESTAMP,
                        rotated_from VARCHAR(64),
                        metadata JSONB
                    )
                """)
                
                # 암호화 작업 로그 테이블
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS security.crypto_operations (
                        id SERIAL PRIMARY KEY,
                        operation_type VARCHAR(20) NOT NULL,
                        key_id VARCHAR(64) NOT NULL,
                        data_size INTEGER,
                        user_id INTEGER,
                        ip_address INET,
                        success BOOLEAN NOT NULL,
                        error_message TEXT,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # 인증서 테이블
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS security.certificates (
                        id SERIAL PRIMARY KEY,
                        cert_id VARCHAR(64) UNIQUE NOT NULL,
                        subject_name VARCHAR(255) NOT NULL,
                        issuer_name VARCHAR(255) NOT NULL,
                        certificate_data BYTEA NOT NULL,
                        private_key_data BYTEA,
                        serial_number VARCHAR(64),
                        not_before TIMESTAMP NOT NULL,
                        not_after TIMESTAMP NOT NULL,
                        is_ca BOOLEAN DEFAULT FALSE,
                        status VARCHAR(20) DEFAULT 'active',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # 인덱스 생성
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_crypto_keys_key_id ON security.crypto_keys(key_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_crypto_keys_type ON security.crypto_keys(key_type)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_crypto_operations_timestamp ON security.crypto_operations(timestamp)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_certificates_cert_id ON security.certificates(cert_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_certificates_status ON security.certificates(status)")
                
            conn.commit()
            logger.info("✅ 암호화 테이블 생성 완료")
            
        except Exception as e:
            logger.error(f"❌ 암호화 테이블 생성 실패: {str(e)}")
            conn.rollback()
            raise
        finally:
            conn.close()

    async def verify_master_key(self):
        """마스터 키 검증"""
        try:
            # 테스트 데이터 암호화/복호화로 마스터 키 검증
            test_data = b"test_master_key_verification"
            encrypted = await self.encrypt_with_master_key(test_data)
            decrypted = await self.decrypt_with_master_key(encrypted.ciphertext, encrypted.iv, encrypted.tag)
            
            if decrypted != test_data:
                raise ValueError("Master key verification failed")
                
            logger.info("✅ 마스터 키 검증 완료")
            
        except Exception as e:
            logger.error(f"❌ 마스터 키 검증 실패: {str(e)}")
            raise

    async def initialize_default_keys(self):
        """기본 키 생성"""
        try:
            # 데이터 암호화 키 (DEK) 생성
            dek_exists = await self.get_key_by_type(KeyType.DATA_ENCRYPTION_KEY)
            if not dek_exists:
                await self.generate_data_encryption_key()
                
            # 키 암호화 키 (KEK) 생성  
            kek_exists = await self.get_key_by_type(KeyType.KEY_ENCRYPTION_KEY)
            if not kek_exists:
                await self.generate_key_encryption_key()
                
            # 서명 키 생성
            signing_key_exists = await self.get_key_by_type(KeyType.SIGNING_KEY)
            if not signing_key_exists:
                await self.generate_signing_key()
                
            logger.info("✅ 기본 키 초기화 완료")
            
        except Exception as e:
            logger.error(f"❌ 기본 키 초기화 실패: {str(e)}")
            raise

    async def generate_data_encryption_key(self) -> str:
        """데이터 암호화 키 생성"""
        key_id = f"dek_{secrets.token_hex(16)}"
        key_data = os.urandom(32)  # 256비트 키
        
        # 마스터 키로 암호화
        encrypted_key = await self.encrypt_with_master_key(key_data)
        
        crypto_key = CryptoKey(
            id=None,
            key_id=key_id,
            key_type=KeyType.DATA_ENCRYPTION_KEY,
            algorithm=EncryptionAlgorithm.AES_256_GCM,
            key_data=encrypted_key.ciphertext,
            iv=encrypted_key.iv,
            status=KeyStatus.ACTIVE,
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(days=KEY_ROTATION_DAYS),
            rotated_from=None,
            metadata={"tag": base64.b64encode(encrypted_key.tag).decode() if encrypted_key.tag else None}
        )
        
        await self.store_key(crypto_key)
        logger.info(f"✅ 데이터 암호화 키 생성 완료: {key_id}")
        return key_id

    async def generate_key_encryption_key(self) -> str:
        """키 암호화 키 생성"""
        key_id = f"kek_{secrets.token_hex(16)}"
        key_data = os.urandom(32)  # 256비트 키
        
        # 마스터 키로 암호화
        encrypted_key = await self.encrypt_with_master_key(key_data)
        
        crypto_key = CryptoKey(
            id=None,
            key_id=key_id,
            key_type=KeyType.KEY_ENCRYPTION_KEY,
            algorithm=EncryptionAlgorithm.AES_256_GCM,
            key_data=encrypted_key.ciphertext,
            iv=encrypted_key.iv,
            status=KeyStatus.ACTIVE,
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(days=KEY_ROTATION_DAYS),
            rotated_from=None,
            metadata={"tag": base64.b64encode(encrypted_key.tag).decode() if encrypted_key.tag else None}
        )
        
        await self.store_key(crypto_key)
        logger.info(f"✅ 키 암호화 키 생성 완료: {key_id}")
        return key_id

    async def generate_signing_key(self) -> str:
        """서명 키 생성"""
        key_id = f"sign_{secrets.token_hex(16)}"
        
        # RSA 키 쌍 생성
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        
        # 개인키 직렬화
        private_key_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
        
        # 마스터 키로 암호화
        encrypted_key = await self.encrypt_with_master_key(private_key_bytes)
        
        # 공개키 저장을 위한 메타데이터
        public_key = private_key.public_key()
        public_key_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        
        crypto_key = CryptoKey(
            id=None,
            key_id=key_id,
            key_type=KeyType.SIGNING_KEY,
            algorithm=EncryptionAlgorithm.RSA_2048,
            key_data=encrypted_key.ciphertext,
            iv=encrypted_key.iv,
            status=KeyStatus.ACTIVE,
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(days=KEY_ROTATION_DAYS),
            rotated_from=None,
            metadata={
                "tag": base64.b64encode(encrypted_key.tag).decode() if encrypted_key.tag else None,
                "public_key": base64.b64encode(public_key_bytes).decode()
            }
        )
        
        await self.store_key(crypto_key)
        logger.info(f"✅ 서명 키 생성 완료: {key_id}")
        return key_id

    async def encrypt_with_master_key(self, data: bytes) -> EncryptedData:
        """마스터 키로 데이터 암호화"""
        iv = os.urandom(12)  # GCM 모드용 96비트 IV
        
        cipher = Cipher(
            algorithms.AES(self.master_key),
            modes.GCM(iv),
            backend=default_backend()
        )
        
        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(data) + encryptor.finalize()
        
        return EncryptedData(
            ciphertext=ciphertext,
            iv=iv,
            tag=encryptor.tag,
            key_id="master",
            algorithm=EncryptionAlgorithm.AES_256_GCM,
            timestamp=datetime.utcnow()
        )

    async def decrypt_with_master_key(self, ciphertext: bytes, iv: bytes, tag: bytes) -> bytes:
        """마스터 키로 데이터 복호화"""
        cipher = Cipher(
            algorithms.AES(self.master_key),
            modes.GCM(iv, tag),
            backend=default_backend()
        )
        
        decryptor = cipher.decryptor()
        return decryptor.update(ciphertext) + decryptor.finalize()

    async def encrypt_data(self, data: bytes, key_id: Optional[str] = None) -> EncryptedData:
        """데이터 암호화"""
        try:
            # 기본 DEK 사용
            if not key_id:
                dek = await self.get_key_by_type(KeyType.DATA_ENCRYPTION_KEY)
                if not dek:
                    key_id = await self.generate_data_encryption_key()
                    dek = await self.get_key_by_id(key_id)
                else:
                    key_id = dek.key_id
            else:
                dek = await self.get_key_by_id(key_id)
                
            if not dek:
                raise ValueError(f"Encryption key not found: {key_id}")
            
            # 키 복호화
            decrypted_key = await self.decrypt_with_master_key(
                dek.key_data,
                dek.iv,
                base64.b64decode(dek.metadata.get("tag", "")) if dek.metadata and dek.metadata.get("tag") else b""
            )
            
            # 데이터 암호화
            iv = os.urandom(12)
            cipher = Cipher(
                algorithms.AES(decrypted_key),
                modes.GCM(iv),
                backend=default_backend()
            )
            
            encryptor = cipher.encryptor()
            ciphertext = encryptor.update(data) + encryptor.finalize()
            
            # 작업 로그
            await self.log_crypto_operation("encrypt", key_id, len(data), None, None, True)
            
            return EncryptedData(
                ciphertext=ciphertext,
                iv=iv,
                tag=encryptor.tag,
                key_id=key_id,
                algorithm=dek.algorithm,
                timestamp=datetime.utcnow()
            )
            
        except Exception as e:
            await self.log_crypto_operation("encrypt", key_id or "unknown", len(data) if data else 0, None, None, False, str(e))
            logger.error(f"❌ 데이터 암호화 실패: {str(e)}")
            raise

    async def decrypt_data(self, encrypted_data: EncryptedData) -> bytes:
        """데이터 복호화"""
        try:
            # 키 조회
            dek = await self.get_key_by_id(encrypted_data.key_id)
            if not dek:
                raise ValueError(f"Decryption key not found: {encrypted_data.key_id}")
            
            # 키 복호화
            decrypted_key = await self.decrypt_with_master_key(
                dek.key_data,
                dek.iv,
                base64.b64decode(dek.metadata.get("tag", "")) if dek.metadata and dek.metadata.get("tag") else b""
            )
            
            # 데이터 복호화
            cipher = Cipher(
                algorithms.AES(decrypted_key),
                modes.GCM(encrypted_data.iv, encrypted_data.tag),
                backend=default_backend()
            )
            
            decryptor = cipher.decryptor()
            plaintext = decryptor.update(encrypted_data.ciphertext) + decryptor.finalize()
            
            # 작업 로그
            await self.log_crypto_operation("decrypt", encrypted_data.key_id, len(plaintext), None, None, True)
            
            return plaintext
            
        except Exception as e:
            await self.log_crypto_operation("decrypt", encrypted_data.key_id, 0, None, None, False, str(e))
            logger.error(f"❌ 데이터 복호화 실패: {str(e)}")
            raise

    async def sign_data(self, data: bytes, key_id: Optional[str] = None) -> DigitalSignature:
        """데이터 서명"""
        try:
            # 기본 서명 키 사용
            if not key_id:
                signing_key = await self.get_key_by_type(KeyType.SIGNING_KEY)
                if not signing_key:
                    key_id = await self.generate_signing_key()
                    signing_key = await self.get_key_by_id(key_id)
                else:
                    key_id = signing_key.key_id
            else:
                signing_key = await self.get_key_by_id(key_id)
                
            if not signing_key:
                raise ValueError(f"Signing key not found: {key_id}")
            
            # 개인키 복호화
            private_key_bytes = await self.decrypt_with_master_key(
                signing_key.key_data,
                signing_key.iv,
                base64.b64decode(signing_key.metadata.get("tag", "")) if signing_key.metadata and signing_key.metadata.get("tag") else b""
            )
            
            private_key = serialization.load_pem_private_key(
                private_key_bytes,
                password=None,
                backend=default_backend()
            )
            
            # 데이터 서명
            signature = private_key.sign(
                data,
                asym_padding.PSS(
                    mgf=asym_padding.MGF1(hashes.SHA256()),
                    salt_length=asym_padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            
            # 작업 로그
            await self.log_crypto_operation("sign", key_id, len(data), None, None, True)
            
            return DigitalSignature(
                signature=signature,
                algorithm="RSA-PSS-SHA256",
                key_id=key_id,
                timestamp=datetime.utcnow()
            )
            
        except Exception as e:
            await self.log_crypto_operation("sign", key_id or "unknown", len(data) if data else 0, None, None, False, str(e))
            logger.error(f"❌ 데이터 서명 실패: {str(e)}")
            raise

    async def verify_signature(self, data: bytes, signature: DigitalSignature) -> bool:
        """서명 검증"""
        try:
            # 서명 키 조회
            signing_key = await self.get_key_by_id(signature.key_id)
            if not signing_key:
                raise ValueError(f"Signing key not found: {signature.key_id}")
            
            # 공개키 추출
            public_key_bytes = base64.b64decode(signing_key.metadata.get("public_key", ""))
            public_key = serialization.load_pem_public_key(
                public_key_bytes,
                backend=default_backend()
            )
            
            # 서명 검증
            public_key.verify(
                signature.signature,
                data,
                asym_padding.PSS(
                    mgf=asym_padding.MGF1(hashes.SHA256()),
                    salt_length=asym_padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            
            # 작업 로그
            await self.log_crypto_operation("verify", signature.key_id, len(data), None, None, True)
            
            return True
            
        except Exception as e:
            await self.log_crypto_operation("verify", signature.key_id, len(data) if data else 0, None, None, False, str(e))
            logger.error(f"❌ 서명 검증 실패: {str(e)}")
            return False

    async def rotate_key(self, key_id: str) -> str:
        """키 순환"""
        try:
            # 기존 키 조회
            old_key = await self.get_key_by_id(key_id)
            if not old_key:
                raise ValueError(f"Key not found: {key_id}")
            
            # 새 키 생성
            if old_key.key_type == KeyType.DATA_ENCRYPTION_KEY:
                new_key_id = await self.generate_data_encryption_key()
            elif old_key.key_type == KeyType.KEY_ENCRYPTION_KEY:
                new_key_id = await self.generate_key_encryption_key()
            elif old_key.key_type == KeyType.SIGNING_KEY:
                new_key_id = await self.generate_signing_key()
            else:
                raise ValueError(f"Unsupported key type for rotation: {old_key.key_type}")
            
            # 새 키에 순환 정보 업데이트
            await self.update_key_metadata(new_key_id, {"rotated_from": key_id})
            
            # 기존 키 비활성화
            await self.update_key_status(key_id, KeyStatus.INACTIVE)
            
            logger.info(f"✅ 키 순환 완료: {key_id} → {new_key_id}")
            return new_key_id
            
        except Exception as e:
            logger.error(f"❌ 키 순환 실패: {str(e)}")
            raise

    async def store_key(self, crypto_key: CryptoKey):
        """키 저장"""
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
                    INSERT INTO security.crypto_keys 
                    (key_id, key_type, algorithm, key_data, iv, status, expires_at, rotated_from, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    crypto_key.key_id,
                    crypto_key.key_type.value,
                    crypto_key.algorithm.value,
                    crypto_key.key_data,
                    crypto_key.iv,
                    crypto_key.status.value,
                    crypto_key.expires_at,
                    crypto_key.rotated_from,
                    json.dumps(crypto_key.metadata) if crypto_key.metadata else None
                ))
                
            conn.commit()
            
        except Exception as e:
            logger.error(f"❌ 키 저장 실패: {str(e)}")
            conn.rollback()
            raise
        finally:
            conn.close()

    async def get_key_by_id(self, key_id: str) -> Optional[CryptoKey]:
        """키 ID로 키 조회"""
        # 캐시 확인
        if key_id in self._key_cache:
            return self._key_cache[key_id]
        
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
                    SELECT * FROM security.crypto_keys 
                    WHERE key_id = %s AND status = 'active'
                """, (key_id,))
                
                row = cursor.fetchone()
                
            if not row:
                return None
            
            crypto_key = CryptoKey(
                id=row['id'],
                key_id=row['key_id'],
                key_type=KeyType(row['key_type']),
                algorithm=EncryptionAlgorithm(row['algorithm']),
                key_data=bytes(row['key_data']),
                iv=bytes(row['iv']) if row['iv'] else None,
                status=KeyStatus(row['status']),
                created_at=row['created_at'],
                expires_at=row['expires_at'],
                rotated_from=row['rotated_from'],
                metadata=json.loads(row['metadata']) if row['metadata'] else None
            )
            
            # 캐시 저장
            self._key_cache[key_id] = crypto_key
            
            return crypto_key
            
        except Exception as e:
            logger.error(f"❌ 키 조회 실패: {str(e)}")
            return None
        finally:
            conn.close()

    async def get_key_by_type(self, key_type: KeyType) -> Optional[CryptoKey]:
        """키 타입으로 키 조회"""
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
                    SELECT * FROM security.crypto_keys 
                    WHERE key_type = %s AND status = 'active'
                    ORDER BY created_at DESC
                    LIMIT 1
                """, (key_type.value,))
                
                row = cursor.fetchone()
                
            if not row:
                return None
            
            return CryptoKey(
                id=row['id'],
                key_id=row['key_id'],
                key_type=KeyType(row['key_type']),
                algorithm=EncryptionAlgorithm(row['algorithm']),
                key_data=bytes(row['key_data']),
                iv=bytes(row['iv']) if row['iv'] else None,
                status=KeyStatus(row['status']),
                created_at=row['created_at'],
                expires_at=row['expires_at'],
                rotated_from=row['rotated_from'],
                metadata=json.loads(row['metadata']) if row['metadata'] else None
            )
            
        except Exception as e:
            logger.error(f"❌ 키 타입별 조회 실패: {str(e)}")
            return None
        finally:
            conn.close()

    async def update_key_status(self, key_id: str, status: KeyStatus):
        """키 상태 업데이트"""
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
                    UPDATE security.crypto_keys 
                    SET status = %s 
                    WHERE key_id = %s
                """, (status.value, key_id))
                
            conn.commit()
            
            # 캐시 무효화
            if key_id in self._key_cache:
                del self._key_cache[key_id]
                
        except Exception as e:
            logger.error(f"❌ 키 상태 업데이트 실패: {str(e)}")
            conn.rollback()
            raise
        finally:
            conn.close()

    async def update_key_metadata(self, key_id: str, metadata: Dict):
        """키 메타데이터 업데이트"""
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
                    UPDATE security.crypto_keys 
                    SET metadata = %s 
                    WHERE key_id = %s
                """, (json.dumps(metadata), key_id))
                
            conn.commit()
            
            # 캐시 무효화
            if key_id in self._key_cache:
                del self._key_cache[key_id]
                
        except Exception as e:
            logger.error(f"❌ 키 메타데이터 업데이트 실패: {str(e)}")
            conn.rollback()
            raise
        finally:
            conn.close()

    async def log_crypto_operation(self, operation_type: str, key_id: str, data_size: int, 
                                 user_id: Optional[int], ip_address: Optional[str], 
                                 success: bool, error_message: Optional[str] = None):
        """암호화 작업 로깅"""
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
                    INSERT INTO security.crypto_operations 
                    (operation_type, key_id, data_size, user_id, ip_address, success, error_message)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (operation_type, key_id, data_size, user_id, ip_address, success, error_message))
                
            conn.commit()
            
        except Exception as e:
            logger.error(f"❌ 암호화 작업 로깅 실패: {str(e)}")
        finally:
            conn.close()

    async def cleanup_expired_keys(self):
        """만료된 키 정리"""
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
                    UPDATE security.crypto_keys 
                    SET status = 'expired' 
                    WHERE expires_at < CURRENT_TIMESTAMP AND status = 'active'
                """)
                
                expired_count = cursor.rowcount
                
            conn.commit()
            
            if expired_count > 0:
                logger.info(f"✅ 만료된 키 {expired_count}개 정리 완료")
                
        except Exception as e:
            logger.error(f"❌ 만료된 키 정리 실패: {str(e)}")
            conn.rollback()
        finally:
            conn.close()

async def main():
    """테스트 실행"""
    crypto_manager = CryptoManager()
    await crypto_manager.initialize()
    
    # 테스트 데이터 암호화/복호화
    test_data = b"HankookTire SmartSensor 2.0 - Sensitive Data"
    logger.info(f"원본 데이터: {test_data}")
    
    # 암호화
    encrypted = await crypto_manager.encrypt_data(test_data)
    logger.info(f"암호화 완료: {len(encrypted.ciphertext)} bytes")
    
    # 복호화
    decrypted = await crypto_manager.decrypt_data(encrypted)
    logger.info(f"복호화 완료: {decrypted}")
    
    # 서명
    signature = await crypto_manager.sign_data(test_data)
    logger.info(f"서명 완료: {len(signature.signature)} bytes")
    
    # 서명 검증
    is_valid = await crypto_manager.verify_signature(test_data, signature)
    logger.info(f"서명 검증: {is_valid}")

if __name__ == "__main__":
    asyncio.run(main())