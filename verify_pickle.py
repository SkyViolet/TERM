import pickle

FILENAME = "vector_store.pkl"

try:
    with open(FILENAME, "rb") as f:
        vector_store = pickle.load(f)

    print(f"✅ '{FILENAME}' 파일을 성공적으로 불러왔습니다.")
    print("-" * 50)

    if not vector_store:
        print("!!! 파일 안에 데이터가 없습니다. !!!")
    else:
        print(f"총 {len(vector_store)}개의 정보 조각이 저장되어 있습니다.")

        # '셔틀버스' 또는 '찾아오시는길' 정보가 포함된 조각이 있는지 확인
        shuttle_info_found = False
        print("\n--- '셔틀버스' 관련 정보 조각 샘플 ---")
        count = 0
        for item in vector_store:
            if "셔틀" in item['content'] or "망우역" in item['content']:
                print(f"\n[조각 {count+1}]")
                print(item['content'])
                shuttle_info_found = True
                count += 1
            if count >= 3: # 최대 3개까지만 출력
                break

        if not shuttle_info_found:
            print("!!! '셔틀버스' 관련 정보를 파일에서 찾지 못했습니다. !!!")

except FileNotFoundError:
    print(f"❌ '{FILENAME}' 파일을 찾을 수 없습니다. 'prepare_data.py'를 먼저 실행했는지 확인해주세요.")
except Exception as e:
    print(f"파일을 읽는 중 오류가 발생했습니다: {e}")