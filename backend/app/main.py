#!/usr/bin/env python3
"""
HankookTire SmartSensor 2.0 - Main FastAPI Application
차세대 통합 스마트 타이어 센서 시스템 메인 서버
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import asyncio
import json
import logging
from datetime import datetime
from typing import List, Dict, Any
import uvicorn

# Internal imports
from app.core.config import settings
from app.api.routes import sensors, analytics, tpms, quality, dashboard
from app.services.ai_engine import HankookAIEngine
from app.services.iot_manager import IoTDeviceManager
from app.services.websocket_manager import WebSocketManager
from app.models.sensor_data import SensorReading, TPMSData, QualityMetrics
from app.core.database import get_database

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# FastAPI app instance
app = FastAPI(
    title="HankookTire SmartSensor 2.0",
    description="차세대 통합 스마트 타이어 센서 시스템",
    version="2.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Production에서는 구체적인 도메인 설정
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Global instances
ai_engine = HankookAIEngine()
iot_manager = IoTDeviceManager()
ws_manager = WebSocketManager()

# API Routes
app.include_router(sensors.router, prefix="/api/v1/sensors", tags=["sensors"])
app.include_router(analytics.router, prefix="/api/v1/analytics", tags=["analytics"])
app.include_router(tpms.router, prefix="/api/v1/tpms", tags=["tpms"])
app.include_router(quality.router, prefix="/api/v1/quality", tags=["quality"])
app.include_router(dashboard.router, prefix="/api/v1/dashboard", tags=["dashboard"])

@app.on_event("startup")
async def startup_event():
    """애플리케이션 시작 시 초기화"""
    logger.info("🚀 HankookTire SmartSensor 2.0 시작")
    
    # AI 엔진 초기화
    await ai_engine.initialize()
    logger.info("✓ AI 엔진 초기화 완료")
    
    # IoT 디바이스 매니저 초기화
    await iot_manager.initialize()
    logger.info("✓ IoT 디바이스 매니저 초기화 완료")
    
    # 백그라운드 태스크 시작
    asyncio.create_task(data_processing_worker())
    asyncio.create_task(ai_inference_worker())
    asyncio.create_task(health_check_worker())
    
    logger.info("✅ 모든 서비스 초기화 완료")

@app.on_event("shutdown")
async def shutdown_event():
    """애플리케이션 종료 시 정리"""
    logger.info("🔄 HankookTire SmartSensor 2.0 종료 중...")
    
    await ai_engine.cleanup()
    await iot_manager.cleanup()
    await ws_manager.disconnect_all()
    
    logger.info("✅ 모든 서비스 정리 완료")

@app.get("/", response_class=HTMLResponse)
async def root():
    """메인 페이지"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>HankookTire SmartSensor 2.0</title>
        <meta charset="utf-8">
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }
            .container { max-width: 800px; margin: 0 auto; background: white; padding: 40px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
            h1 { color: #ff6b35; text-align: center; }
            .status { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin: 30px 0; }
            .card { background: #f8f9fa; padding: 20px; border-radius: 8px; text-align: center; }
            .metric { font-size: 24px; font-weight: bold; color: #ff6b35; }
            .nav { text-align: center; margin: 30px 0; }
            .nav a { margin: 0 10px; padding: 10px 20px; background: #ff6b35; color: white; text-decoration: none; border-radius: 5px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🚀 HankookTire SmartSensor 2.0</h1>
            <p style="text-align: center; font-size: 18px; color: #666;">
                차세대 통합 스마트 타이어 센서 시스템
            </p>
            
            <div class="status">
                <div class="card">
                    <div class="metric" id="sensors">--</div>
                    <div>활성 센서</div>
                </div>
                <div class="card">
                    <div class="metric" id="tires">4</div>
                    <div>TPMS 센서</div>
                </div>
                <div class="card">
                    <div class="metric" id="ai-models">8</div>
                    <div>AI 모델</div>
                </div>
                <div class="card">
                    <div class="metric" id="uptime">--</div>
                    <div>가동시간</div>
                </div>
            </div>
            
            <div class="nav">
                <a href="/api/docs">API 문서</a>
                <a href="/dashboard">대시보드</a>
                <a href="/mobile">모바일 앱</a>
                <a href="/api/v1/sensors/status">센서 상태</a>
            </div>
            
            <script>
                // 실시간 상태 업데이트
                async function updateStatus() {
                    try {
                        const response = await fetch('/api/v1/dashboard/status');
                        const data = await response.json();
                        
                        document.getElementById('sensors').textContent = data.active_sensors || '--';
                        document.getElementById('uptime').textContent = data.uptime || '--';
                    } catch (error) {
                        console.error('상태 업데이트 오류:', error);
                    }
                }
                
                setInterval(updateStatus, 5000);
                updateStatus();
            </script>
        </div>
    </body>
    </html>
    """

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    """WebSocket 연결 엔드포인트"""
    await ws_manager.connect(websocket, client_id)
    try:
        while True:
            # 클라이언트로부터 메시지 수신
            data = await websocket.receive_text()
            message = json.loads(data)
            
            # 메시지 타입에 따른 처리
            if message.get("type") == "command":
                await handle_websocket_command(message, client_id)
            elif message.get("type") == "subscribe":
                await ws_manager.subscribe(client_id, message.get("channel"))
                
    except WebSocketDisconnect:
        await ws_manager.disconnect(client_id)
    except Exception as e:
        logger.error(f"WebSocket 오류 ({client_id}): {e}")
        await ws_manager.disconnect(client_id)

async def handle_websocket_command(message: Dict[str, Any], client_id: str):
    """WebSocket 명령 처리"""
    command = message.get("command")
    
    if command == "get_sensor_data":
        # 최신 센서 데이터 전송
        data = await iot_manager.get_latest_sensor_data()
        await ws_manager.send_to_client(client_id, {
            "type": "sensor_data",
            "data": data,
            "timestamp": datetime.now().isoformat()
        })
    
    elif command == "start_calibration":
        # 센서 캘리브레이션 시작
        sensor_id = message.get("sensor_id")
        result = await iot_manager.start_calibration(sensor_id)
        await ws_manager.send_to_client(client_id, {
            "type": "calibration_result",
            "result": result
        })
    
    elif command == "emergency_stop":
        # 비상 정지
        await iot_manager.emergency_stop()
        await ws_manager.broadcast({
            "type": "emergency_alert",
            "message": "비상 정지가 실행되었습니다."
        })

async def data_processing_worker():
    """데이터 처리 백그라운드 워커"""
    logger.info("📊 데이터 처리 워커 시작")
    
    while True:
        try:
            # IoT 디바이스에서 데이터 수집
            raw_data = await iot_manager.collect_all_data()
            
            if raw_data:
                # 데이터 전처리
                processed_data = await preprocess_sensor_data(raw_data)
                
                # 데이터베이스 저장
                await save_sensor_data(processed_data)
                
                # 실시간 WebSocket 브로드캐스트
                await ws_manager.broadcast({
                    "type": "sensor_update",
                    "data": processed_data,
                    "timestamp": datetime.now().isoformat()
                })
                
        except Exception as e:
            logger.error(f"데이터 처리 워커 오류: {e}")
        
        await asyncio.sleep(1)  # 1초마다 실행

async def ai_inference_worker():
    """AI 추론 백그라운드 워커"""
    logger.info("🤖 AI 추론 워커 시작")
    
    while True:
        try:
            # 최근 센서 데이터 가져오기
            recent_data = await get_recent_sensor_data()
            
            if recent_data:
                # AI 분석 실행
                predictions = await ai_engine.run_inference(recent_data)
                
                # 이상 탐지
                anomalies = await ai_engine.detect_anomalies(recent_data)
                
                # 예측 정비 분석
                maintenance = await ai_engine.predict_maintenance(recent_data)
                
                # 결과 브로드캐스트
                await ws_manager.broadcast({
                    "type": "ai_analysis",
                    "predictions": predictions,
                    "anomalies": anomalies,
                    "maintenance": maintenance,
                    "timestamp": datetime.now().isoformat()
                })
                
        except Exception as e:
            logger.error(f"AI 추론 워커 오류: {e}")
        
        await asyncio.sleep(10)  # 10초마다 실행

async def health_check_worker():
    """시스템 상태 모니터링 워커"""
    logger.info("🔍 상태 모니터링 워커 시작")
    
    while True:
        try:
            # 시스템 상태 체크
            system_health = await check_system_health()
            
            # IoT 디바이스 상태 체크
            device_health = await iot_manager.check_device_health()
            
            # AI 엔진 상태 체크
            ai_health = await ai_engine.health_check()
            
            # 종합 상태 브로드캐스트
            await ws_manager.broadcast({
                "type": "health_status",
                "system": system_health,
                "devices": device_health,
                "ai": ai_health,
                "timestamp": datetime.now().isoformat()
            })
            
        except Exception as e:
            logger.error(f"상태 모니터링 워커 오류: {e}")
        
        await asyncio.sleep(30)  # 30초마다 실행

async def preprocess_sensor_data(raw_data: Dict[str, Any]) -> Dict[str, Any]:
    """센서 데이터 전처리"""
    processed = {}
    
    for sensor_id, data in raw_data.items():
        # 데이터 검증 및 정규화
        if validate_sensor_data(data):
            processed[sensor_id] = {
                "temperature": normalize_temperature(data.get("temperature")),
                "humidity": normalize_humidity(data.get("humidity")),
                "pressure": normalize_pressure(data.get("pressure")),
                "acceleration": normalize_acceleration(data.get("acceleration")),
                "timestamp": datetime.now().isoformat(),
                "quality_score": calculate_data_quality(data)
            }
    
    return processed

def validate_sensor_data(data: Dict[str, Any]) -> bool:
    """센서 데이터 유효성 검증"""
    required_fields = ["temperature", "humidity", "pressure"]
    return all(field in data for field in required_fields)

def normalize_temperature(value: float) -> float:
    """온도 데이터 정규화 (-40°C ~ 85°C)"""
    return max(-40, min(85, value))

def normalize_humidity(value: float) -> float:
    """습도 데이터 정규화 (0% ~ 100%)"""
    return max(0, min(100, value))

def normalize_pressure(value: float) -> float:
    """압력 데이터 정규화 (800hPa ~ 1200hPa)"""
    return max(800, min(1200, value))

def normalize_acceleration(value: float) -> float:
    """가속도 데이터 정규화 (0g ~ 5g)"""
    return max(0, min(5, value))

def calculate_data_quality(data: Dict[str, Any]) -> float:
    """데이터 품질 점수 계산 (0.0 ~ 1.0)"""
    quality_score = 1.0
    
    # 누락된 필드 체크
    required_fields = ["temperature", "humidity", "pressure", "acceleration"]
    missing_fields = sum(1 for field in required_fields if field not in data)
    quality_score -= missing_fields * 0.25
    
    # 이상값 체크
    if data.get("temperature", 0) < -40 or data.get("temperature", 0) > 85:
        quality_score -= 0.1
    
    if data.get("humidity", 0) < 0 or data.get("humidity", 0) > 100:
        quality_score -= 0.1
    
    return max(0.0, quality_score)

async def save_sensor_data(processed_data: Dict[str, Any]):
    """전처리된 센서 데이터를 데이터베이스에 저장"""
    db = await get_database()
    try:
        for sensor_id, data in processed_data.items():
            await db.sensor_readings.insert_one({
                "sensor_id": sensor_id,
                **data
            })
    except Exception as e:
        logger.error(f"데이터 저장 오류: {e}")

async def get_recent_sensor_data(limit: int = 100):
    """최근 센서 데이터 조회"""
    db = await get_database()
    try:
        cursor = db.sensor_readings.find().sort("timestamp", -1).limit(limit)
        return await cursor.to_list(length=limit)
    except Exception as e:
        logger.error(f"데이터 조회 오류: {e}")
        return []

async def check_system_health() -> Dict[str, Any]:
    """시스템 상태 체크"""
    import psutil
    
    return {
        "cpu_percent": psutil.cpu_percent(),
        "memory_percent": psutil.virtual_memory().percent,
        "disk_percent": psutil.disk_usage('/').percent,
        "uptime": datetime.now().isoformat(),
        "status": "healthy"
    }

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info"
    )