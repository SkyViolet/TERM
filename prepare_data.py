import google.generativeai as genai
import requests
from bs4 import BeautifulSoup
import chromadb

# 본인의 API 키를 입력하세요
API_KEY = "AIzaSyD_BbwVdQZfH71Fez8gyDQlW09BbbY15VM"
genai.configure(api_key=API_KEY)

def scrape_and_process_page(topic, url):
    """
    페이지의 주제(topic)에 따라 최적화된 방법으로 스크레이핑을 수행하는 함수.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')

    # 1. 모든 페이지의 기본 콘텐츠 영역을 찾습니다.
    main_content = soup.find(id='_contentBuilder')

    if main_content:
        print(f" INFO: '{topic}' 페이지에서 id='_contentBuilder' 내용을 추출했습니다.")
        return main_content.get_text(separator='\n', strip=True)
    else:
        print(f"  -> WARN: '{topic}' 페이지에서 id='_contentBuilder' 영역을 찾지 못했습니다. 전체 텍스트를 추출합니다.")
        return soup.get_text(separator='\n', strip=True)
        
        
def prepare_and_save_embeddings():
    print("서일대학교 홈페이지 정보 스크레이핑 시작...")
    urls = {
        "학사공지": "https://www.seoil.ac.kr/seoil/599/subview.do",
        "공지사항": "https://www.seoil.ac.kr/seoil/598/subview.do",
        "행사안내": "https://www.seoil.ac.kr/seoil/600/subview.do",
        "홍보사항": "https://www.seoil.ac.kr/seoil/602/subview.do",
        "셔틀버스": "https://www.seoil.ac.kr/seoil/520/subview.do",
        "서일대학교": "https://www.seoil.ac.kr/sites/seoil/index.do",
        "학교소식": "https://www.seoil.ac.kr/seoil/616/subview.do",
        "스터디공간": "https://www.seoil.ac.kr/seoil/583/subview.do",
        "PC이용, VR실": "https://www.seoil.ac.kr/seoil/584/subview.do",
        "편의점, 카페": "https://www.seoil.ac.kr/seoil/585/subview.do",
        "학생식당": "https://www.seoil.ac.kr/seoil/3896/subview.do",
        "휴게공간": "https://www.seoil.ac.kr/seoil/586/subview.do",
        "편의시설": "https://www.seoil.ac.kr/seoil/587/subview.do",
        "체육시설": "https://www.seoil.ac.kr/seoil/588/subview.do",
        "대학생활메뉴얼": "https://www.seoil.ac.kr/seoil/3409/subview.do",
        "찾아오시는길": "https://www.seoil.ac.kr/seoil/520/subview.do",
        "도서관": "https://www.seoil.ac.kr/seoil/580/subview.do"
    }
    
    all_chunks = []
    for topic, url in urls.items():
        try:
            text = scrape_and_process_page(topic, url)
            if not text.strip():
                print(f"  -> WARN: '{topic}' 페이지에서 추출된 텍스트가 없습니다.")
                continue
            
            # 텍스트를 500자 단위로 자르기
            for i in range(0, len(text), 500):
                chunk = text[i:i+500]
                all_chunks.append({"topic": topic, "content": chunk})
            print(f"✅ '{topic}' 페이지 스크레이핑 완료")

        except Exception as e:
            print(f"❌ '{topic}' 페이지 처리 중 오류 발생: {e}")
            continue

    print("\n텍스트 조각들을 임베딩하는 중... (시간이 걸릴 수 있습니다)")
    if not all_chunks:
        print("스크레이핑된 데이터가 없어 임베딩을 진행할 수 없습니다.")
        return
    

    contents = [chunk['content'] for chunk in all_chunks]

    # ChromaDB 클라이언트 초기화 및 컬렉션 생성
    # (ChromaDB는 데이터를 디스크에 자동으로 저장/관리해줍니다)
    db_path = "./chroma_db"
    client = chromadb.PersistentClient(path=db_path)
    collection = client.get_or_create_collection(name="seoil_info_db") # DB 이름 지정
    
    embedding_result = genai.embed_content(model="models/embedding-001", content=contents, task_type="RETRIEVAL_DOCUMENT")

    # ChromaDB에 저장할 데이터 형식으로 준비
    documents = contents
    embeddings = embedding_result['embedding']
    ids = [f"chunk_{i}" for i in range(len(documents))] # 각 정보 조각의 고유 ID

    try:
        if collection.count() > 0:
            print(f"기존 DB({collection.count()}개)를 삭제하고 새로 생성합니다.")
            client.delete_collection(name="seoil_info_db")
            collection = client.get_or_create_collection(name="seoil_info_db")
    except Exception:
        pass

    # 데이터를 ChromaDB에 추가
    collection.add(
        embeddings=embeddings,
        documents=documents,
        ids=ids
    )
        
    print(f"\n🎉 임베딩 완료! 총 {len(documents)}개의 정보 조각이 '{db_path}' 폴더에 저장되었습니다.")
if __name__ == "__main__":
    prepare_and_save_embeddings()