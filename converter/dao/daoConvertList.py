"""
프로젝트 폴더 파일 비교 스크립트
- Business + Common 프로젝트 폴더 통합(Freezing Source) vs 1차 전환 프로젝트 비교(Git)
- 통합본에는 있지만 1차 전환 프로젝트에 없는 파일 추출

[ History ]
2026-05-07
    2차 프리징버전 소스 받아서 1차의 프로젝트 폴더와 비교해서 새로운 파일을 2차 대상파일로 간주
"""

from pathlib import Path

# ─────────────────────────────────────────────
# 경로 설정 (여기만 수정하면 됨)
# ─────────────────────────────────────────────
PATH_SOM   = r"C:\Projects\somSecond\SOM_Business_Sysm\ejbModule\com\stx\som\business\dao\basicData"
PATH_COMMON = r"C:\Projects\somSecond\SOM_Common\CommonFnDaoSource\com\stx\som\business\dao\basicData"

PATH_GIT   = r"C:\Projects\Panocean\src\main\java\com\pan\som\dao\basicData"

EXTENSIONS = [".java"]  # 빈 리스트면 전체 파일 비교
# ─────────────────────────────────────────────


def get_filenames(path: str, extensions: list) -> set:
    """폴더 내 파일명 목록 반환 (없는 경로면 빈 set)"""
    p = Path(path)
    if not p.exists():
        print(f"  ⚠️  경로 없음 (건너뜀): {path}")
        return set()

    files = set()
    for f in p.rglob("*"):
        if f.is_file():
            if not extensions or f.suffix in extensions:
                files.add(f.name)
    return files


def main():
    print("=" * 120)
    print("  프로젝트 파일 비교 v2 (Business + Common vs Git 1차 전환)")
    print("=" * 120)
    print(f"  Business   : {PATH_SOM}")
    print(f"  Common     : {PATH_COMMON}")
    print(f"  Git 1차 전환 : {PATH_GIT}")
    print(f"  필터: {EXTENSIONS if EXTENSIONS else '전체'}")
    print("=" * 120)

    names_a   = get_filenames(PATH_SOM,   EXTENSIONS)
    names_a_1 = get_filenames(PATH_COMMON, EXTENSIONS)
    names_b   = get_filenames(PATH_GIT,   EXTENSIONS)

    # Business와 Common 합집합
    names_a_total = names_a | names_a_1

    # Business+Common에는 있고 Git 1차 전환에는 없는 파일
    only_in_a   = names_a_total - names_b

    # Git 1차 전환에만 있는 파일 (참고용)
    only_in_b   = names_b - names_a_total

    # 공통 파일
    common      = names_a_total & names_b

    # Business에만 있는 것 / Common에만 있는 것 / 둘 다 있는 것 구분 (only_in_a 내에서)
    only_a_src      = only_in_a & names_a       # Business 출처
    only_a_1_src    = only_in_a & names_a_1     # Common 출처
    both_src        = only_in_a & names_a & names_a_1  # 둘 다 있음

    print(f"\n🎯 Freezing Source에 있고 1차 전환 프로젝트에 없는 파일 ({len(only_in_a)}개) ← 변환 대상")
    print("-" * 120)
    if only_in_a:
        for name in sorted(only_in_a):
            source = []
            if name in names_a:
                source.append("A")
            if name in names_a_1:
                source.append("A_1")
            print(f"  {name:50s} [{', '.join(source)}]")
    else:
        print("  없음")

    # ── 참고: Git 1차 전환에만 있는 파일 ──
    print(f"\n⚠️  Git 1차 전환에만 있는 파일 ({len(only_in_b)}개) ← Business/Common에 없는 이상 파일")
    print("-" * 120)
    if only_in_b:
        for name in sorted(only_in_b):
            print(f"  {name}")
    else:
        print("  없음")

    # ── 공통 파일 ──
    # print(f"\n📋 공통 파일 ({len(common)}개) ← 양쪽 다 존재")
    # print("-" * 120)
    # for name in sorted(common):
    #     print(f"  {name}")

    # ── 요약 ──
    print("\n" + "=" * 120)
    print(f"  Business 파일 수    : {len(names_a)}개")
    print(f"  Common 파일 수  : {len(names_a_1)}개")
    print(f"  Business+Common 합계   : {len(names_a_total)}개 (중복 제거)")
    print(f"  Git 1차 전환 파일 수    : {len(names_b)}개")
    print(f"  ─────────────────────────────")
    print(f"  변환 대상    : {len(only_in_a)}개 (Business+Common에 있고 Git 1차 전환에 없음)")
    print(f"  Git 1차 전환 신규 파일  : {len(only_in_b)}개 (Git 1차 전환에만 있음)")
    print(f"  공통         : {len(common)}개")
    print("=" * 120)

    # ── 결과를 텍스트 파일로 저장 ──
    output_path = Path("dao/daoConvertList_result.txt")
    with open(output_path, "w", encoding="utf-8") as out:
        out.write(f"Business   : {PATH_SOM}\n")
        out.write(f"Common     : {PATH_COMMON}\n")
        out.write(f"Git 1차 전환 : {PATH_GIT}\n\n")

        out.write(f"[Business+Common에 있고 Git 1차 전환에 없는 파일 - {len(only_in_a)}개]\n")
        for name in sorted(only_in_a):
            source = []
            if name in names_a:   source.append("SOM_BUSINESS")
            if name in names_a_1: source.append("SOM_COMMON")
            out.write(f"  {name:50s} [{', '.join(source)}]\n")

        out.write(f"\n[Git 1차 전환에만 있는 파일 - {len(only_in_b)}개]\n")
        for name in sorted(only_in_b):
            out.write(f"  {name}\n")

        out.write(f"\n[공통 파일 - {len(common)}개]\n")
        for name in sorted(common):
            out.write(f"  {name}\n")

    print(f"\n  결과 저장됨: {output_path.resolve()}")


if __name__ == "__main__":
    main()