import React, { useState } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from './components/ui/card';
import { Button } from './components/ui/button';
import { Slider } from './components/ui/slider';
import { Input } from './components/ui/input';
import { Textarea } from './components/ui/textarea';
import { Alert, AlertDescription } from './components/ui/alert';

const ROISimulator = () => {
  // 기본 정보
  const [channelId, setChannelId] = useState('');
  const [brandName, setBrandName] = useState('');
  const [brandDescription, setBrandDescription] = useState('');
  const [brandTone, setBrandTone] = useState('');
  const [brandCategory, setBrandCategory] = useState('');
  const [brandImageUrl, setBrandImageUrl] = useState('');

  // 분석 옵션
  const [numVideos, setNumVideos] = useState(3);
  const [maxComments, setMaxComments] = useState(200);

  // 가중치
  const [weights, setWeights] = useState({
    brand: 40,
    sentiment: 30,
    roi: 30
  });

  // 결과 및 상태
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [comparing, setComparing] = useState(false);
  const [activeTab, setActiveTab] = useState('full'); // 'full', 'brand', 'sentiment'

  // 가중치 합이 100인지 확인
  const weightsSum = weights.brand + weights.sentiment + weights.roi;
  const isWeightsValid = weightsSum === 100;

  const handleWeightChange = (type, value) => {
    setWeights(prev => ({
      ...prev,
      [type]: value[0]
    }));
  };

  // 브랜드 적합도 분석만 실행
  const runBrandAnalysis = async () => {
    if (!channelId || !brandName || !brandDescription || !brandTone || !brandCategory) {
      alert('모든 브랜드 정보를 입력해주세요');
      return;
    }

    setLoading(true);
    try {
      const response = await fetch('http://localhost:8000/simulator/brand-compatibility', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          channel_id: channelId,
          brand_name: brandName,
          brand_description: brandDescription,
          brand_tone: brandTone,
          brand_category: brandCategory,
          brand_image_url: brandImageUrl || null
        })
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      setResult({ brand_image: data });
    } catch (error) {
      alert('브랜드 분석 실패: ' + error.message);
    } finally {
      setLoading(false);
    }
  };

  // 감성분석만 실행
  const runSentimentAnalysis = async () => {
    if (!channelId) {
      alert('채널 ID를 입력해주세요');
      return;
    }

    setLoading(true);
    try {
      const response = await fetch(
        `http://localhost:8000/simulator/sentiment/${channelId}?num_videos=${numVideos}&max_comments_per_video=${maxComments}`,
        {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
          }
        }
      );

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      setResult({ sentiment: data });
    } catch (error) {
      alert('감성분석 실패: ' + error.message);
    } finally {
      setLoading(false);
    }
  };

  // 전체 시뮬레이션 실행
  const runSimulation = async () => {
    if (!channelId || !brandName || !brandDescription || !brandTone || !brandCategory) {
      alert('모든 필수 정보를 입력해주세요');
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
          brand_description: brandDescription,
          brand_tone: brandTone,
          brand_category: brandCategory,
          brand_image_url: brandImageUrl || null,
          num_videos: numVideos,
          max_comments_per_video: maxComments,
          weights: {
            brand_image_weight: weights.brand / 100,
            sentiment_weight: weights.sentiment / 100,
            roi_weight: weights.roi / 100
          }
        })
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      setResult(data);
    } catch (error) {
      alert('시뮬레이션 실패: ' + error.message);
      console.error('Error:', error);
    } finally {
      setLoading(false);
    }
  };

  // 가중치 비교
  const compareWeights = async () => {
    if (!result || !result.brand_image) {
      alert('먼저 전체 시뮬레이션을 실행해주세요');
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
        'http://localhost:8000/simulator/compare-weights',
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            channel_id: channelId,
            brand_name: brandName,
            brand_description: brandDescription,
            brand_tone: brandTone,
            brand_category: brandCategory,
            brand_image_url: brandImageUrl || null,
            weight_configs: weightConfigs
          })
        }
      );

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

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

  const ScoreCard = ({ title, score, color, subtitle }) => (
    <div className="bg-white p-4 rounded-lg shadow-sm border border-gray-200">
      <h3 className="text-sm font-medium text-gray-600 mb-2">{title}</h3>
      {subtitle && <p className="text-xs text-gray-500 mb-2">{subtitle}</p>}
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
      'S': 'bg-gradient-to-r from-yellow-400 to-yellow-600',
      'A': 'bg-green-500',
      'B': 'bg-blue-500',
      'C': 'bg-yellow-500',
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
        <h1 className="text-4xl font-bold text-gray-900 mb-2">
          유튜버 마케팅 ROI 시뮬레이터
        </h1>
        <p className="text-gray-600 mb-8">
          AI 기반 브랜드 적합도 분석 및 감성분석으로 최적의 인플루언서를 찾아보세요
        </p>

        {/* 탭 메뉴 */}
        <div className="flex gap-2 mb-6 border-b">
          <button
            className={`px-6 py-3 font-medium transition ${
              activeTab === 'full'
                ? 'border-b-2 border-blue-600 text-blue-600'
                : 'text-gray-600 hover:text-gray-900'
            }`}
            onClick={() => setActiveTab('full')}
          >
            전체 시뮬레이션
          </button>
          <button
            className={`px-6 py-3 font-medium transition ${
              activeTab === 'brand'
                ? 'border-b-2 border-blue-600 text-blue-600'
                : 'text-gray-600 hover:text-gray-900'
            }`}
            onClick={() => setActiveTab('brand')}
          >
            브랜드 적합도만
          </button>
          <button
            className={`px-6 py-3 font-medium transition ${
              activeTab === 'sentiment'
                ? 'border-b-2 border-blue-600 text-blue-600'
                : 'text-gray-600 hover:text-gray-900'
            }`}
            onClick={() => setActiveTab('sentiment')}
          >
            감성분석만
          </button>
        </div>

        {/* 입력 섹션 */}
        <Card className="mb-6">
          <CardHeader>
            <CardTitle>1. 기본 정보 입력</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                채널 ID <span className="text-red-500">*</span>
              </label>
              <Input
                type="text"
                placeholder="UCxxxxxxxxxxxxxxxxxx"
                value={channelId}
                onChange={(e) => setChannelId(e.target.value)}
                className="w-full"
              />
              <p className="text-xs text-gray-500 mt-1">
                유튜브 채널 URL의 UC로 시작하는 ID를 입력하세요
              </p>
            </div>

            {(activeTab === 'full' || activeTab === 'brand') && (
              <>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    브랜드명 <span className="text-red-500">*</span>
                  </label>
                  <Input
                    type="text"
                    placeholder="예: 올리브영, 나이키, 삼성전자"
                    value={brandName}
                    onChange={(e) => setBrandName(e.target.value)}
                    className="w-full"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    제품/브랜드 설명 <span className="text-red-500">*</span>
                  </label>
                  <Textarea
                    placeholder="예: K-뷰티를 선도하는 헬스앤뷰티 스토어로, 트렌디한 화장품과 생활용품을 제공합니다"
                    value={brandDescription}
                    onChange={(e) => setBrandDescription(e.target.value)}
                    className="w-full min-h-[100px]"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    브랜드 톤앤매너 <span className="text-red-500">*</span>
                  </label>
                  <Input
                    type="text"
                    placeholder="예: 전문적이면서도 친절한 가이드를 제공하는 신뢰감 있는 톤"
                    value={brandTone}
                    onChange={(e) => setBrandTone(e.target.value)}
                    className="w-full"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    브랜드 카테고리 <span className="text-red-500">*</span>
                  </label>
                  <Input
                    type="text"
                    placeholder="예: 뷰티, 패션, 테크, 푸드, 라이프스타일"
                    value={brandCategory}
                    onChange={(e) => setBrandCategory(e.target.value)}
                    className="w-full"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    제품 이미지 URL (선택)
                  </label>
                  <Input
                    type="text"
                    placeholder="https://example.com/product-image.jpg"
                    value={brandImageUrl}
                    onChange={(e) => setBrandImageUrl(e.target.value)}
                    className="w-full"
                  />
                  <p className="text-xs text-gray-500 mt-1">
                    제품 이미지를 제공하면 더 정확한 시각적 유사도 분석이 가능합니다
                  </p>
                </div>
              </>
            )}

            {(activeTab === 'full' || activeTab === 'sentiment') && (
              <>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      분석할 영상 수
                    </label>
                    <Input
                      type="number"
                      min="1"
                      max="10"
                      value={numVideos}
                      onChange={(e) => setNumVideos(parseInt(e.target.value))}
                      className="w-full"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      영상당 댓글 수
                    </label>
                    <Input
                      type="number"
                      min="50"
                      max="500"
                      value={maxComments}
                      onChange={(e) => setMaxComments(parseInt(e.target.value))}
                      className="w-full"
                    />
                  </div>
                </div>
              </>
            )}
          </CardContent>
        </Card>

        {/* 가중치 설정 (전체 시뮬레이션에만 표시) */}
        {activeTab === 'full' && (
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
        )}

        {/* 실행 버튼 */}
        <div className="flex gap-4 mb-6">
          {activeTab === 'full' && (
            <>
              <Button
                onClick={runSimulation}
                disabled={loading || !isWeightsValid}
                className="flex-1 h-14 text-lg font-semibold"
              >
                {loading ? '분석 중...' : '🚀 전체 시뮬레이션 실행'}
              </Button>
              
              {result && result.brand_image && (
                <Button
                  onClick={compareWeights}
                  disabled={comparing}
                  variant="outline"
                  className="h-14 px-8"
                >
                  {comparing ? '비교 중...' : '📊 가중치 비교'}
                </Button>
              )}
            </>
          )}

          {activeTab === 'brand' && (
            <Button
              onClick={runBrandAnalysis}
              disabled={loading}
              className="flex-1 h-14 text-lg font-semibold"
            >
              {loading ? '분석 중...' : '🎨 브랜드 적합도 분석'}
            </Button>
          )}

          {activeTab === 'sentiment' && (
            <Button
              onClick={runSentimentAnalysis}
              disabled={loading}
              className="flex-1 h-14 text-lg font-semibold"
            >
              {loading ? '분석 중...' : '💬 감성분석 실행'}
            </Button>
          )}
        </div>

        {/* 결과 표시 */}
        {result && (
          <>
            {/* 전체 시뮬레이션 결과 */}
            {result.total_score && (
              <Card className="mb-6">
                <CardHeader>
                  <CardTitle>분석 결과</CardTitle>
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
                    <p className="text-sm text-gray-600 mt-2">
                      처리 시간: {result.processing_time_seconds}초
                    </p>
                  </div>

                  {/* 개별 점수 */}
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <ScoreCard
                      title="브랜드 적합도"
                      score={result.total_score.brand_image_score}
                      color="text-blue-600"
                      subtitle="CLIP + Sentence-BERT"
                    />
                    <ScoreCard
                      title="감성 분석"
                      score={result.total_score.sentiment_score}
                      color="text-green-600"
                      subtitle="KoBERT 기반"
                    />
                    <ScoreCard
                      title="ROI 효율"
                      score={result.total_score.roi_score}
                      color="text-purple-600"
                      subtitle="참여율 기반"
                    />
                  </div>

                  {/* 브랜드 적합도 상세 */}
                  {result.brand_image && (
                    <div className="p-4 border rounded-lg">
                      <h4 className="font-semibold mb-3">🎨 브랜드 적합도 상세</h4>
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        <div>
                          <p className="text-xs text-gray-600">이미지 유사도</p>
                          <p className="text-xl font-bold text-blue-600">
                            {result.brand_image.image_similarity.toFixed(1)}
                          </p>
                        </div>
                        <div>
                          <p className="text-xs text-gray-600">텍스트 유사도</p>
                          <p className="text-xl font-bold text-green-600">
                            {result.brand_image.text_similarity.toFixed(1)}
                          </p>
                        </div>
                        <div>
                          <p className="text-xs text-gray-600">톤 매칭</p>
                          <p className="text-xl font-bold text-purple-600">
                            {result.brand_image.tone_match.toFixed(1)}
                          </p>
                        </div>
                        <div>
                          <p className="text-xs text-gray-600">카테고리 매칭</p>
                          <p className="text-xl font-bold text-orange-600">
                            {result.brand_image.category_match.toFixed(1)}
                          </p>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* 상세 정보 */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {/* 감성 분석 상세 */}
                    {result.sentiment && (
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
                              총 {result.sentiment.total_comments}개 댓글 분석 ({result.sentiment.videos_analyzed}개 영상)
                            </span>
                          </div>
                        </div>
                      </div>
                    )}

                    {/* ROI 상세 */}
                    {result.roi_estimate && (
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
                          <div className="flex justify-between">
                            <span>참여율:</span>
                            <span className="font-bold">
                              {result.roi_estimate.engagement_rate.toFixed(2)}%
                            </span>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* 에러 메시지 */}
                  {result.errors && result.errors.length > 0 && (
                    <Alert className="bg-yellow-50 border-yellow-200">
                      <AlertDescription>
                        <p className="font-semibold text-yellow-800 mb-2">⚠️ 경고:</p>
                        <ul className="text-sm text-yellow-700 space-y-1">
                          {result.errors.map((error, idx) => (
                            <li key={idx}>• {error}</li>
                          ))}
                        </ul>
                      </AlertDescription>
                    </Alert>
                  )}
                </CardContent>
              </Card>
            )}

            {/* 브랜드 적합도 단독 결과 */}
            {result.brand_image && !result.total_score && (
              <Card className="mb-6">
                <CardHeader>
                  <CardTitle>브랜드 적합도 분석 결과</CardTitle>
                </CardHeader>
                <CardContent className="space-y-6">
                  <div className="p-6 bg-gradient-to-r from-blue-50 to-indigo-50 rounded-lg">
                    <div className="text-center">
                      <div className="text-5xl font-bold text-blue-600 mb-2">
                        {result.brand_image.overall_score.toFixed(1)}
                      </div>
                      <p className="text-gray-600">종합 적합도 점수</p>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <ScoreCard
                      title="이미지 유사도"
                      score={result.brand_image.image_similarity}
                      color="text-blue-600"
                    />
                    <ScoreCard
                      title="텍스트 유사도"
                      score={result.brand_image.text_similarity}
                      color="text-green-600"
                    />
                    <ScoreCard
                      title="톤 매칭"
                      score={result.brand_image.tone_match}
                      color="text-purple-600"
                    />
                    <ScoreCard
                      title="카테고리 매칭"
                      score={result.brand_image.category_match}
                      color="text-orange-600"
                    />
                  </div>

                  <div className="p-4 bg-gray-50 rounded-lg">
                    <p className="text-sm text-gray-600">
                      분석 방법: {result.brand_image.analysis_method}
                    </p>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* 감성분석 단독 결과 */}
            {result.sentiment && !result.total_score && (
              <Card className="mb-6">
                <CardHeader>
                  <CardTitle>감성분석 결과</CardTitle>
                </CardHeader>
                <CardContent className="space-y-6">
                  <div className="p-6 bg-gradient-to-r from-green-50 to-emerald-50 rounded-lg">
                    <div className="text-center">
                      <div className="text-5xl font-bold text-green-600 mb-2">
                        {result.sentiment.sentiment_score.toFixed(1)}
                      </div>
                      <p className="text-gray-600">감성 점수</p>
                    </div>
                  </div>

                  <div className="grid grid-cols-3 gap-4">
                    <div className="p-4 bg-green-50 rounded-lg text-center">
                      <p className="text-sm text-gray-600 mb-1">긍정</p>
                      <p className="text-2xl font-bold text-green-600">
                        {result.sentiment.positive_ratio}%
                      </p>
                    </div>
                    <div className="p-4 bg-gray-50 rounded-lg text-center">
                      <p className="text-sm text-gray-600 mb-1">중립</p>
                      <p className="text-2xl font-bold text-gray-600">
                        {result.sentiment.neutral_ratio}%
                      </p>
                    </div>
                    <div className="p-4 bg-red-50 rounded-lg text-center">
                      <p className="text-sm text-gray-600 mb-1">부정</p>
                      <p className="text-2xl font-bold text-red-600">
                        {result.sentiment.negative_ratio}%
                      </p>
                    </div>
                  </div>

                  <div className="p-4 bg-gray-50 rounded-lg">
                    <p className="text-sm text-gray-600">
                      총 {result.sentiment.total_comments.toLocaleString()}개 댓글 분석 
                      ({result.sentiment.videos_analyzed}개 영상)
                    </p>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* 가중치 비교 결과 */}
            {result.weight_comparison && (
              <Card>
                <CardHeader>
                  <CardTitle>가중치별 점수 비교</CardTitle>
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
                            <span className={`px-3 py-1 rounded text-white text-sm font-medium ${
                              comp.grade === 'S' ? 'bg-gradient-to-r from-yellow-400 to-yellow-600' :
                              comp.grade === 'A' ? 'bg-green-500' :
                              comp.grade === 'B' ? 'bg-blue-500' :
                              comp.grade === 'C' ? 'bg-yellow-500' : 'bg-red-500'
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