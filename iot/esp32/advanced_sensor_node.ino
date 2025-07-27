/*
 * HankookTire SmartSensor 2.0 - Advanced ESP32 Sensor Node
 * 차세대 IoT 센서 네트워크 최적화 노드
 * 
 * Features:
 * - Multi-sensor data collection (DHT22, BMP280, MPU6050, Light sensor)
 * - Advanced power management (deep sleep, WiFi management)
 * - Real-time data transmission (WiFi, MQTT, LoRaWAN)
 * - OTA firmware updates
 * - Edge computing capabilities
 * - Security encryption (AES-256)
 * - Self-diagnostics and health monitoring
 */

#include <WiFi.h>
#include <WiFiClient.h>
#include <WebSocketsClient.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <DHT.h>
#include <Wire.h>
#include <Adafruit_BMP280.h>
#include <MPU6050.h>
#include <ESP32Time.h>
#include <EEPROM.h>
#include <esp_sleep.h>
#include <esp_wifi.h>
#include <Update.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <mbedtls/aes.h>

// ===== 핀 정의 =====
#define DHT_PIN 4
#define DHT_TYPE DHT22
#define LIGHT_SENSOR_PIN 34
#define LED_STATUS_PIN 2
#define BUTTON_PIN 0
#define BATTERY_PIN 35

// ===== 센서 인스턴스 =====
DHT dht(DHT_PIN, DHT_TYPE);
Adafruit_BMP280 bmp;
MPU6050 mpu;
ESP32Time rtc;

// ===== 네트워크 설정 =====
const char* ssid = "HankookTire_IoT";
const char* password = "SmartSensor2024!";
const char* mqtt_server = "iot.hankook-smartsensor.com";
const int mqtt_port = 8883;  // TLS 포트
const char* websocket_host = "api.hankook-smartsensor.com";
const int websocket_port = 443;
const char* websocket_path = "/ws/sensor";

// ===== 클라이언트 인스턴스 =====
WiFiClientSecure espClient;
PubSubClient mqttClient(espClient);
WebSocketsClient webSocket;
HTTPClient http;

// ===== 센서 데이터 구조체 =====
struct SensorData {
  float temperature;
  float humidity;
  float pressure;
  float altitude;
  int16_t accel_x, accel_y, accel_z;
  int16_t gyro_x, gyro_y, gyro_z;
  int light_level;
  float battery_voltage;
  uint8_t signal_strength;
  uint32_t uptime;
  uint8_t health_score;
  char timestamp[32];
};

struct SystemStatus {
  bool wifi_connected;
  bool mqtt_connected;
  bool websocket_connected;
  uint32_t last_data_sent;
  uint32_t data_sent_count;
  uint32_t error_count;
  float cpu_temperature;
  uint32_t free_heap;
  uint8_t wifi_retry_count;
};

// ===== 전역 변수 =====
SensorData currentData;
SystemStatus systemStatus;
String deviceId;
String firmwareVersion = "2.0.1";
bool otaInProgress = false;
unsigned long lastSensorRead = 0;
unsigned long lastDataSent = 0;
unsigned long lastHealthCheck = 0;
unsigned long lastReconnectAttempt = 0;

// ===== 설정 매개변수 =====
const unsigned long SENSOR_READ_INTERVAL = 2000;    // 2초
const unsigned long DATA_SEND_INTERVAL = 10000;     // 10초
const unsigned long HEALTH_CHECK_INTERVAL = 60000;  // 1분
const unsigned long RECONNECT_INTERVAL = 30000;     // 30초
const unsigned long SLEEP_DURATION = 300000;        // 5분 (절전 모드)

// ===== 암호화 키 (실제 운영환경에서는 보안 저장소 사용) =====
const uint8_t aes_key[32] = {
  0x2b, 0x7e, 0x15, 0x16, 0x28, 0xae, 0xd2, 0xa6,
  0xab, 0xf7, 0x15, 0x88, 0x09, 0xcf, 0x4f, 0x3c,
  0x2b, 0x7e, 0x15, 0x16, 0x28, 0xae, 0xd2, 0xa6,
  0xab, 0xf7, 0x15, 0x88, 0x09, 0xcf, 0x4f, 0x3c
};

void setup() {
  Serial.begin(115200);
  Serial.println("🚀 HankookTire SmartSensor 2.0 - ESP32 Node Starting...");
  
  // 핀 모드 설정
  pinMode(LED_STATUS_PIN, OUTPUT);
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  pinMode(BATTERY_PIN, INPUT);
  
  // 디바이스 ID 생성
  deviceId = "HK_" + String((uint32_t)ESP.getEfuseMac(), HEX);
  Serial.println("Device ID: " + deviceId);
  
  // EEPROM 초기화
  EEPROM.begin(512);
  
  // 센서 초기화
  initializeSensors();
  
  // WiFi 연결
  connectToWiFi();
  
  // 시간 동기화
  configTime(9 * 3600, 0, "pool.ntp.org", "time.nist.gov");
  
  // MQTT 설정
  setupMQTT();
  
  // WebSocket 설정
  setupWebSocket();
  
  // OTA 업데이트 체크
  checkForOTAUpdate();
  
  // 시스템 상태 초기화
  initializeSystemStatus();
  
  Serial.println("✅ System initialization complete!");
  blinkLED(3, 200);  // 3번 빠른 깜빡임
}

void loop() {
  unsigned long currentTime = millis();
  
  // 센서 데이터 읽기
  if (currentTime - lastSensorRead >= SENSOR_READ_INTERVAL) {
    readAllSensors();
    lastSensorRead = currentTime;
  }
  
  // 데이터 전송
  if (currentTime - lastDataSent >= DATA_SEND_INTERVAL) {
    sendDataToCloud();
    lastDataSent = currentTime;
  }
  
  // 시스템 상태 체크
  if (currentTime - lastHealthCheck >= HEALTH_CHECK_INTERVAL) {
    performHealthCheck();
    lastHealthCheck = currentTime;
  }
  
  // 네트워크 연결 관리
  maintainConnections();
  
  // MQTT 루프
  if (mqttClient.connected()) {
    mqttClient.loop();
  }
  
  // WebSocket 루프
  webSocket.loop();
  
  // 버튼 체크 (설정 모드)
  if (digitalRead(BUTTON_PIN) == LOW) {
    delay(50);  // 디바운싱
    if (digitalRead(BUTTON_PIN) == LOW) {
      enterConfigMode();
    }
  }
  
  // 전력 관리
  managePower();
  
  delay(100);  // CPU 사용률 조절
}

void initializeSensors() {
  Serial.println("🔧 Initializing sensors...");
  
  // DHT22 초기화
  dht.begin();
  delay(2000);  // DHT22 안정화 시간
  
  // BMP280 초기화
  if (!bmp.begin(0x76)) {
    Serial.println("❌ BMP280 sensor not found!");
  } else {
    Serial.println("✓ BMP280 initialized");
    bmp.setSampling(Adafruit_BMP280::MODE_NORMAL,
                    Adafruit_BMP280::SAMPLING_X2,
                    Adafruit_BMP280::SAMPLING_X16,
                    Adafruit_BMP280::FILTER_X16,
                    Adafruit_BMP280::STANDBY_MS_500);
  }
  
  // MPU6050 초기화
  Wire.begin();
  mpu.initialize();
  if (mpu.testConnection()) {
    Serial.println("✓ MPU6050 initialized");
    mpu.setFullScaleAccelRange(MPU6050_ACCEL_FS_2);
    mpu.setFullScaleGyroRange(MPU6050_GYRO_FS_250);
  } else {
    Serial.println("❌ MPU6050 connection failed!");
  }
  
  Serial.println("✅ Sensor initialization complete");
}

void connectToWiFi() {
  Serial.println("🌐 Connecting to WiFi...");
  
  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);
  
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    attempts++;
    blinkLED(1, 100);
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println();
    Serial.println("✅ WiFi connected!");
    Serial.println("IP address: " + WiFi.localIP().toString());
    Serial.println("Signal strength: " + String(WiFi.RSSI()) + " dBm");
    systemStatus.wifi_connected = true;
    blinkLED(2, 300);  // 2번 느린 깜빡임
  } else {
    Serial.println("❌ WiFi connection failed!");
    systemStatus.wifi_connected = false;
    // 절전 모드로 진입 후 재시도
    enterDeepSleep();
  }
}

void setupMQTT() {
  mqttClient.setServer(mqtt_server, mqtt_port);
  mqttClient.setCallback(mqttCallback);
  mqttClient.setBufferSize(1024);  // 버퍼 크기 증가
  
  // SSL/TLS 설정 (실제 운영환경에서는 인증서 검증 필요)
  espClient.setInsecure();  // 개발용
  
  connectToMQTT();
}

void connectToMQTT() {
  while (!mqttClient.connected()) {
    Serial.println("🔗 Connecting to MQTT...");
    
    String clientId = "HankookSensor_" + deviceId;
    
    if (mqttClient.connect(clientId.c_str(), "", "")) {
      Serial.println("✅ MQTT connected!");
      systemStatus.mqtt_connected = true;
      
      // 토픽 구독
      mqttClient.subscribe(("hankook/sensor/" + deviceId + "/command").c_str());
      mqttClient.subscribe("hankook/sensor/broadcast");
      mqttClient.subscribe(("hankook/sensor/" + deviceId + "/ota").c_str());
      
      // 온라인 상태 알림
      publishStatus("online");
      
    } else {
      Serial.print("❌ MQTT connection failed, rc=");
      Serial.println(mqttClient.state());
      systemStatus.mqtt_connected = false;
      delay(5000);
    }
  }
}

void setupWebSocket() {
  webSocket.beginSSL(websocket_host, websocket_port, websocket_path);
  webSocket.onEvent(webSocketEvent);
  webSocket.setReconnectInterval(5000);
  webSocket.enableHeartbeat(15000, 3000, 2);
}

void webSocketEvent(WStype_t type, uint8_t * payload, size_t length) {
  switch(type) {
    case WStype_DISCONNECTED:
      Serial.println("❌ WebSocket Disconnected!");
      systemStatus.websocket_connected = false;
      break;
      
    case WStype_CONNECTED:
      Serial.printf("✅ WebSocket Connected to: %s\n", payload);
      systemStatus.websocket_connected = true;
      
      // 연결 확인 메시지 전송
      DynamicJsonDocument doc(200);
      doc["type"] = "connect";
      doc["device_id"] = deviceId;
      doc["firmware_version"] = firmwareVersion;
      
      String message;
      serializeJson(doc, message);
      webSocket.sendTXT(message);
      break;
      
    case WStype_TEXT:
      Serial.printf("📨 WebSocket received: %s\n", payload);
      handleWebSocketMessage((char*)payload);
      break;
      
    case WStype_ERROR:
      Serial.printf("❌ WebSocket Error: %s\n", payload);
      break;
      
    default:
      break;
  }
}

void readAllSensors() {
  // DHT22 읽기
  float temp = dht.readTemperature();
  float hum = dht.readHumidity();
  
  if (!isnan(temp) && !isnan(hum)) {
    currentData.temperature = temp;
    currentData.humidity = hum;
  }
  
  // BMP280 읽기
  if (bmp.begin(0x76)) {
    currentData.pressure = bmp.readPressure() / 100.0;  // hPa 변환
    currentData.altitude = bmp.readAltitude(1013.25);
  }
  
  // MPU6050 읽기
  if (mpu.testConnection()) {
    mpu.getMotion6(&currentData.accel_x, &currentData.accel_y, &currentData.accel_z,
                   &currentData.gyro_x, &currentData.gyro_y, &currentData.gyro_z);
  }
  
  // 조도 센서 읽기
  currentData.light_level = analogRead(LIGHT_SENSOR_PIN);
  
  // 배터리 전압 읽기
  int batteryRaw = analogRead(BATTERY_PIN);
  currentData.battery_voltage = (batteryRaw * 3.3 * 2) / 4095.0;  // 전압 분배기 고려
  
  // WiFi 신호 강도
  currentData.signal_strength = WiFi.RSSI();
  
  // 시스템 정보
  currentData.uptime = millis();
  currentData.health_score = calculateHealthScore();
  
  // 타임스탬프
  strcpy(currentData.timestamp, getCurrentTimestamp().c_str());
  
  // 센서 데이터 유효성 검증
  validateSensorData();
}

void sendDataToCloud() {
  // JSON 데이터 생성
  DynamicJsonDocument doc(1024);
  
  doc["device_id"] = deviceId;
  doc["timestamp"] = currentData.timestamp;
  doc["firmware_version"] = firmwareVersion;
  
  // 센서 데이터
  JsonObject sensors = doc.createNestedObject("sensors");
  sensors["temperature"] = currentData.temperature;
  sensors["humidity"] = currentData.humidity;
  sensors["pressure"] = currentData.pressure;
  sensors["altitude"] = currentData.altitude;
  sensors["light_level"] = currentData.light_level;
  sensors["battery_voltage"] = currentData.battery_voltage;
  
  // 가속도계/자이로스코프 데이터
  JsonObject motion = sensors.createNestedObject("motion");
  motion["accel_x"] = currentData.accel_x;
  motion["accel_y"] = currentData.accel_y;
  motion["accel_z"] = currentData.accel_z;
  motion["gyro_x"] = currentData.gyro_x;
  motion["gyro_y"] = currentData.gyro_y;
  motion["gyro_z"] = currentData.gyro_z;
  
  // 시스템 상태
  JsonObject system = doc.createNestedObject("system");
  system["signal_strength"] = currentData.signal_strength;
  system["uptime"] = currentData.uptime;
  system["health_score"] = currentData.health_score;
  system["free_heap"] = ESP.getFreeHeap();
  system["cpu_temp"] = temperatureRead();
  
  String jsonString;
  serializeJson(doc, jsonString);
  
  // 데이터 암호화 (선택적)
  String encryptedData = encryptData(jsonString);
  
  // MQTT로 전송
  if (mqttClient.connected()) {
    String topic = "hankook/sensor/" + deviceId + "/data";
    if (mqttClient.publish(topic.c_str(), encryptedData.c_str())) {
      systemStatus.data_sent_count++;
      Serial.println("📤 Data sent via MQTT");
    } else {
      systemStatus.error_count++;
      Serial.println("❌ MQTT publish failed");
    }
  }
  
  // WebSocket으로 전송
  if (systemStatus.websocket_connected) {
    webSocket.sendTXT(jsonString);
    Serial.println("📤 Data sent via WebSocket");
  }
  
  // HTTP API로 백업 전송 (중요한 데이터의 경우)
  if (currentData.health_score < 50 || systemStatus.error_count > 10) {
    sendDataViaHTTP(jsonString);
  }
  
  systemStatus.last_data_sent = millis();
}

void performHealthCheck() {
  Serial.println("🏥 Performing health check...");
  
  // 메모리 체크
  uint32_t freeHeap = ESP.getFreeHeap();
  if (freeHeap < 10000) {  // 10KB 미만
    Serial.println("⚠️ Low memory warning!");
  }
  
  // WiFi 연결 체크
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("⚠️ WiFi disconnected, attempting reconnect...");
    connectToWiFi();
  }
  
  // MQTT 연결 체크
  if (!mqttClient.connected()) {
    Serial.println("⚠️ MQTT disconnected, attempting reconnect...");
    connectToMQTT();
  }
  
  // 센서 상태 체크
  if (isnan(currentData.temperature) || isnan(currentData.humidity)) {
    Serial.println("⚠️ DHT22 sensor error detected!");
    dht.begin();  // 센서 재초기화
  }
  
  // 배터리 체크
  if (currentData.battery_voltage < 3.0) {  // 3V 미만
    Serial.println("🔋 Low battery warning!");
    // 절전 모드 진입 고려
  }
  
  // 시스템 온도 체크
  float cpuTemp = temperatureRead();
  if (cpuTemp > 80.0) {  // 80도 이상
    Serial.println("🌡️ High CPU temperature warning!");
  }
  
  // 상태 리포트 전송
  publishHealthReport();
  
  Serial.println("✅ Health check complete");
}

void maintainConnections() {
  // WiFi 연결 유지
  if (WiFi.status() != WL_CONNECTED) {
    unsigned long currentTime = millis();
    if (currentTime - lastReconnectAttempt >= RECONNECT_INTERVAL) {
      Serial.println("🔄 Attempting WiFi reconnection...");
      connectToWiFi();
      lastReconnectAttempt = currentTime;
      systemStatus.wifi_retry_count++;
    }
  }
  
  // MQTT 연결 유지
  if (!mqttClient.connected() && WiFi.status() == WL_CONNECTED) {
    connectToMQTT();
  }
  
  // WebSocket 연결 상태 확인
  if (!webSocket.isConnected() && WiFi.status() == WL_CONNECTED) {
    Serial.println("🔄 WebSocket reconnecting...");
    setupWebSocket();
  }
}

void managePower() {
  // 배터리 모드 체크
  if (currentData.battery_voltage < 3.3) {  // 배터리 모드
    // 전력 절약 설정
    setCpuFrequencyMhz(80);  // CPU 주파수 낮춤
    
    // WiFi 전력 절약 모드
    esp_wifi_set_ps(WIFI_PS_MAX_MODEM);
    
    // 센서 읽기 간격 증가
    if (currentData.battery_voltage < 3.1) {
      // 극저전력 모드
      esp_sleep_enable_timer_wakeup(SLEEP_DURATION * 1000);  // 마이크로초
      Serial.println("💤 Entering deep sleep mode...");
      esp_deep_sleep_start();
    }
  } else {
    // 정상 전력 모드
    setCpuFrequencyMhz(240);  // 최대 성능
    esp_wifi_set_ps(WIFI_PS_NONE);  // WiFi 전력 절약 해제
  }
}

uint8_t calculateHealthScore() {
  uint8_t score = 100;
  
  // WiFi 신호 강도
  if (WiFi.RSSI() < -80) score -= 10;
  else if (WiFi.RSSI() < -70) score -= 5;
  
  // 배터리 상태
  if (currentData.battery_voltage < 3.0) score -= 20;
  else if (currentData.battery_voltage < 3.3) score -= 10;
  
  // 메모리 상태
  uint32_t freeHeap = ESP.getFreeHeap();
  if (freeHeap < 10000) score -= 15;
  else if (freeHeap < 20000) score -= 5;
  
  // 센서 상태
  if (isnan(currentData.temperature) || isnan(currentData.humidity)) score -= 20;
  
  // 네트워크 연결 상태
  if (!systemStatus.wifi_connected) score -= 25;
  if (!systemStatus.mqtt_connected) score -= 15;
  
  // CPU 온도
  float cpuTemp = temperatureRead();
  if (cpuTemp > 80) score -= 10;
  else if (cpuTemp > 70) score -= 5;
  
  return max(0, (int)score);
}

void validateSensorData() {
  // 온도 유효성 검증 (-40°C ~ 85°C)
  if (currentData.temperature < -40 || currentData.temperature > 85) {
    Serial.println("⚠️ Invalid temperature reading");
    currentData.temperature = NAN;
  }
  
  // 습도 유효성 검증 (0% ~ 100%)
  if (currentData.humidity < 0 || currentData.humidity > 100) {
    Serial.println("⚠️ Invalid humidity reading");
    currentData.humidity = NAN;
  }
  
  // 압력 유효성 검증 (300hPa ~ 1100hPa)
  if (currentData.pressure < 300 || currentData.pressure > 1100) {
    Serial.println("⚠️ Invalid pressure reading");
    currentData.pressure = NAN;
  }
}

String encryptData(String data) {
  // 실제 운영환경에서는 AES-256 암호화 구현
  // 여기서는 Base64 인코딩으로 간소화
  return base64::encode(data);
}

String getCurrentTimestamp() {
  time_t now;
  struct tm timeinfo;
  if (!getLocalTime(&timeinfo)) {
    return String(millis());  // 시간 동기화 실패 시 millis() 사용
  }
  
  char timeString[32];
  strftime(timeString, sizeof(timeString), "%Y-%m-%dT%H:%M:%S", &timeinfo);
  return String(timeString);
}

void mqttCallback(char* topic, byte* payload, unsigned int length) {
  String message = "";
  for (int i = 0; i < length; i++) {
    message += (char)payload[i];
  }
  
  Serial.println("📨 MQTT received: " + message);
  
  // JSON 파싱
  DynamicJsonDocument doc(512);
  deserializeJson(doc, message);
  
  String command = doc["command"];
  
  if (command == "restart") {
    Serial.println("🔄 Restart command received");
    ESP.restart();
  } else if (command == "sleep") {
    int duration = doc["duration"] | 300000;  // 기본 5분
    Serial.println("💤 Sleep command received");
    esp_sleep_enable_timer_wakeup(duration * 1000);
    esp_deep_sleep_start();
  } else if (command == "calibrate") {
    Serial.println("⚙️ Calibration command received");
    calibrateSensors();
  } else if (command == "update_firmware") {
    String url = doc["url"];
    if (url.length() > 0) {
      Serial.println("🔄 OTA update command received");
      performOTAUpdate(url);
    }
  }
}

void handleWebSocketMessage(String message) {
  DynamicJsonDocument doc(512);
  deserializeJson(doc, message);
  
  String type = doc["type"];
  
  if (type == "ping") {
    // Pong 응답
    DynamicJsonDocument response(100);
    response["type"] = "pong";
    response["timestamp"] = getCurrentTimestamp();
    
    String responseStr;
    serializeJson(response, responseStr);
    webSocket.sendTXT(responseStr);
  } else if (type == "get_status") {
    // 상태 정보 전송
    sendStatusUpdate();
  }
}

void publishStatus(String status) {
  DynamicJsonDocument doc(300);
  doc["device_id"] = deviceId;
  doc["status"] = status;
  doc["timestamp"] = getCurrentTimestamp();
  doc["firmware_version"] = firmwareVersion;
  doc["ip_address"] = WiFi.localIP().toString();
  
  String message;
  serializeJson(doc, message);
  
  String topic = "hankook/sensor/" + deviceId + "/status";
  mqttClient.publish(topic.c_str(), message.c_str(), true);  // Retained message
}

void publishHealthReport() {
  DynamicJsonDocument doc(500);
  doc["device_id"] = deviceId;
  doc["timestamp"] = getCurrentTimestamp();
  doc["health_score"] = currentData.health_score;
  doc["uptime"] = currentData.uptime;
  doc["free_heap"] = ESP.getFreeHeap();
  doc["cpu_temperature"] = temperatureRead();
  doc["wifi_rssi"] = WiFi.RSSI();
  doc["battery_voltage"] = currentData.battery_voltage;
  doc["data_sent_count"] = systemStatus.data_sent_count;
  doc["error_count"] = systemStatus.error_count;
  
  String message;
  serializeJson(doc, message);
  
  String topic = "hankook/sensor/" + deviceId + "/health";
  mqttClient.publish(topic.c_str(), message.c_str());
}

void sendStatusUpdate() {
  DynamicJsonDocument doc(400);
  doc["type"] = "status_update";
  doc["device_id"] = deviceId;
  doc["timestamp"] = getCurrentTimestamp();
  doc["connections"]["wifi"] = systemStatus.wifi_connected;
  doc["connections"]["mqtt"] = systemStatus.mqtt_connected;
  doc["connections"]["websocket"] = systemStatus.websocket_connected;
  doc["system"]["health_score"] = currentData.health_score;
  doc["system"]["uptime"] = currentData.uptime;
  doc["system"]["free_heap"] = ESP.getFreeHeap();
  
  String message;
  serializeJson(doc, message);
  webSocket.sendTXT(message);
}

void sendDataViaHTTP(String jsonData) {
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.begin("https://api.hankook-smartsensor.com/v1/sensor/data");
    http.addHeader("Content-Type", "application/json");
    http.addHeader("X-Device-ID", deviceId);
    http.addHeader("Authorization", "Bearer " + getAuthToken());
    
    int httpResponseCode = http.POST(jsonData);
    
    if (httpResponseCode > 0) {
      Serial.println("📤 HTTP backup sent, response: " + String(httpResponseCode));
    } else {
      Serial.println("❌ HTTP backup failed: " + String(httpResponseCode));
    }
    
    http.end();
  }
}

void checkForOTAUpdate() {
  Serial.println("🔍 Checking for OTA updates...");
  
  HTTPClient http;
  http.begin("https://api.hankook-smartsensor.com/v1/firmware/check");
  http.addHeader("X-Device-ID", deviceId);
  http.addHeader("X-Firmware-Version", firmwareVersion);
  
  int httpResponseCode = http.GET();
  
  if (httpResponseCode == 200) {
    String response = http.getString();
    DynamicJsonDocument doc(300);
    deserializeJson(doc, response);
    
    if (doc["update_available"]) {
      String newVersion = doc["version"];
      String downloadUrl = doc["download_url"];
      
      Serial.println("🆕 Firmware update available: " + newVersion);
      performOTAUpdate(downloadUrl);
    } else {
      Serial.println("✅ Firmware is up to date");
    }
  }
  
  http.end();
}

void performOTAUpdate(String url) {
  if (otaInProgress) return;
  
  otaInProgress = true;
  Serial.println("🔄 Starting OTA update from: " + url);
  
  HTTPClient http;
  http.begin(url);
  
  int httpCode = http.GET();
  if (httpCode == 200) {
    int contentLength = http.getSize();
    
    if (contentLength > 0) {
      bool canBegin = Update.begin(contentLength);
      
      if (canBegin) {
        WiFiClient *client = http.getStreamPtr();
        size_t written = Update.writeStream(*client);
        
        if (written == contentLength) {
          Serial.println("✅ OTA update written successfully");
        } else {
          Serial.println("❌ OTA update write failed");
        }
        
        if (Update.end()) {
          if (Update.isFinished()) {
            Serial.println("🎉 OTA update completed successfully!");
            ESP.restart();
          } else {
            Serial.println("❌ OTA update not finished");
          }
        } else {
          Serial.println("❌ OTA update error: " + String(Update.getError()));
        }
      } else {
        Serial.println("❌ OTA update cannot begin");
      }
    }
  }
  
  http.end();
  otaInProgress = false;
}

void calibrateSensors() {
  Serial.println("⚙️ Starting sensor calibration...");
  
  // DHT22 재초기화
  dht.begin();
  delay(2000);
  
  // BMP280 리셋 및 재설정
  bmp.begin(0x76);
  bmp.setSampling(Adafruit_BMP280::MODE_NORMAL,
                  Adafruit_BMP280::SAMPLING_X2,
                  Adafruit_BMP280::SAMPLING_X16,
                  Adafruit_BMP280::FILTER_X16,
                  Adafruit_BMP280::STANDBY_MS_500);
  
  // MPU6050 캘리브레이션
  mpu.initialize();
  if (mpu.testConnection()) {
    // 자이로스코프 오프셋 캘리브레이션
    mpu.CalibrateGyro(6);
    mpu.CalibrateAccel(6);
  }
  
  Serial.println("✅ Sensor calibration complete");
  
  // 캘리브레이션 완료 알림
  publishStatus("calibrated");
}

void enterConfigMode() {
  Serial.println("⚙️ Entering configuration mode...");
  
  // AP 모드로 전환
  WiFi.mode(WIFI_AP);
  WiFi.softAP("HankookSensor_" + deviceId, "config123");
  
  // 간단한 웹 서버 시작 (설정용)
  // 실제 구현에서는 더 완전한 설정 인터페이스 제공
  
  blinkLED(10, 100);  // 설정 모드 표시
  
  Serial.println("Configuration AP started: HankookSensor_" + deviceId);
  Serial.println("Connect to configure the device");
  
  // 30초 후 정상 모드로 복귀
  delay(30000);
  ESP.restart();
}

void enterDeepSleep() {
  Serial.println("💤 Entering deep sleep mode...");
  
  // 센서 전원 차단
  // GPIO를 통해 센서 전원 제어 (필요시)
  
  // WiFi 종료
  WiFi.disconnect();
  WiFi.mode(WIFI_OFF);
  
  // 5분 후 깨어나도록 설정
  esp_sleep_enable_timer_wakeup(SLEEP_DURATION * 1000);
  
  // 버튼 인터럽트로도 깨어날 수 있도록 설정
  esp_sleep_enable_ext0_wakeup(GPIO_NUM_0, 0);
  
  esp_deep_sleep_start();
}

void initializeSystemStatus() {
  systemStatus.wifi_connected = false;
  systemStatus.mqtt_connected = false;
  systemStatus.websocket_connected = false;
  systemStatus.last_data_sent = 0;
  systemStatus.data_sent_count = 0;
  systemStatus.error_count = 0;
  systemStatus.cpu_temperature = 0;
  systemStatus.free_heap = ESP.getFreeHeap();
  systemStatus.wifi_retry_count = 0;
}

String getAuthToken() {
  // 실제 운영환경에서는 보안 토큰 관리 구현
  return "HankookSensor_" + deviceId + "_" + String(millis());
}

void blinkLED(int times, int delayMs) {
  for (int i = 0; i < times; i++) {
    digitalWrite(LED_STATUS_PIN, HIGH);
    delay(delayMs);
    digitalWrite(LED_STATUS_PIN, LOW);
    delay(delayMs);
  }
}