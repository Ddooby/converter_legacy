#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import pandas as pd
from pathlib import Path

def find_java_files_with_imports(root_directory):
    """
    Java 파일에서 import 경로 중 'service' 또는 'function'이 포함된 파일들을 찾아서 분석
    """
    
    results = []
    
    print(f"🔍 디렉토리 스캔 시작: {root_directory}")
    
    # Java 파일 찾기
    java_files = []
    for root, dirs, files in os.walk(root_directory):
        for file in files:
            if file.endswith('.java'):
                java_files.append(os.path.join(root, file))
    
    
    print(f"📄 총 Java 파일 수: {len(java_files)}개")
    
    # 각 Java 파일 분석
    for java_file in java_files:
        try:
            # 파일 읽기 (여러 인코딩 시도)
            content = read_file_safely(java_file)
            if content is None:
                continue
            
            # import 라인 찾기
            import_lines = re.findall(r'^import\s+([^;]+);', content, re.MULTILINE)
            
            # service 또는 function이 포함된 import 찾기
            matching_imports = []
            for import_path in import_lines:
                if 'service' in import_path.lower() or 'function' in import_path.lower():
                    matching_imports.append(import_path.strip())
            
            # 매칭되는 import가 있으면 결과에 추가
            if matching_imports:
                # 상대 경로 계산 (깊이 분석용)
                relative_path = os.path.relpath(java_file, root_directory)
                depth = len(Path(relative_path).parts) - 1  # 파일명 제외한 폴더 깊이
                
                for import_path in matching_imports:
                    results.append({
                        'file_path': java_file,
                        'relative_path': relative_path,
                        'file_name': os.path.basename(java_file),
                        'directory': os.path.dirname(relative_path),
                        'depth': depth,
                        'import_path': import_path,
                        'import_type': get_import_type(import_path)
                    })
                
                print(f"✅ {os.path.basename(java_file)}: {len(matching_imports)}개 매칭")
        
        except Exception as e:
            print(f"❌ 파일 처리 오류 {java_file}: {e}")
            continue
    
    print(f"🎯 총 매칭된 import: {len(results)}개")
    return results

def read_file_safely(file_path):
    """여러 인코딩으로 파일을 안전하게 읽기"""
    encodings = ['utf-8', 'cp949', 'euc-kr', 'utf-8-sig', 'latin1']
    
    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
        except Exception as e:
            print(f"❌ 파일 읽기 오류 {file_path}: {e}")
            return None
    
    print(f"❌ 인코딩 실패: {file_path}")
    return None

def get_import_type(import_path):
    """import 경로 타입 분류"""
    if 'service' in import_path.lower():
        return 'SERVICE'
    elif 'function' in import_path.lower():
        return 'FUNCTION'
    else:
        return 'OTHER'

def save_to_excel(results, output_file):
    """결과를 엑셀 파일로 저장"""
    
    if not results:
        print("❌ 저장할 데이터가 없습니다.")
        return
    
    # DataFrame 생성
    df = pd.DataFrame(results)
    
    # 엑셀 파일 생성
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        
        # 1. 전체 결과 시트
        df_sorted = df.sort_values(['depth', 'relative_path', 'import_path'])
        df_sorted.to_excel(writer, sheet_name='전체결과', index=False)
        
        # 2. 깊이별 분류 시트
        depth_summary = df.groupby('depth').agg({
            'file_name': 'count',
            'import_path': 'count'
        }).rename(columns={'file_name': '파일수', 'import_path': 'import수'})
        depth_summary.to_excel(writer, sheet_name='깊이별통계')
        
        # 3. import 타입별 시트
        type_summary = df.groupby('import_type').agg({
            'file_name': 'count',
            'import_path': 'count'
        }).rename(columns={'file_name': '파일수', 'import_path': 'import수'})
        type_summary.to_excel(writer, sheet_name='타입별통계')
        
        # 4. 디렉토리별 시트
        dir_summary = df.groupby('directory').agg({
            'file_name': 'count',
            'import_path': 'count'
        }).rename(columns={'file_name': '파일수', 'import_path': 'import수'})
        dir_summary.to_excel(writer, sheet_name='디렉토리별통계')
        
        # 5. SERVICE만 따로 시트
        service_df = df[df['import_type'] == 'SERVICE'].sort_values(['depth', 'relative_path'])
        if not service_df.empty:
            service_df.to_excel(writer, sheet_name='SERVICE만', index=False)
        
        # 6. FUNCTION만 따로 시트
        function_df = df[df['import_type'] == 'FUNCTION'].sort_values(['depth', 'relative_path'])
        if not function_df.empty:
            function_df.to_excel(writer, sheet_name='FUNCTION만', index=False)
    
    print(f"✅ 엑셀 파일 저장 완료: {output_file}")
    
    # 결과 요약 출력
    print(f"\n📊 결과 요약:")
    print(f"   총 파일 수: {df['file_name'].nunique()}개")
    print(f"   총 import 수: {len(df)}개")
    print(f"   SERVICE 타입: {len(df[df['import_type'] == 'SERVICE'])}개")
    print(f"   FUNCTION 타입: {len(df[df['import_type'] == 'FUNCTION'])}개")
    
    # 깊이별 요약
    print(f"\n📁 깊이별 분포:")
    for depth in sorted(df['depth'].unique()):
        count = len(df[df['depth'] == depth])
        print(f"   깊이 {depth}: {count}개")

def main():
    """메인 실행 함수"""
    
    print("🔍 Java Import 분석기 (service/function 검색)")
    print("=" * 50)
    
    # 입력 받기
    root_dir = input("📂 분석할 루트 디렉토리 경로를 입력하세요: ").strip().strip('"').strip("'")
    output_file = input("📝 출력할 엑셀 파일명을 입력하세요 (예: import_analysis.xlsx): ").strip()
    
    # 기본값 설정
    if not output_file:
        output_file = "import_analysis.xlsx"
    
    if not output_file.endswith('.xlsx'):
        output_file += '.xlsx'
    
    # 경로 정규화
    root_dir = os.path.normpath(root_dir)
    
    print(f"\n🔍 설정 확인:")
    print(f"   분석 디렉토리: {root_dir}")
    print(f"   출력 파일: {output_file}")
    
    # 디렉토리 존재 확인
    if not os.path.exists(root_dir):
        print(f"❌ 디렉토리가 존재하지 않습니다: {root_dir}")
        return
    
    if not os.path.isdir(root_dir):
        print(f"❌ 지정된 경로가 디렉토리가 아닙니다: {root_dir}")
        return
    
    try:
        # 분석 실행
        print(f"\n🚀 분석 시작...")
        results = find_java_files_with_imports(root_dir)
        
        if results:
            # 엑셀 저장
            save_to_excel(results, output_file)
            print(f"\n🎉 분석 완료! 결과가 {output_file}에 저장되었습니다.")
        else:
            print(f"\n⚠️ 'service' 또는 'function'이 포함된 import를 찾을 수 없습니다.")
            
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()