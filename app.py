import streamlit as st
import google.generativeai as genai
import chromadb
import requests
import json
import time
import base64
from PIL import Image, ImageDraw, ImageFont

def get_base64_of_bin_file(bin_file):
    with open(bin_file, 'rb') as f:
        data = f.read()
    return base64.b64encode(data).decode()

try:
    img_base64 = get_base64_of_bin_file("yongyong.png")
    yongyong_icon_html = f'<img src="data:image/png;base64,{img_base64}" style="width: 40px; height: 40px; vertical-align: middle; margin-right: 10px;">'
except FileNotFoundError:
    yongyong_icon_html = "🎓"

try:
    icon_image = Image.open("yongyong.png")
    st.set_page_config(page_title="서일대학교 용용이 비서", page_icon=icon_image)
except FileNotFoundError:
    st.set_page_config(page_title="서일대학교 용용이 비서", page_icon="🎓")

SEOIL_LOCATIONS = {
    "흥학관": {"x": 515, "y": 210, "desc": "1번 건물: 카페, 동아리방", "keywords": ["흥학관", "카페", "커피", "동아리"]},
    "호천관": {"x": 370, "y": 250, "desc": "2번 건물: 열람실", "keywords": ["호천관"]},
    "세종관": {"x": 490, "y": 150, "desc": "3번 건물: 강의실", "keywords": ["세종관", "강의실"]},
    "서일관": {"x": 670, "y": 110, "desc": "4번 건물: 대학본부", "keywords": ["서일관", "본부", "총장실"]},
    "지덕관": {"x": 750, "y": 140, "desc": "5번 건물: 학생회관", "keywords": ["지덕관", "학생회관"]},
    "누리관": {"x": 835, "y": 160, "desc": "6번 건물: 종합정보관", "keywords": ["누리관", "정보관"]},
    "도서관": {"x": 770, "y": 70, "desc": "7번 건물: 도서관", "keywords": ["도서관, 열람실, 책"]},
    "배양관": {"x": 860, "y": 100, "desc": "8번 건물: 편의점(B2)", "keywords": ["배양관", "편의점", "매점"]},
    "동아리관": {"x": 660, "y": 260, "desc": "9번 건물", "keywords": ["동아리관"]},
    "정문": {"x": 615, "y": 325, "desc": "10번: 정문", "keywords": ["정문", "입구"]},
}

# --- 이미지 위에 위치 표시하는 함수 ---
def highlight_building_on_image(target_name, x, y):
    """
    seoil_map.png 이미지를 불러와서 해당 좌표(x,y)에 빨간 동그라미를 그립니다.
    """
    try:
        # 1. 기본 지도 이미지 불러오기
        base_image = Image.open("seoil_map.png")
        draw = ImageDraw.Draw(base_image)
        
        # 2. 동그라미 그리기 (반지름 30px)
        radius = 30
        # 빨간색 굵은 원 (두께 5)
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), outline="red", width=5)
        
        # 3. 반투명한 빨간색 채우기
        # overlay = Image.new('RGBA', base_image.size, (255, 255, 255, 0))
        # draw_overlay = ImageDraw.Draw(overlay)
        # draw_overlay.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(255, 0, 0, 60))
        # base_image = Image.alpha_composite(base_image.convert('RGBA'), overlay)

        return base_image
    except FileNotFoundError:
        return None

try:
    FIREBASE_API_KEY = st.secrets["firebase_web"]["apiKey"]
    FIREBASE_DB_URL = st.secrets["firebase_web"]["databaseURL"]
    
    GOOGLE_CLIENT_ID = st.secrets["firebase_web"]["GOOGLE_CLIENT_ID"]
    GOOGLE_CLIENT_SECRET = st.secrets["firebase_web"]["GOOGLE_CLIENT_SECRET"]
    REDIRECT_URI = "http://localhost:8501"

    # Google API 엔드포인트
    AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URL = "https://oauth2.googleapis.com/token"

    # Firebase REST API 엔드포인트 URL 정의
    SIGNUP_URL = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"
    LOGIN_URL = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}"
    GOOGLE_LOGIN_URL = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithIdp?key={FIREBASE_API_KEY}"

except KeyError as e:
    st.error(f"Firebase 설정(.streamlit/secrets.toml)에 '{e.args[0]}' 키가 누락되었습니다.")
    st.stop()
except Exception as e:
    st.error(f"Firebase 설정 로드 중 오류 발생: {e}")
    st.stop()

# --- 세션 상태 초기화 ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'user_info' not in st.session_state:
    st.session_state.user_info = None # {'email', 'uid', 'name', 'idToken'}
if 'page' not in st.session_state:
    st.session_state.page = 'login'
if 'user_msg_count' not in st.session_state:
    st.session_state.user_msg_count = 0
try:
    # 1. secrets.toml에서만 키를 불러옵니다.
    API_KEY = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=API_KEY)
    
except (KeyError, FileNotFoundError):
    st.error("GEMINI_API_KEY가 .streamlit/secrets.toml에 설정되지 않았습니다.")
    st.stop()
except Exception as e:
    st.error(f"Gemini API 설정 중 오류 발생: {e}")
    st.stop()

# --- ChromaDB 로딩 함수 ---
@st.cache_resource(show_spinner="AI 지식 베이스를 로딩 중입니다...")
def load_chroma_collection():
    """ChromaDB에서 'seoil_info_db' 컬렉션을 불러옵니다."""
    try:
        db_path = "./chroma_db"
        client = chromadb.PersistentClient(path=db_path)
        collection = client.get_collection(name="seoil_info_db")
        return collection
    except Exception as e:
        st.error(f"ChromaDB 컬렉션을 불러오는 데 실패했습니다: {e}")
        st.error("'prepare_data.py'를 먼저 실행하여 데이터베이스를 생성해야 합니다.")
        return None

# --- 관련 정보 검색 함수 ---
def find_relevant_info(query, collection, top_k=5):
    """사용자 질문을 임베딩하고, ChromaDB에서 의미상 가장 유사한 정보 조각 top_k개를 찾습니다."""
    if collection is None:
        return ""
    
    query_embedding = genai.embed_content(model="models/embedding-001",
                                          content=query,
                                          task_type="RETRIEVAL_QUERY")['embedding']
    
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k
    )
    
    if results['documents'] and results['documents'][0]:
        relevant_info = "\n\n".join(results['documents'][0])
        return relevant_info
    else:
        return ""

# --- Firebase 오류 파싱 함수 ---
def parse_firebase_error(response_text):
    """Firebase의 JSON 오류 응답을 파싱하여 사용자 친화적인 메시지로 변환합니다."""
    try:
        error_json = json.loads(response_text)
        error_message = error_json.get('error', {}).get('message', '알 수 없는 오류')
        
        if error_message == "INVALID_LOGIN_CREDENTIALS":
            return "이메일 또는 비밀번호가 올바르지 않습니다."
        if error_message == "EMAIL_NOT_FOUND":
            return "등록되지 않은 이메일입니다."
        elif error_message == "INVALID_PASSWORD":
            return "비밀번호가 틀렸습니다."
        elif error_message == "EMAIL_EXISTS":
            return "이미 가입된 이메일입니다."
        elif "WEAK_PASSWORD" in error_message:
            return "비밀번호는 6자리 이상이어야 합니다."
        else:
            return f"오류: {error_message}"
    except json.JSONDecodeError:
        return "알 수 없는 오류가 발생했습니다. (오류 메시지 파싱 실패)"

# 채팅 기록을 Firebase에 저장하는 함수
def save_chat_log(uid, token, role, message):
    """채팅 메시지를 Firebase Realtime Database에 저장합니다."""
    
    # uid나 token이 없으면 저장하지 않음
    if not uid or not token:
        return
    try:
        # timestamp를 키로 사용하여 시간순으로 정렬
        timestamp = int(time.time() * 1000)
        chat_ref = f"chat_history/{uid}/{timestamp}"
        
        data = {
            "role": role,
            "content": message,
            "timestamp": timestamp
        }
        
        db_url = FIREBASE_DB_URL # 전역 변수 사용
        if not db_url.endswith('/'): 
            db_url += '/'
        
        save_url = f"{db_url}{chat_ref}.json?auth={token}"
        
        # requests.put을 사용하되, 앱이 멈추지 않게 timeout 설정
        requests.put(save_url, json=data, timeout=3)
    except Exception as e:
        print(f"Log save error: {e}")
    except requests.exceptions.RequestException as e:
        # 사용자에게 오류를 띄우는 대신, 터미널에만 로그를 남김
        print(f"Error saving chat log to Firebase: {e}")
    except Exception as e:
        print(f"An unexpected error occurred in save_chat_log: {e}")

# --- 키워드 분석 및 업데이트 함수 ---
def analyze_chat_keywords(uid, token):
    """채팅 기록을 분석하여 키워드를 추출하고 DB에 업데이트합니다."""
    try:
        db_url = FIREBASE_DB_URL
        if not db_url.endswith('/'): db_url += '/'
        
        # 1. 채팅 기록 가져오기
        load_url = f"{db_url}chat_history/{uid}.json?auth={token}"
        response = requests.get(load_url)
        
        if response.status_code != 200 or not response.json():
            return []

        chat_data = response.json()
        # 최근 대화 10개만 분석 (6개로 축소하여 최근 주제만을 강조 가능)
        full_text = ""
        for key in sorted(chat_data.keys())[-10:]: 
            msg = chat_data[key]
            if msg['role'] == 'user':
                full_text += msg['content'] + "\n"
        
        if len(full_text) < 5: return []

        # 2. Gemini에게 키워드 추출 요청
        analysis_model = genai.GenerativeModel('gemini-flash-latest')
        prompt = f"""
        다음은 사용자가 AI와 나눈 대화 내용이야. 
        이 사용자가 관심 있어 하는 핵심 주제나 키워드를 3개만 단어 형태로 추출해줘.
        결과는 콤마(,)로만 구분해서 알려줘. 설명은 필요 없어.
        (예시: 장학금, 셔틀버스, 수강신청)

        [대화 내용]
        {full_text}
        """
        result = analysis_model.generate_content(prompt).text
        keywords = [k.strip() for k in result.split(',') if k.strip()]
        
        # 3. DB에 저장
        update_url = f"{db_url}users/{uid}/dynamic_keywords.json?auth={token}"
        requests.put(update_url, json=keywords)
        
        return keywords
    except Exception as e:
        print(f"Analysis error: {e}")
        return []
    
def exchange_code_for_token(code):
    """Google로부터 받은 'code'를 'id_token'으로 교환합니다."""
    payload = {
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI
    }
    try:
        response = requests.post(TOKEN_URL, data=payload)
        response.raise_for_status() # 오류가 있으면 예외 발생
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Google 토큰 교환 실패: {e.response.json()}")
        return None

def sign_in_with_google(google_id_token):
    payload = {
        'postBody': f"id_token={google_id_token}&providerId=google.com",
        'requestUri': REDIRECT_URI,
        'returnSecureToken': True
    }
    response = requests.post(GOOGLE_LOGIN_URL, json=payload)

    if response.status_code == 200:
        user_data = response.json()
        uid = user_data['localId']
        id_token = user_data['idToken']
        email = user_data.get('email', '이메일 없음')
        
        db_url = FIREBASE_DB_URL
        if not db_url.endswith('/'): 
            db_url += '/'
        user_db_url = f"{db_url}users/{uid}.json?auth={id_token}"

        name_response = requests.get(user_db_url)
        user_name = "사용자"
        user_interests = None
        user_dynamic_keywords = []
        
        if name_response.status_code == 200 and name_response.json():
            name_data = name_response.json()
            user_name = name_data.get('name', '사용자')
            user_interests = name_data.get('interests')
            user_dynamic_keywords = name_data.get('dynamic_keywords', [])
        else:
            user_name = user_data.get('displayName', '사용자')
            # 신규 가입 시 dynamic_keywords: [] 초기화
            user_data_payload = {"name": user_name, "email": email, "interests": None, "dynamic_keywords": []}
            requests.put(user_db_url, json=user_data_payload)
            
        return {"email": email, "uid": uid, "name": user_name, "idToken": id_token, "interests": user_interests}
    else:
        st.error(f"Google 로그인 실패: {parse_firebase_error(response.text)}")
        return None

def get_google_auth_url():
    """클릭 가능한 Google 로그인 URL을 생성합니다."""
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile", # 필수 스코프
        "access_type": "offline"
    }
    # URL 파라미터를 안전하게 인코딩하여 생성
    req = requests.Request('GET', AUTH_URL, params=params)
    return req.prepare().url

# --- Google 로그인 리디렉션 처리 ---
if 'code' in st.query_params:
    auth_code = st.query_params["code"]
    
    with st.spinner("Google 계정 인증 중..."):
        token_data = exchange_code_for_token(auth_code)
    
    if token_data and "id_token" in token_data:
        google_id_token = token_data["id_token"]
        with st.spinner("Firebase 로그인 중..."):
            user_info = sign_in_with_google(google_id_token)
        
        if user_info:
            st.session_state.logged_in = True
            st.session_state.user_info = user_info
            st.query_params.clear() # URL에서 'code' 제거
            st.rerun()
    else:
        st.error("Google 인증에 실패했습니다. 토큰을 가져올 수 없습니다.")

# --- 페이지 전환용 콜백 함수 ---
def set_page(page):
    st.session_state.page = page

# 메인 앱 로직: 로그인 상태에 따라 UI 분기
if st.session_state.logged_in:
    # --- 1. [로그인 성공 시] 챗봇 메인 앱 ---
    
    # 1. Onboarding/Chat 페이지 라우팅 로직
    
    # 'interests' 필드가 None이면 (신규 가입자) 'onboarding'으로 강제 설정
    if st.session_state.user_info.get('interests') is None:
        st.session_state.page = 'onboarding'
    else:
        # interests가 None이 아니면(즉, 이미 온보딩을 완료했으면)
        # page 상태가 'login'(초기 상태)일 경우 'chat'으로 변경
        if st.session_state.page == 'login':
            st.session_state.page = 'chat'

    # 2. 페이지 라우팅
    if st.session_state.page == 'onboarding':
        # --- 1-A. 온보딩 페이지\ ---
        st.markdown(f"<h1>{yongyong_icon_html} 용용이 시작하기</h1>", unsafe_allow_html=True)
        st.subheader(f"{st.session_state.user_info['name']}님, 환영합니다!")
        st.write("용용이가 맞춤형 정보를 추천해드릴 수 있도록, 관심사를 선택해주세요. (선택사항)")

        INTEREST_OPTIONS = [
            "학사공지", "장학금", "셔틀버스", 
            "도서관", "학생식당", "카페", "편의점"
        ]
        
        selected_interests = st.multiselect(
            "관심있는 주제를 모두 선택해주세요. (여러 개 선택 가능)",
            INTEREST_OPTIONS
        )

        # "저장하기"와 "건너뛰기" 버튼
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("저장하기", use_container_width=True, type="primary"):
                # "저장하기" 로직 (선택한 리스트 저장)
                with st.spinner("관심사 저장 중..."):
                    uid = st.session_state.user_info['uid']
                    token = st.session_state.user_info['idToken']
                    db_url = FIREBASE_DB_URL
                    if not db_url.endswith('/'): 
                        db_url += '/'
                    user_db_url = f"{db_url}users/{uid}/interests.json?auth={token}"
                    
                    update_data = {"interests": selected_interests, "dynamic_keywords": []}
                    response = requests.put(user_db_url, json=selected_interests) 
                    
                    if response.status_code == 200:
                        st.session_state.user_info['interests'] = selected_interests
                        st.session_state.user_info['dynamic_keywords'] = []
                        st.session_state.page = 'chat' # 챗봇 페이지로 전환
                        st.success("저장되었습니다! 용용이 비서를 시작합니다.")
                        st.rerun()
                    else:
                        st.error("관심사 저장에 실패했습니다. 다시 시도해주세요.")

        with col2:
            if st.button("건너뛰기", use_container_width=True):
                # "건너뛰기" 로직 (빈 리스트 '[]' 저장)
                with st.spinner("설정 저장 중..."):
                    uid = st.session_state.user_info['uid']
                    token = st.session_state.user_info['idToken']
                    db_url = FIREBASE_DB_URL
                    if not db_url.endswith('/'): 
                        db_url += '/'
                    user_db_url = f"{db_url}users/{uid}/interests.json?auth={token}"
                    
                    # [중요] 빈 리스트를 저장하여 다시는 이 페이지가 안 뜨게 함
                    response = requests.put(user_db_url, json=[]) 
                    
                    if response.status_code == 200:
                        st.session_state.user_info['interests'] = []
                        st.session_state.user_info['dynamic_keywords'] = []
                        st.session_state.page = 'chat' # 챗봇 페이지로 전환
                        st.rerun()
                    else:
                        st.error("설정 저장에 실패했습니다. 다시 시도해주세요.")

    elif st.session_state.page == 'chat':

        uid = st.session_state.user_info.get('uid')
        token = st.session_state.user_info.get('idToken')

       # Popover 내부에서 사용할 콜백 함수 정의
        def go_to_onboarding():
            """관심사 수정 페이지로 이동"""
            st.session_state.page = 'onboarding'
        
        def do_logout():
            """로그아웃 처리"""
            st.session_state.logged_in = False
            st.session_state.user_info = None
            st.session_state.page = 'login'
        
        user_initial = st.session_state.user_info['name']
        
        with st.popover(user_initial): # 👤
            st.write(f"{st.session_state.user_info['name']}님, 환영합니다.")
            st.divider()
            st.button("⚙️ 관심사 수정", on_click=go_to_onboarding, use_container_width=True)
            st.button("🚪 로그아웃", on_click=do_logout, use_container_width=True)
            
        st.markdown('</div>', unsafe_allow_html=True)

        collection = load_chroma_collection() # DB 로드
        
        # 1. 사용자의 관심사 불러오기
        static_interests = st.session_state.user_info.get('interests', []) or []
        dynamic_keywords = st.session_state.user_info.get('dynamic_keywords', []) or []
        all_interests = list(set(static_interests + dynamic_keywords))
        
        if all_interests:
            interests_string = ", ".join(all_interests)
            interest_prompt_part = f"\n\n# 사용자의 관심사 및 최근 관심 키워드: [{interests_string}]\n사용자가 이 주제와 관련하여 질문하면, 이 정보를 바탕으로 더 상세하게 답변해주세요."
        else:
            interest_prompt_part = ""

        # 3. 최종 시스템 프롬프트에 관심사 삽입
        system_instruction = f"""
        너는 '서일대학교' 학생들을 위한 AI 챗봇 '용용이 비서'야. 학생들의 질문에 친절하고 정확하게 답변해야 해.
        {interest_prompt_part}

        기존에 답변 가능한 범위의 질문을 받았다면 원래 하던 답변대로 응답해.
        # 사용자의 질문이 아래 [서일대학교 핵심 고정 정보]와 관련이 있다면,
        # [참고 정보]를 보기 전에 이 내용을 바탕으로 "즉시" 답변해줘.

        [서일대학교 핵심 고정 정보]
        **1. 셔틀버스 및 찾아오시는 길**
        * **지하철**: 7호선 면목역(서일대입구) 2번 출구
        * **파랑(간선)버스**: 271번 (서일대 하차)
        * **녹색(지선)버스**: 2013번, 2230번, 1213번
        * **노랑(마을)버스**: 중랑2번
        * **대학 셔틀버스 (학기 중 평일 오전 운행)**
            * **운행 시간**: 오전 08:30 ~ 10:30
            * **배차 간격**: 20분~25분 간격
            * **승차 위치 (망우역)**: 1번 출구 역앞 로터리
            * **승차 위치 (면목역)**: 2번 출구 버스정류장 위
            * **비고**: 운행시간 외에는 운행하지 않습니다.

        **2. 주요 편의시설**
        * **학생식당**: 동아리관 2F
            * **운영시간**: 11:00 ~ 13:30
        * **편의점 (emart24)**: 배양관 B2
            * **운영시간**: 오전 08:00 ~ 오후 17:00(학기 중 운영)
        * **카페 (CAFEING)**: 흥학관 2F
            * **운영시간**: 평일 09:00 ~ 18:00
        * # 만약 위 [핵심 고정 정보]에 내용이 없다면,
        # 그 때 [참고 정보]와 [이전 대화 내용]을 종합적으로 고려하여 답변을 생성해줘.
        # 참고 정보에도 내용이 없다면 솔직하게 모른다고 말해줘.
        """
        st.markdown(f"""
            <div style="text-align: center;">
                <h2>{yongyong_icon_html} 서일대학교 AI 챗봇 '용용이'</h2>
                <p>안녕하세요! 서일대학교에 대해 궁금한 점을 무엇이든 물어보세요.</p>
            </div>
            """, unsafe_allow_html=True)
        st.write("")

        if st.session_state.get("run_recommendation"):
            
            # 1. 클릭된 관심사를 가져오고 플래그를 즉시 제거
            interest_query = st.session_state.run_recommendation
            st.session_state.run_recommendation = None 
            
            # 2.채팅 기록이 없다면 초기화
            if "messages" not in st.session_state:
                st.session_state.messages = []
                
            # 3. 사용자가 버튼을 눌러 질문한 것처럼 채팅 기록에 추가
            user_question = f"{interest_query} 관련 정보 알려줘"
            st.session_state.messages.append({"role": "user", "content": user_question})
            save_chat_log(uid, token, "user", user_question)

            # 4. AI 응답 로직 실행
            with st.spinner("관련 정보를 찾는 중..."):
                retrieved_info = find_relevant_info(user_question, collection)
            
            previous_conversation = "\n".join([f'{msg["role"]}: {msg["content"]}' for msg in st.session_state.messages])
            
            final_prompt = f"""
[참고 정보]
{retrieved_info if retrieved_info else "가져온 정보 없음"}
[이전 대화 내용]
{previous_conversation}
[사용자 질문]
{user_question}
"""
            # (AI 모델 호출 및 응답 추가 로직)
            model = genai.GenerativeModel('gemini-flash-latest')
            chat_session = model.start_chat(history=[{'role': 'user', 'parts': [system_instruction]}])
            
            with st.chat_message("model"):
                with st.spinner("답변을 생성 중..."):
                    response = chat_session.send_message(final_prompt)
                    ai_response = response.text
                    st.markdown(ai_response)

                    # 추천 질문 클릭 시에도 지도 표시 로직 추가
                    target_location = None
                    for loc_name, data in SEOIL_LOCATIONS.items():
                         if loc_name in ai_response or any(k in ai_response for k in data.get('keywords', [])) or \
                            any(k in user_question for k in data.get('keywords', [])):
                             target_location = loc_name
                             break
                    
                    if target_location:
                        data = SEOIL_LOCATIONS[target_location]
                        # 이미지 함수 사용
                        map_image = highlight_building_on_image(target_location, data['x'], data['y'])
                        if map_image:
                             st.divider()
                             st.caption(f"📍 **{target_location}** 위치 안내")
                             st.image(map_image, caption=f"{target_location} ({data['desc']})", use_container_width=True)
            
            st.session_state.messages.append({"role": "model", "content": ai_response})
            save_chat_log(uid, token, "model", ai_response)
            st.rerun()
            
        # --- 여기서부터 기존 챗봇 UI 및 로직 ---
        st.markdown("""
            <style>
                /* 1. Streamlit 기본 헤더 숨기기 (햄버거 메뉴 등) */
                header[data-testid="stHeader"] {
                    visibility: hidden;
                    height: 0 !important;
                }
                
                /* 2. Top Bar 컨테이너 */
                .top-bar {
                    position: fixed;
                    top: 0;
                    left: 0;
                    width: 100%;
                    height: 4rem;      /* 상단 바 높이 설정 */
                    background-color: #131314; /* 배경색: 흰색 */
                    z-index: 9999;       /* 다른 요소들보다 위에 위치 */
                    display: flex;       /* 내부 요소를 가로로 정렬 */
                    align-items: center; /* 세로 중앙 정렬 */
                    padding-left: 1rem;  /* 왼쪽 여백 */
                    box-shadow: 0 1px 2px 0 rgba(0,0,0,0.05); /* 아주 연한 그림자 효과 */
                }

                /* 3. Top Bar 내부의 로고 이미지 스타일 */
                .top-bar-logo {
                    height: 3.5rem;      /* 로고 높이 (바 높이보다 약간 작게) */
                    width: auto;         /* 비율 유지 */
                    object-fit: contain;
                }

                /* 4. 본문(채팅창) 위치 조정 */
                /* 상단 바가 생겼으므로 본문이 가려지지 않게 패딩을 줍니다 */
                .block-container {
                    padding-top: 5rem !important; /* 상단 바 높이(3.5rem) + 여유공간 */
                }
                    
                div[data-testid="stPopover"] {
                    position: fixed !important;
                    top: 0.5rem !important;    /* 상단 여백 (Top bar 높이 내 중앙) */
                    right: 1rem !important;    /* 우측 여백 */
                    left: auto !important;     /* [중요] 왼쪽 기준 해제 (가로 꽉 참 방지) */
                    width: auto !important;    /* [중요] 너비 자동 (내용물만큼만) */
                    z-index: 10001 !important; /* Top bar보다 위 */
                }

                /* 2. 버튼 모양 동그랗게 만들기 */
                div[data-testid="stPopover"] > button {
                    background-color: #3C4043 !important; 
                    color: #E8EAED !important; 
                    border: none !important;
                    border-radius: 50% !important; /* 완벽한 원형 */
                    width: 3.5rem !important;      /* 가로 크기 고정 */
                    height: 3.5rem !important;     /* 세로 크기 고정 */
                    padding: 0 !important;         /* 내부 여백 제거 */
                    display: flex !important;      /* 글자 중앙 정렬용 Flex */
                    align-items: center !important;
                    justify-content: center !important;
                    font-size: 1.1rem !important;
                    font-weight: 600 !important;
                    box-shadow: none !important;   /* 기본 그림자 제거 */
                }
                
                /* 3. 호버 효과 */
                div[data-testid="stPopover"] > button:hover {
                    background-color: #4A4E51 !important;
                    color: #FFFFFF !important;
                    border: 1px solid #5f6368 !important;
                }
                
                /* 버튼 눌렀을 때 포커스 테두리 제거 */
                div[data-testid="stPopover"] > button:focus {
                    box-shadow: none !important;
                    outline: none !important;
            </style>
            
            <div class="top-bar">
                <a href="https://www.seoil.ac.kr/" target="_blank">
                    <img src="https://ncs.seoil.ac.kr/GateWeb/Common/images/login/%EC%84%9C%EC%9D%BC%EB%8C%80%20%EB%A1%9C%EA%B3%A0.png" class="top-bar-logo">
                </a>
            </div>
            """, unsafe_allow_html=True)
        st.write("")

        # 5. 세션 상태에 대화 기록 초기화
        if "messages" not in st.session_state:
            st.session_state.messages = []

        # 6. 추천 버튼 UI 생성 (채팅 내역이 비어있을 때만)
        with st.expander("💡 맞춤 추천 질문 보기", expanded=(not st.session_state.messages)):
            if all_interests:
                cols = st.columns(len(all_interests)) if len(all_interests) < 5 else st.columns(4)
                for i, interest in enumerate(all_interests):
                    # 간단한 그리드 배치
                    col = cols[i % 4] if len(all_interests) >= 5 else cols[i]
                    with col:
                        st.button(
                            f"👉 {interest}", 
                            key=f"rec_{interest}", 
                            on_click=lambda i=interest: st.session_state.update(run_recommendation=i),
                            use_container_width=True
                        )
            else:
                st.info("관심사가 없습니다. 대화를 많이 나누면 추천이 생깁니다!")
        
        # 7. 이전 대화 내용 표시
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

                # 이전 대화 기록에서 지도(이미지) 표시
                if message["role"] == "model":
                     for loc_name, data in SEOIL_LOCATIONS.items():
                        # 건물 이름이나 키워드가 AI 답변에 포함되어 있는지 확인
                        if loc_name in message["content"] or any(k in message["content"] for k in data.get('keywords', [])):
                             # 이미지 함수 사용
                             map_image = highlight_building_on_image(loc_name, data['x'], data['y'])
                             if map_image:
                                 st.image(map_image, caption=f"📍 {loc_name} ({data['desc']})", use_container_width=True)
                             break

        # 8. 사용자 입력 처리 (기존 코드와 동일)
        if prompt := st.chat_input("질문을 입력해주세요..."):
            st.session_state.messages.append({"role": "user", "content": prompt})
            save_chat_log(uid, token, "user", prompt)

            # 2회마다 키워드 학습 로직 실행
            st.session_state.user_msg_count += 1
            if st.session_state.user_msg_count % 2 == 0:
                with st.spinner("AI가 대화 내용을 학습하여 관심사를 업데이트 중입니다..."):
                    new_keywords = analyze_chat_keywords(uid, token)
                    if new_keywords:
                        st.session_state.user_info['dynamic_keywords'] = new_keywords
                        st.toast(f"새로운 관심 키워드 발견! : {', '.join(new_keywords)}", icon="🎉")
            
            with st.chat_message("user"):
                st.markdown(prompt)

            with st.spinner("관련 정보를 찾는 중..."):
                retrieved_info = find_relevant_info(prompt, collection)

            previous_conversation = "\n".join([f'{msg["role"]}: {msg["content"]}' for msg in st.session_state.messages])

            final_prompt = f"""
[참고 정보]
{retrieved_info if retrieved_info else "가져온 정보 없음"}
[이전 대화 내용]
{previous_conversation}
[사용자 질문]
{prompt}
"""
            
            model = genai.GenerativeModel('gemini-flash-latest')
            chat_session = model.start_chat(history=[{'role': 'user', 'parts': [system_instruction]}])

            with st.chat_message("model"):
                with st.spinner("답변 생성 중..."):
                    response = chat_session.send_message(final_prompt)
                    ai_response = response.text
                    st.markdown(ai_response)

                    # 직접 입력 시에도 지도(이미지) 표시
                    target_location = None
                    for loc_name, data in SEOIL_LOCATIONS.items():
                        if loc_name in ai_response or any(k in ai_response for k in data.get('keywords', [])) or \
                           any(k in prompt for k in data.get('keywords', [])):
                            target_location = loc_name
                            break

                    if target_location:
                        data = SEOIL_LOCATIONS[target_location]
                        # 이미지 함수 사용
                        map_image = highlight_building_on_image(target_location, data['x'], data['y'])
                        if map_image:
                             st.divider()
                             st.caption(f"📍 **{target_location}** 위치 안내")
                             st.image(map_image, caption=f"{target_location} ({data['desc']})", use_container_width=True)

            st.session_state.messages.append({"role": "model", "content": ai_response})
            save_chat_log(uid, token, "model", ai_response)
else:
    st.markdown(f"""
        <style>
        /* --- 폼 정렬 --- */
        div[data-testid="stVerticalBlock"] > [data-testid="stHorizontalBlock"] > div[data-testid="stVerticalBlock"] {{
            margin: 0 auto;
            max-width: 400px;
        }}
        .form-container {{
            background-color: #f6f8fa; border: 1px solid #d0d7de;
            border-radius: 6px; padding: 24px;
        }}
        /* 폼 아래 '계정이 없으시면...' 버튼을 담을 컨테이너 */
        .switch-container {{
            border: 1px solid #d0d7de; border-radius: 6px;
            padding: 16px; margin-top: 16px; text-align: center;
        }}
        .or-divider {{
            text-align: center; color: #57606a;
            padding: 1rem 0; font-size: 0.9rem;
        }}
        
        /* --- 이메일 로그인/가입 버튼 --- */
        /* st.form_submit_button을 타겟팅 */
        div[data-testid="stFormSubmitButton"] > button {{
            background: #2da44e;
            color: white;
            border: 1px solid #2da44e;
            border-radius: 6px;
            padding: 10px 24px;
            font-size: 14px;
            font-weight: 500;
            width: 100%;
            box-sizing: border-box;
        }}
        div[data-testid="stFormSubmitButton"] > button:hover {{
            background: #2c974b;
            border-color: #2c974b;
            color: white;
        }}

        */
        div[data-testid="stVerticalBlock"]:has(>div[data-testid="stHorizontalBlock"] > div[data-testid="stVerticalBlock"]) .stButton > button {{
            background: none !important;
            border: none !important;
            color: #0969da !important; 
            width: auto !important; 
            padding: 0 !important;
            text-decoration: none !important;
            font-weight: normal !important;
        }}
        div[data-testid="stVerticalBlock"]:has(>div[data-testid="stHorizontalBlock"] > div[data-testid="stVerticalBlock"]) .stButton > button:hover {{
            background: none !important;
            color: #0969da !important;
            text-decoration: underline !important;
        }}

        /* --- Google 로그인 버튼 --- */
        .google-btn-container {{
            display: flex;
            justify-content: center;
            margin-bottom: 10px;
        }}
        .google-btn {{
            display: inline-block;
            background: #131314; 
            color: #444;
            border: 1px solid #d0d7de;
            border-radius: 6px;
            padding: 10px 24px;
            font-size: 14px;
            font-weight: 500;
            text-decoration: none;
            cursor: pointer;
            text-align: center;
            width: 100%; 
            box-sizing: border-box; 
        }}
        .google-btn:hover {{
            background: #f0f2f5;
            border-color: #d0d7de;
            color: #444;
            text-decoration: none;
        }}
        .google-btn img {{
            vertical-align: middle;
            margin-right: 12px;
            height: 18px;
        }}
        </style>
    """, unsafe_allow_html=True)

    # --- 2. [로그인 안 된 상태] 로그인/회원가입 페이지 ---
    
    st.markdown(f"<h1 style='text-align: center;'>{yongyong_icon_html} 서일대학교 용용이</h1>", unsafe_allow_html=True)
    st.markdown("<h3 style='text-align: center;'>로그인 또는 회원가입을 해주세요.</h3>", unsafe_allow_html=True)

    col1, col_main, col3 = st.columns([1, 3, 1])
    
    with col_main:
        # --- 페이지 상태에 따라 폼 렌더링 ---
        # Google 로그인 버튼에 사용할 인증 URL 생성
        auth_url = get_google_auth_url()
        google_btn_html = f"""
            <div class="google-btn-container">
                <a href="{auth_url}" class="google-btn" target="_self">
                    <img src="https://upload.wikimedia.org/wikipedia/commons/c/c1/Google_%22G%22_logo.svg" alt="Google logo">
                    Google계정으로 로그인
                </a>
            </div>
        """

        if st.session_state.page == 'login':
            # --- 2-A. 로그인 폼 ---

            with st.form("login_form"):
                login_email = st.text_input("이메일 또는 아이디", key="login_email")
                login_password = st.text_input("비밀번호", type="password", key="login_pass")
                login_submit = st.form_submit_button("로그인", use_container_width=True)

                if login_submit:
                    login_payload = {"email": login_email, "password": login_password, "returnSecureToken": True}
                    response = requests.post(LOGIN_URL, json=login_payload)
                    if response.status_code == 200:
                        user_data = response.json()
                        uid, id_token = user_data['localId'], user_data['idToken']
                        db_url = FIREBASE_DB_URL
                        if not db_url.endswith('/'): 
                            db_url += '/'
                        user_db_url = f"{db_url}users/{uid}.json?auth={id_token}"
                        
                        name_response = requests.get(user_db_url)

                        user_name = "사용자"
                        user_interests = None 
                        user_dynamic_keywords = []
                        
                        if name_response.status_code == 200:
                            name_data = name_response.json()
                            if name_data: 
                                user_name = name_data.get('name', '사용자')
                                user_interests = name_data.get('interests')
                                user_dynamic_keywords = name_data.get('dynamic_keywords', [])

                        st.session_state.logged_in = True
                        st.session_state.user_info = {
                            "email": user_data['email'],
                            "uid": uid,
                            "name": user_name,
                            "idToken": id_token, 
                            "interests": user_interests,
                            "dynamic_keywords": user_dynamic_keywords
                        }
                        st.rerun()
                    else:
                        st.error(parse_firebase_error(response.text))
                        
                # "or" 구분선
                st.markdown('<p class="or-divider">or</p>', unsafe_allow_html=True)
                
                # Google 로그인 버튼
                st.markdown(google_btn_html, unsafe_allow_html=True)

            # 회원가입 전환 링크
            st.button("계정이 없으시면 회원가입하기", on_click=set_page, args=('signup',), use_container_width=True)
            # st.markdown('</div>', unsafe_allow_html=True) # <-- 이 줄이 원본 코드에 있었으나 삭제함

        elif st.session_state.page == 'signup':
            # --- 2-B. 회원가입 폼 ---
            with st.form("signup_form"):
                signup_email = st.text_input("이메일 또는 아이디", key="signup_email")
                signup_name = st.text_input("이름 (예: 홍길동)", key="signup_name")
                signup_password = st.text_input("비밀번호 (6자리 이상)", type="password", key="signup_pass")
                signup_confirm = st.text_input("비밀번호 확인", type="password", key="signup_confirm")
                signup_submit = st.form_submit_button("가입하기", use_container_width=True)

                if signup_submit:
                    if not all([signup_email, signup_name, signup_password, signup_confirm]):
                        st.error("모든 항목을 입력해주세요.")
                    elif signup_password != signup_confirm:
                        st.error("비밀번호가 일치하지 않습니다.")
                    elif len(signup_password) < 6:
                        st.error("비밀번호는 6자리 이상이어야 합니다.")
                    else:
                        signup_payload = {"email": signup_email, "password": signup_password, "returnSecureToken": True}
                        response = requests.post(SIGNUP_URL, json=signup_payload)
                        if response.status_code == 200:
                            user_data = response.json()
                            uid, id_token = user_data['localId'], user_data['idToken']
                            db_url = FIREBASE_DB_URL
                            if not db_url.endswith('/'): 
                                db_url += '/'
                            # db_url 변수 사용 및 interests: None 추가
                            user_db_url = f"{db_url}users/{uid}.json?auth={id_token}"
                            user_data_payload = {"name": signup_name, "email": signup_email, "interests": None, "dynamic_keywords": []}
                            put_response = requests.put(user_db_url, json=user_data_payload)
                            if put_response.status_code == 200:
                                st.success("회원가입이 완료되었습니다! '로그인' 탭에서 로그인해주세요.")
                                st.session_state.page = 'login' # 로그인 페이지로 자동 전환
                                st.rerun()
                            else:
                                st.error(f"회원가입은 되었으나, 이름 저장 실패: {put_response.text}")
                        else:
                            st.error(parse_firebase_error(response.text)) 

                # "or" 구분선
                st.markdown('<p class="or-divider">or</p>', unsafe_allow_html=True)
                
                # Google 회원가입 버튼
                st.markdown(google_btn_html, unsafe_allow_html=True)
                        
            # 로그인 전환 링크
            st.button("이미 계정이 있다면 로그인하기.", on_click=set_page, args=('login',), use_container_width=True)