#!/usr/bin/env python3
"""
HankookTire SmartSensor 2.0 - AI-Powered Anomaly Detection System
차세대 AI 기반 이상 탐지 및 예측 분석 시스템

Advanced anomaly detection using multiple ML algorithms:
- Isolation Forest for outlier detection
- LSTM for time series anomaly detection
- Statistical analysis for sensor data validation
- Real-time prediction and alerting
"""

import asyncio
import numpy as np
import pandas as pd
import logging
import json
import os
import pickle
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from enum import Enum
import warnings
warnings.filterwarnings('ignore')

# ML/AI Libraries
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler, MinMaxScaler
from sklearn.cluster import DBSCAN
from sklearn.metrics import classification_report
import tensorflow as tf
from tensorflow.keras.models import Sequential, load_model
from tensorflow.keras.layers import LSTM, Dense, Dropout, Bidirectional
from tensorflow.keras.optimizers import Adam
from tensorflow.keras.callbacks import EarlyStopping, ModelCheckpoint
import joblib

# Data Processing
import psycopg2
from psycopg2.extras import RealDictCursor
import redis
import aiohttp
from scipy import stats
from scipy.signal import savgol_filter

# Configuration
DATABASE_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'postgres-service'),
    'port': int(os.getenv('POSTGRES_PORT', '5432')),
    'database': os.getenv('POSTGRES_DB', 'smarttire_sensors'),
    'user': os.getenv('POSTGRES_USER', 'smarttire'),
    'password': os.getenv('POSTGRES_PASSWORD', 'password')
}

REDIS_CONFIG = {
    'host': os.getenv('REDIS_HOST', 'redis-service'),
    'port': int(os.getenv('REDIS_PORT', '6379')),
    'password': os.getenv('REDIS_PASSWORD', '')
}

API_BASE_URL = os.getenv('API_BASE_URL', 'http://api-service:8000')
MODEL_PATH = os.getenv('MODEL_PATH', '/app/models')
ALERT_WEBHOOK = os.getenv('ALERT_WEBHOOK', '')

# Logging Setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/anomaly-detector.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class AnomalyType(Enum):
    """이상 탐지 유형"""
    SENSOR_MALFUNCTION = "sensor_malfunction"
    TEMPERATURE_ANOMALY = "temperature_anomaly"
    PRESSURE_ANOMALY = "pressure_anomaly"
    BATTERY_DEGRADATION = "battery_degradation"
    COMMUNICATION_ISSUE = "communication_issue"
    DATA_QUALITY_DROP = "data_quality_drop"
    PREDICTIVE_MAINTENANCE = "predictive_maintenance"
    SECURITY_BREACH = "security_breach"

class SeverityLevel(Enum):
    """심각도 레벨"""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4
    EMERGENCY = 5

@dataclass
class AnomalyResult:
    """이상 탐지 결과"""
    device_id: str
    anomaly_type: AnomalyType
    severity: SeverityLevel
    confidence_score: float
    predicted_value: float
    actual_value: float
    threshold: float
    timestamp: datetime
    description: str
    recommendation: str
    model_used: str
    feature_importance: Dict[str, float] = None
    location: str = None
    maintenance_window: int = None  # 예상 유지보수 필요 시간 (시간 단위)

class AdvancedAnomalyDetector:
    """고급 AI 기반 이상 탐지 시스템"""
    
    def __init__(self):
        self.models = {}
        self.scalers = {}
        self.redis_client = None
        self.session = None
        self.model_metrics = {}
        
        # 모델 설정
        self.isolation_forest_params = {
            'contamination': 0.1,
            'random_state': 42,
            'n_estimators': 100
        }
        
        self.lstm_params = {
            'sequence_length': 60,  # 1시간 데이터 (1분 간격)
            'features': ['temperature', 'humidity', 'pressure', 'battery_voltage', 'signal_strength'],
            'epochs': 100,
            'batch_size': 32
        }
        
        self.dbscan_params = {
            'eps': 0.5,
            'min_samples': 5
        }

    async def __aenter__(self):
        """비동기 컨텍스트 관리자 진입"""
        # Redis 연결
        self.redis_client = redis.Redis(
            host=REDIS_CONFIG['host'],
            port=REDIS_CONFIG['port'],
            password=REDIS_CONFIG['password'] if REDIS_CONFIG['password'] else None,
            decode_responses=True
        )
        
        # HTTP 세션
        timeout = aiohttp.ClientTimeout(total=30)
        self.session = aiohttp.ClientSession(timeout=timeout)
        
        # 모델 로드
        await self.load_models()
        
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """비동기 컨텍스트 관리자 종료"""
        if self.session:
            await self.session.close()

    async def load_models(self):
        """저장된 모델 로드"""
        logger.info("🤖 AI 모델 로딩 중...")
        
        try:
            # Isolation Forest 모델
            isolation_forest_path = f"{MODEL_PATH}/isolation_forest.joblib"
            if os.path.exists(isolation_forest_path):
                self.models['isolation_forest'] = joblib.load(isolation_forest_path)
                logger.info("✅ Isolation Forest 모델 로드 완료")
            else:
                logger.info("🔄 Isolation Forest 모델 없음 - 새로 훈련합니다")
                await self.train_isolation_forest()
            
            # LSTM 모델
            lstm_model_path = f"{MODEL_PATH}/lstm_anomaly_detector.h5"
            if os.path.exists(lstm_model_path):
                self.models['lstm'] = load_model(lstm_model_path)
                logger.info("✅ LSTM 모델 로드 완료")
            else:
                logger.info("🔄 LSTM 모델 없음 - 새로 훈련합니다")
                await self.train_lstm_model()
            
            # 스케일러 로드
            scaler_path = f"{MODEL_PATH}/scaler.joblib"
            if os.path.exists(scaler_path):
                self.scalers['standard'] = joblib.load(scaler_path)
                logger.info("✅ 스케일러 로드 완료")
            else:
                self.scalers['standard'] = StandardScaler()
                logger.info("🔄 새 스케일러 생성")
                
        except Exception as e:
            logger.error(f"❌ 모델 로딩 실패: {str(e)}")
            # 기본 모델 생성
            await self.create_default_models()

    async def create_default_models(self):
        """기본 모델 생성"""
        logger.info("🔧 기본 모델 생성 중...")
        
        # 기본 Isolation Forest
        self.models['isolation_forest'] = IsolationForest(**self.isolation_forest_params)
        
        # 기본 LSTM 모델
        self.models['lstm'] = self.build_lstm_model()
        
        # 기본 스케일러
        self.scalers['standard'] = StandardScaler()
        self.scalers['minmax'] = MinMaxScaler()

    def build_lstm_model(self, input_shape=(60, 5)) -> tf.keras.Model:
        """LSTM 모델 구조 정의"""
        model = Sequential([
            Bidirectional(LSTM(64, return_sequences=True), input_shape=input_shape),
            Dropout(0.2),
            Bidirectional(LSTM(32, return_sequences=True)),
            Dropout(0.2),
            LSTM(16),
            Dropout(0.1),
            Dense(8, activation='relu'),
            Dense(1, activation='linear')  # 이상 스코어 출력
        ])
        
        model.compile(
            optimizer=Adam(learning_rate=0.001),
            loss='mse',
            metrics=['mae']
        )
        
        return model

    async def get_sensor_data(self, hours_back: int = 24) -> pd.DataFrame:
        """센서 데이터 조회"""
        try:
            conn = psycopg2.connect(**DATABASE_CONFIG)
            
            query = """
            SELECT 
                sr.device_id,
                sr.timestamp,
                sr.temperature,
                sr.humidity,
                sr.pressure,
                sr.battery_voltage,
                sr.signal_strength,
                sr.acceleration_x,
                sr.acceleration_y,
                sr.acceleration_z,
                sr.quality_score,
                d.location_info,
                d.device_type,
                d.firmware_version
            FROM sensors.sensor_readings sr
            JOIN sensors.devices d ON sr.device_id = d.device_id
            WHERE sr.timestamp >= NOW() - INTERVAL %s
            ORDER BY sr.device_id, sr.timestamp
            """
            
            df = pd.read_sql_query(query, conn, params=(f'{hours_back} hours',))
            conn.close()
            
            # 데이터 전처리
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df.sort_values(['device_id', 'timestamp'])
            
            # 파생 변수 생성
            df['acceleration_magnitude'] = np.sqrt(
                df['acceleration_x']**2 + 
                df['acceleration_y']**2 + 
                df['acceleration_z']**2
            )
            
            # 시간 기반 특성
            df['hour'] = df['timestamp'].dt.hour
            df['day_of_week'] = df['timestamp'].dt.dayofweek
            
            logger.info(f"📊 센서 데이터 로드 완료: {len(df)} 레코드")
            return df
            
        except Exception as e:
            logger.error(f"❌ 센서 데이터 조회 실패: {str(e)}")
            return pd.DataFrame()

    async def train_isolation_forest(self):
        """Isolation Forest 모델 훈련"""
        logger.info("🎯 Isolation Forest 모델 훈련 시작...")
        
        try:
            # 훈련 데이터 로드 (최근 7일간)
            df = await self.get_sensor_data(hours_back=168)
            
            if df.empty:
                logger.warning("⚠️ 훈련 데이터가 없습니다")
                return
            
            # 특성 선택
            features = ['temperature', 'humidity', 'pressure', 'battery_voltage', 
                       'signal_strength', 'acceleration_magnitude', 'quality_score']
            
            # 결측값 처리
            df_clean = df[features].fillna(df[features].median())
            
            # 이상값 제거 (3-sigma rule)
            df_clean = df_clean[(np.abs(stats.zscore(df_clean)) < 3).all(axis=1)]
            
            # 스케일링
            X_scaled = self.scalers['standard'].fit_transform(df_clean)
            
            # 모델 훈련
            self.models['isolation_forest'].fit(X_scaled)
            
            # 모델 저장
            os.makedirs(MODEL_PATH, exist_ok=True)
            joblib.dump(self.models['isolation_forest'], f"{MODEL_PATH}/isolation_forest.joblib")
            joblib.dump(self.scalers['standard'], f"{MODEL_PATH}/scaler.joblib")
            
            # 성능 평가
            anomaly_scores = self.models['isolation_forest'].decision_function(X_scaled)
            threshold = np.percentile(anomaly_scores, 10)  # 하위 10%를 이상으로 간주
            
            self.model_metrics['isolation_forest'] = {
                'threshold': threshold,
                'training_samples': len(X_scaled),
                'contamination_rate': self.isolation_forest_params['contamination'],
                'last_trained': datetime.now().isoformat()
            }
            
            logger.info(f"✅ Isolation Forest 훈련 완료 - 샘플: {len(X_scaled)}, 임계값: {threshold:.4f}")
            
        except Exception as e:
            logger.error(f"❌ Isolation Forest 훈련 실패: {str(e)}")

    async def train_lstm_model(self):
        """LSTM 시계열 이상 탐지 모델 훈련"""
        logger.info("🧠 LSTM 모델 훈련 시작...")
        
        try:
            # 훈련 데이터 로드 (최근 30일간)
            df = await self.get_sensor_data(hours_back=720)
            
            if len(df) < 1000:
                logger.warning("⚠️ LSTM 훈련에 충분한 데이터가 없습니다")
                return
            
            # 디바이스별로 시퀀스 생성
            sequences = []
            targets = []
            
            for device_id in df['device_id'].unique():
                device_data = df[df['device_id'] == device_id].sort_values('timestamp')
                
                if len(device_data) < self.lstm_params['sequence_length']:
                    continue
                
                # 특성 선택 및 정규화
                features = device_data[self.lstm_params['features']].fillna(method='ffill')
                features_scaled = self.scalers['minmax'].fit_transform(features)
                
                # 시퀀스 생성
                for i in range(len(features_scaled) - self.lstm_params['sequence_length']):
                    sequences.append(features_scaled[i:i+self.lstm_params['sequence_length']])
                    
                    # 다음 값 예측을 위한 타겟 (온도 기준)
                    targets.append(features_scaled[i+self.lstm_params['sequence_length'], 0])
            
            if len(sequences) == 0:
                logger.warning("⚠️ 생성된 시퀀스가 없습니다")
                return
            
            X = np.array(sequences)
            y = np.array(targets)
            
            # 훈련/검증 데이터 분할
            split_idx = int(len(X) * 0.8)
            X_train, X_val = X[:split_idx], X[split_idx:]
            y_train, y_val = y[:split_idx], y[split_idx:]
            
            # 모델 훈련
            callbacks = [
                EarlyStopping(patience=10, restore_best_weights=True),
                ModelCheckpoint(f"{MODEL_PATH}/lstm_anomaly_detector.h5", save_best_only=True)
            ]
            
            history = self.models['lstm'].fit(
                X_train, y_train,
                validation_data=(X_val, y_val),
                epochs=self.lstm_params['epochs'],
                batch_size=self.lstm_params['batch_size'],
                callbacks=callbacks,
                verbose=1
            )
            
            # 성능 평가
            val_loss = min(history.history['val_loss'])
            val_mae = min(history.history['val_mae'])
            
            self.model_metrics['lstm'] = {
                'val_loss': val_loss,
                'val_mae': val_mae,
                'training_samples': len(X_train),
                'validation_samples': len(X_val),
                'epochs_trained': len(history.history['loss']),
                'last_trained': datetime.now().isoformat()
            }
            
            logger.info(f"✅ LSTM 모델 훈련 완료 - Val Loss: {val_loss:.4f}, Val MAE: {val_mae:.4f}")
            
        except Exception as e:
            logger.error(f"❌ LSTM 모델 훈련 실패: {str(e)}")

    async def detect_isolation_forest_anomalies(self, df: pd.DataFrame) -> List[AnomalyResult]:
        """Isolation Forest를 이용한 이상 탐지"""
        results = []
        
        if 'isolation_forest' not in self.models:
            return results
        
        try:
            features = ['temperature', 'humidity', 'pressure', 'battery_voltage', 
                       'signal_strength', 'acceleration_magnitude', 'quality_score']
            
            for device_id in df['device_id'].unique():
                device_data = df[df['device_id'] == device_id].copy()
                
                if len(device_data) < 5:  # 최소 데이터 요구사항
                    continue
                
                # 특성 추출 및 전처리
                X = device_data[features].fillna(device_data[features].median())
                X_scaled = self.scalers['standard'].transform(X)
                
                # 이상 탐지
                anomaly_scores = self.models['isolation_forest'].decision_function(X_scaled)
                anomaly_predictions = self.models['isolation_forest'].predict(X_scaled)
                
                # 이상치 분석
                anomaly_indices = np.where(anomaly_predictions == -1)[0]
                
                for idx in anomaly_indices:
                    row = device_data.iloc[idx]
                    score = anomaly_scores[idx]
                    
                    # 심각도 평가
                    if score < -0.5:
                        severity = SeverityLevel.CRITICAL
                    elif score < -0.3:
                        severity = SeverityLevel.HIGH
                    elif score < -0.1:
                        severity = SeverityLevel.MEDIUM
                    else:
                        severity = SeverityLevel.LOW
                    
                    # 이상 유형 분류
                    anomaly_type = self.classify_anomaly_type(row, features, X.iloc[idx])
                    
                    # 특성 중요도 계산
                    feature_importance = dict(zip(features, np.abs(X_scaled[idx])))
                    
                    results.append(AnomalyResult(
                        device_id=device_id,
                        anomaly_type=anomaly_type,
                        severity=severity,
                        confidence_score=abs(score),
                        predicted_value=0.0,  # Isolation Forest는 예측값 없음
                        actual_value=score,
                        threshold=self.model_metrics.get('isolation_forest', {}).get('threshold', -0.1),
                        timestamp=row['timestamp'],
                        description=f"Isolation Forest에서 이상 패턴 감지 (점수: {score:.4f})",
                        recommendation=self.get_recommendation(anomaly_type, severity),
                        model_used="Isolation Forest",
                        feature_importance=feature_importance,
                        location=row.get('location_info', 'Unknown')
                    ))
            
            logger.info(f"🔍 Isolation Forest 이상 탐지 완료: {len(results)}개 발견")
            
        except Exception as e:
            logger.error(f"❌ Isolation Forest 이상 탐지 실패: {str(e)}")
        
        return results

    async def detect_lstm_anomalies(self, df: pd.DataFrame) -> List[AnomalyResult]:
        """LSTM 시계열 이상 탐지"""
        results = []
        
        if 'lstm' not in self.models:
            return results
        
        try:
            for device_id in df['device_id'].unique():
                device_data = df[df['device_id'] == device_id].sort_values('timestamp')
                
                if len(device_data) < self.lstm_params['sequence_length']:
                    continue
                
                # 특성 준비
                features = device_data[self.lstm_params['features']].fillna(method='ffill')
                features_scaled = self.scalers['minmax'].transform(features)
                
                # 시퀀스 생성 및 예측
                for i in range(len(features_scaled) - self.lstm_params['sequence_length']):
                    sequence = features_scaled[i:i+self.lstm_params['sequence_length']]
                    X_seq = sequence.reshape(1, self.lstm_params['sequence_length'], len(self.lstm_params['features']))
                    
                    # 예측
                    predicted = self.models['lstm'].predict(X_seq, verbose=0)[0][0]
                    actual = features_scaled[i+self.lstm_params['sequence_length'], 0]  # 온도 기준
                    
                    # 예측 오차 계산
                    error = abs(predicted - actual)
                    
                    # 이상 탐지 (임계값 기반)
                    threshold = 0.1  # 정규화된 데이터 기준
                    
                    if error > threshold:
                        row = device_data.iloc[i+self.lstm_params['sequence_length']]
                        
                        # 심각도 평가
                        if error > 0.3:
                            severity = SeverityLevel.CRITICAL
                        elif error > 0.2:
                            severity = SeverityLevel.HIGH
                        elif error > 0.15:
                            severity = SeverityLevel.MEDIUM
                        else:
                            severity = SeverityLevel.LOW
                        
                        results.append(AnomalyResult(
                            device_id=device_id,
                            anomaly_type=AnomalyType.TEMPERATURE_ANOMALY,
                            severity=severity,
                            confidence_score=min(error * 10, 1.0),  # 0-1 범위로 정규화
                            predicted_value=predicted,
                            actual_value=actual,
                            threshold=threshold,
                            timestamp=row['timestamp'],
                            description=f"LSTM 시계열 예측에서 큰 오차 감지 (오차: {error:.4f})",
                            recommendation=self.get_recommendation(AnomalyType.TEMPERATURE_ANOMALY, severity),
                            model_used="LSTM",
                            location=row.get('location_info', 'Unknown')
                        ))
            
            logger.info(f"🧠 LSTM 이상 탐지 완료: {len(results)}개 발견")
            
        except Exception as e:
            logger.error(f"❌ LSTM 이상 탐지 실패: {str(e)}")
        
        return results

    def classify_anomaly_type(self, row: pd.Series, features: List[str], feature_values: pd.Series) -> AnomalyType:
        """이상 유형 분류"""
        # 온도 이상
        if 'temperature' in features and abs(feature_values['temperature']) > 2:
            return AnomalyType.TEMPERATURE_ANOMALY
        
        # 압력 이상
        if 'pressure' in features and abs(feature_values['pressure']) > 2:
            return AnomalyType.PRESSURE_ANOMALY
        
        # 배터리 이상
        if 'battery_voltage' in features and feature_values['battery_voltage'] < -1:
            return AnomalyType.BATTERY_DEGRADATION
        
        # 통신 이상
        if 'signal_strength' in features and feature_values['signal_strength'] < -1:
            return AnomalyType.COMMUNICATION_ISSUE
        
        # 데이터 품질 이상
        if 'quality_score' in features and feature_values['quality_score'] < -1:
            return AnomalyType.DATA_QUALITY_DROP
        
        # 기본값
        return AnomalyType.SENSOR_MALFUNCTION

    def get_recommendation(self, anomaly_type: AnomalyType, severity: SeverityLevel) -> str:
        """이상 유형별 권장사항"""
        recommendations = {
            AnomalyType.SENSOR_MALFUNCTION: {
                SeverityLevel.LOW: "센서 상태 모니터링 강화",
                SeverityLevel.MEDIUM: "센서 캘리브레이션 고려",
                SeverityLevel.HIGH: "센서 점검 및 청소 필요",
                SeverityLevel.CRITICAL: "즉시 센서 교체 검토",
                SeverityLevel.EMERGENCY: "긴급 센서 교체 필요"
            },
            AnomalyType.TEMPERATURE_ANOMALY: {
                SeverityLevel.LOW: "온도 변화 추이 관찰",
                SeverityLevel.MEDIUM: "환경 요인 확인",
                SeverityLevel.HIGH: "냉각 시스템 점검",
                SeverityLevel.CRITICAL: "즉시 온도 조치 필요",
                SeverityLevel.EMERGENCY: "긴급 안전 조치 실행"
            },
            AnomalyType.PRESSURE_ANOMALY: {
                SeverityLevel.LOW: "압력 변화 모니터링",
                SeverityLevel.MEDIUM: "압력 센서 점검",
                SeverityLevel.HIGH: "압력 시스템 진단",
                SeverityLevel.CRITICAL: "즉시 압력 조정 필요",
                SeverityLevel.EMERGENCY: "안전을 위한 즉시 정지"
            },
            AnomalyType.BATTERY_DEGRADATION: {
                SeverityLevel.LOW: "배터리 사용량 모니터링",
                SeverityLevel.MEDIUM: "배터리 최적화 설정",
                SeverityLevel.HIGH: "배터리 교체 준비",
                SeverityLevel.CRITICAL: "즉시 배터리 교체",
                SeverityLevel.EMERGENCY: "긴급 전원 공급 필요"
            },
            AnomalyType.COMMUNICATION_ISSUE: {
                SeverityLevel.LOW: "신호 강도 모니터링",
                SeverityLevel.MEDIUM: "네트워크 설정 확인",
                SeverityLevel.HIGH: "통신 장비 점검",
                SeverityLevel.CRITICAL: "네트워크 인프라 진단",
                SeverityLevel.EMERGENCY: "백업 통신 수단 활성화"
            },
            AnomalyType.DATA_QUALITY_DROP: {
                SeverityLevel.LOW: "데이터 검증 강화",
                SeverityLevel.MEDIUM: "센서 캘리브레이션",
                SeverityLevel.HIGH: "데이터 파이프라인 점검",
                SeverityLevel.CRITICAL: "데이터 수집 시스템 재시작",
                SeverityLevel.EMERGENCY: "수동 데이터 수집 모드"
            }
        }
        
        return recommendations.get(anomaly_type, {}).get(
            severity, 
            "전문가 검토 필요"
        )

    async def predict_maintenance_needs(self, df: pd.DataFrame) -> List[AnomalyResult]:
        """예측 유지보수 분석"""
        results = []
        
        try:
            for device_id in df['device_id'].unique():
                device_data = df[df['device_id'] == device_id].sort_values('timestamp')
                
                if len(device_data) < 24:  # 최소 24시간 데이터
                    continue
                
                # 배터리 수명 예측
                battery_data = device_data['battery_voltage'].dropna()
                if len(battery_data) > 10:
                    # 배터리 방전 추세 분석
                    x = np.arange(len(battery_data))
                    slope, intercept, r_value, p_value, std_err = stats.linregress(x, battery_data)
                    
                    if slope < -0.001 and r_value < -0.5:  # 감소 추세
                        # 임계 전압 (3.0V)까지 남은 시간 예측
                        current_voltage = battery_data.iloc[-1]
                        if current_voltage > 3.0:
                            hours_to_critical = (current_voltage - 3.0) / abs(slope)
                            
                            if hours_to_critical < 168:  # 1주일 미만
                                severity = SeverityLevel.HIGH if hours_to_critical < 48 else SeverityLevel.MEDIUM
                                
                                results.append(AnomalyResult(
                                    device_id=device_id,
                                    anomaly_type=AnomalyType.PREDICTIVE_MAINTENANCE,
                                    severity=severity,
                                    confidence_score=abs(r_value),
                                    predicted_value=3.0,
                                    actual_value=current_voltage,
                                    threshold=3.2,
                                    timestamp=device_data['timestamp'].iloc[-1],
                                    description=f"배터리 교체 필요 예상: {hours_to_critical:.0f}시간 후",
                                    recommendation=f"예방적 배터리 교체 계획 수립 ({hours_to_critical:.0f}시간 내)",
                                    model_used="Linear Regression",
                                    location=device_data['location_info'].iloc[-1] if 'location_info' in device_data.columns else 'Unknown',
                                    maintenance_window=int(hours_to_critical)
                                ))
                
                # 센서 품질 저하 예측
                quality_data = device_data['quality_score'].dropna()
                if len(quality_data) > 10:
                    # 스무딩을 통한 추세 분석
                    if len(quality_data) > 20:
                        smoothed = savgol_filter(quality_data, window_length=min(11, len(quality_data)//2*2+1), polyorder=2)
                        recent_trend = np.mean(np.diff(smoothed[-10:]))
                        
                        if recent_trend < -0.5:  # 품질 저하 추세
                            results.append(AnomalyResult(
                                device_id=device_id,
                                anomaly_type=AnomalyType.PREDICTIVE_MAINTENANCE,
                                severity=SeverityLevel.MEDIUM,
                                confidence_score=0.7,
                                predicted_value=quality_data.iloc[-1] + recent_trend * 24,
                                actual_value=quality_data.iloc[-1],
                                threshold=70.0,
                                timestamp=device_data['timestamp'].iloc[-1],
                                description=f"센서 품질 저하 추세 감지 (추세: {recent_trend:.2f}/시간)",
                                recommendation="센서 캘리브레이션 및 청소 계획",
                                model_used="Trend Analysis",
                                location=device_data['location_info'].iloc[-1] if 'location_info' in device_data.columns else 'Unknown',
                                maintenance_window=48
                            ))
            
            logger.info(f"🔮 예측 유지보수 분석 완료: {len(results)}개 예측")
            
        except Exception as e:
            logger.error(f"❌ 예측 유지보수 분석 실패: {str(e)}")
        
        return results

    async def detect_security_anomalies(self, df: pd.DataFrame) -> List[AnomalyResult]:
        """보안 이상 탐지"""
        results = []
        
        try:
            # 비정상적인 접속 패턴 분석
            device_counts = df.groupby(['device_id', df['timestamp'].dt.hour]).size().reset_index(name='count')
            
            for device_id in df['device_id'].unique():
                device_hourly = device_counts[device_counts['device_id'] == device_id]
                
                if len(device_hourly) > 0:
                    # DBSCAN을 이용한 이상 패턴 탐지
                    X = device_hourly[['timestamp', 'count']].values
                    
                    if len(X) > 5:
                        clustering = DBSCAN(**self.dbscan_params).fit(X)
                        anomaly_mask = clustering.labels_ == -1
                        
                        if anomaly_mask.any():
                            anomaly_hours = device_hourly[anomaly_mask]
                            
                            for _, row in anomaly_hours.iterrows():
                                # 최근 데이터에서 해당 시간대 찾기
                                timestamp = df[
                                    (df['device_id'] == device_id) & 
                                    (df['timestamp'].dt.hour == row['timestamp'])
                                ]['timestamp'].max()
                                
                                results.append(AnomalyResult(
                                    device_id=device_id,
                                    anomaly_type=AnomalyType.SECURITY_BREACH,
                                    severity=SeverityLevel.HIGH,
                                    confidence_score=0.8,
                                    predicted_value=0,
                                    actual_value=row['count'],
                                    threshold=0,
                                    timestamp=timestamp,
                                    description=f"비정상적인 접속 패턴 감지 (시간대: {row['timestamp']}시, 횟수: {row['count']})",
                                    recommendation="보안 점검 및 접속 로그 분석 필요",
                                    model_used="DBSCAN Clustering"
                                ))
            
            logger.info(f"🔒 보안 이상 탐지 완료: {len(results)}개 발견")
            
        except Exception as e:
            logger.error(f"❌ 보안 이상 탐지 실패: {str(e)}")
        
        return results

    async def run_comprehensive_analysis(self) -> List[AnomalyResult]:
        """종합 이상 탐지 분석"""
        logger.info("🔍 종합 AI 이상 탐지 분석 시작...")
        
        all_results = []
        
        try:
            # 최근 데이터 로드
            df = await self.get_sensor_data(hours_back=24)
            
            if df.empty:
                logger.warning("⚠️ 분석할 데이터가 없습니다")
                return all_results
            
            # 각 알고리즘별 이상 탐지 실행
            detection_tasks = [
                self.detect_isolation_forest_anomalies(df),
                self.detect_lstm_anomalies(df),
                self.predict_maintenance_needs(df),
                self.detect_security_anomalies(df)
            ]
            
            results_list = await asyncio.gather(*detection_tasks, return_exceptions=True)
            
            # 결과 통합
            for results in results_list:
                if isinstance(results, list):
                    all_results.extend(results)
                elif isinstance(results, Exception):
                    logger.error(f"❌ 이상 탐지 작업 실패: {str(results)}")
            
            # 중복 제거 및 우선순위 정렬
            all_results = self.deduplicate_and_prioritize(all_results)
            
            # 결과 저장
            await self.save_anomaly_results(all_results)
            
            # 알림 전송
            await self.send_anomaly_alerts(all_results)
            
            logger.info(f"✅ 종합 이상 탐지 완료: 총 {len(all_results)}개 이상 감지")
            
        except Exception as e:
            logger.error(f"❌ 종합 이상 탐지 실패: {str(e)}")
        
        return all_results

    def deduplicate_and_prioritize(self, results: List[AnomalyResult]) -> List[AnomalyResult]:
        """중복 제거 및 우선순위 정렬"""
        # 디바이스별, 유형별로 그룹화하여 중복 제거
        unique_results = {}
        
        for result in results:
            key = f"{result.device_id}_{result.anomaly_type.value}"
            
            if key not in unique_results or result.severity.value > unique_results[key].severity.value:
                unique_results[key] = result
        
        # 심각도 및 신뢰도로 정렬
        sorted_results = sorted(
            unique_results.values(),
            key=lambda x: (x.severity.value, x.confidence_score),
            reverse=True
        )
        
        return sorted_results

    async def save_anomaly_results(self, results: List[AnomalyResult]):
        """이상 탐지 결과 저장"""
        if not results:
            return
        
        try:
            conn = psycopg2.connect(**DATABASE_CONFIG)
            cursor = conn.cursor()
            
            for result in results:
                cursor.execute("""
                INSERT INTO analytics.anomalies 
                (device_id, timestamp, anomaly_type, severity, anomaly_score, 
                 affected_sensors, description, resolved, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    result.device_id,
                    result.timestamp,
                    result.anomaly_type.value,
                    result.severity.name,
                    result.confidence_score,
                    [result.model_used],
                    result.description,
                    False,
                    datetime.now()
                ))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            logger.info(f"💾 이상 탐지 결과 저장 완료: {len(results)}건")
            
        except Exception as e:
            logger.error(f"❌ 결과 저장 실패: {str(e)}")

    async def send_anomaly_alerts(self, results: List[AnomalyResult]):
        """이상 탐지 알림 전송"""
        if not results or not ALERT_WEBHOOK:
            return
        
        try:
            # 심각도별 필터링
            critical_results = [r for r in results if r.severity.value >= SeverityLevel.HIGH.value]
            
            if not critical_results:
                return
            
            # 알림 메시지 구성
            alert_data = {
                "timestamp": datetime.now().isoformat(),
                "total_anomalies": len(results),
                "critical_anomalies": len(critical_results),
                "anomalies": [
                    {
                        "device_id": result.device_id,
                        "type": result.anomaly_type.value,
                        "severity": result.severity.name,
                        "confidence": result.confidence_score,
                        "description": result.description,
                        "recommendation": result.recommendation,
                        "location": result.location,
                        "timestamp": result.timestamp.isoformat()
                    }
                    for result in critical_results[:10]  # 최대 10개만 전송
                ]
            }
            
            async with self.session.post(ALERT_WEBHOOK, json=alert_data) as response:
                if response.status == 200:
                    logger.info(f"🚨 이상 탐지 알림 전송 완료: {len(critical_results)}건")
                else:
                    logger.error(f"❌ 알림 전송 실패: HTTP {response.status}")
                    
        except Exception as e:
            logger.error(f"❌ 알림 전송 중 오류: {str(e)}")

    async def retrain_models(self):
        """모델 재훈련 (정기적 실행)"""
        logger.info("🔄 AI 모델 재훈련 시작...")
        
        try:
            # 새로운 훈련 데이터로 모델 업데이트
            await self.train_isolation_forest()
            await self.train_lstm_model()
            
            # 성능 메트릭 업데이트
            await self.update_model_metrics()
            
            logger.info("✅ AI 모델 재훈련 완료")
            
        except Exception as e:
            logger.error(f"❌ 모델 재훈련 실패: {str(e)}")

    async def update_model_metrics(self):
        """모델 성능 메트릭 업데이트"""
        try:
            # Redis에 메트릭 저장
            metrics_key = "ai_model_metrics"
            metrics_data = {
                "last_updated": datetime.now().isoformat(),
                "models": self.model_metrics
            }
            
            self.redis_client.setex(
                metrics_key, 
                86400,  # 24시간 TTL
                json.dumps(metrics_data)
            )
            
            logger.info("📊 모델 메트릭 업데이트 완료")
            
        except Exception as e:
            logger.error(f"❌ 메트릭 업데이트 실패: {str(e)}")

async def main():
    """메인 실행 함수"""
    logger.info("🚀 HankookTire SmartSensor AI 이상 탐지 시스템 시작")
    
    async with AdvancedAnomalyDetector() as detector:
        # 종합 이상 탐지 실행
        results = await detector.run_comprehensive_analysis()
        
        # 결과 요약 출력
        if results:
            logger.info("=" * 80)
            logger.info("🤖 AI 이상 탐지 결과 요약")
            logger.info("=" * 80)
            
            severity_counts = {}
            type_counts = {}
            
            for result in results:
                severity_counts[result.severity.name] = severity_counts.get(result.severity.name, 0) + 1
                type_counts[result.anomaly_type.value] = type_counts.get(result.anomaly_type.value, 0) + 1
            
            logger.info(f"📊 총 이상 감지: {len(results)}건")
            logger.info(f"📋 심각도별: {severity_counts}")
            logger.info(f"🔍 유형별: {type_counts}")
            
            # 상위 5개 이상 출력
            logger.info("\n🚨 주요 이상 탐지 결과:")
            for i, result in enumerate(results[:5], 1):
                logger.info(f"{i}. {result.device_id} - {result.anomaly_type.value}")
                logger.info(f"   심각도: {result.severity.name}, 신뢰도: {result.confidence_score:.3f}")
                logger.info(f"   설명: {result.description}")
                logger.info(f"   권장사항: {result.recommendation}")
                logger.info("")
        else:
            logger.info("✅ 이상 징후가 발견되지 않았습니다.")
        
        # 정기적 모델 재훈련 (주간 실행 시)
        if datetime.now().weekday() == 6:  # 일요일
            await detector.retrain_models()
        
        logger.info("🎉 AI 이상 탐지 시스템 실행 완료")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 AI 이상 탐지 시스템이 사용자에 의해 중단되었습니다.")
    except Exception as e:
        logger.error(f"💥 예상치 못한 오류: {str(e)}")
        exit(1)