# OnRamp STT API

회의 음성을 WebRTC VAD로 분할하고 Naver CLOVA Speech로 전사하는 내부 서비스입니다.

현재 구현 범위는 다음과 같습니다.

```text
Redis 전사 요청
  → Object Storage 원본 다운로드
  → ffprobe 검증
  → 16 kHz mono PCM WAV 변환
  → WebRTC VAD
  → 최대 55초 청크 생성
  → Redis 청크 요청
  → CLOVA Speech ko-KR 전사
  → 청크별 결과 저장
  → timestamp 기준 원본 transcript 병합
  → 용어 사전 1차 교정
  → OpenAI 기반 제한적 2차 교정
  → 교정 결과 저장
  → 최종 완료 이벤트 발행
```

`onramp-api` 보고서 연동과 사전 운영 자동화는 후속 범위입니다.

## 구성

- FastAPI: health와 내부 작업 상태 조회
- PostgreSQL: STT job, chunk, outbox, inbox 원장
- Redis Streams: 전사 요청과 CLOVA 청크 작업 전달
- MinIO/S3: 원본, 정규화 WAV, VAD 청크, CLOVA raw response 저장
- ffmpeg/ffprobe: 오디오 검증과 변환
- WebRTC VAD: 발화 탐지와 최대 55초 청크 생성

## 로컬 설치

Python 3.11과 ffmpeg가 필요합니다.

```bash
cp .env.example .env
uv venv --python 3.11 .venv
source .venv/bin/activate
uv pip install -e ".[dev,s3]"
```

`.env`에 CLOVA와 교정 정보를 입력합니다.

```dotenv
NAVER_CLOVA_SPEECH_INVOKE_URL=https://clovaspeech-gw.ncloud.com/external/v1/<domain-id>
NAVER_CLOVA_SPEECH_SECRET_KEY=<secret-key>
OPENAI_API_KEY=<openai-api-key>
```

`INVOKE_URL`은 `/recognizer/upload`를 제외한 도메인 URL입니다.

## Docker Compose

API와 로컬 인프라만 실행:

```bash
docker compose up --build -d
curl http://localhost:8001/v1/health
```

CLOVA worker까지 실행:

```bash
docker compose --profile pipeline up --build -d
```

호스트에서 `scripts/enqueue_audio.py`를 실행할 때는 `.env`의 storage 설정을
Compose의 MinIO에 맞춥니다.

```dotenv
STORAGE_BACKEND=s3
STORAGE_ENDPOINT_URL=http://localhost:9000
STORAGE_ACCESS_KEY=onramp
STORAGE_SECRET_KEY=onramp-secret
STORAGE_BUCKET=onramp-stt
```

서비스:

| 서비스 | 로컬 주소 |
|---|---|
| STT API | `http://localhost:8001` |
| PostgreSQL | `localhost:5434` |
| Redis | `localhost:6380` |
| MinIO API | `http://localhost:9000` |
| MinIO Console | `http://localhost:9001` |

MinIO 로컬 계정은 개발 전용 `onramp / onramp-secret`입니다.

## 로컬 전사 테스트

Docker Compose pipeline을 실행한 뒤 테스트 파일을 enqueue합니다.

```bash
source .venv/bin/activate
python scripts/enqueue_audio.py "/absolute/path/meeting.m4a" --tenant-id local
```

출력된 `transcription_id`로 상태를 확인합니다.

```bash
curl http://localhost:8001/v1/internal/transcriptions/<transcription-id>
```

이 스크립트는 개발용입니다. 운영에서는 `onramp-api`가 object key를 생성하고 `onramp:stt:requests:v1` 이벤트를 발행합니다.

## 프로세스별 실행

```bash
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8001
python -m app.workers.outbox_publisher
python -m app.workers.orchestrator
python -m app.workers.clova
python -m app.workers.correction
```

worker 역할:

- `outbox_publisher`: PostgreSQL outbox를 Redis Stream에 발행
- `orchestrator`: 원본 다운로드, WAV 변환, VAD, chunk job 생성
- `clova`: CLOVA 호출, retry/backoff, 청크 결과 저장
- `correction`: 병합 transcript 교정, audit log 저장, 최종 완료 event 발행

## 주요 환경변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `DATABASE_URL` | 로컬 PostgreSQL | STT 작업 원장 |
| `REDIS_URL` | `redis://localhost:6380/0` | Redis Streams |
| `STORAGE_BACKEND` | `local` | `local` 또는 `s3` |
| `STORAGE_ENDPOINT_URL` | `http://localhost:9000` | MinIO/S3 endpoint |
| `STT_VAD_AGGRESSIVENESS` | `1` | 낮은 음량 발화 보존 |
| `STT_VAD_PADDING_MS` | `500` | 발화 경계 padding |
| `STT_VAD_TRIGGER_RATIO` | `0.8` | 발화 진입·종료 기준 |
| `STT_VAD_MAX_CHUNK_SECONDS` | `55` | 내부 청크 상한 |
| `CLOVA_MAX_CONCURRENT_JOBS` | `2` | 전체 worker 전역 동시 요청 수 |
| `CLOVA_MAX_RETRY_COUNT` | `3` | retryable 오류 재시도 횟수 |
| `CLOVA_CHUNK_LEASE_SEC` | `600` | 중단된 processing 청크 재점유 대기 시간 |
| `REDIS_PENDING_RECLAIM_IDLE_MS` | `300000` | 중단된 Redis 메시지 회수 기준 |

CLOVA 요청은 `ko-KR`, sync, word alignment, noise filtering, diarization을 사용합니다. `boostings`와 `useDomainBoostings`는 보내지 않습니다.

## 품질 검사

```bash
make lint
make typecheck
make test
```

Jenkins는 PR에서 lint, mypy, test, Kaniko 이미지 빌드를 검사합니다. `main`에서는 Harbor에 Git SHA tag로 이미지를 push하고 digest를 출력합니다. GitOps image 갱신은 STT Helm chart가 추가되는 후속 PR에서 연결합니다.
