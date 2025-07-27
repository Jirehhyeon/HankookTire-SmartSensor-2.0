import React, { useState, useEffect, useCallback } from 'react';
import { 
  Grid, Card, CardContent, Typography, Box, Alert, Badge,
  Chip, LinearProgress, CircularProgress, IconButton, Tooltip
} from '@mui/material';
import { 
  Speed as SpeedIcon, 
  Warning as WarningIcon,
  CheckCircle as CheckIcon,
  Error as ErrorIcon,
  Refresh as RefreshIcon,
  Settings as SettingsIcon,
  Timeline as TimelineIcon
} from '@mui/icons-material';
import { Line, Doughnut, Bar } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip as ChartTooltip,
  Legend,
  ArcElement,
  BarElement
} from 'chart.js';
import { useWebSocket } from '../hooks/useWebSocket';
import { formatDistanceToNow } from 'date-fns';
import { ko } from 'date-fns/locale';

// Chart.js 등록
ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  ChartTooltip,
  Legend,
  ArcElement,
  BarElement
);

const Dashboard = () => {
  const [sensorData, setSensorData] = useState({});
  const [tpmsData, setTpmsData] = useState([]);
  const [aiAnalysis, setAiAnalysis] = useState({});
  const [systemHealth, setSystemHealth] = useState({});
  const [alerts, setAlerts] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [lastUpdate, setLastUpdate] = useState(new Date());

  // WebSocket 연결
  const { sendMessage, lastMessage, connectionStatus } = useWebSocket('ws://localhost:8000/ws/dashboard');

  // WebSocket 메시지 처리
  useEffect(() => {
    if (lastMessage !== null) {
      const data = JSON.parse(lastMessage.data);
      
      switch (data.type) {
        case 'sensor_update':
          setSensorData(data.data);
          setLastUpdate(new Date());
          break;
        case 'ai_analysis':
          setAiAnalysis(data);
          break;
        case 'health_status':
          setSystemHealth(data);
          break;
        case 'alert':
          setAlerts(prev => [data, ...prev.slice(0, 9)]); // 최근 10개만 유지
          break;
        default:
          break;
      }
      setIsLoading(false);
    }
  }, [lastMessage]);

  // 데이터 요청
  const requestData = useCallback(() => {
    if (connectionStatus === 'Open') {
      sendMessage(JSON.stringify({
        type: 'command',
        command: 'get_sensor_data'
      }));
    }
  }, [sendMessage, connectionStatus]);

  // 초기 데이터 로드 및 주기적 업데이트
  useEffect(() => {
    requestData();
    const interval = setInterval(requestData, 5000); // 5초마다 업데이트
    return () => clearInterval(interval);
  }, [requestData]);

  // TPMS 데이터 차트 옵션
  const tpmsChartOptions = {
    responsive: true,
    plugins: {
      legend: {
        position: 'top',
      },
      title: {
        display: true,
        text: 'TPMS 실시간 모니터링'
      }
    },
    scales: {
      y: {
        beginAtZero: true,
        max: 300
      }
    }
  };

  // TPMS 차트 데이터
  const tpmsChartData = {
    labels: ['타이어 1', '타이어 2', '타이어 3', '타이어 4'],
    datasets: [
      {
        label: '압력 (kPa)',
        data: tpmsData.map(tire => tire.pressure || 220),
        borderColor: 'rgb(255, 107, 53)',
        backgroundColor: 'rgba(255, 107, 53, 0.2)',
        borderWidth: 2
      },
      {
        label: '온도 (°C)',
        data: tpmsData.map(tire => tire.temperature || 35),
        borderColor: 'rgb(53, 162, 235)',
        backgroundColor: 'rgba(53, 162, 235, 0.2)',
        borderWidth: 2
      }
    ]
  };

  // AI 분석 도넛 차트
  const aiAnalysisData = {
    labels: ['정상', '주의', '경고', '위험'],
    datasets: [
      {
        data: [
          aiAnalysis.predictions?.normal || 85,
          aiAnalysis.predictions?.caution || 10,
          aiAnalysis.predictions?.warning || 3,
          aiAnalysis.predictions?.critical || 2
        ],
        backgroundColor: [
          '#4CAF50',
          '#FF9800',
          '#F44336',
          '#9C27B0'
        ],
        hoverOffset: 4
      }
    ]
  };

  // 시스템 상태 카드
  const SystemStatusCard = ({ title, value, status, icon: Icon }) => (
    <Card sx={{ height: '100%' }}>
      <CardContent>
        <Box display="flex" alignItems="center" justifyContent="space-between">
          <Box>
            <Typography color="textSecondary" gutterBottom variant="h6">
              {title}
            </Typography>
            <Typography variant="h4" component="div">
              {value}
            </Typography>
          </Box>
          <Box>
            <Icon 
              sx={{ 
                fontSize: 40, 
                color: status === 'good' ? 'success.main' : 
                       status === 'warning' ? 'warning.main' : 'error.main'
              }} 
            />
          </Box>
        </Box>
        <Box mt={2}>
          <Chip 
            label={status === 'good' ? '정상' : status === 'warning' ? '주의' : '경고'}
            color={status === 'good' ? 'success' : status === 'warning' ? 'warning' : 'error'}
            size="small"
          />
        </Box>
      </CardContent>
    </Card>
  );

  // TPMS 타이어 카드
  const TireCard = ({ tireNumber, data }) => {
    const getStatusColor = (pressure, temperature) => {
      if (pressure < 200 || pressure > 280 || temperature > 80) return 'error';
      if (pressure < 210 || pressure > 270 || temperature > 70) return 'warning';
      return 'success';
    };

    const statusColor = getStatusColor(data?.pressure || 220, data?.temperature || 35);

    return (
      <Card sx={{ height: '100%' }}>
        <CardContent>
          <Box display="flex" alignItems="center" justifyContent="space-between" mb={2}>
            <Typography variant="h6">타이어 {tireNumber}</Typography>
            <Badge 
              color={statusColor} 
              variant="dot"
              sx={{ '& .MuiBadge-badge': { width: 12, height: 12 } }}
            >
              <SpeedIcon />
            </Badge>
          </Box>
          
          <Box mb={2}>
            <Typography variant="body2" color="textSecondary">압력</Typography>
            <Typography variant="h5">{data?.pressure || 220} kPa</Typography>
            <LinearProgress 
              variant="determinate" 
              value={(data?.pressure || 220) / 3} 
              color={statusColor}
              sx={{ mt: 1 }}
            />
          </Box>
          
          <Box mb={2}>
            <Typography variant="body2" color="textSecondary">온도</Typography>
            <Typography variant="h5">{data?.temperature || 35}°C</Typography>
            <LinearProgress 
              variant="determinate" 
              value={(data?.temperature || 35) * 1.25} 
              color={statusColor}
              sx={{ mt: 1 }}
            />
          </Box>
          
          <Box>
            <Typography variant="body2" color="textSecondary">상태</Typography>
            <Chip 
              label={statusColor === 'success' ? '정상' : statusColor === 'warning' ? '주의' : '경고'}
              color={statusColor}
              size="small"
            />
          </Box>
        </CardContent>
      </Card>
    );
  };

  // 알림 카드
  const AlertCard = ({ alert, index }) => (
    <Alert 
      severity={alert.severity || 'info'} 
      sx={{ mb: 1 }}
      action={
        <Tooltip title="설정">
          <IconButton size="small">
            <SettingsIcon fontSize="inherit" />
          </IconButton>
        </Tooltip>
      }
    >
      <Typography variant="body2">
        {alert.message} - {formatDistanceToNow(new Date(alert.timestamp), { locale: ko, addSuffix: true })}
      </Typography>
    </Alert>
  );

  if (isLoading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" height="100vh">
        <CircularProgress size={60} />
        <Typography variant="h6" sx={{ ml: 2 }}>
          시스템 로딩 중...
        </Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ flexGrow: 1, p: 3 }}>
      {/* 헤더 */}
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h4" component="h1">
          🚀 HankookTire SmartSensor 2.0
        </Typography>
        <Box display="flex" alignItems="center" gap={2}>
          <Chip 
            icon={connectionStatus === 'Open' ? <CheckIcon /> : <ErrorIcon />}
            label={connectionStatus === 'Open' ? '연결됨' : '연결 끊김'}
            color={connectionStatus === 'Open' ? 'success' : 'error'}
          />
          <Typography variant="body2" color="textSecondary">
            마지막 업데이트: {formatDistanceToNow(lastUpdate, { locale: ko, addSuffix: true })}
          </Typography>
          <IconButton onClick={requestData} color="primary">
            <RefreshIcon />
          </IconButton>
        </Box>
      </Box>

      <Grid container spacing={3}>
        {/* 시스템 상태 카드들 */}
        <Grid item xs={12} sm={6} md={3}>
          <SystemStatusCard 
            title="활성 센서"
            value={Object.keys(sensorData).length || '--'}
            status="good"
            icon={SpeedIcon}
          />
        </Grid>
        
        <Grid item xs={12} sm={6} md={3}>
          <SystemStatusCard 
            title="AI 신뢰도"
            value={`${Math.round((aiAnalysis.confidence || 0.85) * 100)}%`}
            status={aiAnalysis.confidence > 0.8 ? 'good' : 'warning'}
            icon={TimelineIcon}
          />
        </Grid>
        
        <Grid item xs={12} sm={6} md={3}>
          <SystemStatusCard 
            title="시스템 상태"
            value={systemHealth.status === 'healthy' ? '정상' : '점검 필요'}
            status={systemHealth.status === 'healthy' ? 'good' : 'warning'}
            icon={CheckIcon}
          />
        </Grid>
        
        <Grid item xs={12} sm={6} md={3}>
          <SystemStatusCard 
            title="활성 알림"
            value={alerts.length}
            status={alerts.length === 0 ? 'good' : alerts.length < 3 ? 'warning' : 'error'}
            icon={WarningIcon}
          />
        </Grid>

        {/* TPMS 타이어 모니터링 */}
        <Grid item xs={12} md={8}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                TPMS 실시간 모니터링
              </Typography>
              <Box height={300}>
                <Bar data={tpmsChartData} options={tpmsChartOptions} />
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* AI 분석 결과 */}
        <Grid item xs={12} md={4}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                AI 분석 결과
              </Typography>
              <Box height={300} display="flex" justifyContent="center" alignItems="center">
                <Doughnut data={aiAnalysisData} />
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* 개별 타이어 상태 */}
        {[1, 2, 3, 4].map(tireNumber => (
          <Grid item xs={12} sm={6} md={3} key={tireNumber}>
            <TireCard 
              tireNumber={tireNumber}
              data={tpmsData.find(tire => tire.position === tireNumber)}
            />
          </Grid>
        ))}

        {/* 센서 데이터 트렌드 */}
        <Grid item xs={12} md={8}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                센서 데이터 트렌드
              </Typography>
              <Box height={300}>
                <Line 
                  data={{
                    labels: Array.from({length: 10}, (_, i) => `${i + 1}분 전`),
                    datasets: [
                      {
                        label: '온도 (°C)',
                        data: Array.from({length: 10}, () => Math.random() * 10 + 25),
                        borderColor: 'rgb(255, 99, 132)',
                        backgroundColor: 'rgba(255, 99, 132, 0.2)',
                      },
                      {
                        label: '습도 (%)',
                        data: Array.from({length: 10}, () => Math.random() * 20 + 50),
                        borderColor: 'rgb(54, 162, 235)',
                        backgroundColor: 'rgba(54, 162, 235, 0.2)',
                      }
                    ]
                  }}
                  options={{
                    responsive: true,
                    plugins: {
                      legend: {
                        position: 'top',
                      },
                    },
                    scales: {
                      y: {
                        beginAtZero: true
                      }
                    }
                  }}
                />
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* 알림 및 이벤트 */}
        <Grid item xs={12} md={4}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                최근 알림
              </Typography>
              <Box maxHeight={300} overflow="auto">
                {alerts.length > 0 ? (
                  alerts.map((alert, index) => (
                    <AlertCard key={index} alert={alert} index={index} />
                  ))
                ) : (
                  <Typography variant="body2" color="textSecondary" textAlign="center">
                    알림이 없습니다.
                  </Typography>
                )}
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* 예측 정비 정보 */}
        <Grid item xs={12}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                예측 정비 정보
              </Typography>
              <Grid container spacing={2}>
                <Grid item xs={12} sm={6} md={3}>
                  <Box textAlign="center" p={2}>
                    <Typography variant="h4" color="primary">
                      {aiAnalysis.maintenance?.days_remaining || 90}
                    </Typography>
                    <Typography variant="body2" color="textSecondary">
                      정비까지 남은 일수
                    </Typography>
                  </Box>
                </Grid>
                <Grid item xs={12} sm={6} md={3}>
                  <Box textAlign="center" p={2}>
                    <Typography variant="h4" color="success.main">
                      95%
                    </Typography>
                    <Typography variant="body2" color="textSecondary">
                      예측 정확도
                    </Typography>
                  </Box>
                </Grid>
                <Grid item xs={12} sm={6} md={3}>
                  <Box textAlign="center" p={2}>
                    <Typography variant="h4" color="warning.main">
                      ₩150,000
                    </Typography>
                    <Typography variant="body2" color="textSecondary">
                      예상 정비 비용
                    </Typography>
                  </Box>
                </Grid>
                <Grid item xs={12} sm={6} md={3}>
                  <Box textAlign="center" p={2}>
                    <Typography variant="h4" color="info.main">
                      정기점검
                    </Typography>
                    <Typography variant="body2" color="textSecondary">
                      권장 정비 유형
                    </Typography>
                  </Box>
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
};

export default Dashboard;