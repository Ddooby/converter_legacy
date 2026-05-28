#!/usr/bin/env python32
# -*- coding: utf-8 -*-

import re
import os
import shutil
from pathlib import Path

def safe_read_file(file_path):
    """파일을 안전하게 읽기 - 여러 인코딩을 시도합니다."""
    
    # 시도할 인코딩 목록 (한국어 환경에서 자주 사용되는 순서)
    encodings_to_try = ['cp949', 'euc-kr', 'utf-8', 'utf-8-sig', 'latin1']
    
    for encoding in encodings_to_try:
        try:
            print(f"  🔄 {encoding} 인코딩으로 파일 읽기 시도...")
            with open(file_path, 'r', encoding=encoding) as f:
                content = f.read()
            print(f"  ✅ {encoding} 인코딩으로 성공적으로 읽었습니다.")
            return content, encoding
        except UnicodeDecodeError as e:
            print(f"  ❌ {encoding} 인코딩 실패: {e}")
            continue
        except Exception as e:
            print(f"  ❌ {encoding} 인코딩에서 예상치 못한 오류: {e}")
            continue
    
    # 모든 인코딩이 실패한 경우
    raise Exception(f"모든 인코딩 시도 실패: {encodings_to_try}")

def safe_write_file(file_path, content, original_encoding=None):
    """파일을 안전하게 쓰기 - UTF-8로 저장합니다."""
    try:
        # 항상 UTF-8로 저장
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"  ✅ UTF-8 인코딩으로 파일을 저장했습니다: {file_path}")
    except Exception as e:
        print(f"  ❌ 파일 저장 오류: {e}")
        raise

def convert_status_to_datasetrowstatus(content):
    """문자열 status 체크를 DataSetRowStatus enum으로 변환"""
    
    print("🔧 Status → DataSetRowStatus 변환 시작...")
    
    original_content = content
    conversion_count = 0
    
    # 1. getStatus() → getRowStatus() 변환
    before_getstatus = content.count('.getStatus()')
    content = re.sub(r'\.getStatus\(\)', '.getRowStatus()', content)
    after_getstatus = content.count('.getStatus()')
    conversion_count += (before_getstatus - after_getstatus)
    
    # 2. 문자열 상태 체크를 DataSetRowStatus enum으로 변환
    # "insert".equals(...) → DataSetRowStatus.INSERT.equals(...)
    content = re.sub(r'"insert"\.equals\(([^)]+)\.getRowStatus\(\)\)', r'DataSetRowStatus.INSERT.equals(\1.getRowStatus())', content)
    content = re.sub(r'"update"\.equals\(([^)]+)\.getRowStatus\(\)\)', r'DataSetRowStatus.UPDATE.equals(\1.getRowStatus())', content)
    content = re.sub(r'"delete"\.equals\(([^)]+)\.getRowStatus\(\)\)', r'DataSetRowStatus.DELETE.equals(\1.getRowStatus())', content)
    content = re.sub(r'"normal"\.equals\(([^)]+)\.getRowStatus\(\)\)', r'DataSetRowStatus.NORMAL.equals(\1.getRowStatus())', content)
    
    # 3. 대소문자 구분 없이 변환
    content = re.sub(r'"INSERT"\.equals\(([^)]+)\.getRowStatus\(\)\)', r'DataSetRowStatus.INSERT.equals(\1.getRowStatus())', content)
    content = re.sub(r'"UPDATE"\.equals\(([^)]+)\.getRowStatus\(\)\)', r'DataSetRowStatus.UPDATE.equals(\1.getRowStatus())', content)
    content = re.sub(r'"DELETE"\.equals\(([^)]+)\.getRowStatus\(\)\)', r'DataSetRowStatus.DELETE.equals(\1.getRowStatus())', content)
    content = re.sub(r'"NORMAL"\.equals\(([^)]+)\.getRowStatus\(\)\)', r'DataSetRowStatus.NORMAL.equals(\1.getRowStatus())', content)
    
    if content != original_content:
        print(f"🔄 Status → DataSetRowStatus 변환 완료! ({conversion_count}개 변환)")
    else:
        print("ℹ️ 변환할 status 체크가 없습니다.")
    
    return content

def convert_stringbuffer_to_stringbuilder(content):
    """StringBuffer를 StringBuilder로 변환"""
    
    print("🔧 StringBuffer → StringBuilder 변환 시작...")
    
    original_content = content
    conversion_count = 0
    
    # 1. StringBuffer 타입 선언을 StringBuilder로 변환
    # 예: StringBuffer sb = new StringBuffer();
    before_declarations = content.count('StringBuffer')
    content = re.sub(r'\bStringBuffer\b', 'StringBuilder', content)
    after_declarations = content.count('StringBuffer')
    
    if before_declarations > after_declarations:
        conversion_count = before_declarations - after_declarations
        print(f"   ✓ StringBuffer → StringBuilder 변환: {conversion_count}개")
    
    # 2. import 문에서 StringBuffer를 StringBuilder로 변환
    content = re.sub(r'^import\s+java\.lang\.StringBuffer;', 'import java.lang.StringBuilder;', content, flags=re.MULTILINE)
    
    # 3. JavaDoc에서 StringBuffer 언급을 StringBuilder로 변환
    content = re.sub(r'(\*\s+.*?)StringBuffer', r'\1StringBuilder', content)
    
    # 4. 주석에서 StringBuffer 언급을 StringBuilder로 변환
    content = re.sub(r'(//.*?)StringBuffer', r'\1StringBuilder', content)
    
    if content != original_content:
        print(f"🔄 StringBuffer → StringBuilder 변환 완료! ({conversion_count}개 변환)")
    else:
        print("ℹ️ 변환할 StringBuffer가 없습니다.")
    
    return content

def fix_method_syntax_issues(content):
    """메서드 구문 문제 수정 - return문과 닫는 중괄호 복구"""
    
    print("🔧 메서드 구문 문제 수정 시작...")
    
    lines = content.split('\n')
    fixed_lines = []
    i = 0
    
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        
        # catch 블록을 찾음
        if re.match(r'\s*}\s*catch\s*\(\s*Exception\s+\w+\s*\)\s*\{', stripped):
            fixed_lines.append(line)
            i += 1
            
            # catch 블록 내용 처리
            catch_content = []
            brace_count = 1
            
            while i < len(lines) and brace_count > 0:
                catch_line = lines[i]
                catch_stripped = catch_line.strip()
                
                brace_count += catch_stripped.count('{') - catch_stripped.count('}')
                
                # catch 블록 끝에 도달
                if brace_count == 0:
                    # catch 블록의 마지막 중괄호 추가
                    catch_content.append(catch_line)
                    
                    # catch 블록 다음에 메서드가 바로 시작하는지 확인
                    next_i = i + 1
                    if next_i < len(lines):
                        next_stripped = lines[next_i].strip()
                        
                        # 다음 줄이 메서드 시작이면 현재 메서드에 return과 닫는 중괄호 추가
                        if (re.match(r'(/\*\*|public\s+\w+)', next_stripped) or 
                            next_stripped.startswith('/**') or
                            'public ' in next_stripped):
                            
                            # return문 추가 (메서드 반환 타입에 따라)
                            method_signature = ""
                            for prev_line in reversed(fixed_lines[-20:]):  # 최근 20줄에서 메서드 시그니처 찾기
                                if 'public ' in prev_line and '(' in prev_line:
                                    method_signature = prev_line
                                    break
                            
                            if 'void ' in method_signature:
                                catch_content.append('\t\treturn;')
                            elif 'Collection' in method_signature:
                                catch_content.append('\t\treturn result;')
                            elif 'Hashtable' in method_signature:
                                catch_content.append('\t\treturn ht;')
                            elif 'String' in method_signature:
                                catch_content.append('\t\treturn result;')
                            else:
                                catch_content.append('\t\treturn null;')
                            
                            # 메서드 닫는 중괄호 추가
                            catch_content.append('\t}')
                            
                            print(f"  ✓ 메서드 구문 복구: return문과 닫는 중괄호 추가")
                    
                    break
                else:
                    catch_content.append(catch_line)
                
                i += 1
            
            # catch 블록 내용을 결과에 추가
            fixed_lines.extend(catch_content)
        else:
            fixed_lines.append(line)
        
        i += 1
    
    result = '\n'.join(fixed_lines)
    print("🔧 메서드 구문 문제 수정 완료!")
    return result


def clean_catch_blocks_and_incomplete_code(content):
    """중복 catch 블록과 불완전한 코드 정리"""
    
    print("🔧 중복 catch 블록 및 불완전한 코드 정리 시작...")
    
    # 1. 중복 catch 블록 제거
    duplicate_catch_patterns = [
        # 동일한 Exception을 두 번 catch하는 패턴들
        r'\}\s*catch\s*\(\s*Exception\s+e\s*\)\s*\{\s*log\.error\(e\.getCause\(\)\);\s*throw\s+e;\s*\}\s*catch\s*\(\s*Exception\s+e\s*\)\s*\{\s*log\.error\(e\.getMessage\(\)\);\s*throw\s+new\s+UxbException\(e\);\s*',
        r'\}\s*catch\s*\(\s*Exception\s+e\s*\)\s*\{\s*log\.error\(e\.getMessage\(\)\);\s*throw\s+new\s+UxbException\(e\);\s*\}\s*catch\s*\(\s*Exception\s+e\s*\)\s*\{\s*log\.error\(e\.getMessage\(\)\);\s*throw\s+new\s+UxbException\(e\);\s*',
    ]
    
    # 단일 catch 블록으로 교체
    single_catch_replacements = [
        '} catch (Exception e) {\n\t\tlog.error(e.getMessage());\n\t\tthrow new UxbException(e);\n\t',
        '} catch (Exception e) {\n\t\tlog.error(e.getMessage());\n\t\tthrow new UxbException(e);\n\t',
    ]
    
    for i, pattern in enumerate(duplicate_catch_patterns):
        content = re.sub(pattern, single_catch_replacements[i], content, flags=re.MULTILINE | re.DOTALL)
    
    # 2. 불완전한 conn 관련 코드 제거
    incomplete_conn_patterns = [
        r'if\s*\(\s*conn\s*!=\s*null\s*\)\s*conn\.close\(\);\s*',
        r'if\s*\(\s*conn\s*!=\s*null\s*\)\s*$',  # 끝에서 끊어진 패턴
        r'if\s*\(\s*conn\s*!=\s*null\s*\)$',      # 개행 없이 끊어진 패턴
    ]
    
    for pattern in incomplete_conn_patterns:
        content = re.sub(pattern, '', content, flags=re.MULTILINE)
    
    # 3. 빈 줄 정리
    content = re.sub(r'\n\s*\n\s*\n', '\n\n', content)
    
    print("🔧 중복 catch 블록 및 불완전한 코드 정리 완료!")
    return content


def unified_java_conversion(content):
    """
    모든 Java 변환을 한번에 처리하는 통합 함수
    A->B->C 방식이 아닌 A->최종결과 방식으로 처리
    """
    
    # 1. Import 정리 (한번에 모든 import 처리)
    content = clean_all_imports_once(content)
    
    # 2. Exception 처리 (한번에 모든 exception 처리 - 중복 제거 제외)
    content = convert_all_exceptions_once(content)
    
    # 3. StringBuffer → StringBuilder 변환
    content = convert_stringbuffer_to_stringbuilder(content)
    
    # 4. EJB 레거시 코드 제거 (한번에)
    content = remove_ejb_legacy_once(content)
    print(f"🔍 EJB 제거 후 conn 개수: {content.count('defaultInsert(conn,')}")
    
    # 5. 메서드 구문 문제 수정 (return문과 닫는 중괄호 복구)
    content = fix_method_syntax_issues(content)
    
    # 6. 중복 catch 블록 및 불완전한 코드 정리
    content = clean_catch_blocks_and_incomplete_code(content)
    
    # 7. 중복 코드 제거 (한번에 모든 중복 처리 - import와 필드만)
    content = remove_basic_duplicates_once(content)
    print(f"🔍 중복 제거 후 conn 개수: {content.count('defaultInsert(conn,')}")
    
    # 7. 포맷팅 정리 (한번에)
    content = format_code_once(content)
    print(f"🔍 포맷팅 후 conn 개수: {content.count('defaultInsert(conn,')}")
    
    # 8. Status를 DataSetRowStatus로 변환
    content = convert_status_to_datasetrowstatus(content)
    print(f"🔍 DataSetRowStatus 변환 완료")
    
    return content

def remove_basic_duplicates_once(content):
    """기본 중복 제거 (catch 블록은 제외)"""
    
    # 중복 private final 필드 제거 (강력한 패턴)
    content = remove_duplicate_dependency_fields_optimized(content)
    
    # 중복 어노테이션 제거
    content = remove_duplicate_annotations_optimized(content)
    
    # 중복 import 제거 (최종)
    lines = content.split('\n')
    seen_imports = set()
    cleaned_lines = []
    
    for line in lines:
        if line.strip().startswith('import '):
            if line not in seen_imports:
                seen_imports.add(line)
                cleaned_lines.append(line)
        else:
            cleaned_lines.append(line)
    
    content = '\n'.join(cleaned_lines)
    
    return content

def remove_duplicate_catch_blocks_final(content):
    """변환 완료 후 최종 중복 catch 블록 제거 - 직접 replace 방식"""
    
    print("🔧 최종 중복 catch 블록 제거 시작...")
    
    removed_count = 0
    original_content = content
    
    # 1단계: 기본적인 잘못된 throw 문법만 수정 (exception 변환은 하지 않음)
    content = content.replace("throw new UxbException(e.getMessage());", "throw new UxbException(e);")
    
    # 1.5단계: 변환 과정에서 생긴 괄호 문제 후처리
    content = content.replace("throw new UxbException(e));", "throw new UxbException(e);")
    content = content.replace("throw new UxbException(e))", "throw new UxbException(e);")
    
    # 2단계: 실제 중복 패턴들을 직접 replace로 제거
    duplicate_patterns = [
        # VesselCode에서 발견된 실제 패턴 (83-86줄)
        "\t\t} catch (Exception e){\n\t\t\tthrow new UxbException(e);\n\t\t} catch (Exception e){\n\t\t\tthrow new UxbException(e);",
        
        # 첫 번째 중복 (142-146줄)
        "\t\t} catch (Exception e) {\n\t\t\tthrow new UxbException(e);\n\t\t} catch (Exception e) {\n\t\t\tthrow new UxbException(e);\n\t\t}",
        
        # 두 번째 중복 (173-177줄)  
        "\t\t} catch (Exception e) {\n\t\t\tthrow new UxbException(e);\n\t\t} catch (Exception e) {\n\t\t\tthrow new UxbException(e);\n\t\t}",
        
        # 세 번째 중복 (201-205줄)
        "\t\t} catch (Exception e) {\n\t\t\tthrow new UxbException(e);\n\t\t} catch (Exception e) {\n\t\t\tthrow new UxbException(e);\n\t\t}",
        
        # 일반적인 중복 패턴들
        "\t\t} catch (Exception e) {\n\t\t\tthrow new UxbException(e);\n\t\t} catch (Exception e) {\n\t\t\tthrow new UxbException(e);",
        "} catch (Exception e) {\n\t\t\tthrow new UxbException(e);\n\t\t} catch (Exception e) {\n\t\t\tthrow new UxbException(e);",
        "\t} catch (Exception e) {\n\t\tthrow new UxbException(e);\n\t} catch (Exception e) {\n\t\tthrow new UxbException(e);",
    ]
    
    # 대응하는 단일 패턴들
    single_patterns = [
        "\t\t} catch (Exception e){\n\t\t\tthrow new UxbException(e);",
        "\t\t} catch (Exception e) {\n\t\t\tthrow new UxbException(e);\n\t\t}",
        "\t\t} catch (Exception e) {\n\t\t\tthrow new UxbException(e);\n\t\t}",
        "\t\t} catch (Exception e) {\n\t\t\tthrow new UxbException(e);\n\t\t}",
        "\t\t} catch (Exception e) {\n\t\t\tthrow new UxbException(e);",
        "} catch (Exception e) {\n\t\t\tthrow new UxbException(e);",
        "\t} catch (Exception e) {\n\t\tthrow new UxbException(e);",
    ]
    
    # 3단계: 모든 중복 패턴을 제거할 때까지 반복
    for i, pattern in enumerate(duplicate_patterns):
        while pattern in content:
            content = content.replace(pattern, single_patterns[i])
            removed_count += 1
            print(f"   ✓ 중복 catch 블록 제거: 패턴 {i+1}")
    
    # 변경 사항 확인
    if content != original_content:
        print(f"🧹 {removed_count}개 중복 catch 블록 제거 완료! (throw 문법: e.getMessage() -> e)")
    else:
        print("🧹 제거할 중복 catch 블록이 없습니다.")
    
    return content

def clean_all_imports_once(content):
    """모든 import 관련 처리를 한번에"""
    
    # 특정 패키지 경로 교체 (삭제하기 전에 먼저 교체)
    # business는 제거, common은 유지
    content = re.sub(r'^import\s+com\.stx\.som\.business\.', 'import kr.co.panocean.', content, flags=re.MULTILINE)
    content = re.sub(r'^import\s+com\.stx\.som\.common\.', 'import kr.co.panocean.common.', content, flags=re.MULTILINE)

    # import kr.co.panocean.common.exception.STXException; 제거  
    content = re.sub(r'^import\s+kr\.co\.panocean\.common\.exception\.STXException;\s*\n', '', content, flags=re.MULTILINE)

    # import kr.co.panocean.common.utility.UserBean; 제거
    content = re.sub(r'^import\s+kr\.co\.panocean\.common\.utility\.UserBean;\s*\n', '', content, flags=re.MULTILINE)

    # private Logger log = Logger.getLogger(this.getClass()); 제거
    content = re.sub(r'^\s*private\s+Logger\s+log\s*=\s*Logger\.getLogger\(this\.getClass\(\)\);\s*\n?', '', content, flags=re.MULTILINE)
    

    
    # 기존 import 제거 (패턴 한번에) - 이미 교체된 것은 제외됨
    content = re.sub(r'^import\s+com\.stx\.som\..*?;\s*\n', '', content, flags=re.MULTILINE)
    content = re.sub(r'^import\s+kr\.co\.takeit\..*?;\s*\n', '', content, flags=re.MULTILINE)
    content = re.sub(r'^import\s+com\.infohandling\..*?;\s*\n', '', content, flags=re.MULTILINE)
    
    # 새로운 import 추가 (한번에 전체 블록으로)
    new_imports = """import kr.co.panocean.common.utility.CommonDao;
import kr.co.takeit.dataset.DataSetRowStatus;
import kr.co.takeit.exception.UxbException;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Repository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.sql.Time;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Hashtable;
import java.util.Iterator;
import java.util.Map;
"""
    
    # 패키지 선언 후에 import 블록 삽입
    package_pattern = r'(package\s+[\w\.]+;\s*\n)'
    if re.search(package_pattern, content):
        content = re.sub(package_pattern, r'\1\n' + new_imports + '\n', content)
    
    return content

def convert_all_exceptions_once(content):
    """모든 exception 관련 처리를 한번에 (JavaDoc 보호)"""
    
    # throws 절 통일 (JavaDoc이 끝난 후 메서드 시그니처만 대상으로)
    # /** ... */ 다음에 오는 public 메서드만 대상
    content = re.sub(r'(\*/\s*\n\s*public\s+\w+\s+\w+\s*\([^)]*\)\s+throws\s+)\w*Exception(\s*\{)', 
                    r'\1UxbException\2', content)
    
    # throws STXException, SQLException -> throws UxbException 으로 변환
    content = re.sub(
        r'(\*/\s*\n\s*public\s+\w+\s+\w+\s*\([^)]*\)\s+throws\s+)(STXException\s*,\s*SQLException|SQLException\s*,\s*STXException)(\s*\{)',
        r'\1UxbException\3',
        content
    )

    # throws 절에서 STXException을 UxbException으로 변환 (파라미터 타입이 ArrayList 등인 경우도 포함)
    content = re.sub(
        r'(public\s+\w+\s+\w+\s*\([^\)]*\)\s+throws\s+)STXException(\s*\{)',
        r'\1UxbException\2',
        content
    )

    # log.error(e); -> log.error(e.getMessage()); 변환
    content = re.sub(r'log\.error\s*\(\s*e\s*\)\s*;', 'log.error(e.getMessage());', content)

    # 모든 throws 절을 UxbException으로 통일 (여러 Exception이 콤마로 나열된 경우 포함)
    # 간단하고 확실한 방법: throws 뒤부터 { 앞까지 모든 내용을 UxbException으로 대체
    content = re.sub(
        r'(public\s+\w+\s+\w+\s*\([^\)]*\)\s+throws\s+)[^{]+(\s*\{)',
        r'\1UxbException\2',
        content
    )

    
    # catch 블록 통일 (한번에)
    content = re.sub(r'catch\s*\(\s*\w*Exception\s+(\w+)\s*\)', r'catch (Exception \1)', content)
    
    # throw new Exception 통일 (UxbException 제외하고 변환) - 순차적으로 정확히 매칭
    # 1단계: 가장 구체적인 e.getMessage() 패턴 먼저 변환  
    content = re.sub(r'throw\s+new\s+(?!UxbException)(\w+Exception)\s*\(\s*e\.getMessage\(\)\s*\)\s*;', 'throw new UxbException(e);', content)
    # 2단계: 기본 Exception(e) 패턴 변환
    content = re.sub(r'throw\s+new\s+(?!UxbException)(\w+Exception)\s*\(\s*e\s*\)\s*;', 'throw new UxbException(e);', content)
    # 3단계: 문자열 매개변수가 있는 Exception 패턴 변환 (에러 코드 보존)
    content = re.sub(r'throw\s+new\s+(?!UxbException)(\w+Exception)\s*\(([^;)]+)\)\s*;', r'throw new UxbException(\2);', content)

    
    # catch (Exception e) { throw e; } 패턴 제거
    content = re.sub(
        r'catch\s*\(\s*Exception\s+e\s*\)\s*\{\s*throw\s+e;\s*\}',
        ' ',
        content
    )
    return content

def remove_ejb_legacy_once(content):
    """EJB 레거시 코드를 한번에 제거"""
    
    # 먼저 conn 매개변수 제거 (특별한 처리)
    # DAO 메소드 호출에서 conn 매개변수 제거
    before_conn_removal = content.count('conn,')
    content = re.sub(r'(\w+)\.(\w+)\(conn,\s*([^)]+)\)', r'\1.\2(\3)', content)
    after_conn_removal = content.count('conn,')
    print(f"🔧 conn 매개변수 제거: {before_conn_removal} -> {after_conn_removal}")
    
    # 대입문에서도 conn 매개변수 제거
    content = re.sub(r'=\s*(\w+)\.(\w+)\(conn,\s*([^)]+)\)', r'= \1.\2(\3)', content)

    # 단일 매개변수로서의 conn 제거 추가        
    before_one_conn = content.count('(conn)')
    content = re.sub(r'\(conn\)', r'()', content)
    after_one_conn = content.count('(conn)')
    print(f"🔧 단일 conn 매개변수 제거: {before_one_conn} -> {after_one_conn}")
    
    
    # 마지막 매개변수로서의 conn 제거 추가
    before_last_conn = content.count(', conn)')
    content = re.sub(r',\s*conn\s*(\))', r'\1', content)
    after_last_conn = content.count(', conn)')
    print(f"🔧 마지막 conn 매개변수 제거: {before_last_conn} -> {after_last_conn}")

    #  DAO 메소드 호출에서 userBean 매개변수 제거
    before_userbean_removal = content.count('userBean,')
    content = re.sub(r'(\w+)\.(\w+)\(userBean,\s*([^)]+)\)', r'\1.\2(\3)', content)
    after_userbean_removal = content.count('userBean,')
    print(f"🔧 userBean 매개변수 제거: {before_userbean_removal} -> {after_userbean_removal}")

    # 단일 매개변수로서의 userBean 제거 추가
    before_one_userbean = content.count('(userBean)')
    content = re.sub(r'\(userBean\)', r'()', content)
    after_one_userbean = content.count('(userBean)')
    print(f"🔧 단일 userBean 매개변수 제거: {before_one_userbean} -> {after_one_userbean}")

    # 마지막 매개변수로서의 userBean 제거 추가
    before_last_userbean = content.count(', userBean)')
    content = re.sub(r',\s*userBean\s*(\))', r'\1', content)
    after_last_userbean = content.count(', userBean)')
    print(f"🔧 마지막 userBean 매개변수 제거: {before_last_userbean} -> {after_last_userbean}")

    # 중간 매개변수로서의 userBean 제거 추가
    content = re.sub(r',\s*userBean\s*,\s*', r', ', content)
    print(f"🔧 중간 userBean 매개변수 제거 완료!")
    
    # userBean 메서드 호출을 안전한 값으로 대체 (log.debug 등에서 사용되는 경우)
    print("🔧 userBean 메서드 호출을 안전한 값으로 대체 중...")
    content = re.sub(r'userBean\.getEmp_no\(\)', '"DEFAULT_USER"', content)
    content = re.sub(r'userBean\.getUser_id\(\)', '"DEFAULT_USER"', content)
    content = re.sub(r'userBean\.getUser_name\(\)', '"DEFAULT_USER"', content)
    content = re.sub(r'userBean\.getDept_cd\(\)', '"DEFAULT_DEPT"', content)
    content = re.sub(r'userBean\.getUser_id\(\)\.concat\("@panocean\.com"\)', '"DEFAULT_USER@panocean.com"', content)
    # 일반적인 userBean.메서드() 패턴을 안전한 기본값으로 대체
    content = re.sub(r'userBean\.\w+\(\)', '"DEFAULT_VALUE"', content)
    print("🔧 userBean 메서드 호출 대체 완료!")

    
    # 메서드 시그니처에서 Connection conn 매개변수 제거 (간단한 패턴)
    print("🔧 메서드 시그니처에서 Connection conn 제거 중...")
    
    # Connection conn 매개변수 제거 (모든 위치 처리)
    before_method_params = content.count('Connection conn')
    
    # Connection conn이 마지막 매개변수인 경우
    content = re.sub(r',\s*Connection\s+conn\s*(\)\s+throws)', r'\1', content)
    # Connection conn이 단일 매개변수인 경우
    content = re.sub(r'\(Connection\s+conn\)', r'()', content)
    # Connection conn이 첫 번째 매개변수인 경우
    content = re.sub(r'(\(\s*)Connection\s+conn,\s*', r'\1', content)
    # Connection conn이 중간 매개변수인 경우 (가장 중요한 추가!)
    content = re.sub(r',\s*Connection\s+conn,\s*', r', ', content)
    
    after_method_params = content.count('Connection conn')
    print(f"   전체 Connection conn 매개변수 제거: {before_method_params} -> {after_method_params}")


    # 메서드 시그니처에서 UserBean userBean 매개변수 제거 (간단한 패턴)
    print("🔧 메서드 시그니처에서 UserBean userBean 제거 중...")
    
    # UserBean userBean 매개변수 제거 (모든 위치 처리)
    before_method_params = content.count('UserBean userBean')
    
    # UserBean userBean이 마지막 매개변수인 경우
    content = re.sub(r',\s*UserBean\s+userBean\s*(\)\s+throws)', r'\1', content)
    # UserBean userBean이 마지막 매개변수인 경우 2
    content = re.sub(r',\s*UserBean\s+userBean*(\)\s+throws)', r'\1', content)
    # UserBean userBean이 단일 매개변수인 경우
    content = re.sub(r'\(UserBean\s+userBean\)', r'()', content)
    # UserBean userBean이 첫 번째 매개변수인 경우
    content = re.sub(r'(\(\s*)UserBean\s+userBean,\s*', r'\1', content)
    # UserBean userBean이 중간 매개변수인 경우 (가장 중요한 추가!)
    content = re.sub(r',\s*UserBean\s+userBean,\s*', r', ', content)
    
    after_method_params = content.count('UserBean userBean')
    print(f" 전체 UserBean userBean 매개변수 제거: {before_method_params} -> {after_method_params}")

    

    
    
    
    
    # EJB 관련 패턴들을 안전하게 제거 (return문과 메서드 닫는 중괄호 보호)
    
    # 1단계: 안전한 변수 선언 제거
    safe_variable_patterns = [
        # Connection 관련 변수 선언 (라인 단위로 안전하게)
        r'^\s*Connection\s+conn\s*=\s*null;\s*$',
        r'^\s*Connection\s+\w+\s*=\s*null;\s*$',
        
        # PreparedStatement 관련 변수 선언
        r'^\s*PreparedStatement\s+pstmt\s*=\s*null;\s*$',
        r'^\s*PreparedStatement\s+\w+\s*=\s*null;\s*$',
        
        # ResultSet 관련 변수 선언
        r'^\s*ResultSet\s+rs\s*=\s*null;\s*$',
        r'^\s*ResultSet\s+\w+\s*=\s*null;\s*$',
        
        # UserBean 관련 변수 선언2
        r'^\s*UserBean\s+\w+\s*=\s*[^;]+;\s*$',
        r'^\s*UserBean\s+userBean\s*=\s*[^;]+;\s*$',
    ]
    
    for pattern in safe_variable_patterns:
        content = re.sub(pattern, '', content, flags=re.MULTILINE)
    
    # 2단계: 안전한 대입문 제거 (세미콜론으로 끝나는 라인만)
    safe_assignment_patterns = [
        r'^\s*conn\s*=\s*[^;]+;\s*$',
        r'^\s*pstmt\s*=\s*conn\.prepareStatement[^;]+;\s*$',
        r'^\s*rs\s*=\s*pstmt\.executeQuery\(\);\s*$',
        r'^\s*userBean\s*=\s*[^;]+;\s*$',
    ]
    
    for pattern in safe_assignment_patterns:
        content = re.sub(pattern, '', content, flags=re.MULTILINE)
    
    # 3단계: 안전한 메서드 호출 제거 (특정 패턴만)
    safe_method_patterns = [
        r'^\s*\w+\.getConnection\(\);\s*$',
        r'^\s*conn\.close\(\);\s*$',
        r'^\s*pstmt\.close\(\);\s*$',
        r'^\s*rs\.close\(\);\s*$',
    ]
    
    for pattern in safe_method_patterns:
        content = re.sub(pattern, '', content, flags=re.MULTILINE)
    
    # 4단계: 안전한 if문 제거 (null 체크만)
    safe_if_patterns = [
        r'^\s*if\s*\(\s*conn\s*!=\s*null\s*\)\s*\{\s*conn\.close\(\);\s*\}\s*$',
        r'^\s*if\s*\(\s*pstmt\s*!=\s*null\s*\)\s*\{\s*pstmt\.close\(\);\s*\}\s*$',
        r'^\s*if\s*\(\s*rs\s*!=\s*null\s*\)\s*\{\s*rs\.close\(\);\s*\}\s*$',
    ]
    
    for pattern in safe_if_patterns:
        content = re.sub(pattern, '', content, flags=re.MULTILINE)
    
    # 5단계: finally 블록만 안전하게 제거 (return문이 없는 경우만)
    # finally 블록을 찾아서 return문이 없으면 제거
    lines = content.split('\n')
    in_finally = False
    finally_start = -1
    brace_count = 0
    finally_lines = []
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        # finally 블록 시작 감지
        if 'finally' in stripped and '{' in stripped:
            in_finally = True
            finally_start = i
            brace_count = stripped.count('{') - stripped.count('}')
            finally_lines = [i]
            continue
            
        if in_finally:
            finally_lines.append(i)
            brace_count += stripped.count('{') - stripped.count('}')
            
            # finally 블록 내용에 return이 있으면 보존
            if 'return' in stripped:
                in_finally = False
                finally_lines = []
                continue
                
            # finally 블록 끝
            if brace_count <= 0:
                # return문이 없는 finally 블록만 제거
                finally_content = '\n'.join([lines[j] for j in finally_lines])
                if 'return' not in finally_content:
                    # finally 블록 제거
                    for j in reversed(finally_lines):
                        if j < len(lines):
                            lines[j] = ''
                            
                in_finally = False
                finally_lines = []
    
    content = '\n'.join(lines)
    
    # 6단계: 빈 줄 정리
    content = re.sub(r'\n\s*\n\s*\n', '\n\n', content)
    
    return content



def remove_duplicate_dependency_fields_optimized(content):
    """의존성 필드 중복 제거 최적화 버전 - 완전 재작성"""
    
    # 1. 모든 private final 필드를 추출
    field_pattern = r'^\s*private\s+final\s+(\w+)\s+(\w+);\s*$'
    all_fields = re.findall(field_pattern, content, re.MULTILINE)
    
    if not all_fields:
        print("💉 제거할 중복 의존성 필드가 없습니다.")
        return content
    
    # 2. 타입별로 첫 번째 필드만 유지
    seen_types = {}
    unique_fields = []
    removed_count = 0
    
    for field_type, field_name in all_fields:
        if field_type not in seen_types:
            seen_types[field_type] = field_name
            unique_fields.append((field_type, field_name))
            print(f"   ✓ 유지된 필드: {field_type} {field_name}")
        else:
            removed_count += 1
            print(f"   ✗ 중복 제거: {field_type} {field_name}")
    
    # 3. 기존 모든 private final 필드 제거
    content = re.sub(field_pattern, '', content, flags=re.MULTILINE)
    
    # 4. 클래스 선언 후에 유니크한 필드들만 다시 삽입
    class_pattern = r'(public class \w+\s*\{)'
    if re.search(class_pattern, content):
        dependency_block = ""
        for field_type, field_name in unique_fields:
            dependency_block += f"    private final {field_type} {field_name};\n"
        
        replacement = r'\1' + '\n' + dependency_block
        content = re.sub(class_pattern, replacement, content, count=1)
    print(f"💉 {removed_count}개 중복 의존성 필드 제거 완료! (타입 기준)")
    return content

def remove_duplicate_annotations_optimized(content):
    """어노테이션 중복 제거 최적화 버전"""
    
    annotations = ['@Slf4j', '@RequiredArgsConstructor', '@Component']
    
    for annotation in annotations:
        # 해당 어노테이션이 여러 번 나타나는지 확인
        matches = list(re.finditer(rf'^{annotation}\s*$', content, re.MULTILINE))
        
        if len(matches) > 1:
            print(f"   중복 어노테이션 제거: {annotation}")
            # 첫 번째를 제외한 나머지 제거
            for match in reversed(matches[1:]):
                start, end = match.span()
                content = content[:start] + content[end+1:]  # 개행문자도 제거
    
    print(f"🏷️ {len([a for a in annotations if len(re.findall(rf'^{a}\s*$', content, re.MULTILINE)) > 1])}개 중복 어노테이션 제거 완료!")
    
    return content

def format_code_once(content):
    """모든 포맷팅을 한번에 처리"""
    
    # JavaDoc에서 @throws STXException을 @throws UxbException으로 변경 (안전한 패턴)
    # JavaDoc 내부에서만 변경하도록 제한
    content = re.sub(r'(/\*\*[^*]*\*(?:[^*/][^*]*\*+)*/).*?(@throws\s+)STXException', 
                    lambda m: m.group(0).replace('STXException', 'UxbException'), content, flags=re.DOTALL)
    
    # 메서드 시그니처에서만 throws 절 변경 (JavaDoc 영역 제외)
    # JavaDoc이 끝나고 나서의 메서드 시그니처만 대상으로 함
    content = re.sub(r'(\*/\s*\n\s*public\s+\w+\s+\w+\s*\([^)]*\)\s+throws\s+)\w*Exception(\s*\{)', 
                    r'\1UxbException\2', content)
    
    # 빈 줄 정리 (과도한 빈 줄 제거)
    content = re.sub(r'\n\s*\n\s*\n', '\n\n', content)
    
    # 🔧 최종 throws 절 정리 (모든 변환 이후)
    content = re.sub(r'throws\s+UxbException,\s*Exception', 'throws UxbException', content)
    content = re.sub(r'throws\s+Exception,\s*UxbException', 'throws UxbException', content)
    content = re.sub(r'throws\s+UxbException,\s*Exception\s*\)\s+throws\s+UxbException', 'throws UxbException', content)
    
    return content

def refactor_java_file_optimized(content):
    """최적화된 Java 파일 변환 메인 함수"""
    
    print("    - 통합 최적화 변환 시작...")
    
    # 원본 클래스명 추출
    class_match = re.search(r'public class (\w+)', content)
    if not class_match:
        print("    ❌ 클래스명을 찾을 수 없습니다.")
        return content
    
    original_class_name = class_match.group(1)
    
    # Bean 파일 여부 확인
    is_bean_file = original_class_name.endswith('Bean')
    
    if is_bean_file:
        # Bean 파일: Bean 제거하고 Service 추가
        new_class_name = original_class_name[:-4] + 'Service'
        target_package = 'service'
    else:
        # 일반 파일: 이름 유지
        new_class_name = original_class_name
        target_package = 'function'
    
    print(f"    - 변환: {original_class_name} -> {new_class_name} ({'Bean->Service' if is_bean_file else '일반 파일'})")
    
    # 🚀 통합 변환 실행 (한번에 모든 처리)
    content = unified_java_conversion(content)
    
    # 의존성 감지 및 변수 매핑 추출 (중복 제거 포함)
    content, dependencies, variable_mappings = detect_dependencies_optimized(content, new_class_name)
    
    # 변수 매핑 적용 (new DAO() 제거 포함)
    if variable_mappings:
        print("    - 변수 매핑 적용 중...")
        print(f"🔍 변수 매핑 전 new DAO() 개수: {len(re.findall(r'new\s+\w+DAO\(\)', content))}")
        content = apply_variable_mapping_to_content(content, variable_mappings)
        print(f"🔍 변수 매핑 후 new DAO() 개수: {len(re.findall(r'new\s+\w+DAO\(\)', content))}")
    
    # Spring 어노테이션 및 중복 제거된 의존성 필드 추가
    content = add_spring_annotations_optimized(content, new_class_name, dependencies, is_bean_file)
    
    # 클래스명 변경
    content = re.sub(rf'public class {original_class_name}', f'public class {new_class_name}', content)
    
    # 패키지명 변경
    if is_bean_file:
        content = re.sub(r'package com\.stx\.som\.business\.(service|function)\.standardInfo;', 
                        'package kr.co.panocean.service.standardInfo;', content)
    else:
        content = re.sub(r'package com\.stx\.som\.business\.(service|function)\.standardInfo;', 
                        'package kr.co.panocean.function.standardInfo;', content)
    
    print("    ✅ 통합 최적화 변환 완료!")
    
    return content

def detect_dependencies_optimized(content, class_name):
    """의존성 감지 최적화 버전 - 중복 제거된 의존성만 반환"""
    
    # CommonDao 메서드 목록 정의 (apply_variable_mapping_to_content와 동일)
    common_dao_methods = [
        # 기본 CRUD 메서드들 (6개)
        'defaultVoObjSysValue', 'defaultSelect', 'defaultSearch', 'defaultInsert', 
        'defaultUpdate', 'defaultDelete',
        
        # 유틸리티 메서드들 (4개)
        'getMaxFieldSeq', 'getMaxFieldSeq2', 'chkCodeMaster', 'getMathDur',
        
        # 기본 조회 메서드들 (7개)
        'inquiryMagam', 'inquiryMagamNew', 'cbMagam', 'inquiryBackup', 'inquiryBackupNew',
        'getUserGroupTeamTotis', 'searchExchangeList',
        
        # OVA/메일 관련 메서드들 (2개)
        'ovaMailList', 'scb_voyage_anal_ag_mail_newprcCall',
        
        # 정기/성과 관련 메서드들 (12개)
        'searchPeriodicalList', 'cbSummaryPeriodicalList', 'cbSummaryPeriodicalSummary',
        'cbSummaryPeriodicalListRawData', 'searchPeriodicalDifferenceList', 'searchEisPeriodicalList',
        'searchPeriodicalBgtList', 'searchPeriodicalTotisList', 'inquiryMagamList',
        'inquiryMagamListNew', 'inquiryCbMagamList', 'inquiryCbMagamCommExp',
        
        # 백업 관련 메서드들 (4개)
        'inquiryBackupList', 'inquiryBackupListNew', 'inquiryBackupSmryList', 'inquiryBackupSmryListNew',
        
        # CB/선박 관련 메서드들 (6개)
        'cbCargoQtySearch', 'getCbDeleteList', 'getModelCb', 'getCbVslVoyInfo', 'getCbVslVoyInfo2',
        'searchEisVslVoyCbSmryList', 'getMultiData',
        
        # ⭐ DBWrap 위임 메서드들 (28개) - 새로 추가 필요!
        'getObject', 'getObjects', 'setObject',
        'getInt', 'getLong', 'getString', 'getDouble',
        'getHashtable', 'isExist', 'updateQuery', 'getObjectCstmt'
    ]
    
    # 제외할 클래스들 (Java 기본 클래스, VO/DTO, 유틸리티 클래스 등)
    excluded_classes = {
        'ArrayList', 'HashMap', 'HashSet', 'Vector', 'LinkedList', 'TreeMap', 'TreeSet',
        'List', 'Map', 'Set', 'Collection', 'Iterator', 'Enumeration',
        'String', 'StringBuilder', 'StringBuffer', 'Object', 'Class',
        'Date', 'Calendar', 'SimpleDateFormat', 'Timestamp',
        'Collections', 'Arrays', 'Properties', 'ResourceBundle',
        'Integer', 'Long', 'Double', 'Float', 'Boolean', 'Character',
        'Exception', 'RuntimeException', 'TakeBizException', 'UxbException',
        'CCDVslCodeMVO', 'CCDVslCodeMDTO', 'StringBuilder',  # VesselCode 전용 제외 항목
        # 추가 VO/DTO 패턴들
        'CCDVslCodeGenDTO', 'SCBVslVoyMDTO', 'CCDOperVslHistoryMDTO', 
        'CCDOperVslStateMDTO', 'CCDOtherAreaRepairMDTO', 'CCDUsedVslMstSDTO',
        'CCDVslCodeSearchDTO', 'CCDVslCrewEmbarkMDTO', 'OWNVslDryScheduleMDTO',
        'CBDVslSpdBnkMDTO', 'CCDVslCiiEstimateMDTO'
    }
    
    # 1. 변수 매핑 추출 (필터링된 것만)
    variable_mappings = extract_filtered_variable_mapping(content, excluded_classes)
    
    # 2. CommonDao 메서드 사용 감지
    uses_common_dao = False
    for method in common_dao_methods:
        pattern = rf'\w+\.{re.escape(method)}\s*\('
        if re.search(pattern, content):
            uses_common_dao = True
            print(f"  ✓ CommonDao 메서드 사용 감지: {method}")
            break
    
    # 3. 변수 매핑에서 추출된 의존성 수집
    dependencies_dict = {}
    for old_var, mapping_info in variable_mappings.items():
        class_name_var = mapping_info['class_name']
        standard_var = mapping_info['standard_var']
        
        # 제외 대상이 아닌 경우만 추가 (타입 기준으로 중복 제거)
        if class_name_var not in excluded_classes:
            if class_name_var not in dependencies_dict:
                dependencies_dict[class_name_var] = standard_var
                print(f"  ✓ 유니크 의존성 추가: {class_name_var} {standard_var}")
            else:
                print(f"  ✗ 중복 타입 제거: {class_name_var} {standard_var}")
    
    # 4. CommonDao 의존성 추가 (사용하는 경우)
    if uses_common_dao:
        dependencies_dict['CommonDao'] = 'commonDao'
        print(f"  ✓ CommonDao 의존성 추가: CommonDao commonDao")
    
    # 5. 의존성 리스트 생성 (타입별로 하나씩만)
    dependencies = []
    for dep_type, dep_name in dependencies_dict.items():
        dependencies.append(f"{dep_type} {dep_name}")
    
    print(f"💉 최종 의존성 목록: {len(dependencies)}개")
    for dep in dependencies:
        print(f"     {dep}")
    
    return content, dependencies, variable_mappings

def extract_filtered_variable_mapping(content, excluded_classes):
    """필터링된 변수 매핑 추출 - 의존성 주입이 필요한 것만"""
    variable_mappings = {}
    # new 선언 패턴 찾기: CCDVslCodeMDAO ccdVslCodeMDAO = new CCDVslCodeMDAO();
    new_declarations = re.findall(r'(\w+)\s+(\w+)\s*=\s*new\s+(\w+)\(\)', content)
    for class_name, var_name, constructor_class in new_declarations:
        if class_name == constructor_class:
            # 1. 기본 제외 클래스 체크
            if class_name in excluded_classes:
                print(f"  ✗ 제외된 변수 매핑: {class_name} (제외 대상)")
                continue
            
            # 2. VO/DTO 패턴 체크 (끝나는 패턴과 포함하는 패턴 모두)
            if (class_name.endswith('VO') or class_name.endswith('DTO') or 
                class_name.endswith('Bean') or class_name.endswith('Entity') or
                'VO' in class_name or 'DTO' in class_name):
                print(f"  ✗ 제외된 변수 매핑: {class_name} (VO/DTO/Bean/Entity 패턴)")
                continue
                
            usage_patterns = re.findall(rf'{re.escape(var_name)}\.(\w+)', content)
            if usage_patterns:
                if class_name.endswith('DAO'):
                    standard_var = class_name[0].lower() + class_name[1:].replace('DAO', 'Dao')
                else:
                    standard_var = class_name[0].lower() + class_name[1:]
                variable_mappings[var_name] = {
                    'class_name': class_name,
                    'standard_var': standard_var,
                    'usage_count': len(usage_patterns)
                }
                print(f"  ✓ 필터링된 변수 매핑: {class_name} {var_name} -> {standard_var} (사용 {len(usage_patterns)}회)")
    return variable_mappings

def apply_variable_mapping_to_content(content, variable_mappings):
    """변수 매핑을 적용하여 콘텐츠의 변수 사용을 수정 - DAO만 제거하고 VO/DTO는 보존"""
    
    # CommonDao 메서드 목록 정의 - 실제 CommonDao.java에서 추출한 메서드들
    common_dao_methods = [
        # 기본 CRUD 메서드들 (6개)
        'defaultVoObjSysValue', 'defaultSelect', 'defaultSearch', 'defaultInsert', 
        'defaultUpdate', 'defaultDelete',
        
        # 유틸리티 메서드들 (4개)
        'getMaxFieldSeq', 'getMaxFieldSeq2', 'chkCodeMaster', 'getMathDur',
        
        # 기본 조회 메서드들 (7개)
        'inquiryMagam', 'inquiryMagamNew', 'cbMagam', 'inquiryBackup', 'inquiryBackupNew',
        'getUserGroupTeamTotis', 'searchExchangeList',
        
        # OVA/메일 관련 메서드들 (2개)
        'ovaMailList', 'scb_voyage_anal_ag_mail_newprcCall',
        
        # 정기/성과 관련 메서드들 (12개)
        'searchPeriodicalList', 'cbSummaryPeriodicalList', 'cbSummaryPeriodicalSummary',
        'cbSummaryPeriodicalListRawData', 'searchPeriodicalDifferenceList', 'searchEisPeriodicalList',
        'searchPeriodicalBgtList', 'searchPeriodicalTotisList', 'inquiryMagamList',
        'inquiryMagamListNew', 'inquiryCbMagamList', 'inquiryCbMagamCommExp',
        
        # 백업 관련 메서드들 (4개)
        'inquiryBackupList', 'inquiryBackupListNew', 'inquiryBackupSmryList', 'inquiryBackupSmryListNew',
        
        # CB/선박 관련 메서드들 (6개)
        'cbCargoQtySearch', 'getCbDeleteList', 'getModelCb', 'getCbVslVoyInfo', 'getCbVslVoyInfo2',
        'searchEisVslVoyCbSmryList', 'getMultiData',
        
        # ⭐ DBWrap 위임 메서드들 (28개) - 새로 추가 필요!
        'getObject', 'getObjects', 'setObject',
        'getInt', 'getLong', 'getString', 'getDouble',
        'getHashtable', 'isExist', 'updateQuery', 'getObjectCstmt'
    ]
    
    # 1. 의존성으로 추가된 모든 클래스의 new 인스턴스 생성 라인 제거 (DAO뿐만 아니라 모든 의존성)
    # 변수 매핑에 포함된 모든 클래스명 추출
    dependency_classes = set()
    for mapping_info in variable_mappings.values():
        dependency_classes.add(mapping_info['class_name'])
    
    print(f"  🔍 의존성으로 관리될 클래스들: {dependency_classes}")
    
    # 의존성 클래스들의 new 선언 제거 (DAO뿐만 아니라 모든 의존성 클래스)
    total_removed = 0
    for class_name in dependency_classes:
        # 각 클래스별로 new 선언 패턴 제거
        dependency_new_patterns = [
            rf'^\s*{re.escape(class_name)}\s+(\w+)\s*=\s*new\s+{re.escape(class_name)}\(\)\s*;\s*$',  # 기본 패턴
            rf'^\s*/[/*]?\s*{re.escape(class_name)}\s+(\w+)\s*=\s*new\s+{re.escape(class_name)}\(\)\s*;\s*$',  # 주석처리된 것
            rf'^\s*{re.escape(class_name)}\s+(\w+)\s*=\s*new\s+{re.escape(class_name)}\(\)\s*;.*$',  # 뒤에 주석이 있는 것
        ]
        
        for pattern in dependency_new_patterns:
            matches = re.findall(pattern, content, re.MULTILINE)
            before_count = len(matches)
            content = re.sub(pattern, '', content, flags=re.MULTILINE)
            if before_count > 0:
                total_removed += before_count
                print(f"    ✓ {class_name} new 선언 제거: {before_count}개")
    
    if total_removed > 0:
        print(f"  ✅ 총 new 의존성 선언 제거: {total_removed}개 (DAO 및 모든 의존성 클래스)")
    else:
        print(f"  ℹ️ 제거할 new 의존성 선언이 없습니다.")

    # 2. 메서드 내부의 모든 DAO 변수 사용을 표준화된 단일 변수로 교체
    lines = content.split('\n')
    for i, line in enumerate(lines):
        # import, package, 주석, 클래스 선언 라인은 건너뛰기
        stripped_line = line.strip()
        if (stripped_line.startswith(('import ', 'package ', '//', '/*', '*', '*/')) or 
            'class' in stripped_line or 'private final' in stripped_line):
            continue
        
        # 3. CommonDao 메서드 사용 감지 및 변수명을 commonDao로 변경
        for method in common_dao_methods:
            # 패턴: 변수명.메서드명( 형태를 찾아서 commonDao.메서드명( 으로 변경
            pattern = rf'(\w+)\.{re.escape(method)}\s*\('
            if re.search(pattern, line):
                line = re.sub(pattern, rf'commonDao.{method}(', line)
                print(f"  🔄 CommonDao 메서드 감지: {method} -> commonDao.{method}")
            
        for old_var, mapping_info in variable_mappings.items():
            new_var = mapping_info['standard_var']
            # 단어 경계(\b)를 사용하여 정확한 변수명만 치환
            if old_var in line:
                line = re.sub(rf'\b{re.escape(old_var)}\b', new_var, line)
        lines[i] = line

    content = '\n'.join(lines)
    
    # 3. 추가 정리: 혹시 남은 의존성 클래스의 new 패턴들 제거
    for class_name in dependency_classes:
        pattern = rf'new\s+{re.escape(class_name)}\(\)'
        if re.search(pattern, content):
            content = re.sub(pattern, f'null /* removed new {class_name}() */', content)
            print(f"    🧹 남은 new {class_name}() 패턴 제거 완료")
    
    for old_var, mapping_info in variable_mappings.items():
        new_var = mapping_info['standard_var']
        print(f"  ✓ 변수 사용 변경: {old_var} -> {new_var}")
        
    return content

def add_spring_annotations_optimized(content, class_name, dependencies, is_bean_file):
    """Spring 어노테이션 추가 최적화 버전 - 모든 기존 필드 완전 제거"""
    
    # 기존 어노테이션들 먼저 제거
    content = re.sub(r'^@Slf4j\s*\n', '', content, flags=re.MULTILINE)
    content = re.sub(r'^@RequiredArgsConstructor\s*\n', '', content, flags=re.MULTILINE)
    content = re.sub(r'^@Component\s*\n', '', content, flags=re.MULTILINE)
    
    # 🔥 더 강력한 접근: regex로 직접 제거
    print("  🔍 기존 private final 필드 제거 시작...")
    field_pattern = r'^\s*private\s+final\s+\w+\s+\w+;\s*\n'
    
    # 제거 전 카운트
    before_count = len(re.findall(field_pattern, content, re.MULTILINE))
    print(f"  📊 제거 전 private final 필드: {before_count}개")
    
    # 제거 실행
    content = re.sub(field_pattern, '', content, flags=re.MULTILINE)
    
    # 제거 후 카운트
    after_count = len(re.findall(field_pattern, content, re.MULTILINE))
    print(f"  📊 제거 후 private final 필드: {after_count}개")
    print(f"  🗑️ 총 {before_count - after_count}개 필드 제거 완료!")

    # 의존성 주입 필드 블록 생성 (이미 중복이 제거된 dependencies 사용)
    dependency_block = ""
    if dependencies:
        for dep in dependencies:
            parts = dep.split()
            if len(parts) == 2:
                dep_type, dep_name = parts
                dependency_block += f"    private final {dep_type} {dep_name};\n"
                print(f"  ✓ 의존성 필드 추가: private final {dep_type} {dep_name};")
        
    # 어노테이션 추가 (클래스 선언 바로 위에) - Bean 파일 여부에 따라 다르게 처리
    if is_bean_file:
        # Bean 파일인 경우: @Transactional, @Service 사용
        annotations = """@Slf4j
@RequiredArgsConstructor
@Transactional
@Service"""
    else:
        # 일반 파일인 경우: @Component 사용
        annotations = """@Slf4j
@RequiredArgsConstructor
@Component"""
    
    # 클래스 선언 찾아서 위에 어노테이션과 필드 추가
    class_pattern = r'(public class \w+\s*\{)'
    
    # 클래스 선언이 이미 있는지 확인
    if re.search(class_pattern, content):
        replacement = annotations + '\n' + r'\1' + '\n' + dependency_block
        content = re.sub(class_pattern, replacement, content, count=1)
    else:
        # 클래스 선언이 없는 경우, 파일 시작 부분에 추가 (예외 케이스)
        content = annotations + '\n' + f'public class {class_name} {{\n' + dependency_block + content

    return content

def refactor_java_folder_optimized(source_dir, output_dir):
    """
    폴더 내의 모든 Java 파일을 최적화된 방식으로 리팩토링하여 지정된 디렉토리에 저장합니다.
    
    :param source_dir: 원본 Java 파일들이 있는 디렉토리 경로
    :param output_dir: 변환된 파일을 저장할 디렉토리 경로
    """
    if not os.path.exists(source_dir):
        print(f"❌ 원본 디렉토리를 찾을 수 없습니다: {source_dir}")
        return
    
    if not os.path.isdir(source_dir):
        print(f"❌ 지정된 경로가 디렉토리가 아닙니다: {source_dir}")
        return
    
    # .java 파일 찾기
    java_files = []
    for root, dirs, files in os.walk(source_dir):
        for file in files:
            if file.endswith('.java'):
                java_files.append(os.path.join(root, file))
    
    if not java_files:
        print(f"⚠️ 지정된 디렉토리에 Java 파일이 없습니다: {source_dir}")
        return
    
    print(f"📄 발견된 Java 파일: {len(java_files)}개")
    
    # 각 Java 파일 리팩토링
    success_count = 0
    error_count = 0
    
    for java_file in java_files:
        try:
            print(f"\n🔄 처리 중: {os.path.basename(java_file)}")
            
            # 안전한 파일 읽기 (인코딩 자동 처리)
            content, detected_encoding = safe_read_file(java_file)
            print(f"    📖 파일을 {detected_encoding} 인코딩으로 읽었습니다.")
            
            # 최적화된 변환 실행
            converted_content = refactor_java_file_optimized(content)
            
            # 출력 파일명 결정 (Bean -> Service 변환 고려)
            original_filename = os.path.basename(java_file)
            if original_filename.endswith('Bean.java'):
                new_filename = original_filename.replace('Bean.java', 'Service.java')
            else:
                new_filename = original_filename
            
            # 결과 파일 저장 (UTF-8로)
            output_file = os.path.join(output_dir, new_filename)
            safe_write_file(output_file, converted_content)
            
            print(f"    ✅ 성공: {new_filename}")
            success_count += 1
            
        except Exception as e:
            print(f"    ❌ 오류: {java_file} 처리 중 오류 발생 - {e}")
            error_count += 1
    
    print(f"\n🎉 === 작업 완료 ===")
    print(f"✅ 성공: {success_count}개 파일")
    print(f"❌ 실패: {error_count}개 파일")
    print(f"📊 전체: {len(java_files)}개 파일")

def main():
    """메인 실행 함수"""
    
    print("🚀 Java EJB to Spring 최적화 변환 도구")
    print("1. 단일 파일 처리")
    print("2. 폴더 단위 처리")
    
    choice = input("선택하세요 (1 또는 2): ").strip()
    
    if choice == '1':
        # 단일 파일 처리
        print("\n📝 원본 Java 파일 경로 입력")
        print("   (따옴표 포함 또는 제외 모두 가능)")
        source_file = input("원본 Java 파일의 절대 경로를 입력하세요: ").strip().strip('"').strip("'")
        
        print("\n📁 출력 디렉토리 경로 입력")
        print("   (따옴표 포함 또는 제외 모두 가능)")
        output_directory = input("변환된 파일을 저장할 디렉토리의 절대 경로를 입력하세요: ").strip().strip('"').strip("'")
        
        # 경로 정규화
        source_file = os.path.normpath(source_file)
        output_directory = os.path.normpath(output_directory)
        
        print(f"\n🔍 입력된 경로 확인:")
        print(f"   원본 파일: {source_file}")
        print(f"   출력 디렉토리: {output_directory}")
        
        if not os.path.exists(source_file):
            print(f"❌ 지정된 원본 파일이 존재하지 않습니다: {source_file}")
        else:
            # 출력 디렉토리가 없으면 생성
            if not os.path.isdir(output_directory):
                try:
                    os.makedirs(output_directory)
                    print(f"📁 출력 디렉토리를 생성했습니다: {output_directory}")
                except OSError as e:
                    print(f"❌ 출력 디렉토리를 생성할 수 없습니다 {output_directory} - {e}")
                    return
            
            print(f"🚀 최적화된 변환 시작: {source_file}")
            print(f"📁 출력 디렉토리: {output_directory}")
            
            try:
                # 안전한 파일 읽기 (인코딩 자동 처리)
                content, detected_encoding = safe_read_file(source_file)
                print(f"  📖 파일을 {detected_encoding} 인코딩으로 읽었습니다.")
                
                # 최적화된 변환 실행
                converted_content = refactor_java_file_optimized(content)
                
                # 출력 파일명 결정 (Bean -> Service 변환 고려)
                original_filename = os.path.basename(source_file)
                if original_filename.endswith('Bean.java'):
                    new_filename = original_filename.replace('Bean.java', 'Service.java')
                else:
                    new_filename = original_filename
                
                # 결과 파일 저장 (UTF-8로)
                output_file = os.path.join(output_directory, new_filename)
                safe_write_file(output_file, converted_content)
                
                print(f"✅ 성공: 최적화된 파일이 저장되었습니다 - {output_file}")
                
            except Exception as e:
                print(f"❌ 오류 발생: {e}")
    
    elif choice == '2':
        # 폴더 단위 처리
        print("\n📂 원본 디렉토리 경로 입력")
        print("   (따옴표 포함 또는 제외 모두 가능)")
        source_directory = input("원본 Java 파일들이 있는 디렉토리의 절대 경로를 입력하세요: ").strip().strip('"').strip("'")
        
        print("\n📁 출력 디렉토리 경로 입력")
        print("   (따옴표 포함 또는 제외 모두 가능)")
        output_directory = input("변환된 파일을 저장할 디렉토리의 절대 경로를 입력하세요: ").strip().strip('"').strip("'")
        
        # 경로 정규화
        source_directory = os.path.normpath(source_directory)
        output_directory = os.path.normpath(output_directory)
        
        print(f"\n🔍 입력된 경로 확인:")
        print(f"   원본 디렉토리: {source_directory}")
        print(f"   출력 디렉토리: {output_directory}")
        
        if not os.path.exists(source_directory):
            print(f"❌ 지정된 원본 디렉토리가 존재하지 않습니다: {source_directory}")
        else:
            # 출력 디렉토리가 없으면 생성
            if not os.path.isdir(output_directory):
                try:
                    os.makedirs(output_directory)
                    print(f"📁 출력 디렉토리를 생성했습니다: {output_directory}")
                except OSError as e:
                    print(f"❌ 출력 디렉토리를 생성할 수 없습니다 {output_directory} - {e}")
                    return
            
            # 변환 작업 수행
            print(f"🚀 폴더 리팩토링 시작: {source_directory}")
            refactor_java_folder_optimized(source_directory, output_directory)
    
    else:
        print("❌ 잘못된 선택입니다. 1 또는 2를 입력하세요.")

if __name__ == "__main__":
    main()
