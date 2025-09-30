import google.generativeai as genai
import requests
from bs4 import BeautifulSoup
import numpy as np
import pickle

# 본인의 API 키를 입력하세요
API_KEY = "AIzaSyA82LrwZs-SBtfl4REcClLGbDv1-Na2iO4"
genai.configure(api_key=API_KEY)

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
        "찾아오시는길": "https://www.seoil.ac.kr/seoil/520/subview.do"


    }
    
    all_chunks = []
    for topic, url in urls.items():
        try:
            response = requests.get(url, timeout=600)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            text = soup.get_text(separator='\n', strip=True)
            for i in range(0, len(text), 500):
                chunk = text[i:i+500]
                all_chunks.append({"topic": topic, "content": chunk})
            print(f"✅ '{topic}' 페이지 스크레이핑 완료")
        except requests.RequestException as e:
            print(f"❌ '{topic}' 페이지 스크레이핑 실패: {e}")
            continue

    print("\n텍스트 조각들을 임베딩하는 중... (시간이 걸릴 수 있습니다)")
    if not all_chunks:
        print("스크레이핑된 데이터가 없어 임베딩을 진행할 수 없습니다.")
        return
        
    contents = [chunk['content'] for chunk in all_chunks]
    embedding_result = genai.embed_content(model="models/embedding-001", content=contents, task_type="RETRIEVAL_DOCUMENT")
    
    vector_store = [{"content": chunk['content'], "embedding": vector} for chunk, vector in zip(all_chunks, embedding_result['embedding'])]
    
    # 임베딩 결과를 파일로 저장
    with open("vector_store.pkl", "wb") as f:
        pickle.dump(vector_store, f)
        
    print("\n🎉 임베딩 완료! 'vector_store.pkl' 파일이 저장되었습니다.")

if __name__ == "__main__":
    prepare_and_save_embeddings()