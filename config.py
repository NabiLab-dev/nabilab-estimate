import os
import json

# ── Google Service Account 자격증명 ──────────────────────────
CREDS_PATH = "service_account.json"  # 로컬 실행용

CELL_MAP = {
    # 기본 정보
    "estimate_date":     "F5",
    "estimate_number":   "F6",
    "supplier_person":   "B11",
    "supplier_email":    "B12",
    "supplier_phone":    "B13",
    "receiver_company":  "D10",
    "receiver_person":   "E11",
    "receiver_email":    "E12",
    "receiver_phone":    "E13",

    # 품목 1~10 (A16:G25)
    "products[0][name]":   "B16", "products[0][detail]": "C16",
    "products[0][qty]":    "D16", "products[0][price]":  "E16", "products[0][total]": "F16",
    "products[1][name]":   "B17", "products[1][detail]": "C17",
    "products[1][qty]":    "D17", "products[1][price]":  "E17", "products[1][total]": "F17",
    "products[2][name]":   "B18", "products[2][detail]": "C18",
    "products[2][qty]":    "D18", "products[2][price]":  "E18", "products[2][total]": "F18",
    "products[3][name]":   "B19", "products[3][detail]": "C19",
    "products[3][qty]":    "D19", "products[3][price]":  "E19", "products[3][total]": "F19",
    "products[4][name]":   "B20", "products[4][detail]": "C20",
    "products[4][qty]":    "D20", "products[4][price]":  "E20", "products[4][total]": "F20",
    "products[5][name]":   "B21", "products[5][detail]": "C21",
    "products[5][qty]":    "D21", "products[5][price]":  "E21", "products[5][total]": "F21",
    "products[6][name]":   "B22", "products[6][detail]": "C22",
    "products[6][qty]":    "D22", "products[6][price]":  "E22", "products[6][total]": "F22",
    "products[7][name]":   "B23", "products[7][detail]": "C23",
    "products[7][qty]":    "D23", "products[7][price]":  "E23", "products[7][total]": "F23",
    "products[8][name]":   "B24", "products[8][detail]": "C24",
    "products[8][qty]":    "D24", "products[8][price]":  "E24", "products[8][total]": "F24",
    "products[9][name]":   "B25", "products[9][detail]": "C25",
    "products[9][qty]":    "D25", "products[9][price]":  "E25", "products[9][total]": "F25",

    "quote_validity":    "B30",
    "delivery_date":     "B33",
    "product_training":  "B32",
    "extra_note":        "B34",
}

# ── API 설정 ──────────────────────────────────────────────────
API_HOST = "0.0.0.0"
API_PORT = int(os.environ.get("PORT", 9000))

# ── Google Sheets ID ──────────────────────────────────────────
# 인테리어
INTERIOR_TEMPLATE_SHEET_ID = "1Mea0fsZ50TtI3d821fbd6Pp1kzAVQDA7bhlzHjzjc_8"
INTERIOR_DATA_SHEET_ID     = "1YgcdsyC-7MQN1ocnwyiPIxiTlSuMW4XWYaiiA2RoIOc"
INTERIOR_PDF_FOLDER_ID     = "1Xsde4PL_fMAhXVQlH0fSrhnfc6WEuTY0"

# 프린팅
PRINTING_TEMPLATE_SHEET_ID = "1-GIJec5y3TklAo-V-78YdEMAI_G0CaL6JakM4oXcfpg"
PRINTING_DATA_SHEET_ID     = "1T-RKGuhDDhN6E_1koSme_ovnw0ls19uDJEIVa81m2_4"
PRINTING_PDF_FOLDER_ID     = "1ctjPo8g_w17hEafVC1bQe5z7Nsc7KqsI"

# 기본값 (기존 코드 호환)
DATA_COLLECTION_SHEET_ID   = os.environ.get("DATA_COLLECTION_SHEET_ID", INTERIOR_DATA_SHEET_ID)

# ── 담당자 매핑 ───────────────────────────────────────────────
STAFF_MAP = {
    "김나비": "A",
    "이하늘": "B",
    "박서준": "C",
    "최민준": "D",
    "정유진": "E",
    "강지호": "F",
}

# ── Google 자격증명 로드 ──────────────────────────────────────
def get_google_credentials():
    """Render 환경변수 또는 로컬 JSON 파일에서 자격증명 로드"""
    from google.oauth2 import service_account

    SCOPES = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive',
        'https://www.googleapis.com/auth/drive.file',
    ]

    # 1) Render 환경변수 우선
    google_creds = os.getenv("GOOGLE_CREDENTIALS")
    if google_creds:
        try:
            info = json.loads(google_creds)
            if 'private_key' in info and '\\n' in info['private_key']:
                info['private_key'] = info['private_key'].replace('\\n', '\n')
            credentials = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
            print("✅ 환경변수에서 자격증명 로드 성공")
            return credentials
        except Exception as e:
            print(f"❌ 환경변수 자격증명 오류: {e}")

    # 2) 로컬 JSON 파일 fallback
    if os.path.exists(CREDS_PATH):
        try:
            credentials = service_account.Credentials.from_service_account_file(CREDS_PATH, scopes=SCOPES)
            print(f"✅ 로컬 파일({CREDS_PATH})에서 자격증명 로드 성공")
            return credentials
        except Exception as e:
            print(f"❌ 로컬 파일 자격증명 오류: {e}")

    print("❌ Google 자격증명을 찾을 수 없습니다.")
    return None


def get_google_drive_folder_id(category: str = "interior") -> str:
    """카테고리별 PDF 저장 폴더 ID 반환"""
    if category == "printing":
        return os.environ.get("PRINTING_PDF_FOLDER_ID", PRINTING_PDF_FOLDER_ID)
    return os.environ.get("INTERIOR_PDF_FOLDER_ID", INTERIOR_PDF_FOLDER_ID)
