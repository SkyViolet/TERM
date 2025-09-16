# 1. 필요한 라이브러리 불러오기
import streamlit as st
import google.generativeai as genai

# --- 초기 설정 ---

# 2. API 키 설정
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except (FileNotFoundError, KeyError):
    API_KEY = "AIzaSyBZD2AqxEMJTStEm3UXdjaloS-Mjf9-GgE"

genai.configure(api_key=API_KEY)

# --- AI 역할 및 정보 설정 ---

system_instruction = """
너는 '서일대학교' 학생들을 위한 AI 챗봇 '서일비서'야. 학생들의 질문에 친절하고 정확하게 답변해야 해.
아래의 정보를 바탕으로 답변하고, 정보가 없는 내용은 솔직하게 모른다고 말해줘. 항상 존댓말을 사용해줘.

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
    page_icon="🎓"
)

# 화면을 두 개의 단(column)으로 나눕니다.
# 비율을 [1, 3]으로 설정하여 왼쪽 단(로고)보다 오른쪽 단(제목)이 3배 더 넓게 만듭니다.
st.markdown("""
    <style>
           .block-container {
                padding-top: 2rem;
            }
    </style>
    """, unsafe_allow_html=True)

col1, col2 = st.columns([1, 3])

# 왼쪽 단(col1)에 로고 이미지를 넣습니다.
with col1:
    st.markdown(
        """
          <div style="margin-top: -rem; margin-left: -55rem;">
            <a href="https://www.seoil.ac.kr/">
                <img src="https://ncs.seoil.ac.kr/GateWeb/Common/images/login/%EC%84%9C%EC%9D%BC%EB%8C%80%20%EB%A1%9C%EA%B3%A0.png" width="200">
            </a>
        <div>
        """,
        unsafe_allow_html=True,
    )

# 오른쪽 단(col2)에 제목과 설명을 넣습니다.
with col2:
    # 제목의 세로 위치를 로고와 맞추기 위해 약간의 여백(padding)을 추가
    st.markdown("<h1 style='padding-top: 1rem; margin-left: -10rem;'>🎓 서일대학교 AI 챗봇 '서일비서'</h1>", unsafe_allow_html=True)


st.write("안녕하세요! 서일대학교에 대해 궁금한 점을 무엇이든 물어보세요.")
st.write("예시: 셔틀버스는 어디서 타? / 소프트웨어공학과에 대해 알려줘")


if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("질문을 입력해주세요..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    model = genai.GenerativeModel('gemini-1.5-flash')
    
    chat_history_for_api = [
        {'role': 'user', 'parts': [system_instruction]},
        {'role': 'model', 'parts': ["네, 안녕하세요! 저는 서일대학교 안내 AI '서일비서'입니다. 무엇을 도와드릴까요?"]}
    ]
    for msg in st.session_state.messages:
        role = 'user' if msg['role'] == 'user' else 'model'
        chat_history_for_api.append({'role': role, 'parts': [msg['content']]})

    chat_session = model.start_chat(history=chat_history_for_api)

    with st.spinner("서일비서가 답변을 준비 중입니다..."):
        response = chat_session.send_message(prompt)
        ai_response = response.text

    st.session_state.messages.append({"role": "model", "content": ai_response})
    with st.chat_message("model"):
        st.markdown(ai_response)