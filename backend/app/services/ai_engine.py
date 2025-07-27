#!/usr/bin/env python3
"""
HankookTire SmartSensor 2.0 - Advanced AI Engine
차세대 AI 기반 예측 분석 엔진
"""

import asyncio
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
from sklearn.preprocessing import StandardScaler, MinMaxScaler
from sklearn.ensemble import IsolationForest, RandomForestRegressor
from sklearn.model_selection import train_test_split
import joblib
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
import json
from pathlib import Path

# TensorFlow for additional models
import tensorflow as tf
from tensorflow.keras.models import Sequential, load_model
from tensorflow.keras.layers import LSTM, Dense, Dropout, Attention
from tensorflow.keras.optimizers import Adam

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AdvancedLSTMModel(nn.Module):
    """고급 LSTM 모델 (PyTorch)"""
    
    def __init__(self, input_size: int, hidden_size: int = 128, num_layers: int = 3, dropout: float = 0.2):
        super(AdvancedLSTMModel, self).__init__()
        
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        
        # LSTM 레이어들
        self.lstm1 = nn.LSTM(input_size, hidden_size, num_layers, 
                            batch_first=True, dropout=dropout, bidirectional=True)
        self.lstm2 = nn.LSTM(hidden_size * 2, hidden_size, 1, 
                            batch_first=True, dropout=dropout)
        
        # Attention 메커니즘
        self.attention = nn.MultiheadAttention(hidden_size, num_heads=8, dropout=dropout)
        
        # 완전연결 레이어들
        self.fc1 = nn.Linear(hidden_size, 64)
        self.fc2 = nn.Linear(64, 32)
        self.fc3 = nn.Linear(32, 1)
        
        self.dropout = nn.Dropout(dropout)
        self.relu = nn.ReLU()
        
    def forward(self, x):
        # LSTM 처리
        lstm_out1, _ = self.lstm1(x)
        lstm_out2, _ = self.lstm2(lstm_out1)
        
        # Attention 적용
        lstm_out2 = lstm_out2.transpose(0, 1)  # (seq, batch, features)
        attn_out, _ = self.attention(lstm_out2, lstm_out2, lstm_out2)
        attn_out = attn_out.transpose(0, 1)  # (batch, seq, features)
        
        # 마지막 타임스텝 사용
        out = attn_out[:, -1, :]
        
        # 완전연결 레이어
        out = self.relu(self.fc1(out))
        out = self.dropout(out)
        out = self.relu(self.fc2(out))
        out = self.dropout(out)
        out = self.fc3(out)
        
        return out

class TransformerModel(nn.Module):
    """Transformer 기반 시계열 예측 모델"""
    
    def __init__(self, input_size: int, d_model: int = 128, nhead: int = 8, num_layers: int = 6):
        super(TransformerModel, self).__init__()
        
        self.d_model = d_model
        self.input_projection = nn.Linear(input_size, d_model)
        
        # Positional Encoding
        self.pos_encoding = self._generate_pos_encoding(1000, d_model)
        
        # Transformer 인코더
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model, 
            nhead=nhead, 
            dim_feedforward=d_model * 4,
            dropout=0.1
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        
        # 출력 레이어
        self.output_layer = nn.Linear(d_model, 1)
        
    def _generate_pos_encoding(self, max_len: int, d_model: int):
        """Positional Encoding 생성"""
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len).unsqueeze(1).float()
        
        div_term = torch.exp(torch.arange(0, d_model, 2).float() * 
                           -(np.log(10000.0) / d_model))
        
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        
        return pe.unsqueeze(0)
    
    def forward(self, x):
        # 입력 투영
        x = self.input_projection(x) * np.sqrt(self.d_model)
        
        # Positional Encoding 추가
        seq_len = x.size(1)
        pos_enc = self.pos_encoding[:, :seq_len, :].to(x.device)
        x = x + pos_enc
        
        # Transformer 처리 (seq_len, batch_size, d_model)
        x = x.transpose(0, 1)
        x = self.transformer(x)
        x = x.transpose(0, 1)
        
        # 마지막 타임스텝의 출력
        output = self.output_layer(x[:, -1, :])
        
        return output

class HankookAIEngine:
    """한국타이어 차세대 AI 엔진"""
    
    def __init__(self):
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        logger.info(f"AI 엔진 초기화 - 디바이스: {self.device}")
        
        # 모델 저장 경로
        self.model_path = Path("models")
        self.model_path.mkdir(exist_ok=True)
        
        # 데이터 스케일러들
        self.scalers = {}
        
        # 학습된 모델들
        self.models = {
            'tire_life_lstm': None,
            'tire_life_transformer': None,
            'anomaly_detector': None,
            'quality_predictor': None,
            'maintenance_predictor': None,
            'temperature_forecaster': None,
            'pressure_forecaster': None,
            'vibration_analyzer': None
        }
        
        # 모델 성능 메트릭
        self.model_metrics = {}
        
        # 실시간 추론 캐시
        self.inference_cache = {}
        
    async def initialize(self):
        """AI 엔진 초기화"""
        logger.info("🤖 AI 엔진 초기화 시작")
        
        try:
            # 저장된 모델 로드
            await self.load_models()
            
            # 없는 모델들은 기본 모델로 초기화
            await self.initialize_default_models()
            
            # 스케일러 로드
            await self.load_scalers()
            
            logger.info("✅ AI 엔진 초기화 완료")
            
        except Exception as e:
            logger.error(f"AI 엔진 초기화 오류: {e}")
            raise
    
    async def load_models(self):
        """저장된 모델들 로드"""
        for model_name in self.models.keys():
            model_file = self.model_path / f"{model_name}.pth"
            if model_file.exists():
                try:
                    if model_name == 'tire_life_lstm':
                        self.models[model_name] = AdvancedLSTMModel(input_size=8)
                        self.models[model_name].load_state_dict(torch.load(model_file, map_location=self.device))
                    elif model_name == 'tire_life_transformer':
                        self.models[model_name] = TransformerModel(input_size=8)
                        self.models[model_name].load_state_dict(torch.load(model_file, map_location=self.device))
                    elif model_name == 'anomaly_detector':
                        self.models[model_name] = joblib.load(model_file)
                    
                    logger.info(f"✓ {model_name} 모델 로드 완료")
                except Exception as e:
                    logger.warning(f"모델 로드 실패 ({model_name}): {e}")
    
    async def initialize_default_models(self):
        """기본 모델들 초기화"""
        # LSTM 모델
        if self.models['tire_life_lstm'] is None:
            self.models['tire_life_lstm'] = AdvancedLSTMModel(input_size=8).to(self.device)
            logger.info("✓ 기본 LSTM 모델 초기화")
        
        # Transformer 모델
        if self.models['tire_life_transformer'] is None:
            self.models['tire_life_transformer'] = TransformerModel(input_size=8).to(self.device)
            logger.info("✓ 기본 Transformer 모델 초기화")
        
        # 이상 탐지 모델
        if self.models['anomaly_detector'] is None:
            self.models['anomaly_detector'] = IsolationForest(
                contamination=0.1,
                random_state=42,
                n_estimators=200
            )
            logger.info("✓ 기본 이상 탐지 모델 초기화")
        
        # 품질 예측 모델
        if self.models['quality_predictor'] is None:
            self.models['quality_predictor'] = RandomForestRegressor(
                n_estimators=200,
                random_state=42,
                n_jobs=-1
            )
            logger.info("✓ 기본 품질 예측 모델 초기화")
    
    async def load_scalers(self):
        """데이터 스케일러 로드"""
        scaler_file = self.model_path / "scalers.pkl"
        if scaler_file.exists():
            try:
                self.scalers = joblib.load(scaler_file)
                logger.info("✓ 스케일러 로드 완료")
            except Exception as e:
                logger.warning(f"스케일러 로드 실패: {e}")
        
        # 기본 스케일러 초기화
        if not self.scalers:
            self.scalers = {
                'sensor_data': StandardScaler(),
                'tire_data': MinMaxScaler(),
                'quality_data': StandardScaler()
            }
            logger.info("✓ 기본 스케일러 초기화")
    
    async def run_inference(self, sensor_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """실시간 AI 추론 실행"""
        try:
            # 데이터 전처리
            processed_data = await self.preprocess_for_inference(sensor_data)
            
            # 여러 모델로 예측 실행
            predictions = {}
            
            # LSTM 기반 타이어 수명 예측
            if self.models['tire_life_lstm']:
                lstm_prediction = await self.predict_tire_life_lstm(processed_data)
                predictions['tire_life_lstm'] = lstm_prediction
            
            # Transformer 기반 타이어 수명 예측
            if self.models['tire_life_transformer']:
                transformer_prediction = await self.predict_tire_life_transformer(processed_data)
                predictions['tire_life_transformer'] = transformer_prediction
            
            # 앙상블 예측 (LSTM + Transformer)
            if 'tire_life_lstm' in predictions and 'tire_life_transformer' in predictions:
                ensemble_prediction = (predictions['tire_life_lstm'] + predictions['tire_life_transformer']) / 2
                predictions['tire_life_ensemble'] = ensemble_prediction
            
            # 품질 점수 예측
            quality_score = await self.predict_quality_score(processed_data)
            predictions['quality_score'] = quality_score
            
            # 신뢰도 계산
            confidence_score = await self.calculate_confidence(predictions)
            
            return {
                'predictions': predictions,
                'confidence': confidence_score,
                'timestamp': datetime.now().isoformat(),
                'model_versions': await self.get_model_versions()
            }
            
        except Exception as e:
            logger.error(f"AI 추론 오류: {e}")
            return {'error': str(e)}
    
    async def detect_anomalies(self, sensor_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """실시간 이상 탐지"""
        try:
            # 데이터 전처리
            processed_data = await self.preprocess_for_anomaly_detection(sensor_data)
            
            if len(processed_data) == 0:
                return {'anomalies': [], 'risk_level': 'low'}
            
            # 이상 탐지 실행
            anomaly_scores = self.models['anomaly_detector'].decision_function(processed_data)
            is_anomaly = self.models['anomaly_detector'].predict(processed_data) == -1
            
            # 이상 정보 분석
            anomalies = []
            for i, (score, is_anom) in enumerate(zip(anomaly_scores, is_anomaly)):
                if is_anom:
                    anomaly_info = await self.analyze_anomaly_details(sensor_data[i], score)
                    anomalies.append(anomaly_info)
            
            # 위험 수준 계산
            risk_level = await self.calculate_risk_level(anomaly_scores)
            
            return {
                'anomalies': anomalies,
                'risk_level': risk_level,
                'total_anomalies': len(anomalies),
                'average_score': float(np.mean(anomaly_scores)),
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"이상 탐지 오류: {e}")
            return {'error': str(e)}
    
    async def predict_maintenance(self, sensor_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """예측 정비 분석"""
        try:
            # 데이터 기반 정비 예측
            maintenance_data = await self.analyze_maintenance_needs(sensor_data)
            
            # 타이어별 정비 예측
            tire_maintenance = {}
            for i in range(4):  # 4개 타이어
                tire_data = await self.extract_tire_specific_data(sensor_data, i)
                tire_maintenance[f'tire_{i+1}'] = await self.predict_tire_maintenance(tire_data)
            
            # 전체 시스템 정비 예측
            system_maintenance = await self.predict_system_maintenance(sensor_data)
            
            return {
                'tire_maintenance': tire_maintenance,
                'system_maintenance': system_maintenance,
                'maintenance_priority': await self.calculate_maintenance_priority(tire_maintenance),
                'estimated_cost': await self.estimate_maintenance_cost(tire_maintenance, system_maintenance),
                'recommended_date': await self.recommend_maintenance_date(tire_maintenance),
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"정비 예측 오류: {e}")
            return {'error': str(e)}
    
    async def preprocess_for_inference(self, sensor_data: List[Dict[str, Any]]) -> np.ndarray:
        """추론용 데이터 전처리"""
        features = []
        
        for data in sensor_data:
            feature_vector = [
                data.get('temperature', 0),
                data.get('humidity', 0),
                data.get('pressure', 0),
                data.get('acceleration', 0),
                data.get('light', 0),
                data.get('battery_voltage', 0),
                data.get('system_health', 0),
                data.get('quality_score', 0)
            ]
            features.append(feature_vector)
        
        features_array = np.array(features)
        
        # 스케일링
        if 'sensor_data' in self.scalers:
            features_array = self.scalers['sensor_data'].fit_transform(features_array)
        
        return features_array
    
    async def predict_tire_life_lstm(self, processed_data: np.ndarray) -> float:
        """LSTM 모델로 타이어 수명 예측"""
        model = self.models['tire_life_lstm']
        model.eval()
        
        # 시퀀스 데이터로 변환 (배치, 시퀀스, 특성)
        if len(processed_data.shape) == 2:
            # 마지막 10개 데이터포인트 사용
            sequence_length = min(10, len(processed_data))
            sequence_data = processed_data[-sequence_length:]
            sequence_data = sequence_data.reshape(1, sequence_length, -1)
        else:
            sequence_data = processed_data
        
        # 텐서 변환
        input_tensor = torch.FloatTensor(sequence_data).to(self.device)
        
        with torch.no_grad():
            prediction = model(input_tensor)
        
        # 일 단위로 변환 (기본 예측값은 정규화된 값)
        predicted_days = float(prediction.cpu().numpy()[0][0]) * 1095  # 3년 = 1095일
        
        return max(30, predicted_days)  # 최소 30일
    
    async def predict_tire_life_transformer(self, processed_data: np.ndarray) -> float:
        """Transformer 모델로 타이어 수명 예측"""
        model = self.models['tire_life_transformer']
        model.eval()
        
        # 시퀀스 데이터로 변환
        if len(processed_data.shape) == 2:
            sequence_length = min(20, len(processed_data))  # Transformer는 더 긴 시퀀스 사용
            sequence_data = processed_data[-sequence_length:]
            sequence_data = sequence_data.reshape(1, sequence_length, -1)
        else:
            sequence_data = processed_data
        
        # 텐서 변환
        input_tensor = torch.FloatTensor(sequence_data).to(self.device)
        
        with torch.no_grad():
            prediction = model(input_tensor)
        
        # 일 단위로 변환
        predicted_days = float(prediction.cpu().numpy()[0][0]) * 1095
        
        return max(30, predicted_days)
    
    async def predict_quality_score(self, processed_data: np.ndarray) -> float:
        """품질 점수 예측"""
        if self.models['quality_predictor'] and len(processed_data) > 0:
            # 최신 데이터 사용
            latest_data = processed_data[-1].reshape(1, -1)
            quality_score = self.models['quality_predictor'].predict(latest_data)[0]
            return max(0, min(100, quality_score))
        
        return 85.0  # 기본값
    
    async def preprocess_for_anomaly_detection(self, sensor_data: List[Dict[str, Any]]) -> np.ndarray:
        """이상 탐지용 데이터 전처리"""
        return await self.preprocess_for_inference(sensor_data)
    
    async def analyze_anomaly_details(self, data_point: Dict[str, Any], anomaly_score: float) -> Dict[str, Any]:
        """이상 상세 분석"""
        anomaly_types = []
        severity = "낮음"
        
        # 온도 이상
        temp = data_point.get('temperature', 25)
        if temp > 60 or temp < 0:
            anomaly_types.append("극한 온도")
            severity = "높음"
        elif temp > 45 or temp < 5:
            anomaly_types.append("비정상 온도")
            severity = "보통"
        
        # 압력 이상
        pressure = data_point.get('pressure', 1013)
        if abs(pressure - 1013) > 100:
            anomaly_types.append("기압 이상")
            severity = "높음"
        
        # 진동 이상
        acceleration = data_point.get('acceleration', 1.0)
        if acceleration > 3.0:
            anomaly_types.append("과도한 진동")
            severity = "높음"
        
        # 시스템 건강도 이상
        health = data_point.get('system_health', 100)
        if health < 50:
            anomaly_types.append("시스템 성능 저하")
            severity = "매우 높음"
        
        return {
            'anomaly_types': anomaly_types if anomaly_types else ["알 수 없는 이상"],
            'severity': severity,
            'anomaly_score': float(anomaly_score),
            'affected_sensors': await self.identify_affected_sensors(data_point),
            'recommended_action': await self.recommend_action(anomaly_types, severity)
        }
    
    async def calculate_risk_level(self, anomaly_scores: np.ndarray) -> str:
        """위험 수준 계산"""
        avg_score = np.mean(anomaly_scores)
        min_score = np.min(anomaly_scores)
        
        if min_score < -0.5 or avg_score < -0.3:
            return "매우 높음"
        elif min_score < -0.3 or avg_score < -0.2:
            return "높음"
        elif min_score < -0.1 or avg_score < -0.1:
            return "보통"
        else:
            return "낮음"
    
    async def identify_affected_sensors(self, data_point: Dict[str, Any]) -> List[str]:
        """영향받은 센서 식별"""
        affected = []
        
        if data_point.get('temperature', 25) > 50:
            affected.append("DHT22 (온습도)")
        if abs(data_point.get('pressure', 1013) - 1013) > 50:
            affected.append("BMP280 (기압)")
        if data_point.get('acceleration', 1.0) > 2.0:
            affected.append("MPU6050 (가속도)")
        if data_point.get('system_health', 100) < 70:
            affected.append("전체 시스템")
        
        return affected if affected else ["알 수 없음"]
    
    async def recommend_action(self, anomaly_types: List[str], severity: str) -> str:
        """권장 조치 사항"""
        if "시스템 성능 저하" in anomaly_types:
            return "즉시 시스템 점검 및 재시작 필요"
        elif "극한 온도" in anomaly_types:
            return "온도 제어 시스템 점검 및 환기 개선"
        elif "과도한 진동" in anomaly_types:
            return "진동 원인 조사 및 장비 고정 상태 확인"
        elif severity == "매우 높음":
            return "즉시 전문가 점검 필요"
        elif severity == "높음":
            return "24시간 내 점검 권장"
        else:
            return "정기 점검 시 확인"
    
    async def calculate_confidence(self, predictions: Dict[str, float]) -> float:
        """예측 신뢰도 계산"""
        if len(predictions) < 2:
            return 0.7  # 기본 신뢰도
        
        # 여러 모델 예측값의 일치도 기반 신뢰도 계산
        values = list(predictions.values())
        variance = np.var(values)
        
        # 분산이 낮을수록 신뢰도 높음
        confidence = max(0.5, min(0.95, 1.0 - (variance / 10000)))
        
        return confidence
    
    async def get_model_versions(self) -> Dict[str, str]:
        """모델 버전 정보"""
        return {
            'lstm': 'v2.1',
            'transformer': 'v1.3',
            'anomaly_detector': 'v2.0',
            'quality_predictor': 'v1.5'
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """AI 엔진 상태 체크"""
        model_status = {}
        for name, model in self.models.items():
            model_status[name] = "loaded" if model is not None else "not_loaded"
        
        return {
            'status': 'healthy',
            'models': model_status,
            'device': str(self.device),
            'memory_usage': torch.cuda.memory_allocated() if torch.cuda.is_available() else 0,
            'inference_cache_size': len(self.inference_cache)
        }
    
    async def cleanup(self):
        """AI 엔진 정리"""
        logger.info("🔄 AI 엔진 정리 중...")
        
        # 모델 저장
        await self.save_models()
        
        # 캐시 정리
        self.inference_cache.clear()
        
        # GPU 메모리 정리
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        
        logger.info("✅ AI 엔진 정리 완료")
    
    async def save_models(self):
        """모델 저장"""
        try:
            for name, model in self.models.items():
                if model and hasattr(model, 'state_dict'):
                    model_file = self.model_path / f"{name}.pth"
                    torch.save(model.state_dict(), model_file)
                elif model and hasattr(model, 'fit'):  # sklearn 모델
                    model_file = self.model_path / f"{name}.pkl"
                    joblib.dump(model, model_file)
            
            # 스케일러 저장
            scaler_file = self.model_path / "scalers.pkl"
            joblib.dump(self.scalers, scaler_file)
            
            logger.info("✓ 모델 저장 완료")
        except Exception as e:
            logger.error(f"모델 저장 오류: {e}")
    
    # 추가 정비 예측 관련 메소드들
    async def analyze_maintenance_needs(self, sensor_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """정비 필요성 분석"""
        # 구현 예정
        return {}
    
    async def extract_tire_specific_data(self, sensor_data: List[Dict[str, Any]], tire_index: int) -> List[Dict[str, Any]]:
        """특정 타이어 데이터 추출"""
        # 구현 예정
        return sensor_data
    
    async def predict_tire_maintenance(self, tire_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """개별 타이어 정비 예측"""
        # 구현 예정
        return {"days_remaining": 90, "confidence": 0.8}
    
    async def predict_system_maintenance(self, sensor_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """시스템 전체 정비 예측"""
        # 구현 예정
        return {"next_maintenance": "2025-02-15", "type": "정기점검"}
    
    async def calculate_maintenance_priority(self, tire_maintenance: Dict[str, Any]) -> List[Dict[str, Any]]:
        """정비 우선순위 계산"""
        # 구현 예정
        return [{"tire": "tire_1", "priority": "high", "reason": "압력 저하"}]
    
    async def estimate_maintenance_cost(self, tire_maintenance: Dict[str, Any], system_maintenance: Dict[str, Any]) -> Dict[str, float]:
        """정비 비용 추정"""
        # 구현 예정
        return {"tire_cost": 50000, "system_cost": 100000, "total": 150000}
    
    async def recommend_maintenance_date(self, tire_maintenance: Dict[str, Any]) -> str:
        """정비 권장 날짜"""
        # 구현 예정
        return (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")