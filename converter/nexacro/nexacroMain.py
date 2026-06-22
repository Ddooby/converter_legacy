"""
Nexacro XFDL 변환 CLI 진입점

사용법:
  python -m converter.nexacro.nexacroMain                          # .env 기준 실행
  python -m converter.nexacro.nexacroMain <input.xfdl> [output.xfdl]
  python -m converter.nexacro.nexacroMain --dir <input_dir> [output_dir]

.env 환경변수 (우선순위 순):
  NEXACRO_BASE_DIR  - 폴더 재귀 in-place 변환 (하위 *.xfdl 전체)
  NEXACRO_FILES     - 폴더 경로 → 해당 폴더 *.xfdl in-place 변환 (재귀)
                    - 파일 경로(쉼표 구분) → 개별 파일 in-place 변환
  NEXACRO_INPUT_DIR / NEXACRO_OUTPUT_DIR  - as-is → to-be 폴더 변환 (기본값)
"""

import os
import sys
import logging
from pathlib import Path

from dotenv import load_dotenv
from .converter import XfdlConverter

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

_ROOT = Path(__file__).parent.parent.parent  # converter_legacy/

AS_IS_DIR = Path(__file__).parent / "as-is"
TO_BE_DIR = Path(__file__).parent / "to-be"


def _resolve(p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else _ROOT / path


def convert_single(input_path: Path, output_path: Path) -> None:
    XfdlConverter().convert_file(input_path, output_path)


def convert_dir(input_dir: Path, output_dir: Path) -> None:
    converter = XfdlConverter()
    xfdl_files = list(input_dir.glob("*.xfdl"))
    if not xfdl_files:
        logger.warning("변환 대상 xfdl 파일이 없습니다: %s", input_dir)
        return
    for f in xfdl_files:
        converter.convert_file(f, output_dir / f.name)


def main() -> None:
    args = sys.argv[1:]

    # CLI 인수 우선
    if args:
        if args[0] == "--dir":
            input_dir = Path(args[1]) if len(args) > 1 else AS_IS_DIR
            output_dir = Path(args[2]) if len(args) > 2 else TO_BE_DIR
            convert_dir(input_dir, output_dir)
        else:
            input_path = Path(args[0])
            output_path = Path(args[1]) if len(args) > 1 else TO_BE_DIR / input_path.name
            convert_single(input_path, output_path)
        return

    # .env 기준 실행
    base_dir_env = os.getenv("NEXACRO_BASE_DIR", "").strip()
    files_env = os.getenv("NEXACRO_FILES", "").strip()

    if base_dir_env:
        # 디렉토리 기준 in-place 변환: 하위 *.xfdl 전체 재귀 탐색
        base_dir = Path(base_dir_env)
        if not base_dir.exists():
            logger.error("NEXACRO_BASE_DIR 경로가 존재하지 않습니다: %s", base_dir)
            sys.exit(1)
        xfdl_files = sorted(base_dir.rglob("*.xfdl"))
        if not xfdl_files:
            logger.warning("변환 대상 xfdl 파일이 없습니다: %s", base_dir)
            return
        converter = XfdlConverter()
        logger.info("BASE_DIR 변환 시작 (%d개): %s", len(xfdl_files), base_dir)
        for src in xfdl_files:
            converter.convert_file(src, src)
    elif files_env:
        files_path = Path(files_env)
        converter = XfdlConverter()
        if files_path.is_dir():
            # 폴더 경로 모드: 해당 폴더 하위 *.xfdl 전체 in-place 변환
            xfdl_files = sorted(files_path.rglob("*.xfdl"))
            if not xfdl_files:
                logger.warning("변환 대상 xfdl 파일이 없습니다: %s", files_path)
                return
            logger.info("NEXACRO_FILES 폴더 변환 시작 (%d개): %s", len(xfdl_files), files_path)
            for src in xfdl_files:
                converter.convert_file(src, src)
        else:
            # 파일 목록 모드: 쉼표 구분 파일 경로, 원본 위치에 덮어씀 (in-place)
            paths = [p.strip() for p in files_env.split(",") if p.strip()]
            for raw in paths:
                src = _resolve(raw)
                if not src.exists():
                    logger.warning("파일 없음, 건너뜀: %s", src)
                    continue
                converter.convert_file(src, src)
    else:
        # 폴더 일괄 변환 모드
        input_dir = _resolve(os.getenv("NEXACRO_INPUT_DIR", "converter/nexacro/as-is"))
        output_dir = _resolve(os.getenv("NEXACRO_OUTPUT_DIR", "converter/nexacro/to-be"))
        logger.info("일괄 변환: %s → %s", input_dir, output_dir)
        convert_dir(input_dir, output_dir)


if __name__ == "__main__":
    main()
