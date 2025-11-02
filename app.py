# 1. 필요한 라이브러리 불러오기
import streamlit as st
import google.generativeai as genai
import chromadb
import requests
import json

try:
    FIREBASE_API_KEY = st.secrets["firebase_web"]["apiKey"]
    FIREBASE_DB_URL = st.secrets["firebase_web"]["databaseURL"]
    
    # Firebase REST API 엔드포인트 URL 정의
    SIGNUP_URL = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"
    LOGIN_URL = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}"
    
except KeyError:
    st.error("Firebase 설정이 .streamlit/secrets.toml에 올바르게 구성되지 않았습니다. [firebase_web] 섹션과 키 이름을 확인하세요.")
    st.stop()
except Exception as e:
    st.error(f"Firebase 설정 로드 중 오류 발생: {e}")
    st.stop()

# --- 세션 상태 초기화 ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'user_info' not in st.session_state:
    st.session_state.user_info = None # {'email', 'uid', 'name', 'idToken'}

try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except (KeyError, FileNotFoundError):
    st.warning("GEMINI_API_KEY를 .streamlit/secrets.toml에서 찾을 수 없습니다. (보안상 권장됨)")
    API_KEY = "AIzaSyBZD2AqxEMJTStEm3UXdjaloS-Mjf9-GgE"
genai.configure(api_key=API_KEY)


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

# --- 페이지 설정 ---
st.set_page_config(page_title="서일대학교 AI 챗봇", page_icon="🎓")

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
    # --- 2. [로그인 안 된 상태] 로그인/회원가입 페이지 ---
    st.title("🎓 서일대학교 AI 비서")
    st.subheader("로그인 또는 회원가입을 해주세요.")

    tab_login, tab_signup = st.tabs(["로그인", "회원가입"])

    # --- 로그인 탭 ---
    with tab_login:
        with st.form("login_form"):
            login_email = st.text_input("이메일")
            login_password = st.text_input("비밀번호", type="password")
            login_submit = st.form_submit_button("로그인")

            if login_submit:
                # Firebase REST API로 로그인 요청
                login_payload = {
                    "email": login_email,
                    "password": login_password,
                    "returnSecureToken": True
                }
                response = requests.post(LOGIN_URL, json=login_payload)

                if response.status_code == 200:
                    # 로그인 성공
                    user_data = response.json()
                    uid = user_data['localId']
                    id_token = user_data['idToken']
                    
                    # Realtime DB에서 이름 가져오기 (REST API 사용)
                    user_db_url = f"{FIREBASE_DB_URL}/users/{uid}.json?auth={id_token}"
                    name_response = requests.get(user_db_url)
                    
                    user_name = "사용자" # 기본값
                    if name_response.status_code == 200:
                        name_data = name_response.json()
                        if name_data and 'name' in name_data:
                            user_name = name_data['name']
                    
                    # 세션 상태에 로그인 정보 저장
                    st.session_state.logged_in = True
                    st.session_state.user_info = {
                        "email": user_data['email'],
                        "uid": uid,
                        "name": user_name,
                        "idToken": id_token # DB 접근 등을 위해 토큰도 저장
                    }
                    st.rerun()
                else:
                    # 로그인 실패
                    st.error(parse_firebase_error(response.text))

    # --- 회원가입 탭 ---
    with tab_signup:
        with st.form("signup_form"):
            signup_email = st.text_input("사용할 이메일")
            signup_name = st.text_input("이름 (예: 홍길동)")
            signup_password = st.text_input("비밀번호 (6자리 이상)", type="password")
            signup_confirm = st.text_input("비밀번호 확인", type="password")
            signup_submit = st.form_submit_button("가입하기")

            if signup_submit:
                if not all([signup_email, signup_name, signup_password, signup_confirm]):
                    st.error("모든 항목을 입력해주세요.")
                elif signup_password != signup_confirm:
                    st.error("비밀번호가 일치하지 않습니다.")
                elif len(signup_password) < 6:
                    st.error("비밀번호는 6자리 이상이어야 합니다.")
                else:
                    # 1. Firebase Auth에 사용자 생성 (REST API)
                    signup_payload = {
                        "email": signup_email,
                        "password": signup_password,
                        "returnSecureToken": True
                    }
                    response = requests.post(SIGNUP_URL, json=signup_payload)

                    if response.status_code == 200:
                        # 회원가입 성공
                        user_data = response.json()
                        uid = user_data['localId']
                        id_token = user_data['idToken'] # 이름 저장을 위해 토큰 사용
                        
                        # 2. Realtime DB에 사용자 이름 저장 (REST API)
                        # Firebase DB URL이 '/'로 끝나지 않는 경우가 있으므로 확인
                        if not FIREBASE_DB_URL.endswith('/'):
                            FIREBASE_DB_URL += '/'
                            
                        user_db_url = f"{FIREBASE_DB_URL}users/{uid}.json?auth={id_token}"
                        user_data_payload = {"name": signup_name, "email": signup_email}
                        
                        # PUT 요청으로 데이터 저장 (덮어쓰기)
                        put_response = requests.put(user_db_url, json=user_data_payload)
                        
                        if put_response.status_code == 200:
                            st.success("회원가입이 완료되었습니다! '로그인' 탭에서 로그인해주세요.")
                        else:
                            st.error(f"회원가입은 되었으나, 이름 저장 실패: {put_response.text}")
                    else:
                        # 회원가입 실패
                        st.error(parse_firebase_error(response.text))