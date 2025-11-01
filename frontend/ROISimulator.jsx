import React, { useState } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Slider } from '@/components/ui/slider';
import { Input } from '@/components/ui/input';
import { Alert, AlertDescription } from '@/components/ui/alert';

const ROISimulator = () => {
  const [channelId, setChannelId] = useState('');
  const [brandName, setBrandName] = useState('');
  const [weights, setWeights] = useState({
    brand: 30,
    sentiment: 30,
    roi: 40
  });
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [comparing, setComparing] = useState(false);

  // 가중치 합이 100인지 확인
  const weightsSum = weights.brand + weights.sentiment + weights.roi;
  const isWeightsValid = weightsSum === 100;

  const handleWeightChange = (type, value) => {
    setWeights(prev => ({
      ...prev,
      [type]: value[0]
    }));
  };

  const runSimulation = async () => {
    if (!channelId || !brandName) {
      alert('채널 ID와 브랜드명을 입력해주세요');
      return;
    }

    if (!isWeightsValid) {
      alert('가중치 합이 100%가 되어야 합니다');
      return;
    }

    setLoading(true);
    try {
      const response = await fetch('http://localhost:8000/simulator/simulate', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          channel_id: channelId,
          brand_name: brandName,
          weights: {
            brand_image_weight: weights.brand / 100,
            sentiment_weight: weights.sentiment / 100,
            roi_weight: weights.roi / 100
          },
          num_videos: 3,
          max_comments_per_video: 200
        })
      });

      const data = await response.json();
      setResult(data);
    } catch (error) {
      alert('시뮬레이션 실패: ' + error.message);
    } finally {
      setLoading(false);
    }
  };

  const compareWeights = async () => {
    if (!result) {
      alert('먼저 시뮬레이션을 실행해주세요');
      return;
    }

    setComparing(true);
    try {
      const weightConfigs = [
        { brand_image_weight: 0.5, sentiment_weight: 0.3, roi_weight: 0.2 },
        { brand_image_weight: 0.3, sentiment_weight: 0.3, roi_weight: 0.4 },
        { brand_image_weight: 0.3, sentiment_weight: 0.5, roi_weight: 0.2 },
        { brand_image_weight: 0.2, sentiment_weight: 0.2, roi_weight: 0.6 }
      ];

      const response = await fetch(
        `http://localhost:8000/simulator/compare-weights?channel_id=${channelId}&brand_name=${brandName}`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(weightConfigs)
        }
      );

      const data = await response.json();
      setResult(prev => ({
        ...prev,
        weight_comparison: data
      }));
    } catch (error) {
      alert('가중치 비교 실패: ' + error.message);
    } finally {
      setComparing(false);
    }
  };

  const ScoreCard = ({ title, score, color }) => (
    <div className="bg-white p-4 rounded-lg shadow-sm border border-gray-200">
      <h3 className="text-sm font-medium text-gray-600 mb-2">{title}</h3>
      <div className="flex items-end gap-2">
        <span className={`text-3xl font-bold ${color}`}>
          {score.toFixed(1)}
        </span>
        <span className="text-gray-500 mb-1">/100</span>
      </div>
      <div className="mt-2 h-2 bg-gray-200 rounded-full overflow-hidden">
        <div 
          className={`h-full ${color.replace('text', 'bg')} transition-all duration-500`}
          style={{ width: `${score}%` }}
        />
      </div>
    </div>
  );

  const GradeDisplay = ({ grade, score }) => {
    const gradeColors = {
      'A+': 'bg-green-500',
      'A': 'bg-green-400',
      'B+': 'bg-blue-500',
      'B': 'bg-blue-400',
      'C+': 'bg-yellow-500',
      'C': 'bg-yellow-400',
      'D': 'bg-red-500'
    };

    return (
      <div className="flex items-center gap-4">
        <div className={`${gradeColors[grade]} text-white text-4xl font-bold px-6 py-3 rounded-lg shadow-lg`}>
          {grade}
        </div>
        <div>
          <div className="text-3xl font-bold text-gray-800">{score.toFixed(1)}점</div>
          <div className="text-sm text-gray-500">종합 평가</div>
        </div>
      </div>
    );
  };

  return (
    <div className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-6xl mx-auto">
        <h1 className="text-4xl font-bold text-gray-900 mb-8">
          🎯 유튜버 마케팅 ROI 시뮬레이터
        </h1>

        {/* 입력 섹션 */}
        <Card className="mb-6">
          <CardHeader>
            <CardTitle>1. 기본 정보 입력</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                채널 ID
              </label>
              <Input
                type="text"
                placeholder="UCxxxxxxxxxxxxxxxxxx"
                value={channelId}
                onChange={(e) => setChannelId(e.target.value)}
                className="w-full"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                브랜드명
              </label>
              <Input
                type="text"
                placeholder="예: 나이키, 삼성, 스타벅스"
                value={brandName}
                onChange={(e) => setBrandName(e.target.value)}
                className="w-full"
              />
            </div>
          </CardContent>
        </Card>

        {/* 가중치 설정 */}
        <Card className="mb-6">
          <CardHeader>
            <CardTitle>2. 평가 가중치 설정</CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            <div>
              <div className="flex justify-between mb-2">
                <label className="text-sm font-medium text-gray-700">
                  브랜드 이미지 적합도
                </label>
                <span className="text-sm font-bold text-blue-600">
                  {weights.brand}%
                </span>
              </div>
              <Slider
                value={[weights.brand]}
                onValueChange={(val) => handleWeightChange('brand', val)}
                max={100}
                step={5}
                className="w-full"
              />
            </div>

            <div>
              <div className="flex justify-between mb-2">
                <label className="text-sm font-medium text-gray-700">
                  댓글 감성 분석
                </label>
                <span className="text-sm font-bold text-green-600">
                  {weights.sentiment}%
                </span>
              </div>
              <Slider
                value={[weights.sentiment]}
                onValueChange={(val) => handleWeightChange('sentiment', val)}
                max={100}
                step={5}
                className="w-full"
              />
            </div>

            <div>
              <div className="flex justify-between mb-2">
                <label className="text-sm font-medium text-gray-700">
                  ROI 효율성
                </label>
                <span className="text-sm font-bold text-purple-600">
                  {weights.roi}%
                </span>
              </div>
              <Slider
                value={[weights.roi]}
                onValueChange={(val) => handleWeightChange('roi', val)}
                max={100}
                step={5}
                className="w-full"
              />
            </div>

            <Alert className={isWeightsValid ? "bg-green-50 border-green-200" : "bg-red-50 border-red-200"}>
              <AlertDescription>
                {isWeightsValid ? (
                  <span className="text-green-700">✓ 가중치 합계: {weightsSum}%</span>
                ) : (
                  <span className="text-red-700">⚠ 가중치 합계가 100%가 되어야 합니다 (현재: {weightsSum}%)</span>
                )}
              </AlertDescription>
            </Alert>
          </CardContent>
        </Card>

        {/* 실행 버튼 */}
        <div className="flex gap-4 mb-6">
          <Button
            onClick={runSimulation}
            disabled={loading || !isWeightsValid}
            className="flex-1 h-14 text-lg font-semibold"
          >
            {loading ? '분석 중...' : '🚀 시뮬레이션 실행'}
          </Button>
          
          {result && (
            <Button
              onClick={compareWeights}
              disabled={comparing}
              variant="outline"
              className="h-14 px-8"
            >
              {comparing ? '비교 중...' : '📊 가중치 비교'}
            </Button>
          )}
        </div>

        {/* 결과 표시 */}
        {result && (
          <>
            <Card className="mb-6">
              <CardHeader>
                <CardTitle>3. 분석 결과</CardTitle>
              </CardHeader>
              <CardContent className="space-y-6">
                {/* 채널 정보 */}
                <div className="flex items-center gap-4 p-4 bg-gray-50 rounded-lg">
                  {result.total_score.thumbnail_url && (
                    <img
                      src={result.total_score.thumbnail_url}
                      alt="채널 썸네일"
                      className="w-20 h-20 rounded-full object-cover"
                    />
                  )}
                  <div>
                    <h3 className="text-xl font-bold">{result.channel_title}</h3>
                    <p className="text-sm text-gray-600">
                      구독자 {result.total_score.subscriber_count?.toLocaleString()}명 | 
                      참여율 {result.total_score.engagement_rate?.toFixed(2)}%
                    </p>
                  </div>
                </div>

                {/* 최종 점수 */}
                <div className="p-6 bg-gradient-to-r from-blue-50 to-purple-50 rounded-lg">
                  <GradeDisplay 
                    grade={result.total_score.grade} 
                    score={result.total_score.total_score}
                  />
                  <p className="mt-4 text-lg">
                    {result.total_score.recommendation}
                  </p>
                </div>

                {/* 개별 점수 */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <ScoreCard
                    title="브랜드 적합도"
                    score={result.total_score.brand_image_score}
                    color="text-blue-600"
                  />
                  <ScoreCard
                    title="감성 분석"
                    score={result.total_score.sentiment_score}
                    color="text-green-600"
                  />
                  <ScoreCard
                    title="ROI 효율"
                    score={result.total_score.roi_score}
                    color="text-purple-600"
                  />
                </div>

                {/* 상세 정보 */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* 감성 분석 상세 */}
                  <div className="p-4 border rounded-lg">
                    <h4 className="font-semibold mb-3">📝 댓글 감성 분석</h4>
                    <div className="space-y-2 text-sm">
                      <div className="flex justify-between">
                        <span>긍정:</span>
                        <span className="font-bold text-green-600">
                          {result.sentiment.positive_ratio}%
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span>중립:</span>
                        <span className="font-bold text-gray-600">
                          {result.sentiment.neutral_ratio}%
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span>부정:</span>
                        <span className="font-bold text-red-600">
                          {result.sentiment.negative_ratio}%
                        </span>
                      </div>
                      <div className="pt-2 border-t">
                        <span className="text-gray-600">
                          총 {result.sentiment.total_comments}개 댓글 분석
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* ROI 상세 */}
                  <div className="p-4 border rounded-lg">
                    <h4 className="font-semibold mb-3">💰 ROI 예상</h4>
                    <div className="space-y-2 text-sm">
                      <div className="flex justify-between">
                        <span>예상 조회수:</span>
                        <span className="font-bold">
                          {result.roi_estimate.estimated_views.toLocaleString()}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span>예상 참여:</span>
                        <span className="font-bold">
                          {result.roi_estimate.estimated_engagement.toLocaleString()}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span>예상 비용:</span>
                        <span className="font-bold text-blue-600">
                          ₩{result.roi_estimate.cost_estimate.toLocaleString()}
                        </span>
                      </div>
                      {result.roi_estimate.cpe && (
                        <div className="flex justify-between">
                          <span>CPE:</span>
                          <span className="font-bold">
                            ₩{result.roi_estimate.cpe.toLocaleString()}
                          </span>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* 가중치 비교 결과 */}
            {result.weight_comparison && (
              <Card>
                <CardHeader>
                  <CardTitle>4. 가중치별 점수 비교</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4">
                    {result.weight_comparison.comparisons.map((comp, idx) => (
                      <div key={idx} className="p-4 border rounded-lg hover:bg-gray-50 transition">
                        <div className="flex justify-between items-center mb-2">
                          <div className="text-sm space-x-2">
                            <span className="text-blue-600">
                              브랜드 {(comp.weights.brand_image_weight * 100).toFixed(0)}%
                            </span>
                            <span className="text-green-600">
                              감성 {(comp.weights.sentiment_weight * 100).toFixed(0)}%
                            </span>
                            <span className="text-purple-600">
                              ROI {(comp.weights.roi_weight * 100).toFixed(0)}%
                            </span>
                          </div>
                          <div className="flex items-center gap-2">
                            <span className="text-2xl font-bold">
                              {comp.total_score.toFixed(1)}
                            </span>
                            <span className={`px-2 py-1 rounded text-white text-sm ${
                              comp.grade.startsWith('A') ? 'bg-green-500' :
                              comp.grade.startsWith('B') ? 'bg-blue-500' :
                              comp.grade.startsWith('C') ? 'bg-yellow-500' : 'bg-red-500'
                            }`}>
                              {comp.grade}
                            </span>
                          </div>
                        </div>
                        <p className="text-sm text-gray-600">{comp.recommendation}</p>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}
          </>
        )}
      </div>
    </div>
  );
};

export default ROISimulator;