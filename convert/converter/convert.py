import logging
import click
from rich.console import Console
from rich.logging import RichHandler

from .converter import EjbConverter

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(rich_tracebacks=True)],
)
console = Console()


@click.group()
def cli():
    """EJB → Spring Java 변환 도구"""


@cli.command()
def patterns():
    """patterns/learned_patterns.json 내용을 요약 출력합니다."""
    ejb_converter = EjbConverter()
    try:
        p = ejb_converter._load_patterns()
        console.print("[bold green]패턴 파일 로드 성공![/]")
        for key, val in p.items():
            count = len(val) if isinstance(val, list) else "-"
            console.print(f"  {key}: {count}개")
    except FileNotFoundError as e:
        console.print(f"[bold red]{e}[/]")


@cli.command()
def convert():
    """input/ 폴더의 EJB 파일을 Spring 코드로 변환합니다."""
    console.print("[bold cyan]변환 시작...[/]")
    ejb_converter = EjbConverter()
    converted = ejb_converter.convert_all()
    console.print(f"[bold green]변환 완료! {len(converted)}개 파일 → output/[/]")
    for path in converted:
        console.print(f"  [green]✓[/] {path}")


@cli.command()
@click.option(
    "--dir",
    "directory",
    default=None,
    help="검증 대상 폴더 (기본: env VALIDATE_DIR 또는 output/)",
)
@click.option(
    "--report",
    "report",
    default=None,
    help="결과 보고서 저장 경로 (예: validate_report.txt)",
)
def validate(directory, report):
    """DAO + Mapper XML 을 교차 검증합니다 (파라미터/네임스페이스/문법)."""
    from .validate import Validator

    Validator(directory=directory).run(report_path=report)


if __name__ == "__main__":
    cli()
