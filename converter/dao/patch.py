"""
patch.py — 이미 변환·커스텀 완료된 파일에 BigDecimal 패턴만 후처리 적용

사용법:
  python -m converter.dao.patch [--dir <경로>]
  .env 의 PATCH_DIR 으로 기본 경로 지정 가능 (절대경로 허용 → 다른 프로젝트도 대상 가능)

적용 패턴:
  Formatter.nullDouble/Long(StringUtil.nvl(map.get("*AMT/*AMOUNT"), ...))
  → Formatter.nullBigDecimal(StringUtil.nvl(map.get("..."), "0"))
"""
import os
import re
import logging
from pathlib import Path

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.logging import RichHandler

load_dotenv(override=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(rich_tracebacks=True)],
)
log = logging.getLogger(__name__)
console = Console()

_BIGDECIMAL_PATTERN = re.compile(
    r'(?i)Formatter\.null(?:Double|Long)\(\s*StringUtil\.nvl\(\s*map\.get\("(\w*(?:amt|amount))"\)\s*,\s*"[^"]*"\s*\)\s*\)'
)
_BIGDECIMAL_REPL = r'Formatter.nullBigDecimal(StringUtil.nvl(map.get("\1"), "0"))'

_DEFAULT_DIRS = ["validate", "output"]


def _resolve_target_dir(directory: str | None) -> Path:
    # 우선순위: --dir 인수 > PATCH_DIR 환경변수 > 기본 폴더 탐색
    raw = directory or os.getenv("PATCH_DIR")
    if raw:
        p = Path(raw)
        if not p.is_absolute():
            p = Path(__file__).parent / raw
        if not p.exists():
            raise FileNotFoundError(f"지정한 경로가 존재하지 않습니다: {p}")
        return p
    base = Path(__file__).parent
    for name in _DEFAULT_DIRS:
        p = base / name
        if p.exists():
            return p
    raise FileNotFoundError(f"대상 폴더를 찾을 수 없습니다: {_DEFAULT_DIRS}")


def patch_file(path: Path) -> bool:
    original = path.read_text(encoding="utf-8")
    patched = _BIGDECIMAL_PATTERN.sub(_BIGDECIMAL_REPL, original)
    if patched == original:
        return False
    path.write_text(patched, encoding="utf-8")
    return True


@click.command()
@click.option(
    "--dir",
    "directory",
    default=None,
    help="패치 대상 폴더 (기본: validate/ 또는 output/)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="실제 파일을 수정하지 않고 변경 대상만 출력",
)
def main(directory: str | None, dry_run: bool):
    """이미 변환된 Java 파일에 BigDecimal 패턴을 후처리 적용합니다."""
    try:
        target = _resolve_target_dir(directory)
    except FileNotFoundError as e:
        console.print(f"[bold red]{e}[/]")
        raise SystemExit(1)

    java_files = list(target.rglob("*.java"))
    if not java_files:
        console.print(f"[yellow]{target} 에 .java 파일이 없습니다.[/]")
        return

    changed, skipped = [], []
    for f in java_files:
        original = f.read_text(encoding="utf-8")
        patched = _BIGDECIMAL_PATTERN.sub(_BIGDECIMAL_REPL, original)
        if patched != original:
            changed.append(f)
            if not dry_run:
                f.write_text(patched, encoding="utf-8")
        else:
            skipped.append(f)

    mode = "[DRY-RUN] " if dry_run else ""
    console.print(f"\n[bold cyan]{mode}BigDecimal 패치 결과[/]")
    console.print(f"  대상 폴더: {target}")
    console.print(f"  전체 파일: {len(java_files)}개")

    if changed:
        console.print(f"\n[bold green]변경된 파일 ({len(changed)}개):[/]")
        for f in changed:
            console.print(f"  [green]{'(미적용) ' if dry_run else '✓'}[/] {f.name}")
    else:
        console.print("[yellow]  변경 대상 없음[/]")

    if skipped:
        log.debug("패턴 없음 → 스킵: %d개", len(skipped))


if __name__ == "__main__":
    main()
