# 1. 필요한 라이브러리 불러오기
import streamlit as st
import google.generativeai as genai
import requests
from bs4 import BeautifulSoup

# --- 초기 설정 ---

# 2. API 키 설정
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except (FileNotFoundError, KeyError):
    API_KEY = "AIzaSyBZD2AqxEMJTStEm3UXdjaloS-Mjf9-GgE"

genai.configure(api_key=API_KEY)

# 3. 실시간으로 웹사이트 정보를 가져오는 함수
@st.cache_data(ttl=600) # 10분 동안 결과를 캐싱하여 반복적인 스크레이핑 방지
def get_info_from_homepage(url):
    """지정된 URL에서 텍스트를 스크레이핑하여 반환합니다."""
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()  # HTTP 오류가 발생하면 예외를 발생시킴
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 웹페이지의 메인 콘텐츠 영역에서 텍스트 추출 (사이트 구조에 맞게 선택자 수정 필요)
        # 예시로 'main-container' ID를 가진 영역을 선택
        content_area = soup.find('div', id='main-container')
        if content_area:
            return content_area.get_text(separator='\n', strip=True)
        else:
            # 전체 텍스트라도 가져오기
            return soup.get_text(separator='\n', strip=True)
            
    except requests.exceptions.RequestException as e:
        st.error(f"웹사이트 정보를 가져오는 데 실패했습니다: {e}")
        return None

# 검색할 서일대학교의 주요 정보 페이지 URL들
SEOIL_URLS = {
    "학사공지": "https://www.seoil.ac.kr/seoil/599/subview.do",
    "셔틀버스": "https://www.seoil.ac.kr/seoil/520/subview.do",
    "서일대학교": "https://www.seoil.ac.kr/sites/seoil/index.do"
    # 필요한 다른 페이지 URL들을 여기에 추가...
}


# --- AI 역할 및 정보 설정 ---

system_instruction = """
너는 '서일대학교' 학생들을 위한 AI 챗봇 '서일비서'야. 학생들의 질문에 친절하고 정확하게 답변해야 해.
아래의 정보와 서일대학교의 홈페이지의 정보를 바탕으로 답변하고, 정보가 없는 내용은 솔직하게 모른다고 말하고 추가로 질문의 대한 내용을 어디에서 구할 수 있을지도 덧붙혀서 설명해줘. 
홈페이지에서 찾은 정보는 확실하게 말해줘.
항상 존댓말을 사용해줘.

[서일대학교 핵심 정보]
- **위치**: 서울특별시 중랑구 용마산로90길 28 (면목동)
- **교통**:
    - **지하철**: 7호선 면목역 2번 출구, 7호선 사가정역 1번 출구
    - **셔틀버스**:
        - **면목역**: 2번 출구 앞 '파리바게뜨' 앞에서 탑승 (오전 8시부터 수시 운행)
        - **사가정역**: 1번 출구 앞 '롯데리아' 앞에서 탑승 (오전 8시부터 수시 운행)
- **주요 학과**:
    - **IT계열**: 소프트웨어공학과, AI융합콘텐츠학과, 정보보호학과, 컴퓨터전자공학과 등
    - **디자인계열**: 실내디자인학과, 시각디자인학과, 패션산업학과, 영화방송공연예술학과 등
    - **인문사회계열**: 유아교육과, 사회복지학과, 세무회계학과, 비즈니스일본어과, 중국어문화학과 등
    - **기타**: 자율전공학과, 간호학과, 생명화학공학과 등
- **연락처**:
    - **대표 번호**: 02-490-7300
    - **입학 문의**: 02-490-7331~3
- **특징**: '지덕배양, 초지일관'을 교훈으로 삼고 있으며, 실무 중심의 전문 인재 양성을 목표로 함.
"""

# --- 웹 UI 설정 ---

st.set_page_config(
    page_title="서일대학교 AI 챗봇",
    page_icon="🎓",
    layout="centered"
)

# 1. CSS를 이용해 로고를 화면 왼쪽 상단에 고정
st.markdown(
    """
    <style>
        .fixed-logo {
            position: fixed;
            top: rem;
            left: 2rem;
            z-index: 99;
        }
    </style>
    <div class="fixed-logo">
        <a href="https://www.seoil.ac.kr/">
            <img src="https://ncs.seoil.ac.kr/GateWeb/Common/images/login/%EC%84%9C%EC%9D%BC%EB%8C%80%20%EB%A1%9C%EA%B3%A0.png" width="200">
        </a>
    </div>
    """,
    unsafe_allow_html=True,
)

# 2. 메인 콘텐츠
st.markdown(
    """
    <div style="text-align: center;">
        <h2>🎓 서일대학교 AI 챗봇 '서일비서'</h2>
        <p>안녕하세요! 서일대학교에 대해 궁금한 점을 무엇이든 물어보세요.</p>
        <p>예시: 셔틀버스는 어디서 타? / 소프트웨어공학과에 대해 알려줘</p>
    </div>
    """,
    unsafe_allow_html=True
)
st.write("")
st.write("")


# --- 채팅 로직 ---

if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("질문을 입력해주세요..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    retrieved_info = ""
    target_url = None
    if "셔틀" in prompt or "버스" in prompt:
        target_url = SEOIL_URLS["셔틀버스"]
    elif "공지" in prompt or "학사" in prompt:
        target_url = SEOIL_URLS["학사공지"]
    # ... 다른 키워드 규칙 추가

    # 2. 결정된 URL에서 실시간으로 정보 스크레이핑
    if target_url:
        with st.spinner(f"서일대학교 홈페이지({target_url})에서 최신 정보를 찾는 중..."):
            retrieved_info = get_info_from_homepage(target_url)

    # 3. 최종 프롬프트 구성
    final_prompt = f"""
[참고 정보]
{retrieved_info if retrieved_info else "가져온 정보 없음"}

[사용자 질문]
{prompt}
"""

    model = genai.GenerativeModel('gemini-1.5-flash')
    chat_history = [{'role': 'user', 'parts': [system_instruction]}] # 기본 지시사항
    # (선택사항) 이전 대화 기록을 여기에 추가할 수 있음
    
    chat_session = model.start_chat(history=chat_history)

    with st.spinner("서일비서가 답변을 생성 중입니다..."):
        response = chat_session.send_message(final_prompt)
        ai_response = response.text

    st.session_state.messages.append({"role": "model", "content": ai_response})
    with st.chat_message("model"):
        st.markdown(ai_response)