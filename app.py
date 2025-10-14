# 1. 필요한 라이브러리 불러오기
import streamlit as st
import google.generativeai as genai
import numpy as np
import pickle

# --- 초기 설정 ---

# 2. API 키 설정
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except (FileNotFoundError, KeyError):
    API_KEY = "AIzaSyBZD2AqxEMJTStEm3UXdjaloS-Mjf9-GgE"

genai.configure(api_key=API_KEY)

# 의미 기반 검색(RAG) 기능, 의미 검색(Semanric Search) 기능 구현
# 3. 데이터 로딩 및 전처리 함수
@st.cache_resource(show_spinner="사전 학습된 학교 정보를 로딩 중입니다...")
def load_vector_store():
    """저장된 vector_store.pkl 파일을 불러옵니다."""
    try:
        with open("vector_store.pkl", "rb") as f:
            return pickle.load(f)
    except FileNotFoundError:
        st.error("'vector_store.pkl' 파일을 찾을 수 없습니다. 'prepare_data.py'를 먼저 실행해주세요.")
        return None


# 4. 관련 정보 검색 함수
def find_relevant_info(query, vector_store, top_k=5):
    """사용자 질문을 임베딩하고, 저장된 정보들 중에서 의미상 가장 유사한 정보 조각 top_k개를 찾습니다."""
    if not vector_store:
        return ""
        
    # 사용자 질문 임베딩
    query_embedding = genai.embed_content(model="models/embedding-001", content=query, task_type="RETRIEVAL_QUERY")['embedding']
    
    # 코사인 유사도 계산
    similarities = []
    for item in vector_store:
        similarity = np.dot(query_embedding, item['embedding']) / (np.linalg.norm(query_embedding) * np.linalg.norm(item['embedding']))
        similarities.append(similarity)
    
    # 유사도가 가장 높은 top_k개의 인덱스 찾기
    top_indices = np.argsort(similarities)[-top_k:][::-1]
    
    # 관련 정보 텍스트 합치기
    relevant_info = "\n\n".join([vector_store[i]['content'] for i in top_indices])
    return relevant_info

# 앱 시작 시 데이터 로딩 및 임베딩 실행
vector_store = load_vector_store()

# --- AI 역할 및 정보 설정 ---
system_instruction = """
너는 '서일대학교' 학생들을 위한 AI 챗봇 '서일비서'야. 학생들의 질문에 친절하고 정확하게 답변해야 해.
기존에 답변 가능한 범위의 질문을 우선적으로 답변하고 정확한 정보가 없다면 주어진 [참고 정보]와 [이전 대화 내용]을 종합적으로 고려하여 답변을 생성해줘.
참고 정보에도 내용이 없다면, 이전 대화 내용을 바탕으로 답변하거나 솔직하게 모른다고 말해줘.
"""

st.set_page_config(page_title="서일대학교 AI 챗봇", page_icon="🎓")
st.markdown("""
    <style>
           .block-container {
                padding-top: 2rem;
            }
           .fixed-logo { position: fixed; top: 2.5rem; left: 0.7rem; z-index: 99; }
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

# 7. 사용자 입력 처리
if prompt := st.chat_input("질문을 입력해주세요..."):
    # 사용자 메시지를 기록하고 화면에 표시
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 의미 기반(의미 검색_Semanric Sarch)으로 관련 정보 검색
    with st.spinner("관련 정보를 찾는 중..."):
        retrieved_info = find_relevant_info(prompt, vector_store)

    # --- [ 디버깅 코드 ] --- 디버깅시 #7의 코드 주석처리
    #with st.spinner("관련 정보를 찾는 중..."):
     #    retrieved_info = find_relevant_info(prompt, vector_store)

    # AI에게 전달될 참고 정보를 화면에 정보(info) 박스로 표시
    #if retrieved_info:
     #   st.info(f"**[AI 참고 정보]**\n\n---\n\n{retrieved_info}")
    #else:
     #   st.error("**[AI 참고 정보]**\n\n---\n\n관련 정보를 찾지 못했습니다.")
    # --- [ 디버깅 코드 ] ---

    # 이전 대화 내용 형식화
    previous_conversation = "\n".join([f'{msg["role"]}: {msg["content"]}' for msg in st.session_state.messages])

    # AI에게 전달할 최종 프롬프트 구성
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
        # 1. stream=True 옵션을 제거하여 일반적인 방식으로 API 호출
        response = chat_session.send_message(final_prompt)

        # 2. 응답 객체(response)에서 .text를 사용해 "순수 텍스트"만 추출
        ai_response = response.text

        # 3. 추출된 텍스트를 화면에 표시
        st.markdown(ai_response)

    # 4. 깨끗하게 추출된 텍스트를 대화 기록에 저장
    st.session_state.messages.append({"role": "model", "content": ai_response})