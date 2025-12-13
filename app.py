import streamlit as st
import google.generativeai as genai
import chromadb
import requests
import json
import time
import base64
import pandas as pd
import plotly.express as px
from PIL import Image, ImageDraw
from collections import Counter

# [관리자 이메일 설정]
try:
    ADMIN_EMAILS = [email.strip() for email in st.secrets.get("ADMIN_EMAILS", "").split(',') if email.strip()]
except Exception as e:
    st.error(f"ADMIN_EMAILS 설정 로드 중 오류 발생: {e}")
    ADMIN_EMAILS = []

# --- 이미지 처리 함수 ---
def get_base64_of_bin_file(bin_file):
    try:
        with open(bin_file, 'rb') as f:
            data = f.read()
        return base64.b64encode(data).decode()
    except FileNotFoundError:
        return ""

# --- 아이콘 설정 ---
try:
    img_base64 = get_base64_of_bin_file("yongyong.png")
    if img_base64:
        yongyong_icon_html = f'<img src="data:image/png;base64,{img_base64}" style="width: 40px; height: 40px; vertical-align: middle; margin-right: 10px;">'
    else:
        yongyong_icon_html = "🎓"
except Exception:
    yongyong_icon_html = "🎓"

# --- 페이지 설정 ---
try:
    icon_image = Image.open("yongyong.png")
    st.set_page_config(page_title="서일대학교 용용이", page_icon=icon_image)
except FileNotFoundError:
    st.set_page_config(page_title="서일대학교 용용이")

# --- 서일대학교 건물 좌표 ---
SEOIL_LOCATIONS = {
    "흥학관": {"x": 515, "y": 210, "desc": "1번 건물: 카페", "keywords": ["흥학관", "카페", "커피", "휴게공간"]},
    "호천관": {"x": 370, "y": 250, "desc": "2번 건물: 이론강의실", "keywords": ["호천관"]},
    "세종관": {"x": 490, "y": 145, "desc": "3번 건물: 강의실", "keywords": ["세종관", "강의실"]},
    "서일관": {"x": 675, "y": 105, "desc": "4번 건물: 대학본부", "keywords": ["서일관", "본부", "총장실"]},
    "지덕관": {"x": 755, "y": 135, "desc": "5번 건물: 학생회관", "keywords": ["지덕관", "학생회관"]},
    "누리관": {"x": 835, "y": 160, "desc": "6번 건물: 종합정보관", "keywords": ["누리관", "정보관"]},
    "도서관": {"x": 775, "y": 65, "desc": "7번 건물: 도서관", "keywords": ["도서관", "열람실", "책"]},
    "배양관": {"x": 865, "y": 95, "desc": "8번 건물: 실습강의실", "keywords": ["배양관", "실습실", "편의점", "매점"]},
    "동아리관": {"x": 660, "y": 260, "desc": "9번 건물: 학생식당, 학식", "keywords": ["동아리관, 학생식당, 학식"]},
    "정문": {"x": 615, "y": 325, "desc": "10번: 정문", "keywords": ["정문", "입구"]},
}

# --- 이미지 위에 위치 표시하는 함수 ---
def highlight_building_on_image(target_name, x, y):
    try:
        base_image = Image.open("seoil_map.png")
        draw = ImageDraw.Draw(base_image)
        radius = 30
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), outline="red", width=5)
        return base_image
    except FileNotFoundError:
        return None

# --- 설정 로드 ---
try:
    FIREBASE_API_KEY = st.secrets["firebase_web"]["apiKey"]
    FIREBASE_DB_URL = st.secrets["firebase_web"]["databaseURL"]
    
    GOOGLE_CLIENT_ID = st.secrets["firebase_web"]["GOOGLE_CLIENT_ID"]
    GOOGLE_CLIENT_SECRET = st.secrets["firebase_web"]["GOOGLE_CLIENT_SECRET"]
    REDIRECT_URI = "http://localhost:8501"

    AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URL = "https://oauth2.googleapis.com/token"

    SIGNUP_URL = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"
    LOGIN_URL = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}"
    GOOGLE_LOGIN_URL = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithIdp?key={FIREBASE_API_KEY}"

except KeyError as e:
    st.error(f"Firebase 설정(.streamlit/secrets.toml)에 '{e.args[0]}' 키가 누락되었습니다.")
    st.stop()
except Exception as e:
    st.error(f"Firebase 설정 로드 중 오류 발생: {e}")
    st.stop()

# --- 세션 초기화 ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'user_info' not in st.session_state:
    st.session_state.user_info = None 
if 'page' not in st.session_state:
    st.session_state.page = 'login'
if 'user_msg_count' not in st.session_state:
    st.session_state.user_msg_count = 0

# --- Gemini API ---
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=API_KEY)
except Exception:
    st.error("Gemini API 키 설정 오류")
    st.stop()

# --- ChromaDB ---
@st.cache_resource(show_spinner="AI 지식 베이스를 로딩 중입니다...")
def load_chroma_collection():
    try:
        db_path = "./chroma_db"
        client = chromadb.PersistentClient(path=db_path)
        collection = client.get_collection(name="seoil_info_db")
        return collection
    except Exception as e:
        st.error(f"ChromaDB 컬렉션을 불러오는 데 실패했습니다: {e}")
        return None
    
# --- 관련 정보 검색 함수 ---
def find_relevant_info(query, collection, top_k=5):
    if collection is None: return ""
    try:
        query_embedding = genai.embed_content(model="models/embedding-001",
                                              content=query,
                                              task_type="RETRIEVAL_QUERY")['embedding']
        
        results = collection.query(query_embeddings=[query_embedding], n_results=top_k)
        
        if results['documents'] and results['documents'][0]:
            return "\n\n".join(results['documents'][0])
    except:
        pass
    return ""

# --- Firebase 오류 파싱 함수 ---
def parse_firebase_error(response_text):
    try:
        error_json = json.loads(response_text)
        error_message = error_json.get('error', {}).get('message', '알 수 없는 오류')
        if "EMAIL_NOT_FOUND" in error_message: return "등록되지 않은 이메일입니다."
        if "INVALID_PASSWORD" in error_message: return "비밀번호가 틀렸습니다."
        if "EMAIL_EXISTS" in error_message: return "이미 가입된 이메일입니다."
        if "WEAK_PASSWORD" in error_message: return "비밀번호는 6자리 이상이어야 합니다."
        return f"오류: {error_message}"
    except json.JSONDecodeError:
        return "알 수 없는 오류가 발생했습니다."
    
# 채팅 기록을 Firebase에 저장하는 함수
def save_chat_log(uid, token, role, message):
    if not uid or not token: return
    try:
        timestamp = int(time.time() * 1000)
        chat_ref = f"chat_history/{uid}/{timestamp}"
        data = {"role": role, "content": message, "timestamp": timestamp}
        db_url = FIREBASE_DB_URL
        if not db_url.endswith('/'): db_url += '/'
        save_url = f"{db_url}{chat_ref}.json?auth={token}"
        requests.put(save_url, json=data, timeout=3)
    except Exception:
        pass

# --- 키워드 분석 및 업데이트 함수 ---
def analyze_chat_keywords(uid, token):
    try:
        db_url = FIREBASE_DB_URL
        if not db_url.endswith('/'): db_url += '/'
        load_url = f"{db_url}chat_history/{uid}.json?auth={token}"
        response = requests.get(load_url)
        if response.status_code != 200 or not response.json(): return []

        chat_data = response.json()
        full_text = ""
        for key in sorted(chat_data.keys())[-10:]: 
            msg = chat_data[key]
            if msg['role'] == 'user':
                full_text += msg['content'] + "\n"
        if len(full_text) < 5: return []

        analysis_model = genai.GenerativeModel('gemini-flash-latest')
        prompt = f"다음 대화에서 사용자의 핵심 관심 키워드 3개를 콤마로 구분해 추출해줘. 설명 없이 단어만. [대화] {full_text}"
        result = analysis_model.generate_content(prompt).text
        keywords = [k.strip() for k in result.split(',') if k.strip()]
        
        update_url = f"{db_url}users/{uid}/dynamic_keywords.json?auth={token}"
        requests.put(update_url, json=keywords)
        return keywords
    except Exception:
        st.toast("키워드 분석 중 일시적 오류 발생")
        return []

# --- Google OAuth ---
def exchange_code_for_token(code):
    payload = {
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "code": code, 
        "grant_type": "authorization_code", 
        "redirect_uri": REDIRECT_URI
    }
    try:
        response = requests.post(TOKEN_URL, data=payload); 
        response.raise_for_status(); return response.json()
    except: st.error("Google 토큰 교환 실패"); return None

# --- sign in with Google ---
def sign_in_with_google(google_id_token):
    payload = { 
        'postBody': f"id_token={google_id_token}&providerId=google.com",
        'requestUri': REDIRECT_URI, 
        'returnSecureToken': True 
        }
    res = requests.post(GOOGLE_LOGIN_URL, json=payload)
    if res.status_code == 200:
        data = res.json(); uid, token, email = data['localId'], data['idToken'], data.get('email')
        db_url = FIREBASE_DB_URL; 
        if not db_url.endswith('/'): db_url += '/'
        user_db_url = f"{db_url}users/{uid}.json?auth={token}"
        name_res = requests.get(user_db_url)
        
        user_role = 'user'
        if email in ADMIN_EMAILS:
            user_role = 'admin'

        if name_res.status_code == 200 and name_res.json():
            u_data = name_res.json()
            
            if not u_data.get('role'):
                 requests.patch(user_db_url, json={"role": user_role})
            else:
                 user_role = u_data.get('role')
            
            onboarding_completed = u_data.get('onboarding_completed', False)

            return {
                "email": email, "uid": uid, "name": u_data.get('name','사용자'), 
                "idToken": token, "interests": u_data.get('interests'), 
                "dynamic_keywords": u_data.get('dynamic_keywords', []), 
                "role": user_role,
                "onboarding_completed": onboarding_completed
            }
        else:
            u_name = data.get('displayName', '사용자')
            new_user_data = {"name": u_name, "email": email, "interests": None, "dynamic_keywords": [], "role": user_role, "onboarding_completed": False}
            requests.put(user_db_url, json=new_user_data)
            return {
                "email": email, "uid": uid, "name": u_name, "idToken": token, 
                "interests": None, "dynamic_keywords": [], "role": user_role,
                "onboarding_completed": False 
            }
    else: st.error("Google 로그인 실패"); return None

# --- get Google auth url ---
def get_google_auth_url():
    params = { "client_id": GOOGLE_CLIENT_ID, "redirect_uri": REDIRECT_URI, "response_type": "code", "scope": "openid email profile", "access_type": "offline" }
    return requests.Request('GET', AUTH_URL, params=params).prepare().url

# --- Google 로그인 리디렉션 처리 ---
if 'code' in st.query_params:
    token_data = exchange_code_for_token(st.query_params["code"])
    if token_data and "id_token" in token_data:
        user_info = sign_in_with_google(token_data["id_token"])
        if user_info:
            st.session_state.logged_in = True; st.session_state.user_info = user_info
            st.query_params.clear(); st.rerun()

# --- 페이지 전환용 콜백 함수 ---
def set_page(page): st.session_state.page = page

# --- 데이터 로딩 함수 ---
@st.cache_data(ttl=60)
def get_all_users_from_db(token):
    """Firebase에서 모든 사용자 데이터를 가져옵니다."""
    try:
        # 인증된 요청 전송
        response = requests.get(f"{FIREBASE_DB_URL}users.json?auth={token}")
        if response.status_code == 200 and response.json():
            return response.json()
        return {}
    except Exception as e:
        # st.warning(f"유저 데이터 로드 실패: {e}") # 디버깅 시 주석 해제
        return {}
    
@st.cache_data(ttl=60)
def get_all_chats_from_db(token):
    """모든 채팅 기록을 가져옵니다."""
    try:
        # 인증된 요청 전송
        response = requests.get(f"{FIREBASE_DB_URL}chat_history.json?auth={token}")
        if response.status_code == 200 and response.json():
            return response.json()
        return {}
    except Exception as e:
        # st.warning(f"채팅 데이터 로드 실패: {e}") # 디버깅 시 주석 해제
        return {}

# --- 관리자 페이지 함수 (token 인자 받기) ---
def admin_dashboard_page(token):
    st.title("📊 용용이 통합 관리자 대시보드")
    
    col_nav1, col_nav2 = st.columns([8, 2])
    with col_nav2:
        if st.button("⬅️ 챗봇으로 돌아가기", use_container_width=True):
            st.session_state.page = 'chat'
            st.rerun()
            
    st.markdown("---")
    
    with st.spinner("실시간 데이터를 분석 중입니다..."):
        try:
            users_res = requests.get(f"{FIREBASE_DB_URL}users.json?auth={token}")
            chats_res = requests.get(f"{FIREBASE_DB_URL}chat_history.json?auth={token}")
            
            users_data = users_res.json() if users_res.status_code == 200 else {}
            chats_data = chats_res.json() if chats_res.status_code == 200 else {}
        except Exception as e:
            st.error(f"데이터 로드 실패: {e}")
            return

    # --- 데이터 전처리 ---
    total_users = len(users_data) if users_data else 0
    
    # 채팅 데이터 평탄화
    all_chat_records = []
    if chats_data:
        for uid, timestamp_dict in chats_data.items():
            if timestamp_dict:
                for ts, msg_info in timestamp_dict.items():
                    dt = time.strftime('%Y-%m-%d', time.localtime(int(ts)/1000))
                    all_chat_records.append({
                        "date": dt,
                        "role": msg_info.get('role'),
                        "content": msg_info.get('content')
                    })
    
    df_chats = pd.DataFrame(all_chat_records)
    total_chats = len(df_chats)

    # --- 키워드 분석 (실제 채팅 기반) ---
    all_interests = []
    if users_data:
        for info in users_data.values():
            ints = info.get('interests', [])
            if ints: all_interests.extend(ints)

    all_chat_keywords = []
    if not df_chats.empty:
        user_msgs = df_chats[df_chats['role'] == 'user']['content'].tolist()
        stop_words = ["알려줘", "정보", "관련", "대해", "어디", "어떻게", "대한", "알려", "주세요", "질문", "답변", "좀", "내용", "있는지", "있어", "에", "인지", "하데", "있지", "학교"]

        for msg in user_msgs:
            words = msg.split()
            for w in words:
                cleaned_word = w.replace('은', '').replace('는', '').replace('이', '').replace('가', '').replace('을', '').replace('를', '').replace('에', '').replace('?', '')
                if len(cleaned_word) >= 2 and cleaned_word not in stop_words:
                    all_chat_keywords.append(cleaned_word)

    kw_counts = Counter(all_chat_keywords)
    
    # [1] 상단 KPI 지표
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("총 사용자", f"{total_users}명", delta="누적")
    m2.metric("총 대화 수", f"{total_chats}건", delta="누적")
    today_str = time.strftime('%Y-%m-%d')
    today_chats = len(df_chats[df_chats['date'] == today_str]) if not df_chats.empty else 0
    m3.metric("오늘 대화량", f"{today_chats}건", delta="Today")
    m4.metric("분석된 키워드", f"{len(kw_counts)}개", delta="Unique")

    st.markdown("---")

    st.subheader("📈 일자별 대화량 추이")
    if not df_chats.empty:
        daily_counts = df_chats.groupby('date').size().reset_index(name='counts')
        fig_line = px.line(daily_counts, x='date', y='counts', markers=True, 
                            labels={'date': '날짜', 'counts': '대화 수'})
        fig_line.update_traces(line_color='#2ecc71', line_width=3)
        st.plotly_chart(fig_line, use_container_width=True)
    else:
        st.info("아직 대화 기록이 없습니다.")   

    # [2] 인터랙티브 분석 영역 (좌: 키워드 랭킹 / 우: 상세 대화 내용)
    st.subheader("📌 키워드 기반 대화 분석")
    st.info("왼쪽 표에서 키워드를 클릭하면, 오른쪽에서 해당 키워드가 포함된 실제 대화 내용을 볼 수 있습니다.")

    col_left, col_right = st.columns([1, 1])

    with col_left:
        st.subheader("🔥 HOT 키워드 랭킹")
        st.caption("표의 행을 클릭하면 오른쪽에서 상세 내용을 볼 수 있습니다.")
        
        selection = None
        if all_chat_keywords:
            kw_counts_top = kw_counts.most_common(50)
            df_kw = pd.DataFrame(kw_counts_top, columns=['키워드', '빈도수'])
            
            selection = st.dataframe(
                df_kw,
                column_config={
                    "키워드": st.column_config.TextColumn("키워드", help="대화에서 추출된 핵심 단어"),
                    "빈도수": st.column_config.ProgressColumn(
                        "언급 빈도",
                        format="%d회",
                        min_value=0,
                        max_value=df_kw['빈도수'].max() if not df_kw.empty else 1,
                    ),
                },
                hide_index=True,
                use_container_width=True,
                on_select="rerun",
                selection_mode="single-row",
                height=400
            )
        else:
            st.info("분석할 키워드가 없습니다.")

    with col_right:
        # 선택된 키워드 확인
        selected_keyword = None
        if selection and selection.selection.rows:
            selected_index = selection.selection.rows[0]
            selected_keyword = df_kw.iloc[selected_index]['키워드']
            
            # 헤더에 선택된 키워드를 바로 표시
            st.subheader(f"💬 '{selected_keyword}' 관련 질문")
            st.caption(f"키워드가 포함된 사용자 질문 내역입니다.")
            
            if not df_chats.empty:
                # 사용자 질문('user')만 필터링 + 키워드 검색
                filtered_chats = df_chats[
                    (df_chats['role'] == 'user') & 
                    (df_chats['content'].astype(str).str.contains(selected_keyword))
                ].sort_values(by='date', ascending=False)
                
                if not filtered_chats.empty:
                    st.dataframe(
                        filtered_chats[['date', 'content']],
                        column_config={
                            "date": "일시",
                            "content": "질문 내용"
                        },
                        hide_index=True,
                        use_container_width=True,
                        height=400
                    )
                else:
                    st.warning("해당 키워드가 포함된 질문을 찾을 수 없습니다.")
        else:
            # 선택되지 않았을 때의 기본 상태
            st.subheader("💬 키워드 상세 보기")
            st.info("👈 왼쪽 표에서 키워드를 클릭해보세요.")

    st.markdown("---")

    # [3] 관심사 통계 (파이 차트)
    st.subheader("🏫 학생 관심사 비율 (가입 시 선택)")
    if all_interests:
        int_counts = Counter(all_interests)
        df_int = pd.DataFrame.from_dict(int_counts, orient='index', columns=['count']).reset_index()
        fig_pie = px.pie(df_int, values='count', names='index', hole=0.4, 
                         color_discrete_sequence=px.colors.qualitative.Pastel)
        st.plotly_chart(fig_pie, use_container_width=True)
    else:
        st.info("관심사 데이터가 없습니다.")

    if st.button("🔄 데이터 새로고침", use_container_width=True):
        st.rerun()

# 메인 앱 로직: 로그인 상태에 따라 UI 분기
if st.session_state.logged_in:
    if st.session_state.user_info.get('interests') is None: 
        st.session_state.page = 'onboarding'
    elif st.session_state.page == 'login':
        st.session_state.page = 'chat'

   # 2. 페이지 라우팅
    if st.session_state.page == 'onboarding':
        st.markdown(f"<h1 style='text-align: center;'>{yongyong_icon_html} 용용이 시작하기</h1>", unsafe_allow_html=True)
        st.subheader(f"{st.session_state.user_info['name']}님, 환영합니다!")
        st.write("용용이가 맞춤형 정보를 추천해드릴 수 있도록, 관심사를 선택해주세요.")
        
        INTEREST_OPTIONS = ["학사공지", "장학금", "셔틀버스", "도서관", "학생식당", "카페", "편의점"]
        sel_ints = st.multiselect("관심있는 주제를 모두 선택해주세요. (여러 개 선택 가능)", INTEREST_OPTIONS)
        c1, c2 = st.columns(2)
        
        uid, token = st.session_state.user_info['uid'], st.session_state.user_info['idToken']
        db_url = FIREBASE_DB_URL
        if not db_url.endswith('/'): db_url += '/'
        
        if c1.button("저장하기", type="primary", use_container_width=True):
            requests.patch(f"{db_url}users/{uid}.json?auth={token}", json={
                "interests": sel_ints, 
                "dynamic_keywords": [],
                "onboarding_complete": True 
            })
            
            st.session_state.user_info['interests'] = sel_ints
            st.session_state.user_info['dynamic_keywords'] = []
            st.session_state.user_info['onboarding_complete'] = True
            
            st.session_state.page = 'chat'
            st.rerun()
            
        if c2.button("건너뛰기", use_container_width=True):
            requests.patch(f"{db_url}users/{uid}.json?auth={token}", json={
                "interests": [], 
                "dynamic_keywords": [],
                "onboarding_complete": True 
            })
            
            st.session_state.user_info['interests'] = []
            st.session_state.user_info['dynamic_keywords'] = []
            st.session_state.user_info['onboarding_complete'] = True
            
            st.session_state.page = 'chat'
            st.rerun()

    # 2. 관리자 페이지
    elif st.session_state.page == 'admin_dashboard':
        if st.session_state.user_info.get('role') == 'admin':
            admin_dashboard_page(st.session_state.user_info['idToken'])
        else:
            st.error("관리자 권한이 없습니다.")
            st.session_state.page = 'chat'
            st.rerun()

    # 3. 챗봇 페이지
    elif st.session_state.page == 'chat':
        uid, token = st.session_state.user_info.get('uid'), st.session_state.user_info.get('idToken')
        
        
        with st.popover(st.session_state.user_info['name']):
            st.markdown(f"**{st.session_state.user_info['name']}**님")
            st.caption(st.session_state.user_info['email'])
            st.divider()
                
            if st.session_state.user_info.get('role') == 'admin':
                if st.button("📊 관리자 대시보드", use_container_width=True):
                    st.session_state.page = 'admin_dashboard'
                    st.rerun()

            if st.button("⚙️ 프로필 수정", use_container_width=True): st.session_state.page = 'profile'; st.rerun()
            if st.button("🚪 로그아웃", use_container_width=True):
                for key in list(st.session_state.keys()):
                    del st.session_state[key]
                st.rerun()

        collection = load_chroma_collection()
        
        static_ints = st.session_state.user_info.get('interests', []) or []
        if "선택안함" in static_ints: static_ints = []
        dyn_kw = st.session_state.user_info.get('dynamic_keywords', []) or []
        all_ints = list(set(static_ints + dyn_kw))
        
        prompt_part = f"\n\n# 사용자 관심사: {', '.join(all_ints)}" if all_ints else ""
        sys_inst = f"""
        너는 '서일대학교' 학생들을 위한 AI 챗봇 '용용이'야. 친절하게 답변해.
        {prompt_part}
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
        * **프린터**: 배양관 1F, 도서관 1F
            * **운영시간**: 항시 운영
        * **ATM**: 누리관 2F 학생 테라스, 흥학관 2F
            * **운영시간**: 항시 운영
        * # 만약 위 [핵심 고정 정보]에 내용이 없다면,
        # 그 때 [참고 정보]와 [이전 대화 내용]을 종합적으로 고려하여 답변을 생성해줘.
        # 참고 정보에도 내용이 없다면 솔직하게 모른다고 말해줘.
        """
        
        st.markdown(f"""
            <div style="text-align: center;">
                <h2>{yongyong_icon_html} 서일대학교 AI 챗봇 '용용이'</h2>
                <p>안녕하세요! 서일대학교에 대해 궁금한 점을 물어보세요.</p>
            </div>
            """, unsafe_allow_html=True)
        st.write("")

        # 추천 버튼 로직
        if st.session_state.get("run_rec"):
            q = st.session_state.run_rec; st.session_state.run_rec = None
            if "messages" not in st.session_state: st.session_state.messages = []
            
            user_question = f"{q} 관련 정보 알려줘"
            st.session_state.messages.append({"role": "user", "content": user_question})
            save_chat_log(uid, token, "user", user_question)

            with st.spinner("답변 생성 중..."):
                retrieved = find_relevant_info(user_question, collection)
                prev_conv = "\n".join([f'{m["role"]}: {m["content"]}' for m in st.session_state.messages])
                final_p = f"[참고 정보]\n{retrieved}\n[이전 대화]\n{prev_conv}\n[질문]\n{user_question}"
                
                model = genai.GenerativeModel('gemini-flash-latest')
                res = model.generate_content([{'role':'user', 'parts':[sys_inst]}, {'role':'user', 'parts':[final_p]}])
                ai_msg = res.text
                
                with st.chat_message("model"):
                      st.markdown(ai_msg)
                      target_location = None
                      for loc_name, data in SEOIL_LOCATIONS.items():
                        if loc_name in ai_msg: 
                            target_location = loc_name
                            break
                      if target_location:
                            data = SEOIL_LOCATIONS[target_location]
                            map_image = highlight_building_on_image(target_location, data['x'], data['y'])
                            if map_image: 
                                st.divider()
                                st.caption(f"📍 **{target_location}** 위치 안내")
                                st.image(map_image, caption=f"{target_location} ({data['desc']})", use_container_width=True)

            st.session_state.messages.append({"role": "model", "content": ai_msg})
            save_chat_log(uid, token, "model", ai_msg)
            st.rerun()

        if "messages" not in st.session_state: st.session_state.messages = []

        with st.expander("💡 맞춤 추천 질문 보기", expanded=(not st.session_state.messages)):
            if all_ints:
                cols = st.columns(4)
                for i, interest in enumerate(all_ints):
                    cols[i % 4].button(f"👉 {interest}", key=f"btn_{interest}", on_click=lambda x=interest: st.session_state.update(run_rec=x), use_container_width=True)
            else: st.info("관심사가 없습니다.")

        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                if msg["role"] == "model":
                    for loc_name, data in SEOIL_LOCATIONS.items():
                        if loc_name in msg["content"] or any(k in msg["content"] for k in data.get('keywords', [])):
                            st.caption(f"📍 **{loc_name}** 위치 안내")
                            map_image = highlight_building_on_image(loc_name, data['x'], data['y'])
                            if map_image: st.image(map_image, use_container_width=True)
                            break

        if prompt := st.chat_input("질문을 입력해주세요..."):
            st.session_state.messages.append({"role": "user", "content": prompt})
            save_chat_log(uid, token, "user", prompt)
            
            # 키워드 학습 로직
            st.session_state.user_msg_count += 1
            if st.session_state.user_msg_count % 2 == 0:
                with st.spinner("학습 중..."):
                    nk = analyze_chat_keywords(uid, token)
                    if nk: 
                        st.session_state.user_info['dynamic_keywords'] = nk
                        st.toast(f"새로운 관심 키워드 발견! : {', '.join(nk)}", icon="🎉")

            with st.chat_message("user"): st.markdown(prompt)
            
            with st.spinner("답변 생성 중..."):
                retrieved = find_relevant_info(prompt, collection)
                prev_conv = "\n".join([f'{m["role"]}: {m["content"]}' for m in st.session_state.messages])
                final_p = f"[참고 정보]\n{retrieved}\n[이전 대화]\n{prev_conv}\n[질문]\n{prompt}"
                
                model = genai.GenerativeModel('gemini-flash-latest')
                res = model.generate_content([{'role':'user', 'parts':[sys_inst]}, {'role':'user', 'parts':[final_p]}])
                ai_msg = res.text
                
                with st.chat_message("model"):
                    st.markdown(ai_msg)
                    
                    # 조건부 지도 표시 로직 (불필요한 이미지 출력 방지)
                    target_location = None
                    
                    # 1. 사용자가 위치를 물어보는 의도인지 확인하는 단어들
                    location_intents = ["위치", "어디", "지도", "약도", "가는", "찾아", "안내", "장소", "어디에", "어디로"]
                    is_location_intent = any(t in prompt for t in location_intents)
                    
                    for loc_name, data in SEOIL_LOCATIONS.items():
                        # 조건 A: AI 답변에 정확한 '건물 이름'이 포함되어 있으면 표시
                        if loc_name in ai_msg:
                            target_location = loc_name
                            break
                        
                        # 조건 B: 사용자가 '위치'를 물어봤고, 질문에 건물명이나 관련 키워드가 있는 경우
                        if is_location_intent and (loc_name in prompt or any(k in prompt for k in data.get('keywords', []))):
                             target_location = loc_name
                             break

                    # 조건이 맞을 때만 지도 표시
                    if target_location:
                        data = SEOIL_LOCATIONS[target_location]
                        map_image = highlight_building_on_image(target_location, data['x'], data['y'])
                        if map_image: 
                            st.divider()
                            st.caption(f"📍 **{target_location}** 위치 안내")
                            st.image(map_image, caption=f"{target_location} ({data['desc']})", use_container_width=True)
                                    
            st.session_state.messages.append({"role": "model", "content": ai_msg})
            save_chat_log(uid, token, "model", ai_msg)

    # 4. 프로필 수정 페이지
    elif st.session_state.page == 'profile':
        st.title("⚙️ 프로필 수정")
        curr_ints = st.session_state.user_info.get('interests', []) or []
        curr_kws = st.session_state.user_info.get('dynamic_keywords', []) or []
        
        st.subheader("관심사")
        INTEREST_OPTIONS = ["학사공지", "장학금", "셔틀버스", "도서관", "학생식당", "카페", "편의점"]
        new_ints = st.multiselect("주제 선택", INTEREST_OPTIONS, default=[i for i in curr_ints if i in INTEREST_OPTIONS])
        
        st.divider()
        st.caption(f"AI 학습 키워드: {', '.join(curr_kws) if curr_kws else '없음'}")
        
        c1, c2 = st.columns(2)
        uid, token = st.session_state.user_info['uid'], st.session_state.user_info['idToken']
        db_url = FIREBASE_DB_URL; 
        if not db_url.endswith('/'): db_url += '/'
        
        if c1.button("저장", type="primary", use_container_width=True):
            requests.patch(f"{db_url}users/{uid}.json?auth={token}", json={"interests": new_ints})
            st.session_state.user_info['interests'] = new_ints; st.session_state.page = 'chat'; st.rerun()
            
        if c2.button("취소", use_container_width=True):
            st.session_state.page = 'chat'; st.rerun()
    st.markdown("""
            <style>
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
                    height: 4rem;
                    background-color: #131314;
                    z-index: 9999;
                    display: flex;
                    align-items: center;
                    padding-left: 1rem;
                    box-shadow: 0 1px 2px 0 rgba(0,0,0,0.05);
                }

                /* 3. Top Bar 내부의 로고 이미지 스타일 */
                .top-bar-logo {
                    height: 3.5rem;
                    width: auto;
                    object-fit: contain;
                }

                /* 4. 본문(채팅창) 위치 조정 */
                .block-container {
                    padding-top: 5rem !important;
                }
                    
                div[data-testid="stPopover"] {
                    position: fixed !important;
                    top: 0.5rem !important;
                    right: 1rem !important;
                    left: auto !important;
                    width: auto !important;
                    z-index: 10001 !important;
                }

                /* 2. 버튼 모양 동그랗게 만들기 */
                div[data-testid="stPopover"] > button {
                    background-color: #3C4043 !important; 
                    color: #E8EAED !important; 
                    border: none !important;
                    border-radius: 50% !important;
                    width: 3.5rem !important;
                    height: 3.5rem !important;
                    padding: 0 !important;
                    display: flex !important;
                    align-items: center !important;
                    justify-content: center !important;
                    font-size: 1.1rem !important;
                    font-weight: 600 !important;
                    box-shadow: none !important;
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
    
else: # 로그인 페이지
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
    
    st.markdown(f"<h1 style='text-align: center;'>{yongyong_icon_html} 서일대학교 용용이</h1>", unsafe_allow_html=True)
    st.markdown("<h3 style='text-align: center;'>로그인 또는 회원가입을 해주세요.</h3>", unsafe_allow_html=True)
    
    col1, col_main, col3 = st.columns([1, 3, 1])
    with col_main:
        auth_url = get_google_auth_url()
        google_btn_html = f"""<div class="google-btn-container"><a href="{auth_url}" class="google-btn" target="_self"><img src="https://upload.wikimedia.org/wikipedia/commons/c/c1/Google_%22G%22_logo.svg" alt="Google logo">Google계정으로 로그인</a></div>"""
        
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
                        
                st.markdown('<p class="or-divider">or</p>', unsafe_allow_html=True)
                # Google 로그인 버튼
                st.markdown(google_btn_html, unsafe_allow_html=True)

            # 회원가입 전환 링크
            st.button("계정이 없으시면 회원가입하기", on_click=set_page, args=('signup',), use_container_width=True)

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
                            user_db_url = f"{db_url}users/{uid}.json?auth={id_token}"
                            user_data_payload = {"name": signup_name, "email": signup_email, "interests": None, "dynamic_keywords": []}
                            put_response = requests.put(user_db_url, json=user_data_payload)
                            if put_response.status_code == 200:
                                st.success("회원가입이 완료되었습니다! '로그인' 탭에서 로그인해주세요.")
                                st.session_state.page = 'login'
                                st.rerun()
                            else:
                                st.error(f"회원가입은 되었으나, 이름 저장 실패: {put_response.text}")
                        else:
                            st.error(parse_firebase_error(response.text)) 

                st.markdown('<p class="or-divider">or</p>', unsafe_allow_html=True)
                # Google 회원가입 버튼
                st.markdown(google_btn_html, unsafe_allow_html=True)
            # 로그인 전환 링크
            st.button("이미 계정이 있다면 로그인하기.", on_click=set_page, args=('login',), use_container_width=True)