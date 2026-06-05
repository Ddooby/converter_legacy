import logging
import click
from rich.console import Console
from rich.logging import RichHandler

from .converter import ServletConverter

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(rich_tracebacks=True)],
)
console = Console()


@click.group()
def cli():
    """EJB Servlet → Spring Controller 변환 도구"""


@cli.command()
def patterns():
    """patterns/learned_patterns.json 내용을 요약 출력합니다."""
    converter = ServletConverter()
    try:
        p = converter._load_patterns()
        console.print("[bold green]패턴 파일 로드 성공![/]")
        for key, val in p.items():
            count = len(val) if isinstance(val, list) else "-"
            console.print(f"  {key}: {count}개")
    except FileNotFoundError as e:
        console.print(f"[bold red]{e}[/]")


@cli.command()
def convert():
    """input/ 폴더의 EJB Servlet 파일을 Spring Controller로 변환합니다."""
    console.print("[bold cyan]변환 시작...[/]")
    converter = ServletConverter()
    converted = converter.convert_all()
    console.print(f"[bold green]변환 완료! {len(converted)}개 파일 → output/[/]")
    for path in converted:
        console.print(f"  [green]✓[/] {path}")


if __name__ == "__main__":
    cli()
