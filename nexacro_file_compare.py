"""
엑셀 파일 목록 vs 실제 프로젝트 파일 비교 스크립트

- 엑셀 "통합" 시트에 있는 경로 목록과
- C:/Projects/Panocean/nexacro/biz 아래 실제 파일을 비교
- 프로젝트에는 있으나 엑셀에 누락된 파일을 결과로 출력
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

import openpyxl
import os
from pathlib import Path

EXCEL_PATH = r"C:\Users\cheol_hi\Desktop\Ddooby\02.작업\2차\01.Convert\nexacro_list.xlsx"
SHEET_NAME = "통합"
PROJECT_BASE = Path(r"C:\Projects\Panocean\nexacro\biz")
OUTPUT_PATH = Path(__file__).parent / "nexacro_compare_result.txt"

EXCLUDE_EXTENSIONS = {".class", ".jar", ".war", ".ear"}
EXCLUDE_DIRS = {".git", ".svn", "node_modules", "__pycache__"}


def load_excel_paths(excel_path: str, sheet_name: str) -> set[str]:
    wb = openpyxl.load_workbook(excel_path, read_only=True, data_only=True)
    ws = wb[sheet_name]
    paths = set()
    for row in ws.iter_rows(min_col=1, max_col=1, values_only=True):
        val = row[0]
        if val and isinstance(val, str):
            # 슬래시 통일 (역슬래시 → 슬래시), 앞뒤 공백 제거
            normalized = val.strip().replace("\\", "/")
            if normalized:
                paths.add(normalized)
    wb.close()
    return paths


def scan_project_files(base: Path) -> set[str]:
    files = set()
    for root, dirs, filenames in os.walk(base):
        # 제외 폴더 필터링
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for filename in filenames:
            if Path(filename).suffix.lower() in EXCLUDE_EXTENSIONS:
                continue
            full_path = Path(root) / filename
            # base 기준 상대경로, 슬래시로 통일
            rel = full_path.relative_to(base).as_posix()
            files.add(rel)
    return files


def main():
    print(f"엑셀 로드 중: {EXCEL_PATH}")
    excel_paths = load_excel_paths(EXCEL_PATH, SHEET_NAME)
    print(f"  → 엑셀 경로 수: {len(excel_paths)}")

    print(f"프로젝트 스캔 중: {PROJECT_BASE}")
    if not PROJECT_BASE.exists():
        print(f"  [오류] 프로젝트 경로가 존재하지 않습니다: {PROJECT_BASE}")
        return
    project_files = scan_project_files(PROJECT_BASE)
    print(f"  → 실제 파일 수: {len(project_files)}")

    # 프로젝트에는 있으나 엑셀에 없는 파일
    only_in_project = sorted(project_files - excel_paths)

    # 엑셀에는 있으나 프로젝트에 없는 파일 (참고용)
    only_in_excel = sorted(excel_paths - project_files)

    lines = []
    lines.append("=" * 70)
    lines.append("Nexacro 파일 비교 결과")
    lines.append("=" * 70)
    lines.append(f"엑셀 경로 수  : {len(excel_paths)}")
    lines.append(f"실제 파일 수  : {len(project_files)}")
    lines.append("")

    lines.append(f"[A] 프로젝트에는 있으나 엑셀에 누락된 파일 ({len(only_in_project)}건)")
    lines.append("-" * 70)
    for p in only_in_project:
        lines.append(p)

    lines.append("")
    lines.append(f"[B] 엑셀에는 있으나 프로젝트에 없는 파일 ({len(only_in_excel)}건)")
    lines.append("-" * 70)
    for p in only_in_excel:
        lines.append(p)

    result_text = "\n".join(lines)
    print("\n" + result_text)

    OUTPUT_PATH.write_text(result_text, encoding="utf-8")
    print(f"\n결과 저장 완료: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
