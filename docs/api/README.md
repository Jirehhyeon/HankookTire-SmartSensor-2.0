# 📡 API 문서

**SmartTire SmartSensor 2.0 REST API & GraphQL 가이드**

이 문서는 SmartTire SmartSensor 2.0 시스템의 API 사용법을 상세히 안내합니다.

---

## 📋 목차

1. [API 개요](#-api-개요)
2. [인증 및 권한](#-인증-및-권한)
3. [REST API](#-rest-api)
4. [GraphQL API](#-graphql-api)
5. [WebSocket API](#-websocket-api)
6. [MQTT API](#-mqtt-api)
7. [SDK 및 라이브러리](#-sdk-및-라이브러리)
8. [에러 처리](#-에러-처리)

## 🌐 API 개요

### 기본 정보
```yaml
Base URL: https://api.hankook-smartsensor.com
API Version: v2.0
Content-Type: application/json
Encoding: UTF-8
Rate Limiting: 1000 requests/minute per API key
```

### 지원 프로토콜
- **REST API**: HTTP/HTTPS 기반 RESTful API
- **GraphQL**: 유연한 쿼리 언어
- **WebSocket**: 실시간 데이터 스트리밍
- **MQTT**: IoT 디바이스 통신

### API 엔드포인트 구조
```
https://api.hankook-smartsensor.com/
├── v2/                          # API 버전
│   ├── auth/                    # 인증 관련
│   ├── vehicles/                # 차량 관리
│   ├── sensors/                 # 센서 데이터
│   ├── analytics/               # 분석 및 예측
│   ├── alerts/                  # 알림 관리
│   ├── users/                   # 사용자 관리
│   └── system/                  # 시스템 정보
├── graphql                      # GraphQL 엔드포인트
├── ws/                          # WebSocket 연결
└── mqtt/                        # MQTT 브로커
```

## 🔐 인증 및 권한

### OAuth2 인증 플로우

#### 1. 토큰 발급
```http
POST /v2/auth/token
Content-Type: application/json

{
  "grant_type": "password",
  "username": "user@company.com",
  "password": "secure_password",
  "client_id": "smartsensor_client",
  "client_secret": "client_secret_here"
}
```

**응답:**
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "refresh_token": "def502004a8c8c1b...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "read write",
  "user_info": {
    "user_id": "12345",
    "username": "user@company.com",
    "role": "operator",
    "permissions": ["vehicles:read", "sensors:read", "analytics:read"]
  }
}
```

#### 2. 토큰 갱신
```http
POST /v2/auth/refresh
Content-Type: application/json

{
  "grant_type": "refresh_token",
  "refresh_token": "def502004a8c8c1b...",
  "client_id": "smartsensor_client",
  "client_secret": "client_secret_here"
}
```

#### 3. API 호출 시 인증
```http
GET /v2/vehicles
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...
```

### API 키 인증 (서버 간 통신)

```http
GET /v2/sensors/data
X-API-Key: hankook_smartsensor_api_key_here
X-API-Secret: corresponding_secret_here
```

### 다중 인증 (MFA)

```http
POST /v2/auth/mfa/verify
Content-Type: application/json
Authorization: Bearer partial_token...

{
  "mfa_code": "123456",
  "device_id": "mobile_app_device_123"
}
```

## 🔄 REST API

### 차량 관리 API

#### 차량 목록 조회
```http
GET /v2/vehicles?page=1&limit=20&status=active&region=seoul

Response:
{
  "data": [
    {
      "vehicle_id": "HK-2024-001",
      "make": "Hyundai",
      "model": "Sonata",
      "year": 2024,
      "vin": "KMHL14JA4MA123456",
      "status": "active",
      "location": {
        "latitude": 37.5665,
        "longitude": 126.9780,
        "address": "서울시 중구 명동"
      },
      "driver": {
        "name": "김철수",
        "phone": "010-1234-5678"
      },
      "last_updated": "2024-01-26T14:30:25Z",
      "sensor_count": 4,
      "sensor_status": {
        "normal": 3,
        "warning": 1,
        "error": 0
      }
    }
  ],
  "pagination": {
    "page": 1,
    "limit": 20,
    "total": 150,
    "total_pages": 8
  }
}
```

#### 차량 상세 정보
```http
GET /v2/vehicles/HK-2024-001

Response:
{
  "vehicle_id": "HK-2024-001",
  "make": "Hyundai",
  "model": "Sonata",
  "year": 2024,
  "vin": "KMHL14JA4MA123456",
  "registration_date": "2024-01-15T09:00:00Z",
  "status": "active",
  "specifications": {
    "engine_type": "Hybrid",
    "tire_size": "225/60R16",
    "recommended_pressure": {
      "front": 32,
      "rear": 30,
      "unit": "PSI"
    }
  },
  "sensors": [
    {
      "sensor_id": "TIRE_FL_001",
      "position": "front_left",
      "type": "pressure_temperature",
      "status": "normal",
      "last_reading": {
        "pressure": 32.5,
        "temperature": 35.2,
        "timestamp": "2024-01-26T14:30:25Z"
      }
    },
    {
      "sensor_id": "TIRE_FR_001", 
      "position": "front_right",
      "type": "pressure_temperature",
      "status": "warning",
      "last_reading": {
        "pressure": 28.8,
        "temperature": 36.1,
        "timestamp": "2024-01-26T14:30:25Z"
      }
    }
  ]
}
```

#### 차량 등록
```http
POST /v2/vehicles
Content-Type: application/json

{
  "vehicle_id": "HK-2024-002",
  "make": "Kia",
  "model": "K5",
  "year": 2024,
  "vin": "KNAE151A1MA654321",
  "tire_size": "235/55R17",
  "driver": {
    "name": "이영희",
    "phone": "010-9876-5432",
    "email": "lee@company.com"
  },
  "sensors": [
    {
      "sensor_id": "TIRE_FL_002",
      "position": "front_left",
      "type": "pressure_temperature"
    }
  ]
}

Response: 201 Created
{
  "vehicle_id": "HK-2024-002",
  "status": "registered",
  "created_at": "2024-01-26T15:00:00Z"
}
```

### 센서 데이터 API

#### 실시간 센서 데이터 조회
```http
GET /v2/sensors/data?vehicle_id=HK-2024-001&sensor_type=pressure&limit=100

Response:
{
  "data": [
    {
      "id": 1234567,
      "vehicle_id": "HK-2024-001",
      "sensor_id": "TIRE_FL_001",
      "sensor_type": "pressure",
      "position": "front_left",
      "value": 32.5,
      "unit": "PSI",
      "timestamp": "2024-01-26T14:30:25Z",
      "quality": "good",
      "metadata": {
        "temperature": 35.2,
        "battery_level": 85,
        "signal_strength": -45
      }
    }
  ],
  "summary": {
    "count": 100,
    "avg_value": 31.8,
    "min_value": 28.5,
    "max_value": 34.2,
    "time_range": {
      "start": "2024-01-26T13:30:25Z",
      "end": "2024-01-26T14:30:25Z"
    }
  }
}
```

#### 히스토리 데이터 조회
```http
GET /v2/sensors/history?vehicle_id=HK-2024-001&start_time=2024-01-25T00:00:00Z&end_time=2024-01-26T00:00:00Z&interval=1h

Response:
{
  "data": [
    {
      "timestamp": "2024-01-25T00:00:00Z",
      "sensors": {
        "front_left": {
          "pressure": 32.1,
          "temperature": 28.5
        },
        "front_right": {
          "pressure": 31.8,
          "temperature": 28.7
        },
        "rear_left": {
          "pressure": 30.2,
          "temperature": 27.9
        },
        "rear_right": {
          "pressure": 30.5,
          "temperature": 28.1
        }
      }
    }
  ],
  "statistics": {
    "pressure": {
      "avg": 31.15,
      "min": 28.5,
      "max": 34.2,
      "std_dev": 1.23
    }
  }
}
```

#### 센서 데이터 업로드 (IoT 디바이스용)
```http
POST /v2/sensors/data
Content-Type: application/json
X-Device-ID: SENSOR_DEVICE_001

{
  "readings": [
    {
      "vehicle_id": "HK-2024-001",
      "sensor_id": "TIRE_FL_001",
      "timestamp": "2024-01-26T14:30:25Z",
      "measurements": {
        "pressure": 32.5,
        "temperature": 35.2,
        "vibration": 0.12
      }
    }
  ]
}

Response: 202 Accepted
{
  "accepted": 1,
  "rejected": 0,
  "batch_id": "batch_20240126_143025"
}
```

### 분석 및 예측 API

#### AI 분석 결과 조회
```http
GET /v2/analytics/predictions?vehicle_id=HK-2024-001&type=tire_life

Response:
{
  "vehicle_id": "HK-2024-001",
  "analysis_type": "tire_life",
  "generated_at": "2024-01-26T14:30:25Z",
  "predictions": {
    "front_left": {
      "remaining_life_km": 25000,
      "replacement_date": "2024-07-15",
      "confidence": 0.92,
      "wear_pattern": "normal"
    },
    "front_right": {
      "remaining_life_km": 22000,
      "replacement_date": "2024-06-20",
      "confidence": 0.89,
      "wear_pattern": "slight_uneven"
    }
  },
  "recommendations": [
    {
      "priority": "medium",
      "action": "tire_rotation",
      "description": "타이어 위치 교환을 통한 균등 마모",
      "estimated_benefit": "5000km 수명 연장"
    }
  ]
}
```

#### 이상 탐지 결과
```http
GET /v2/analytics/anomalies?vehicle_id=HK-2024-001&time_range=24h

Response:
{
  "anomalies": [
    {
      "id": "anomaly_001",
      "vehicle_id": "HK-2024-001",
      "sensor_id": "TIRE_FR_001",
      "type": "pressure_drop",
      "severity": "medium",
      "detected_at": "2024-01-26T12:15:30Z",
      "description": "급격한 압력 감소 감지",
      "metrics": {
        "pressure_drop_rate": 2.5,
        "duration_minutes": 15,
        "confidence": 0.94
      },
      "suggested_actions": [
        "즉시 차량 점검",
        "타이어 손상 여부 확인",
        "전문가 상담"
      ]
    }
  ]
}
```

### 알림 관리 API

#### 알림 목록 조회
```http
GET /v2/alerts?status=unread&severity=high&limit=50

Response:
{
  "alerts": [
    {
      "id": "alert_001",
      "vehicle_id": "HK-2024-001",
      "type": "pressure_critical",
      "severity": "high",
      "title": "타이어 압력 위험",
      "message": "앞 오른쪽 타이어 압력이 위험 수준으로 낮습니다 (20 PSI)",
      "created_at": "2024-01-26T14:30:25Z",
      "status": "unread",
      "sensor_data": {
        "sensor_id": "TIRE_FR_001",
        "value": 20.0,
        "threshold": 25.0
      },
      "actions": [
        {
          "type": "notify_driver",
          "status": "completed",
          "timestamp": "2024-01-26T14:30:30Z"
        },
        {
          "type": "emergency_contact",
          "status": "pending"
        }
      ]
    }
  ]
}
```

#### 알림 생성
```http
POST /v2/alerts
Content-Type: application/json

{
  "vehicle_id": "HK-2024-001",
  "type": "maintenance_reminder",
  "severity": "low",
  "title": "정기 점검 알림",
  "message": "다음 정기 점검 일정이 다가왔습니다.",
  "scheduled_date": "2024-02-01T10:00:00Z",
  "recipients": [
    "maintenance@company.com",
    "010-1234-5678"
  ]
}

Response: 201 Created
{
  "alert_id": "alert_002",
  "status": "created",
  "delivery_status": {
    "email": "sent",
    "sms": "pending"
  }
}
```

## 🔍 GraphQL API

### GraphQL 엔드포인트
```
POST https://api.hankook-smartsensor.com/graphql
Content-Type: application/json
Authorization: Bearer your_token_here
```

### 스키마 개요

#### 주요 타입
```graphql
type Vehicle {
  id: ID!
  vehicleId: String!
  make: String!
  model: String!
  year: Int!
  vin: String
  status: VehicleStatus!
  location: Location
  driver: Driver
  sensors: [Sensor!]!
  lastUpdated: DateTime!
}

type Sensor {
  id: ID!
  sensorId: String!
  vehicleId: String!
  type: SensorType!
  position: TirePosition!
  status: SensorStatus!
  lastReading: SensorReading
  readings(
    limit: Int = 100
    startTime: DateTime
    endTime: DateTime
  ): [SensorReading!]!
}

type SensorReading {
  id: ID!
  value: Float!
  unit: String!
  timestamp: DateTime!
  quality: DataQuality!
  metadata: JSON
}

enum VehicleStatus {
  ACTIVE
  INACTIVE
  MAINTENANCE
  OFFLINE
}

enum SensorType {
  PRESSURE
  TEMPERATURE
  PRESSURE_TEMPERATURE
  VIBRATION
  MULTI_SENSOR
}

enum TirePosition {
  FRONT_LEFT
  FRONT_RIGHT
  REAR_LEFT
  REAR_RIGHT
}
```

### 쿼리 예제

#### 차량 및 센서 데이터 조회
```graphql
query GetVehicleData($vehicleId: String!) {
  vehicle(vehicleId: $vehicleId) {
    id
    vehicleId
    make
    model
    status
    location {
      latitude
      longitude
      address
    }
    driver {
      name
      phone
    }
    sensors {
      sensorId
      type
      position
      status
      lastReading {
        value
        unit
        timestamp
        quality
      }
    }
  }
}

# Variables:
{
  "vehicleId": "HK-2024-001"
}
```

#### 다중 차량 센서 데이터 조회
```graphql
query GetMultipleVehiclesSensorData($vehicleIds: [String!]!, $sensorType: SensorType!) {
  vehicles(vehicleIds: $vehicleIds) {
    vehicleId
    make
    model
    sensors(type: $sensorType) {
      position
      lastReading {
        value
        unit
        timestamp
      }
      readings(limit: 10) {
        value
        timestamp
      }
    }
  }
}
```

#### 실시간 알림 구독
```graphql
subscription VehicleAlerts($vehicleId: String!) {
  vehicleAlerts(vehicleId: $vehicleId) {
    id
    type
    severity
    title
    message
    createdAt
    sensorData {
      sensorId
      value
      threshold
    }
  }
}
```

### 뮤테이션 예제

#### 차량 등록
```graphql
mutation RegisterVehicle($input: VehicleInput!) {
  registerVehicle(input: $input) {
    id
    vehicleId
    status
    createdAt
  }
}

# Variables:
{
  "input": {
    "vehicleId": "HK-2024-003",
    "make": "Genesis",
    "model": "G90",
    "year": 2024,
    "vin": "KMHGC4DE5MA123789",
    "driver": {
      "name": "박민수",
      "phone": "010-5555-6666"
    }
  }
}
```

#### 알림 상태 업데이트
```graphql
mutation UpdateAlertStatus($alertId: ID!, $status: AlertStatus!) {
  updateAlertStatus(alertId: $alertId, status: $status) {
    id
    status
    updatedAt
  }
}
```

## 🔌 WebSocket API

### 연결 설정
```javascript
const ws = new WebSocket('wss://api.hankook-smartsensor.com/ws');

// 인증
ws.onopen = function() {
  ws.send(JSON.stringify({
    type: 'auth',
    token: 'your_jwt_token_here'
  }));
};

// 인증 완료 후 구독
ws.onmessage = function(event) {
  const data = JSON.parse(event.data);
  
  if (data.type === 'auth_success') {
    // 실시간 센서 데이터 구독
    ws.send(JSON.stringify({
      type: 'subscribe',
      channel: 'sensor_data',
      vehicle_id: 'HK-2024-001'
    }));
    
    // 알림 구독
    ws.send(JSON.stringify({
      type: 'subscribe', 
      channel: 'alerts',
      severity: ['high', 'critical']
    }));
  }
  
  if (data.type === 'sensor_data') {
    console.log('실시간 센서 데이터:', data.payload);
  }
  
  if (data.type === 'alert') {
    console.log('새 알림:', data.payload);
  }
};
```

### 실시간 데이터 스트림

#### 센서 데이터 스트림
```json
{
  "type": "sensor_data",
  "timestamp": "2024-01-26T14:30:25Z",
  "payload": {
    "vehicle_id": "HK-2024-001",
    "sensor_id": "TIRE_FL_001",
    "readings": {
      "pressure": 32.5,
      "temperature": 35.2,
      "vibration": 0.12
    },
    "location": {
      "latitude": 37.5665,
      "longitude": 126.9780
    }
  }
}
```

#### 알림 스트림
```json
{
  "type": "alert",
  "timestamp": "2024-01-26T14:30:25Z",
  "payload": {
    "alert_id": "alert_003",
    "vehicle_id": "HK-2024-001",
    "severity": "high",
    "type": "pressure_critical",
    "title": "타이어 압력 위험",
    "message": "앞 오른쪽 타이어 압력이 위험 수준입니다",
    "action_required": true
  }
}
```

## 📡 MQTT API

### 연결 정보
```yaml
MQTT Broker: mqtt.hankook-smartsensor.com
Port: 1883 (non-SSL), 8883 (SSL)
Protocol: MQTT 3.1.1 / 5.0
Authentication: Username/Password or Certificate
QoS Levels: 0, 1, 2 지원
```

### 토픽 구조
```
smarttire/smartsensor/
├── devices/
│   └── {device_id}/
│       ├── data              # 센서 데이터 발행
│       ├── status            # 디바이스 상태
│       └── commands          # 명령 수신
├── vehicles/
│   └── {vehicle_id}/
│       ├── sensors/
│       │   └── {sensor_type} # 센서별 데이터
│       ├── alerts            # 차량별 알림
│       └── location          # GPS 위치
└── system/
    ├── announcements         # 시스템 공지
    └── maintenance           # 유지보수 알림
```

### 센서 데이터 발행 (IoT 디바이스)
```javascript
const mqtt = require('mqtt');

const client = mqtt.connect('mqtts://mqtt.hankook-smartsensor.com:8883', {
  clientId: 'sensor_device_001',
  username: 'device_username',
  password: 'device_password',
  clean: true
});

// 센서 데이터 발행
const sensorData = {
  vehicle_id: 'HK-2024-001',
  sensor_id: 'TIRE_FL_001',
  timestamp: new Date().toISOString(),
  readings: {
    pressure: 32.5,
    temperature: 35.2,
    battery_level: 85
  }
};

client.publish(
  'smarttire/smartsensor/devices/sensor_device_001/data',
  JSON.stringify(sensorData),
  { qos: 1, retain: false }
);
```

### 알림 구독 (클라이언트 앱)
```javascript
const client = mqtt.connect('mqtts://mqtt.hankook-smartsensor.com:8883', {
  clientId: 'mobile_app_user123',
  username: 'app_username', 
  password: 'app_password'
});

// 특정 차량 알림 구독
client.subscribe('smarttire/smartsensor/vehicles/HK-2024-001/alerts', { qos: 1 });

// 시스템 공지 구독
client.subscribe('smarttire/smartsensor/system/announcements', { qos: 0 });

client.on('message', (topic, message) => {
  const data = JSON.parse(message.toString());
  console.log(`Topic: ${topic}`, data);
  
  if (topic.includes('/alerts')) {
    // 알림 처리 로직
    showNotification(data);
  }
});
```

## 📚 SDK 및 라이브러리

### JavaScript/TypeScript SDK

#### 설치
```bash
npm install @smarttire/smartsensor-sdk
```

#### 사용 예제
```typescript
import { SmartSensorAPI } from '@smarttire/smartsensor-sdk';

const api = new SmartSensorAPI({
  baseURL: 'https://api.hankook-smartsensor.com',
  apiKey: 'your_api_key',
  // 또는 OAuth2 토큰
  accessToken: 'your_access_token'
});

// 차량 목록 조회
const vehicles = await api.vehicles.list({
  status: 'active',
  limit: 20
});

// 실시간 센서 데이터 구독
api.realtime.subscribe('sensor_data', 'HK-2024-001', (data) => {
  console.log('새 센서 데이터:', data);
});

// 알림 생성
await api.alerts.create({
  vehicleId: 'HK-2024-001',
  type: 'maintenance_reminder',
  message: '정기 점검이 필요합니다'
});
```

### Python SDK

#### 설치
```bash
pip install hankook-smartsensor-sdk
```

#### 사용 예제
```python
from hankook_smartsensor import SmartSensorClient

client = SmartSensorClient(
    base_url='https://api.hankook-smartsensor.com',
    api_key='your_api_key'
)

# 차량 데이터 조회
vehicle = client.vehicles.get('HK-2024-001')
print(f"차량: {vehicle.make} {vehicle.model}")

# 센서 데이터 히스토리 조회
sensor_data = client.sensors.get_history(
    vehicle_id='HK-2024-001',
    sensor_type='pressure',
    start_time='2024-01-25T00:00:00Z',
    end_time='2024-01-26T00:00:00Z'
)

# 데이터 분석
import pandas as pd
df = pd.DataFrame(sensor_data)
print(f"평균 압력: {df['value'].mean():.2f} PSI")
```

### Java SDK

#### 설치 (Maven)
```xml
<dependency>
    <groupId>com.hankook</groupId>
    <artifactId>smartsensor-sdk</artifactId>
    <version>2.0.0</version>
</dependency>
```

#### 사용 예제
```java
import com.hankook.smartsensor.SmartSensorClient;
import com.hankook.smartsensor.model.*;

SmartSensorClient client = SmartSensorClient.builder()
    .baseUrl("https://api.hankook-smartsensor.com")
    .apiKey("your_api_key")
    .build();

// 차량 목록 조회
List<Vehicle> vehicles = client.vehicles()
    .list(VehicleQuery.builder()
        .status(VehicleStatus.ACTIVE)
        .limit(20)
        .build());

// 센서 데이터 조회
SensorDataResponse sensorData = client.sensors()
    .getData("HK-2024-001", SensorType.PRESSURE);

System.out.println("최근 압력: " + sensorData.getLatestValue() + " PSI");
```

### C# SDK

#### 설치 (NuGet)
```bash
Install-Package SmartTire.SmartSensor.SDK
```

#### 사용 예제
```csharp
using SmartTire.SmartSensor;

var client = new SmartSensorClient(new SmartSensorConfig
{
    BaseUrl = "https://api.hankook-smartsensor.com",
    ApiKey = "your_api_key"
});

// 차량 정보 조회
var vehicle = await client.Vehicles.GetAsync("HK-2024-001");
Console.WriteLine($"차량: {vehicle.Make} {vehicle.Model}");

// 실시간 알림 구독
client.Alerts.Subscribe(alert => 
{
    Console.WriteLine($"새 알림: {alert.Title}");
    
    if (alert.Severity == AlertSeverity.High)
    {
        // 긴급 알림 처리
        HandleCriticalAlert(alert);
    }
});
```

## ❌ 에러 처리

### HTTP 상태 코드

| 코드 | 의미 | 설명 |
|------|------|------|
| 200 | OK | 요청 성공 |
| 201 | Created | 리소스 생성 성공 |
| 204 | No Content | 성공, 응답 본문 없음 |
| 400 | Bad Request | 잘못된 요청 |
| 401 | Unauthorized | 인증 실패 |
| 403 | Forbidden | 권한 없음 |
| 404 | Not Found | 리소스 없음 |
| 409 | Conflict | 리소스 충돌 |
| 422 | Unprocessable Entity | 유효하지 않은 데이터 |
| 429 | Too Many Requests | 요청 한도 초과 |
| 500 | Internal Server Error | 서버 오류 |
| 503 | Service Unavailable | 서비스 이용 불가 |

### 에러 응답 형식

```json
{
  "error": {
    "code": "VEHICLE_NOT_FOUND",
    "message": "요청한 차량을 찾을 수 없습니다",
    "details": {
      "vehicle_id": "HK-2024-999",
      "searched_at": "2024-01-26T14:30:25Z"
    },
    "request_id": "req_20240126_143025_abc123",
    "timestamp": "2024-01-26T14:30:25Z"
  }
}
```

### 일반적인 에러 코드

#### 인증 관련
```json
{
  "error": {
    "code": "INVALID_TOKEN",
    "message": "유효하지 않은 액세스 토큰입니다",
    "details": {
      "token_expired": true,
      "expires_at": "2024-01-26T13:30:25Z"
    }
  }
}
```

#### 유효성 검사 오류
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "입력 데이터 유효성 검사 실패",
    "details": {
      "field_errors": [
        {
          "field": "vehicle_id",
          "message": "차량 ID는 필수입니다",
          "code": "REQUIRED"
        },
        {
          "field": "sensor_type",
          "message": "지원하지 않는 센서 타입입니다",
          "code": "INVALID_VALUE",
          "allowed_values": ["pressure", "temperature", "vibration"]
        }
      ]
    }
  }
}
```

#### 율 한도 초과
```json
{
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "API 호출 한도를 초과했습니다",
    "details": {
      "limit": 1000,
      "remaining": 0,
      "reset_time": "2024-01-26T15:00:00Z"
    }
  }
}
```

### SDK 에러 처리 예제

#### JavaScript
```javascript
try {
  const vehicle = await api.vehicles.get('HK-2024-001');
} catch (error) {
  if (error.code === 'VEHICLE_NOT_FOUND') {
    console.log('차량을 찾을 수 없습니다');
  } else if (error.code === 'UNAUTHORIZED') {
    // 토큰 갱신 로직
    await api.auth.refreshToken();
  } else {
    console.error('예상치 못한 오류:', error.message);
  }
}
```

#### Python
```python
from hankook_smartsensor.exceptions import (
    VehicleNotFoundError,
    AuthenticationError,
    RateLimitError
)

try:
    vehicle = client.vehicles.get('HK-2024-001')
except VehicleNotFoundError:
    print('차량을 찾을 수 없습니다')
except AuthenticationError:
    # 토큰 갱신
    client.auth.refresh_token()
except RateLimitError as e:
    print(f'요청 한도 초과. {e.reset_time}에 재시도하세요')
except Exception as e:
    print(f'예상치 못한 오류: {e}')
```

### 재시도 및 백오프 전략

#### 지수적 백오프 구현
```javascript
async function apiCallWithRetry(apiCall, maxRetries = 3) {
  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      return await apiCall();
    } catch (error) {
      if (attempt === maxRetries || !isRetryableError(error)) {
        throw error;
      }
      
      const delay = Math.pow(2, attempt) * 1000; // 2^attempt seconds
      await new Promise(resolve => setTimeout(resolve, delay));
    }
  }
}

function isRetryableError(error) {
  return [500, 502, 503, 504].includes(error.status) ||
         error.code === 'NETWORK_ERROR';
}

// 사용 예제
const vehicle = await apiCallWithRetry(() => 
  api.vehicles.get('HK-2024-001')
);
```

## 📞 API 지원

### 개발자 지원
- **API 문서**: https://docs.hankook-smartsensor.com/api
- **개발자 포럼**: https://forum.hankook-smartsensor.com
- **이메일 지원**: api-support@hankook-smartsensor.com
- **Slack 채널**: #api-support

### 테스트 환경
- **Sandbox API**: https://sandbox-api.hankook-smartsensor.com
- **테스트 데이터**: 샘플 차량 및 센서 데이터 제공
- **API 탐색기**: 브라우저에서 직접 API 테스트

### 버전 관리
- **현재 버전**: v2.0 (안정 버전)
- **레거시 지원**: v1.x는 2024년 12월까지 지원
- **API 변경 사항**: 주요 변경 시 3개월 전 공지
- **마이그레이션 가이드**: 버전 업그레이드 지원

---

**🚀 API를 활용하여 혁신적인 스마트 타이어 솔루션을 구축하세요!**

© 2024 SmartTire SmartSensor 2.0. All rights reserved.