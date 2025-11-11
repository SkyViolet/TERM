# 1. 필요한 라이브러리 불러오기
import streamlit as st
import google.generativeai as genai
import chromadb
import requests
import json

st.set_page_config(page_title="서일대학교 용용이 비서", page_icon="🎓") # 아이콘 나중에 용용이 이미지로 바꾸기

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
try:
    # 1. secrets.toml에서만 키를 불러옵니다.
    API_KEY = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=API_KEY)
    
except (KeyError, FileNotFoundError):
    # 2. 하드코딩된 키를 완전히 삭제하고, 키가 없으면 앱을 중지시킵니다.
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
        
        if name_response.status_code == 200 and name_response.json() and 'name' in name_response.json():
            user_name = name_response.json()['name']
        else:
            user_name = user_data.get('displayName', '사용자')
            user_data_payload = {"name": user_name, "email": email}
            requests.put(user_db_url, json=user_data_payload)
            
        return {"email": email, "uid": uid, "name": user_name, "idToken": id_token}
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

# --- Google 로그인 리디렉션 처리 (URL에 'code'가 있는지 확인) ---
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
    
    # 상단에 로그아웃 버튼과 환영 메시지 표시
    col1, col2 = st.columns([4, 1])
    with col1:
        st.write(f"**{st.session_state.user_info['name']}**님, 서일비서에 오신 것을 환영합니다!")
    with col2:
        if st.button("로그아웃"):
            st.session_state.logged_in = False
            st.session_state.user_info = None
            st.rerun() # 로그아웃 시 새로고침

    # --- 여기서부터 기존 챗봇 UI 및 로직 ---
    collection = load_chroma_collection() # DB 로드
    
    system_instruction = """
    너는 '서일대학교' 학생들을 위한 AI 챗봇 '서일비서'야. 학생들의 질문에 친절하고 정확하게 답변해야 해.
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
    
    st.markdown("""
        <style>
                .block-container { padding-top: 10rem; }
                .fixed-logo { position: fixed; top: 2.5rem; left: 1rem; z-index: 99; }
        </style>
        <div class="fixed-logo">
            <a href="https://www.seoil.ac.kr/"><img src="https://ncs.seoil.ac.kr/GateWeb/Common/images/login/%EC%84%9C%EC%9D%BC%EB%8C%80%20%EB%A1%9C%EA%B3%A0.png" width="200"></a>
        </div>
        """, unsafe_allow_html=True)
    st.markdown("""
        <div style="text-align: center;">
            <h2>🎓 서일대학교 AI 챗봇 '서일비서'</h2>
            <p>안녕하세요! 서일대학교에 대해 궁금한 점을 무엇이든 물어보세요.</p>
        </div>
        """, unsafe_allow_html=True)
    st.write("")

    # 5. 세션 상태에 대화 기록 초기화
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # 6. 이전 대화 내용 표시
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # 7. 사용자 입력 처리 (기존 코드와 동일)
    if prompt := st.chat_input("질문을 입력해주세요..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
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
            response = chat_session.send_message(final_prompt)
            ai_response = response.text
            st.markdown(ai_response)

        st.session_state.messages.append({"role": "model", "content": ai_response})
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

        /* --- Google 로그인 버튼 (밝은 회색 - Secondary) --- */
        .google-btn-container {{
            display: flex;
            justify-content: center;
            margin-bottom: 10px;
        }}
        .google-btn {{
            display: inline-block;
            background: #3d3d3d; 
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
    
    st.markdown("<h1 style='text-align: center;'>🎓 서일대학교 용용이 비서</h1>", unsafe_allow_html=True)
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

                        st.session_state.logged_in = True
                        st.session_state.user_info = {"email": user_data['email'], "uid": uid, "name": name_response, "idToken": id_token}
                        st.rerun()
                    else:
                        st.error(parse_firebase_error(response.text))
                        
                # "or" 구분선
                st.markdown('<p class="or-divider">or</p>', unsafe_allow_html=True)
                
                # Google 로그인 버튼
                st.markdown(google_btn_html, unsafe_allow_html=True)

            # 회원가입 전환 링크
            st.button("계정이 없으시면 회원가입하기", on_click=set_page, args=('signup',), use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)

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
                            user_db_url = f"{FIREBASE_DB_URL}users/{uid}.json?auth={id_token}"
                            user_data_payload = {"name": signup_name, "email": signup_email}
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
