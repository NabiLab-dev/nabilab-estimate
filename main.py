import os
import json
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import gspread
from config import (
    CREDS_PATH, CELL_MAP, API_HOST, API_PORT,
    INTERIOR_TEMPLATE_SHEET_ID, INTERIOR_DATA_SHEET_ID, INTERIOR_PDF_FOLDER_ID,
    PRINTING_TEMPLATE_SHEET_ID, PRINTING_DATA_SHEET_ID, PRINTING_PDF_FOLDER_ID,
    DATA_COLLECTION_SHEET_ID, STAFF_MAP,
    get_google_credentials, get_google_drive_folder_id
)
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2 import service_account
import requests
from datetime import datetime
import re
from google.auth.transport.requests import Request as GoogleRequest

app = FastAPI()

# ── Google client 전역 캐시 ─────────────────────────────────────
_GOOGLE_CREDS = None
_GSPREAD_CLIENT = None
_DRIVE_SERVICE = None

# requests 연결 재사용
HTTP = requests.Session()


def get_google_clients():
    """creds / gspread / drive service를 전역 캐시로 재사용."""
    global _GOOGLE_CREDS, _GSPREAD_CLIENT, _DRIVE_SERVICE

    if _GOOGLE_CREDS is None:
        _GOOGLE_CREDS = get_credentials()
        if not _GOOGLE_CREDS:
            raise RuntimeError("Google credentials 로드 실패")
        print("✅ [캐시] Google credentials 초기 생성 완료")

    try:
        if getattr(_GOOGLE_CREDS, "expired", False) or not getattr(_GOOGLE_CREDS, "token", None):
            print("[캐시] creds 만료 감지 → refresh 시도...")
            _GOOGLE_CREDS.refresh(GoogleRequest())
            print("✅ [캐시] creds refresh 완료")
    except Exception as e:
        print(f"⚠️ [캐시] creds.refresh 실패: {e}")

    if _GSPREAD_CLIENT is None:
        _GSPREAD_CLIENT = gspread.authorize(_GOOGLE_CREDS)
        print("✅ [캐시] gspread client 초기 생성 완료")

    if _DRIVE_SERVICE is None:
        _DRIVE_SERVICE = build("drive", "v3", credentials=_GOOGLE_CREDS, cache_discovery=False)
        print("✅ [캐시] drive service 초기 생성 완료")

    return _GOOGLE_CREDS, _GSPREAD_CLIENT, _DRIVE_SERVICE


def get_credentials():
    """Google Service Account 자격증명 가져오기"""
    try:
        credentials = get_google_credentials()
        if credentials:
            print(f"✅ 자격증명 로드 성공 (타입: {type(credentials)})")
            try:
                if not credentials.valid:
                    import google.auth.transport.requests
                    credentials.refresh(google.auth.transport.requests.Request())
                    print("✅ 토큰 새로고침 성공")
            except Exception as e:
                print(f"⚠️ 토큰 새로고침 실패 (무시됨): {e}")
            return credentials
        else:
            print("❌ 자격증명이 None입니다")
            return None
    except Exception as e:
        print(f"❌ 자격증명 생성 실패: {e}")
        import traceback
        traceback.print_exc()
        return None


# ── 서버 시작 시 환경 확인 ───────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    print("=== 나비랩 자동견적 서버 시작 ===")
    try:
        os.environ['TZ'] = 'UTC'
        import time
        try:
            time.tzset()
        except Exception:
            pass

        print(f"PORT: {os.environ.get('PORT', 'Not set')}")
        print(f"GOOGLE_CREDENTIALS 존재: {'GOOGLE_CREDENTIALS' in os.environ}")

        google_creds = os.getenv("GOOGLE_CREDENTIALS")
        if google_creds:
            try:
                creds_data = json.loads(google_creds)
                with open("creds.json", "w", encoding="utf-8") as f:
                    json.dump(creds_data, f, indent=2, ensure_ascii=False)
                print("✅ creds.json 파일 생성 완료")
            except Exception as e:
                print(f"❌ creds.json 생성 오류: {e}")
        else:
            print("ℹ️ GOOGLE_CREDENTIALS 미설정 — 로컬 service_account.json 사용")

        print("=== 서버 시작 완료 ===")
    except Exception as e:
        print(f"❌ 서버 시작 중 오류: {e}")
        import traceback
        traceback.print_exc()


# ── CORS ────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 정적 파일 서빙
app.mount("/static", StaticFiles(directory="."), name="static")


# ── 카테고리별 Sheet/Folder ID 반환 헬퍼 ───────────────────────
def get_ids(category: str):
    """카테고리에 따라 (template_id, data_id, folder_id) 반환"""
    if category == "printing":
        return PRINTING_TEMPLATE_SHEET_ID, PRINTING_DATA_SHEET_ID, PRINTING_PDF_FOLDER_ID
    return INTERIOR_TEMPLATE_SHEET_ID, INTERIOR_DATA_SHEET_ID, INTERIOR_PDF_FOLDER_ID


# ── 기본 엔드포인트 ─────────────────────────────────────────────
@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.get("/ping")
async def ping():
    return {"message": "pong", "timestamp": datetime.now().isoformat()}

@app.get("/test")
async def test_endpoint():
    return {"status": "success", "message": "나비랩 자동견적 서버가 정상적으로 작동 중입니다."}

@app.get("/")
async def root():
    return FileResponse("index.html")

@app.get("/estimate_form_interior.html")
async def estimate_form_interior():
    return FileResponse("estimate_form_interior.html")

@app.get("/estimate_form_printing.html")
async def estimate_form_printing():
    return FileResponse("estimate_form_printing.html")

@app.get("/estimate_form.html")
async def estimate_form():
    return FileResponse("estimate_form_interior.html")

@app.get("/preview.html")
async def preview():
    return FileResponse("preview.html")

@app.get("/pdf-sharing.html")
async def pdf_sharing():
    return FileResponse("pdf-sharing.html")


# ── 견적서 템플릿 복사 ───────────────────────────────────────────
def copy_estimate_template(category: str = "interior"):
    """견적서 템플릿 스프레드시트를 복사하여 새 파일 생성"""
    try:
        template_id, _, folder_id = get_ids(category)
        creds, gc, drive_service = get_google_clients()

        now = datetime.now()
        label = "인테리어" if category != "printing" else "프린팅"
        new_filename = f"나비랩견적서_{label}_{now.strftime('%y%m%d_%H%M%S')}"

        copy_metadata = {
            'name': new_filename,
            'parents': [folder_id]
        }

        copied_file = drive_service.files().copy(
            fileId=template_id,
            body=copy_metadata,
            supportsAllDrives=True,
            fields='id,name,webViewLink'
        ).execute()

        return {
            "status": "success",
            "file_id": copied_file['id'],
            "filename": new_filename,
            "web_view_link": copied_file.get('webViewLink', ''),
            "message": "견적서 템플릿이 성공적으로 복사되었습니다."
        }

    except Exception as e:
        print(f"견적서 템플릿 복사 중 오류: {e}")
        import traceback
        traceback.print_exc()
        error_msg = str(e)
        if "403" in error_msg:
            msg = "권한 없음 — Service Account에 편집 권한이 필요합니다."
        elif "404" in error_msg:
            msg = "파일/폴더를 찾을 수 없습니다. ID를 확인해 주세요."
        else:
            msg = f"템플릿 복사 오류: {error_msg}"
        return {"status": "error", "message": msg}


@app.post("/create-estimate-template")
async def create_estimate_template(request: Request):
    try:
        body = await request.body()
        data = json.loads(body) if body else {}
    except Exception:
        data = {}
    category = data.get("category", "interior")
    result = copy_estimate_template(category)
    return result


# ── CELL_MAP 확인 ───────────────────────────────────────────────
@app.get("/test-cell-map")
async def test_cell_map():
    return {
        "status": "success",
        "cell_map_keys": list(CELL_MAP.keys()),
        "cell_map_count": len(CELL_MAP),
        "estimate_date_exists": "estimate_date" in CELL_MAP,
        "estimate_number_exists": "estimate_number" in CELL_MAP,
        "sample": {
            "estimate_date": CELL_MAP.get("estimate_date"),
            "estimate_number": CELL_MAP.get("estimate_number"),
            "supplier_person": CELL_MAP.get("supplier_person"),
        }
    }


# ── 견적서 셀 채우기 ────────────────────────────────────────────
@app.post("/estimate")
async def fill_estimate(request: Request):
    try:
        data = await request.json()
        print(f"=== /estimate 호출 ===")

        file_id = data.get("fileId")
        category = data.get("category", "interior")

        # fileId 없으면 새 템플릿 생성
        if not file_id or "{{" in str(file_id):
            template_result = copy_estimate_template(category)
            if template_result["status"] == "success":
                file_id = template_result["file_id"]
                print(f"✅ 새 템플릿 생성: {file_id}")
            else:
                return {"status": "error", "msg": f"템플릿 생성 실패: {template_result['message']}"}

        creds, gc, drive_service = get_google_clients()
        sh = gc.open_by_key(file_id)
        ws = sh.sheet1

        # 파일명 변경
        estimate_number = data.get("estimate_number", "").strip()
        if estimate_number:
            try:
                sh.update_title(estimate_number)
            except Exception as e:
                print(f"파일명 변경 실패 (무시됨): {e}")

        updates = []

        # 일반 필드
        basic_fields = [
            "supplier_person", "supplier_email", "supplier_phone",
            "receiver_company", "receiver_person", "receiver_email", "receiver_phone",
            "quote_validity", "delivery_date", "product_training", "extra_note"
        ]
        for key in basic_fields:
            if key in data and key in CELL_MAP:
                updates.append({"range": CELL_MAP[key], "values": [[data[key]]]})

        # 견적일자
        est_date = data.get("estimate_date") or datetime.now().strftime("%Y-%m-%d")
        if "estimate_date" in CELL_MAP:
            updates.append({"range": CELL_MAP["estimate_date"], "values": [[est_date]]})

        # 견적번호 (없으면 자동 생성)
        if not estimate_number:
            supplier = data.get("supplier_person", "")
            person_id = STAFF_MAP.get(supplier, "X")
            today_count = get_today_pdf_count()
            estimate_number = f"NL{datetime.now().strftime('%y%m%d')}-{person_id}-{today_count}"
            print(f"견적번호 자동 생성: {estimate_number}")

        if "estimate_number" in CELL_MAP:
            updates.append({"range": CELL_MAP["estimate_number"], "values": [[estimate_number]]})

        # 제품 정보 (최대 10개)
        products = data.get("products", [])
        for i in range(10):
            product = products[i] if i < len(products) else {}
            for field in ["name", "detail", "qty", "price", "total"]:
                cell_key = f"products[{i}][{field}]"
                value = product.get(field, "")
                if field == "detail" and value:
                    value = value.replace('<br>', '\n').replace('<br/>', '\n').replace('<br />', '\n')
                    value = '\n'.join(line.strip() for line in value.split('\n') if line.strip())
                    value = f'\n{value}\n'
                if cell_key in CELL_MAP:
                    updates.append({"range": CELL_MAP[cell_key], "values": [[value]]})

        print(f"총 {len(updates)}개 셀 업데이트")
        ws.batch_update(updates)

        # 제품 상세 셀 줄바꿈 포맷
        try:
            detail_cells = [CELL_MAP[f"products[{i}][detail]"] for i in range(10) if f"products[{i}][detail]" in CELL_MAP]
            for cell in detail_cells:
                ws.format(cell, {"wrapStrategy": "WRAP"})
        except Exception as e:
            print(f"⚠️ 셀 포맷 오류 (무시됨): {e}")

        return {
            "status": "success",
            "file_id": file_id,
            "estimate_number": estimate_number
        }

    except Exception as e:
        print(f"❌ fill_estimate 오류: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": f"견적서 생성 중 오류: {str(e)}"}


# ── 데이터 수집 + PDF 생성 ──────────────────────────────────────
@app.post("/collect-data")
async def collect_data(request: Request):
    """견적 데이터를 시트에 저장하고 PDF를 Drive에 업로드"""
    print("=== /collect-data 호출 ===")
    try:
        data = await request.json()
        category = data.get("category", "interior")
        _, data_sheet_id, pdf_folder_id = get_ids(category)

        creds, gc, drive_service = get_google_clients()
        sh = gc.open_by_key(data_sheet_id)
        ws = sh.sheet1

        file_id = data.get("fileId", "")
        estimate_link = f"https://docs.google.com/spreadsheets/d/{file_id}/edit" if file_id else ""

        # 제품 정보 추출
        products = data.get("products", [])
        product_names = [(products[i].get("name", "") if i < len(products) else "") for i in range(10)]

        total_sum = sum(p.get("total", 0) for p in products if p.get("total"))
        vat = round(total_sum * 0.1)
        final_total = total_sum + vat

        # PDF 생성 및 업로드
        pdf_link = ""
        pdf_id = ""
        receiver_company = data.get("receiver_company", "")
        estimate_number = data.get("estimate_number", "")

        def clean_filename(s):
            return re.sub(r'[^\w\s-]', '', s).strip()

        pdf_filename = f"나비랩견적서_{clean_filename(receiver_company)}_{estimate_number}.pdf"

        if file_id:
            if export_sheet_to_pdf(file_id, pdf_filename, creds):
                pdf_id, pdf_link = upload_pdf_to_drive(pdf_filename, pdf_folder_id, pdf_filename)
                try:
                    if os.path.exists(pdf_filename):
                        os.remove(pdf_filename)
                except Exception:
                    pass

        # 데이터 시트에 행 추가
        row_data = [
            data.get("estimate_date", ""),     # A: 견적일자
            estimate_number,                    # B: 견적번호
            data.get("supplier_person", ""),    # C: 담당자
            data.get("receiver_company", ""),   # D: 수신 회사
            data.get("receiver_person", ""),    # E: 수신 담당자
            data.get("receiver_email", ""),     # F: 이메일
            data.get("receiver_phone", ""),     # G: 전화
            data.get("product_category", ""),   # H: 제품 카테고리
            *product_names,                     # I~R: 제품명 1~10
            final_total,                        # S: 최종견적(VAT포함)
            data.get("delivery_date", ""),      # T: 납기일
            data.get("product_training", ""),   # U: 제품교육
            estimate_link,                      # V: 견적서(엑셀)
            pdf_link,                           # W: 견적서(PDF)
        ]
        ws.append_row(row_data)

        return {
            "status": "success",
            "message": "견적 데이터 및 PDF가 성공적으로 저장되었습니다.",
            "pdf_link": pdf_link,
            "pdf_id": pdf_id,
        }

    except Exception as e:
        print(f"데이터 수집 오류: {e}")
        import traceback
        print(traceback.format_exc())
        return {"status": "error", "message": f"데이터 수집 실패: {str(e)}"}


# ── /search-deals stub (Pipedrive 제거됨) ───────────────────────
@app.get("/search-deals")
async def search_deals(q: str = ""):
    """Pipedrive 연동 없는 스텁 — 빈 목록 반환"""
    return {"deals": []}


# ── PDF export 및 Drive 업로드 ──────────────────────────────────
def export_sheet_to_pdf(sheet_id, pdf_filename, creds, gid=0):
    """Google Sheets를 PDF로 내보내기"""
    try:
        # 토큰 유효성 확인
        try:
            if getattr(creds, "expired", False) or not getattr(creds, "token", None):
                creds.refresh(GoogleRequest())
        except Exception as e:
            print(f"⚠️ [PDF] 토큰 갱신 실패: {e}")

        export_url = (
            f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?"
            f"format=pdf&portrait=true&size=A4&"
            f"fitw=true&fith=false&"
            f"top_margin=0.5&bottom_margin=0.5&"
            f"left_margin=0.5&right_margin=0.5&"
            f"printtitle=false&sheetnames=false&"
            f"pagenum=UNDEFINED&gridlines=false&"
            f"gid={gid}"
        )

        headers = {'Authorization': f'Bearer {creds.token}'}
        response = HTTP.get(export_url, headers=headers)

        if response.status_code == 200:
            with open(pdf_filename, 'wb') as f:
                f.write(response.content)
            print(f"✅ PDF 생성 성공: {pdf_filename}")
            return True
        else:
            print(f"❌ PDF export 실패: HTTP {response.status_code}")
            # 백업: Drive API
            _, _, drive_service = get_google_clients()
            req = drive_service.files().export_media(fileId=sheet_id, mimeType='application/pdf')
            with open(pdf_filename, 'wb') as f:
                f.write(req.execute())
            print(f"✅ Drive API 백업 PDF 생성 성공: {pdf_filename}")
            return True

    except Exception as e:
        print(f"❌ PDF export 예외: {e}")
        return False


def upload_pdf_to_drive(pdf_path, folder_id, file_name):
    """PDF 파일을 Google Drive에 업로드"""
    try:
        _, _, drive_service = get_google_clients()
        file_metadata = {'name': file_name, 'parents': [folder_id]}
        media = MediaFileUpload(pdf_path, mimetype='application/pdf')
        file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id,webViewLink',
            supportsAllDrives=True
        ).execute()
        return file.get('id'), file.get('webViewLink')
    except Exception as e:
        print(f"❌ PDF 업로드 실패: {e}")
        return None, None


# ── PDF 카운터 (견적번호 자동 생성용) ────────────────────────────
def get_today_pdf_count():
    """오늘 PDF 생성 횟수를 읽고 +1 반환"""
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        count_data = {}
        if os.path.exists("pdf_count.json"):
            with open("pdf_count.json", "r", encoding="utf-8") as f:
                count_data = json.load(f)
        today_count = count_data.get(today, 0) + 1
        count_data[today] = today_count
        with open("pdf_count.json", "w", encoding="utf-8") as f:
            json.dump(count_data, f, ensure_ascii=False, indent=2)
        return today_count
    except Exception as e:
        print(f"PDF 카운트 처리 오류: {e}")
        return 1


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=API_HOST, port=API_PORT)
