import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:fl_chart/fl_chart.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:provider/provider.dart';
import 'dart:convert';
import 'dart:async';
import '../services/sensor_service.dart';
import '../services/websocket_service.dart';
import '../widgets/tire_card.dart';
import '../widgets/sensor_chart.dart';
import '../widgets/ai_analysis_card.dart';
import '../widgets/alert_list.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({Key? key}) : super(key: key);

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen>
    with TickerProviderStateMixin {
  late TabController _tabController;
  late AnimationController _animationController;
  late Animation<double> _fadeAnimation;
  
  Timer? _updateTimer;
  bool _isLoading = true;
  DateTime _lastUpdate = DateTime.now();

  // 데이터 상태
  Map<String, dynamic> _sensorData = {};
  List<TireData> _tpmsData = [];
  Map<String, dynamic> _aiAnalysis = {};
  Map<String, dynamic> _systemHealth = {};
  List<AlertData> _alerts = [];

  @override
  void initState() {
    super.initState();
    
    _tabController = TabController(length: 4, vsync: this);
    _animationController = AnimationController(
      duration: const Duration(milliseconds: 1000),
      vsync: this,
    );
    
    _fadeAnimation = Tween<double>(
      begin: 0.0,
      end: 1.0,
    ).animate(CurvedAnimation(
      parent: _animationController,
      curve: Curves.easeInOut,
    ));

    _initializeData();
    _startPeriodicUpdates();
    _animationController.forward();
  }

  @override
  void dispose() {
    _tabController.dispose();
    _animationController.dispose();
    _updateTimer?.cancel();
    super.dispose();
  }

  Future<void> _initializeData() async {
    try {
      final sensorService = Provider.of<SensorService>(context, listen: false);
      final websocketService = Provider.of<WebSocketService>(context, listen: false);
      
      // WebSocket 연결
      await websocketService.connect();
      
      // 초기 데이터 로드
      await _loadInitialData();
      
      // WebSocket 메시지 리스너 설정
      websocketService.messageStream.listen(_handleWebSocketMessage);
      
      setState(() {
        _isLoading = false;
      });
      
    } catch (e) {
      print('초기화 오류: $e');
      setState(() {
        _isLoading = false;
      });
    }
  }

  Future<void> _loadInitialData() async {
    final sensorService = Provider.of<SensorService>(context, listen: false);
    
    try {
      final data = await sensorService.getSensorData();
      setState(() {
        _sensorData = data;
        _lastUpdate = DateTime.now();
      });
    } catch (e) {
      print('데이터 로드 오류: $e');
    }
  }

  void _handleWebSocketMessage(Map<String, dynamic> message) {
    if (!mounted) return;
    
    setState(() {
      switch (message['type']) {
        case 'sensor_update':
          _sensorData = message['data'] ?? {};
          _lastUpdate = DateTime.now();
          break;
        case 'ai_analysis':
          _aiAnalysis = message;
          break;
        case 'health_status':
          _systemHealth = message;
          break;
        case 'tpms_update':
          _updateTpmsData(message['data']);
          break;
        case 'alert':
          _addAlert(message);
          break;
      }
    });
  }

  void _updateTpmsData(Map<String, dynamic> data) {
    _tpmsData = (data['tires'] as List? ?? [])
        .map((tire) => TireData.fromJson(tire))
        .toList();
  }

  void _addAlert(Map<String, dynamic> alertData) {
    final alert = AlertData.fromJson(alertData);
    _alerts.insert(0, alert);
    if (_alerts.length > 10) {
      _alerts = _alerts.take(10).toList();
    }
  }

  void _startPeriodicUpdates() {
    _updateTimer = Timer.periodic(const Duration(seconds: 5), (timer) {
      _requestDataUpdate();
    });
  }

  void _requestDataUpdate() {
    final websocketService = Provider.of<WebSocketService>(context, listen: false);
    websocketService.sendMessage({
      'type': 'command',
      'command': 'get_sensor_data'
    });
  }

  Future<void> _refreshData() async {
    HapticFeedback.lightImpact();
    await _loadInitialData();
    _requestDataUpdate();
  }

  @override
  Widget build(BuildContext context) {
    if (_isLoading) {
      return const Scaffold(
        body: Center(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              CircularProgressIndicator(
                valueColor: AlwaysStoppedAnimation<Color>(Colors.orange),
              ),
              SizedBox(height: 16),
              Text(
                '시스템 초기화 중...',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.w500),
              ),
            ],
          ),
        ),
      );
    }

    return Scaffold(
      backgroundColor: Colors.grey[100],
      appBar: AppBar(
        title: const Text(
          '🚀 HankookTire SmartSensor 2.0',
          style: TextStyle(fontWeight: FontWeight.bold),
        ),
        backgroundColor: Colors.white,
        foregroundColor: Colors.black87,
        elevation: 0,
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _refreshData,
          ),
          IconButton(
            icon: const Icon(Icons.settings),
            onPressed: () {
              Navigator.pushNamed(context, '/settings');
            },
          ),
        ],
        bottom: TabBar(
          controller: _tabController,
          labelColor: Colors.orange,
          unselectedLabelColor: Colors.grey,
          indicatorColor: Colors.orange,
          tabs: const [
            Tab(icon: Icon(Icons.dashboard), text: '대시보드'),
            Tab(icon: Icon(Icons.tire_repair), text: 'TPMS'),
            Tab(icon: Icon(Icons.analytics), text: 'AI 분석'),
            Tab(icon: Icon(Icons.notifications), text: '알림'),
          ],
        ),
      ),
      body: FadeTransition(
        opacity: _fadeAnimation,
        child: TabBarView(
          controller: _tabController,
          children: [
            _buildDashboardTab(),
            _buildTpmsTab(),
            _buildAiAnalysisTab(),
            _buildAlertsTab(),
          ],
        ),
      ),
    );
  }

  Widget _buildDashboardTab() {
    return RefreshIndicator(
      onRefresh: _refreshData,
      color: Colors.orange,
      child: SingleChildScrollView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // 상태 카드들
            _buildStatusCards(),
            const SizedBox(height: 20),
            
            // 센서 데이터 차트
            _buildSensorChart(),
            const SizedBox(height: 20),
            
            // 예측 정비 정보
            _buildMaintenanceInfo(),
            const SizedBox(height: 20),
            
            // 시스템 상태
            _buildSystemStatus(),
          ],
        ),
      ),
    );
  }

  Widget _buildStatusCards() {
    return Row(
      children: [
        Expanded(
          child: _buildStatusCard(
            '활성 센서',
            '${_sensorData.length}',
            Icons.sensors,
            Colors.blue,
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: _buildStatusCard(
            'AI 신뢰도',
            '${((_aiAnalysis['confidence'] ?? 0.85) * 100).round()}%',
            Icons.psychology,
            Colors.green,
          ),
        ),
      ],
    );
  }

  Widget _buildStatusCard(String title, String value, IconData icon, Color color) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.05),
            blurRadius: 10,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                title,
                style: const TextStyle(
                  fontSize: 14,
                  color: Colors.grey,
                  fontWeight: FontWeight.w500,
                ),
              ),
              Icon(icon, color: color, size: 24),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            value,
            style: TextStyle(
              fontSize: 24,
              fontWeight: FontWeight.bold,
              color: color,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSensorChart() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.05),
            blurRadius: 10,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            '센서 데이터 트렌드',
            style: TextStyle(
              fontSize: 18,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 16),
          SizedBox(
            height: 200,
            child: SensorChart(
              temperatureData: _generateChartData(),
              humidityData: _generateChartData(),
            ),
          ),
        ],
      ),
    );
  }

  List<FlSpot> _generateChartData() {
    return List.generate(10, (index) {
      return FlSpot(index.toDouble(), 20 + (index * 2) + (index % 3) * 5);
    });
  }

  Widget _buildMaintenanceInfo() {
    final daysRemaining = _aiAnalysis['maintenance']?['days_remaining'] ?? 90;
    final confidence = (_aiAnalysis['maintenance']?['confidence'] ?? 0.95) * 100;
    
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.05),
            blurRadius: 10,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            '예측 정비 정보',
            style: TextStyle(
              fontSize: 18,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                child: _buildMaintenanceItem(
                  '정비까지',
                  '$daysRemaining일',
                  Icons.schedule,
                  Colors.orange,
                ),
              ),
              Expanded(
                child: _buildMaintenanceItem(
                  '예측 정확도',
                  '${confidence.round()}%',
                  Icons.accuracy,
                  Colors.green,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: _buildMaintenanceItem(
                  '예상 비용',
                  '₩150,000',
                  Icons.attach_money,
                  Colors.red,
                ),
              ),
              Expanded(
                child: _buildMaintenanceItem(
                  '정비 유형',
                  '정기점검',
                  Icons.build,
                  Colors.blue,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildMaintenanceItem(String title, String value, IconData icon, Color color) {
    return Container(
      padding: const EdgeInsets.all(12),
      margin: const EdgeInsets.only(right: 8),
      decoration: BoxDecoration(
        color: color.withOpacity(0.1),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        children: [
          Icon(icon, color: color, size: 24),
          const SizedBox(height: 4),
          Text(
            title,
            style: const TextStyle(
              fontSize: 12,
              color: Colors.grey,
            ),
          ),
          Text(
            value,
            style: TextStyle(
              fontSize: 16,
              fontWeight: FontWeight.bold,
              color: color,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSystemStatus() {
    final cpuUsage = _systemHealth['cpu_percent'] ?? 15.0;
    final memoryUsage = _systemHealth['memory_percent'] ?? 65.0;
    final status = _systemHealth['status'] ?? 'healthy';
    
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.05),
            blurRadius: 10,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text(
                '시스템 상태',
                style: TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: status == 'healthy' ? Colors.green : Colors.orange,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Text(
                  status == 'healthy' ? '정상' : '점검 필요',
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 12,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          _buildProgressItem('CPU 사용률', cpuUsage, '%', Colors.blue),
          const SizedBox(height: 12),
          _buildProgressItem('메모리 사용률', memoryUsage, '%', Colors.orange),
          const SizedBox(height: 12),
          Text(
            '마지막 업데이트: ${_formatLastUpdate()}',
            style: const TextStyle(
              fontSize: 12,
              color: Colors.grey,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildProgressItem(String title, double value, String unit, Color color) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(
              title,
              style: const TextStyle(
                fontSize: 14,
                fontWeight: FontWeight.w500,
              ),
            ),
            Text(
              '${value.round()}$unit',
              style: TextStyle(
                fontSize: 14,
                fontWeight: FontWeight.bold,
                color: color,
              ),
            ),
          ],
        ),
        const SizedBox(height: 4),
        LinearProgressIndicator(
          value: value / 100,
          backgroundColor: Colors.grey[300],
          valueColor: AlwaysStoppedAnimation<Color>(color),
        ),
      ],
    );
  }

  Widget _buildTpmsTab() {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        children: [
          // TPMS 개요
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(12),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withOpacity(0.05),
                  blurRadius: 10,
                  offset: const Offset(0, 2),
                ),
              ],
            ),
            child: const Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'TPMS 모니터링',
                  style: TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                SizedBox(height: 8),
                Text(
                  '실시간 타이어 압력 및 온도 모니터링 시스템',
                  style: TextStyle(
                    fontSize: 14,
                    color: Colors.grey,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 20),
          
          // 타이어 카드들
          GridView.builder(
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
              crossAxisCount: 2,
              crossAxisSpacing: 12,
              mainAxisSpacing: 12,
              childAspectRatio: 0.8,
            ),
            itemCount: 4,
            itemBuilder: (context, index) {
              final tireData = _tpmsData.length > index ? _tpmsData[index] : null;
              return TireCard(
                tireNumber: index + 1,
                tireData: tireData,
              );
            },
          ),
        ],
      ),
    );
  }

  Widget _buildAiAnalysisTab() {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        children: [
          AiAnalysisCard(analysisData: _aiAnalysis),
          const SizedBox(height: 20),
          
          // 추가 AI 분석 정보
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(12),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withOpacity(0.05),
                  blurRadius: 10,
                  offset: const Offset(0, 2),
                ),
              ],
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  '이상 탐지 결과',
                  style: TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const SizedBox(height: 16),
                _buildAnomalyInfo(),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildAnomalyInfo() {
    final anomalies = _aiAnalysis['anomalies'] as List? ?? [];
    final riskLevel = _aiAnalysis['risk_level'] ?? 'low';
    
    if (anomalies.isEmpty) {
      return const Center(
        child: Column(
          children: [
            Icon(
              Icons.check_circle,
              size: 48,
              color: Colors.green,
            ),
            SizedBox(height: 8),
            Text(
              '이상 없음',
              style: TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.bold,
                color: Colors.green,
              ),
            ),
            Text(
              '모든 센서가 정상 범위에서 작동 중입니다.',
              style: TextStyle(
                fontSize: 14,
                color: Colors.grey,
              ),
            ),
          ],
        ),
      );
    }
    
    return Column(
      children: anomalies.map<Widget>((anomaly) {
        return Container(
          margin: const EdgeInsets.only(bottom: 8),
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: _getAnomalyColor(anomaly['severity']).withOpacity(0.1),
            borderRadius: BorderRadius.circular(8),
            border: Border.all(
              color: _getAnomalyColor(anomaly['severity']),
              width: 1,
            ),
          ),
          child: Row(
            children: [
              Icon(
                _getAnomalyIcon(anomaly['severity']),
                color: _getAnomalyColor(anomaly['severity']),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      anomaly['anomaly_types'] ?? '알 수 없는 이상',
                      style: const TextStyle(
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    Text(
                      anomaly['recommended_action'] ?? '점검 권장',
                      style: const TextStyle(
                        fontSize: 12,
                        color: Colors.grey,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        );
      }).toList(),
    );
  }

  Color _getAnomalyColor(String? severity) {
    switch (severity) {
      case '매우 높음':
        return Colors.red;
      case '높음':
        return Colors.orange;
      case '보통':
        return Colors.yellow[700]!;
      default:
        return Colors.blue;
    }
  }

  IconData _getAnomalyIcon(String? severity) {
    switch (severity) {
      case '매우 높음':
        return Icons.error;
      case '높음':
        return Icons.warning;
      case '보통':
        return Icons.info;
      default:
        return Icons.check_circle;
    }
  }

  Widget _buildAlertsTab() {
    return AlertList(alerts: _alerts);
  }

  String _formatLastUpdate() {
    final now = DateTime.now();
    final difference = now.difference(_lastUpdate);
    
    if (difference.inMinutes < 1) {
      return '방금 전';
    } else if (difference.inMinutes < 60) {
      return '${difference.inMinutes}분 전';
    } else {
      return '${difference.inHours}시간 전';
    }
  }
}

// 데이터 모델들
class TireData {
  final int position;
  final double pressure;
  final double temperature;
  final String status;
  final bool alarm;

  TireData({
    required this.position,
    required this.pressure,
    required this.temperature,
    required this.status,
    required this.alarm,
  });

  factory TireData.fromJson(Map<String, dynamic> json) {
    return TireData(
      position: json['position'] ?? 0,
      pressure: (json['pressure'] ?? 220.0).toDouble(),
      temperature: (json['temperature'] ?? 35.0).toDouble(),
      status: json['status'] ?? 'normal',
      alarm: json['alarm'] ?? false,
    );
  }
}

class AlertData {
  final String message;
  final String severity;
  final DateTime timestamp;
  final String type;

  AlertData({
    required this.message,
    required this.severity,
    required this.timestamp,
    required this.type,
  });

  factory AlertData.fromJson(Map<String, dynamic> json) {
    return AlertData(
      message: json['message'] ?? '',
      severity: json['severity'] ?? 'info',
      timestamp: DateTime.tryParse(json['timestamp'] ?? '') ?? DateTime.now(),
      type: json['type'] ?? 'general',
    );
  }
}