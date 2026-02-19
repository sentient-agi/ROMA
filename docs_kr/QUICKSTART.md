# ROMA-DSPy 퀵스타트 (Quick Start)

인프라 설정 없이 **30초 안에** 시작하세요!

## ROMA-DSPy란?

ROMA-DSPy는 [DSPy](https://github.com/stanfordnlp/dspy)를 사용하여 프로덕션 수준의 AI 에이전트를 구축하기 위한 프레임워크입니다. 다음 기능들을 제공합니다:

- **계층적 작업 분해** - 복잡한 작업을 관리 가능한 하위 작업으로 분해
- **모듈식 에이전트 아키텍처** - Atomizer, Planner, Executor, Aggregator, Verifier
- **광범위한 툴킷 시스템** - 파일 조작, 코드 실행, 웹 검색, 암호화폐 데이터 등
- **MCP 통합** - 모든 Model Context Protocol 서버 연결 가능
- **선택적 프로덕션 기능** - REST API, PostgreSQL 영구 저장, MLflow 관측성, 도커 배포

## 필수 조건 (Prerequisites)

### 최소 설치 (권장)
- **Python 3.12+**
- **API 키** (OpenRouter, OpenAI, Anthropic, 또는 Fireworks)

### 전체 설치 (선택 사항)
- **Docker & Docker Compose** (프로덕션 기능용)
- **Just** 명령 실행기 (선택 사항이지만 권장됨)

---

## 퀵스타트 (3가지 경로)

원하는 설정 방식을 선택하세요:

### 경로 A: 최소 설치 (권장 - 30초 안에 시작)

**적합한 대상**: 빠른 평가, 개발, 테스트 - 인프라 불필요

**제공 기능:**
- ✅ 핵심 에이전트 프레임워크 (모든 모듈)
- ✅ 모든 DSPy 예측 전략
- ✅ 파일 저장소 (데이터베이스 불필요)
- ✅ 내장 툴킷 (계산기, 파일 조작)
- ✅ 모든 LLM 제공업체 지원

**필요 없는 것:**
- ❌ 도커 (Docker)
- ❌ PostgreSQL
- ❌ MLflow
- ❌ 인프라 설정

**30초 안에 설치하기:**

```bash
# uv로 설치 (10-100배 빠름, 추천)
uv pip install roma-dspy

# 또는 pip로 설치
pip install roma-dspy

# API 키 설정
export OPENROUTER_API_KEY="sk-or-v1-..."

# 즉시 문제 해결 시작
python -c "from roma_dspy.core.engine.solve import solve; print(solve('What is 2+2?'))"
```

**Python 사용법:**

```python
from roma_dspy.core.engine.solve import solve

# 간단한 작업
result = solve("What is 25 * 47?")
print(result)

# 복잡한 작업
result = solve("Analyze the pros and cons of electric vehicles")
print(result)
```

**설치 시간:** < 30초
**패키지 크기:** ~15개 핵심 의존성
**사용 가능 시점:** 즉시

---

### 경로 B: 도커를 포함한 전체 설치 (프로덕션 기능)

**적합한 대상**: 영구 저장소, 관측성, REST API가 필요한 프로덕션 배포

**추가 기능:**
- ✅ REST API 서버
- ✅ PostgreSQL 영구 저장소
- ✅ MLflow 관측성
- ✅ S3 저장소 통합
- ✅ E2B 코드 실행 샌드박스
- ✅ 대화형 TUI 시각화

1. **복제 및 설정**
   ```bash
   git clone https://github.com/your-org/ROMA-DSPy.git
   cd ROMA-DSPy

   # 환경변수 템플릿 복사
   cp .env.example .env
   ```

2. **환경변수 설정**
   `.env` 파일을 편집하여 API 키를 추가하세요:
   ```bash
   # 필수
   OPENROUTER_API_KEY=your_key_here

   # 선택 (특정 기능용)
   E2B_API_KEY=your_key_here
   EXA_API_KEY=your_key_here
   ```

3. **서비스 시작**
   ```bash
   # 모든 서비스 빌드 및 시작
   just docker-up

   # 또는 MLflow 관측성 포함
   just docker-up-full

   # 상태 확인
   curl http://localhost:8000/health
   ```

4. **첫 번째 작업 실행**
   ```bash
   # Docker CLI 사용
   just solve "What is the capital of France?"

   # 또는 REST API 사용
   curl -X POST http://localhost:8000/api/v1/executions \
     -H "Content-Type: application/json" \
     -d '{"goal": "What is the capital of France?"}'
   ```

**실행 중인 서비스:**
- API: http://localhost:8000
- PostgreSQL: localhost:5432
- MinIO: http://localhost:9001
- MLflow: http://localhost:5000 (`--profile observability` 사용 시)

---

### 경로 C: 암호화폐 에이전트 (도메인 특화 예제)

**적합한 대상**: 암호화폐 분석 유스케이스

1. **빠른 설정**
   ```bash
   just docker-up
   ```

2. **암호화폐 분석 실행**
   ```bash
   # 비트코인 가격 확인
   just solve "What is the current price of Bitcoin?" crypto_agent

   # 복잡한 분석
   just solve "Compare Bitcoin and Ethereum prices, analyze 7-day trends" crypto_agent

   # DeFi 분석
   just solve "Show top 10 DeFi protocols by TVL" crypto_agent
   ```

**Crypto Agent 포함 내역:**
- CoinGecko (15,000+ 암호화폐)
- Binance (현물/선물 시장)
- DefiLlama (DeFi 프로토콜 데이터)
- Arkham (블록체인 분석)
- Exa (웹 검색)

---

## 설치 옵션 비교

| 기능 | 최소 설치 (Minimal) | 도커 전체 설치 (Docker Full) |
|---|---|---|
| **설치 시간** | < 30초 | 2-5분 |
| **필수 조건** | Python 3.12+ | Docker + Docker Compose |
| **인프라** | 필요 없음 | PostgreSQL, MinIO, MLflow (자동 배포) |
| **패키지 크기** | ~15개 의존성 | 모든 기능 |
| **유스케이스** | 빠른 평가, 개발, 테스트 | 프로덕션 배포 |
| **핵심 프레임워크** | ✅ | ✅ |
| **DSPy 전략** | ✅ | ✅ |
| **파일 저장소** | ✅ | ✅ |
| **내장 툴킷** | ✅ | ✅ |
| **REST API** | ❌ | ✅ |
| **PostgreSQL 영구 저장** | ❌ | ✅ |
| **MLflow 추적** | ❌ | ✅ |
| **S3 저장소** | ❌ | ✅ |
| **E2B 샌드박스** | ❌ | ✅ |
| **TUI 시각화** | ❌ | ✅ |

**핵심 차이점**:
- **최소 설치** = 순수 Python 패키지 (도커 없음, 서비스 없음)
- **도커 설치** = 완전한 프로덕션 스택 (PostgreSQL, MLflow, API 등)

---

## 최소 설치에 기능 추가하기

선택적 기능을 위해 Python 의존성을 추가로 설치할 수 있습니다:

```bash
# 특정 기능용 의존성 설치
uv pip install roma-dspy[api]          # REST API 의존성
uv pip install roma-dspy[persistence]  # PostgreSQL 클라이언트 의존성
uv pip install roma-dspy[observability] # MLflow 클라이언트 의존성
uv pip install roma-dspy[e2b]          # E2B 코드 실행
uv pip install roma-dspy[tui]          # TUI 시각화
uv pip install roma-dspy[dev]          # 개발 도구

# 모든 Python 의존성 설치
uv pip install roma-dspy[all]
```

**중요**: 'extras' 설치는 Python 라이브러리만 추가합니다. PostgreSQL, MLflow, API 서버 같은 서비스들은 도커나 별도 배포가 필요합니다.
**모든 기능을 갖춘 프로덕션 환경을 원하시면 도커(경로 B)를 사용하세요.**

---

## Just 명령어 치트시트

### 기본 사용법
```bash
just                      # 모든 명령어 목록
just solve "task"         # 도커로 작업 해결
just viz <execution_id>   # 실행 DAG 시각화
```

### 도커 관리
```bash
just docker-up            # 서비스 시작
just docker-up-full       # MLflow 포함 시작
just docker-down          # 서비스 중지
just docker-logs          # 로그 보기
just docker-ps            # 상태 확인
just docker-shell         # 컨테이너 쉘 열기
```

### 개발
```bash
just install              # 의존성 설치
just test                 # 테스트 실행
just lint                 # 코드 품질 확인
just format               # 코드 포맷팅
just clean                # 캐시 삭제
```

### 사용 가능한 프로필 목록
```bash
just list-profiles
# 출력:
#   - crypto_agent
#   - general
```

---

## 설치 확인 (Verify Installation)

### 1. 상태 확인 (Health Check)
```bash
curl http://localhost:8000/health
```

예상 응답:
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "storage_connected": true,
  "active_executions": 0,
  "uptime_seconds": 123.45
}
```

### 2. CLI 테스트
```bash
# 간단한 계산
just solve "Calculate 15% of 2500"

# 출력된 execution_id로 시각화
just viz <execution_id>
```

### 3. API 테스트
```bash
# 실행 생성 (max_depth=1 또는 2 권장)
curl -X POST http://localhost:8000/api/v1/executions \
  -H "Content-Type: application/json" \
  -d '{
    "goal": "What are the prime numbers between 1 and 20?",
    "max_depth": 2
  }' | jq

# 상태 폴링 (응답의 execution_id 사용)
curl http://localhost:8000/api/v1/executions/<execution_id>/status | jq
```

---

## 설정 프로필 (Configuration Profiles)

ROMA-DSPy는 다양한 유스케이스를 위해 사전 구성된 프로필을 사용합니다.

### 사용 가능한 프로필

| 프로필 | 목적 | 모델 | 툴킷 |
|---|---|---|---|
| **general** | 범용 작업 | Gemini Flash + Claude Sonnet | E2B, FileToolkit, CalculatorToolkit, Exa MCP |
| **crypto_agent** | 암호화폐 분석 | 다중 모델 (작업 인식) | CoinGecko, Binance, DefiLlama, Arkham, E2B |

### 프로필 사용하기

```bash
# CLI 사용 (미지정 시 'general' 기본값)
just solve "your task"
just solve "crypto task" crypto_agent

# API 사용
curl -X POST http://localhost:8000/api/v1/executions \
  -H "Content-Type: application/json" \
  -d '{
    "goal": "Your task",
    "config_profile": "general"
  }'
```

---

## 환경 변수 (Environment Variables)

### 필수 항목
```bash
# LLM 제공업체 (하나만 선택하거나 OpenRouter 사용)
OPENROUTER_API_KEY=xxx        # 권장 (모든 모델 사용 가능)
# 또는 개별 제공업체:
OPENAI_API_KEY=xxx
ANTHROPIC_API_KEY=xxx
GOOGLE_API_KEY=xxx
```

### 선택적 기능
```bash
# 코드 실행 (E2B)
E2B_API_KEY=xxx

# 웹 검색 (Exa MCP)
EXA_API_KEY=xxx

# 암호화폐 API (퍼블릭 API는 키 불필요)
# CoinGecko, Binance, DefiLlama, Arkham 등은 키 없이 작동
```

### 저장소 및 데이터베이스
```bash
# PostgreSQL (도커에서 자동 설정)
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/roma_dspy
POSTGRES_ENABLED=true

# S3 저장소 (선택 사항)
STORAGE_BASE_PATH=/opt/sentient
ROMA_S3_BUCKET=your-bucket
AWS_ACCESS_KEY_ID=xxx
AWS_SECRET_ACCESS_KEY=xxx
```

---

## 일반적인 작업 예시

### 1. 작업 해결 (Solve a Task)
```bash
# 간단한 예 (기본 'general' 프로필 사용)
just solve "What is 2+2?"

# 특정 프로필 사용
just solve "Analyze Bitcoin" crypto_agent

# 모든 옵션 사용
just solve "Complex task" crypto_agent 5 true json
# 파라미터: <task> [profile] [max_depth] [verbose] [output_format]
```

### 2. 실행 확인
```bash
# 모든 실행 목록
curl http://localhost:8000/api/v1/executions | jq

# 특정 실행 확인
curl http://localhost:8000/api/v1/executions/<id> | jq

# 실행 상태 확인
curl http://localhost:8000/api/v1/executions/<id>/status | jq
```

### 3. 로그 보기
```bash
# 모든 서비스
just docker-logs

# 특정 서비스
just docker-logs-service roma-api
just docker-logs-service postgres
just docker-logs-service mlflow
```

### 4. 대화형 시각화
```bash
# 작업 해결 후 execution_id 획득
just solve "Complex task"

# 실행 트리 시각화
just viz <execution_id>
```

---

## 예제 (Examples)

### 예제 1: 간단한 계산
```bash
just solve "Calculate compound interest on $10,000 at 5% annual rate for 10 years"
```

### 예제 2: 웹 리서치
```bash
just solve "Research the latest developments in quantum computing and summarize in 3 bullet points"
```

### 예제 3: 코드 실행
```bash
just solve "Generate a Python script that creates a fibonacci sequence up to 100, execute it, and show results"
```

### 예제 4: 암호화폐 분석
```bash
just solve "Compare Bitcoin and Ethereum market caps, 24h volumes, and price changes" crypto_agent
```

### 예제 5: 파일 조작
```bash
just solve "Create a JSON file with data about the top 5 programming languages and their use cases"
```

---

## 트러블슈팅 (Troubleshooting)

### 도커가 시작되지 않음
```bash
# 도커 실행 여부 확인
docker ps

# 이미지 재빌드
just docker-down
just docker-build-clean
just docker-up

# 로그 확인
just docker-logs
```

### API 응답 없음
```bash
# 상태 확인
curl http://localhost:8000/health

# 컨테이너 상태 확인
just docker-ps

# 로그 보기
just docker-logs-service roma-api
```

---

## 다음 단계 (Next Steps)

### 더 알아보기
- **[설정 가이드](CONFIGURATION.md)** - 프로필, 에이전트, 설정
- **[툴킷 레퍼런스](TOOLKITS.md)** - 사용 가능한 모든 툴킷
- **[MCP 통합](MCP.md)** - MCP 서버 사용법

### 예제 살펴보기
```bash
# 모든 설정 예제 보기
ls config/examples/*/

# 다른 예제 시도해보기
just solve "task" -c config/examples/basic/minimal.yaml
```

**이제 준비되었습니다!** ROMA-DSPy로 에이전트 구축을 시작해보세요 🚀
