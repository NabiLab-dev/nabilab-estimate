# 나비랩(NabiLab) 자동 견적 시스템

나비랩의 견적서 자동 생성 시스템입니다. 인테리어와 프린팅 두 가지 카테고리의 견적서를 구글 스프레드시트 기반으로 자동 생성하고 PDF로 저장합니다.

## 기능

- 🏠 **인테리어 견적서** — 품목 선택, 수량/단가 자동 계산, PDF 저장
- 🖨️ **프린팅 견적서** — 명함/현수막/리플렛/스티커 버튼 선택, 자동 계산, PDF 저장
- 📊 **구글 시트 자동 저장** — 견적 데이터를 데이터 시트에 자동 기록
- 📄 **PDF 자동 생성** — 구글 드라이브에 PDF 저장 및 링크 공유

## 로컬 실행

```bash
pip install -r requirements.txt
python main.py
```

- 인테리어 견적서: http://localhost:9000/estimate_form_interior.html
- 프린팅 견적서: http://localhost:9000/estimate_form_printing.html

> `service_account.json` 파일이 프로젝트 루트에 있어야 합니다. (git에 포함 안 됨)

## Render 배포

환경 변수 설정:
- `GOOGLE_CREDENTIALS` — service_account.json 파일 내용 전체 (JSON 문자열)
- `PORT` — Render가 자동 설정

## 파일 구조

```
main.py                      # FastAPI 백엔드
config.py                    # 구글 시트 ID, 셀 매핑, 자격증명 로더
estimate_form_interior.html  # 인테리어 견적서 폼 (프론트엔드)
estimate_form_printing.html  # 프린팅 견적서 폼 (프론트엔드)
requirements.txt             # 파이썬 패키지
Procfile                     # Render 실행 명령
render.yaml                  # Render 배포 설정
service_account.json         # ⚠️ 로컬 전용 — git 제외 (.gitignore)
```
