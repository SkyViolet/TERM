import requests
from bs4 import BeautifulSoup
import pandas as pd

def scrape_and_process_page(topic, url):
    """
    모든 페이지에서 id='_contentBuilder' 영역의 텍스트를 추출하는 통일된 함수.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')

    main_content = soup.find(id='_contentBuilder')

    if main_content:
        print(f" INFO: '{topic}' 페이지에서 id='_contentBuilder' 내용을 추출했습니다.")
        return main_content.get_text(separator='\n', strip=True)
    else:
        print(f"  -> WARN: '{topic}' 페이지에서 id='_contentBuilder' 영역을 찾지 못했습니다. 전체 텍스트를 추출합니다.")
        return soup.get_text(separator='\n', strip=True)

# ----------------------------------------------------
# --- 테스트 설정 ---
# 👇 확인하고 싶은 페이지의 주제와 URL을 여기에 입력하세요 👇
TOPIC_TO_CHECK = "찾아오시는길"
URL_TO_CHECK = "https://www.seoil.ac.kr/seoil/520/subview.do"
# ----------------------------------------------------

# --- 메인 실행 부분 ---
if __name__ == "__main__":
    print(f"--- '{TOPIC_TO_CHECK}' 페이지 스크레이핑 결과 확인 시작 ---\n")
    try:
        final_text = scrape_and_process_page(TOPIC_TO_CHECK, URL_TO_CHECK)
        
        print("\n--- [AI에게 전달될 최종 텍스트] ---\n")
        if final_text and final_text.strip():
            print(final_text)
        else:
            print("!!! 텍스트를 전혀 가져오지 못했습니다. !!!")
        print("\n--- [확인 완료] ---")

    except Exception as e:
        print(f"❌ 스크레이핑 중 오류 발생: {e}")