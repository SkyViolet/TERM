# 1. 필요한 라이브러리 불러오기
import streamlit as st
import google.generativeai as genai

# --- 초기 설정 ---

# 2. API 키 설정 (Streamlit Secrets 사용 권장)
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except (FileNotFoundError, KeyError):
    # 로컬 테스트 시, 프로젝트 폴더 안에 .streamlit/secrets.toml 파일을 만들고 키를 저장하세요.

    API_KEY = "AIzaSyBZD2AqxEMJTStEm3UXdjaloS-Mjf9-GgE"

genai.configure(api_key=API_KEY)

# --- 페르소나 정의 ---

# 3. 페르소나 딕셔너리
PERSONAS = {
    "친한 친구 '제니'": {
        "system_instruction": "너는 나의 가장 친한 친구 AI '제니'야. 항상 밝고 긍정적으로, 반말로 대답해줘. 이모티콘도 자주 사용해줘. 사용자가 힘들 땐 따뜻하게 위로해주는 역할을 맡고 있어.",
        "welcome_message": "안녕! 나는 너의 AI 친구 제니야! 😊 오늘 하루는 어땠어? 무슨 일이든 나한테 말해봐!",
        "avatar": "😊"
    },
    "면접관 '박프로'": {
        "system_instruction": "당신은 IT 기업의 채용 면접관 '박프로'입니다. 사용자를 지원자로 간주하고, IT 기술과 문제 해결 능력에 대해 날카롭고 논리적인 질문을 던지세요. 항상 존댓말을 사용하고 전문적인 태도를 유지하세요.",
        "welcome_message": "안녕하십니까, 지원자님. 저는 채용 담당 박프로입니다. 준비되셨으면 면접을 시작하겠습니다.",
        "avatar": "🧑‍💼"
    },
    "영어 선생님 'Emily'": {
        "system_instruction": "You are a friendly and patient English teacher named Emily. Your goal is to help the user practice English conversation. Correct their grammatical mistakes gently and suggest better expressions. Always speak in English.",
        "welcome_message": "Hello! I'm Emily, your English teacher. Let's have a conversation! Don't worry about making mistakes.",
        "avatar": "🧑‍🏫"
    }
}

# --- 웹 UI 설정 ---

st.set_page_config(
    page_title="멀티 페르소나 AI 챗봇",
    page_icon="🤖"
)

st.title("🤖 멀티 페르소나 AI 챗봇")
st.write("왼쪽 사이드바에서 AI 페르소나를 선택하고 대화를 시작하세요!")


# 4. 세션 상태(session_state) 초기화 (구조 변경)
# 'chat_histories'가 없으면 빈 딕셔너리로 새로 만들어줍니다.
if "chat_histories" not in st.session_state:
    st.session_state.chat_histories = {}


# --- 사이드바 로직 ---

with st.sidebar:
    st.header("페르소나 선택")
    
    # 5. 페르소나 선택 드롭다운 메뉴
    selected_persona_name = st.selectbox(
        "대화하고 싶은 AI를 선택하세요.",
        options=list(PERSONAS.keys()),
        key="selected_persona" # 선택 상태를 세션에 저장
    )
    
    persona = PERSONAS[selected_persona_name]

    # 6. '새 대화 시작' 버튼
    if st.button("새 대화 시작", key=f"new_chat_{selected_persona_name}"):
        # 현재 선택된 페르소나의 대화 기록만 삭제
        st.session_state.chat_histories[selected_persona_name] = [
            {"role": "model", "content": persona["welcome_message"]}
        ]
        st.rerun() # 페이지를 새로고침하여 채팅창을 업데이트

# 7. 선택된 페르소나의 대화 기록 초기화
# 해당 페르소나와의 대화 기록이 없으면, 새로 만들어주고 환영 메시지를 추가
if selected_persona_name not in st.session_state.chat_histories:
    st.session_state.chat_histories[selected_persona_name] = [
        {"role": "model", "content": persona["welcome_message"]}
    ]

# 8. 현재 선택된 페르소나의 대화 기록을 화면에 표시
current_chat_history = st.session_state.chat_histories[selected_persona_name]
for message in current_chat_history:
    avatar = persona["avatar"] if message["role"] == "model" else "👤"
    with st.chat_message(message["role"], avatar=avatar):
        st.markdown(message["content"])


# --- Gemini API 연동 및 채팅 로직 ---

# 9. 사용자 입력받기
if prompt := st.chat_input(f"'{selected_persona_name}'에게 메시지 보내기..."):
    # 사용자 메시지를 현재 페르소나의 대화 기록에 추가하고 화면에 표시
    current_chat_history.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="👤"):
        st.markdown(prompt)

    # Gemini 모델 설정
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    # API에 보낼 대화 기록 생성 (시스템 지시사항 포함)
    messages_for_api = [
        {'role': 'user', 'parts': [persona['system_instruction']]}
    ]
    for msg in current_chat_history:
        role = 'user' if msg['role'] == 'user' else 'model'
        messages_for_api.append({'role': role, 'parts': [msg['content']]})

    chat_session = model.start_chat(history=messages_for_api)

    with st.spinner("AI가 생각 중..."):
        response = chat_session.send_message(prompt)
        ai_response = response.text

    # AI 답변을 현재 페르소나의 대화 기록에 추가하고 화면에 표시
    current_chat_history.append({"role": "model", "content": ai_response})
    with st.chat_message("model", avatar=persona["avatar"]):
        st.markdown(ai_response)