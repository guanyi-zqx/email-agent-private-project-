import time
import json
from pathlib import Path
from dataclasses import dataclass, field, asdict
import imaplib
import email

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown
from rich.progress import (
    Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn,
)

from config import EMAIL_USER, EMAIL_PASS, IMAP_SERVER
from llm_client import analyze_email, generate_reply_draft

console = Console()


@dataclass
class EmailResult:
    index: int
    subject: str
    status: str = "pending"        # done / skipped / failed
    intent: str = ""
    urgency: str = ""
    summary: str = ""
    entities: dict = field(default_factory=dict)
    draft: str = ""
    error: str = ""
    elapsed: float = 0.0


def get_email_body(msg):
    """递归提取邮件正文，兼容纯文本、HTML和附件邮件"""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))
            
            if "attachment" in content_disposition:
                continue
                
            if content_type == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or 'utf-8'
                    body = payload.decode(charset, errors="ignore")
                    break
                    
        if not body:
            for part in msg.walk():
                if part.get_content_type() == "text/html" and "attachment" not in str(part.get("Content-Disposition")):
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or 'utf-8'
                        body = payload.decode(charset, errors="ignore")
                        break
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or 'utf-8'
            body = payload.decode(charset, errors="ignore")
        else:
            body = str(msg.get_payload())
            
    return body

def fetch_unread_emails():
    """连接邮箱并拉取未读邮件"""
    mail = imaplib.IMAP4_SSL(IMAP_SERVER, 993)
    mail.login(EMAIL_USER, EMAIL_PASS)
    
    # 适配QQ/163邮箱的安全机制
    try:
        id_str = '("name" "EmailAgent" "version" "1.0" "vendor" "Python" "support-email" "test@test.com")'
        mail.xatom('ID', id_str)
    except Exception:
        pass
        
    mail.select("INBOX")
    _, data = mail.search(None, "UNSEEN")
    
    emails = []
    for num in data[0].split():
        _, msg_data = mail.fetch(num, "(RFC822)")
        msg = email.message_from_bytes(msg_data[0][1])
        subject = msg["subject"]
        body = get_email_body(msg)
        emails.append({"subject": subject, "body": body})
        
    mail.logout()
    return emails

def process_crm_oms(entities: dict) -> list[str]:
    """改成返回信息列表，由调用方决定怎么展示"""
    info = []
    customer = entities.get("customer_name")
    product = entities.get("product_model")
    qty = entities.get("quantity")

    if customer:
        info.append(f"[CRM] 已匹配客户档案：{customer}")
    else:
        info.append("[CRM] 未识别到客户，已创建新线索 (Lead)")

    if product:
        info.append(f"[OMS] 已调取产品库：{product}")
        if qty:
            info.append(f"[OMS] 已记录意向数量：{qty}")
    else:
        info.append("[OMS] 未识别到具体产品型号")

    return info


# ---------- 单封邮件处理 ----------

def _process_one(e: dict, r: EmailResult, drafts_dir: Path | None):
    subject = e["subject"] or "无主题"
    full_content = f"主题：{subject}\n正文：{e['body']}"

    # 1. 分析
    console.print("  [dim]→ 分析邮件内容...[/]")
    analysis = analyze_email(full_content)
    r.intent = analysis.get("intent", "other")
    r.urgency = analysis.get("urgency", "low")
    r.summary = analysis.get("summary", "")
    r.entities = analysis.get("entities", {}) or {}

    urgency_color = {"high": "red", "medium": "yellow", "low": "green"}.get(r.urgency, "white")
    console.print(
        f"    分类 [bold]{r.intent}[/] | "
        f"紧急度 [{urgency_color}]{r.urgency}[/] | "
        f"摘要：{r.summary}"
    )
    console.print(f"    提取信息：{r.entities}")

    # 2. 业务拦截
    if r.intent == "other" or (
        not r.entities.get("customer_name") and not r.entities.get("product_model")
    ):
        r.status = "skipped"
        console.print("    [yellow]→ 非业务邮件，跳过后续流程[/]")
        return

    # 3. 关联系统
    for line in process_crm_oms(r.entities):
        console.print(f"    [cyan]{line}[/]")

    # 4. 生成回复草稿
    console.print("    [dim]→ 生成回复草稿...[/]")
    r.draft = generate_reply_draft(full_content, analysis)

    console.print(Panel(
        Markdown(r.draft),
        title="[bold green]生成的回复草稿（请人工审核）[/]",
        border_style="green",
        padding=(1, 2),
    ))

    # 5. 落盘：每封草稿单独存成 Markdown，便于交付
    if drafts_dir:
        safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in subject)[:50]
        path = drafts_dir / f"{r.index:02d}_{safe}.md"
        path.write_text(
            f"# {subject}\n\n"
            f"- 分类：{r.intent}\n"
            f"- 紧急度：{r.urgency}\n"
            f"- 摘要：{r.summary}\n"
            f"- 实体：{json.dumps(r.entities, ensure_ascii=False)}\n\n"
            f"---\n\n{r.draft}\n",
            encoding="utf-8",
        )
        console.print(f"    [dim]草稿已保存：{path}[/]")

    r.status = "done"


# ---------- 汇总 ----------

def _print_summary(results: list[EmailResult], total_elapsed: float):
    table = Table(title="运行汇总", show_lines=False)
    table.add_column("#", justify="right", style="dim")
    table.add_column("主题", overflow="fold")
    table.add_column("分类")
    table.add_column("紧急度")
    table.add_column("状态")
    table.add_column("耗时", justify="right")

    status_style = {
        "done": "[green]完成[/]",
        "skipped": "[yellow]跳过[/]",
        "failed": "[red]失败[/]",
        "pending": "[dim]待处理[/]",
    }
    urgency_style = {
        "high": "[red]high[/]",
        "medium": "[yellow]medium[/]",
        "low": "[green]low[/]",
    }

    for r in results:
        table.add_row(
            str(r.index),
            r.subject,
            r.intent or "-",
            urgency_style.get(r.urgency, r.urgency or "-"),
            status_style.get(r.status, r.status),
            f"{r.elapsed:.1f}s",
        )

    console.print()
    console.print(table)

    done = sum(1 for r in results if r.status == "done")
    skipped = sum(1 for r in results if r.status == "skipped")
    failed = sum(1 for r in results if r.status == "failed")

    console.print(
        f"[bold]统计：[/]完成 [green]{done}[/] | "
        f"跳过 [yellow]{skipped}[/] | "
        f"失败 [red]{failed}[/] | "
        f"总耗时 [cyan]{total_elapsed:.1f}s[/]"
    )


def _dump_json(results: list[EmailResult], path: str = "run_result.json"):
    Path(path).write_text(
        json.dumps([asdict(r) for r in results], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    console.print(f"[dim]结构化结果已写入：{path}[/]")


def run_agent(save_dir: str | None = "drafts", output_json: bool = False):
    start = time.time()
    console.rule("[bold cyan]AI 邮件 Agent · 运行开始")

    with console.status("[cyan]连接邮箱，拉取未读邮件...", spinner="dots"):
        try:
            emails = fetch_unread_emails()
        except Exception as ex:
            console.print(f"[bold red]✗ 拉取邮件失败：[/]{ex}")
            return

    total = len(emails)
    console.print(f"[bold green]✓[/] 拉取完成，共 [bold]{total}[/] 封未读邮件")

    if total == 0:
        console.print("[yellow]没有未读邮件，流程结束。[/]")
        return

    drafts_dir = Path(save_dir) if save_dir else None
    if drafts_dir:
        drafts_dir.mkdir(exist_ok=True)

    results: list[EmailResult] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]处理邮件", total=total)
        for index, e in enumerate(emails, 1):
            subject = e["subject"] or "无主题"
            progress.update(task, description=f"[cyan]第 {index}/{total} 封：{subject[:40]}")
            console.rule(f"[bold]第 {index}/{total} 封 · {subject}")

            r = EmailResult(index=index, subject=subject)
            t0 = time.time()
            try:
                _process_one(e, r, drafts_dir)
            except Exception as ex:
                r.status = "failed"
                r.error = str(ex)
                console.print(f"[red]✗ 处理失败：{ex}[/]")
            r.elapsed = time.time() - t0
            results.append(r)
            progress.advance(task)

    _print_summary(results, time.time() - start)

    if output_json:
        _dump_json(results)

# 未来扩展点：将草稿通过API推送给企业微信/飞书通知业务员审核