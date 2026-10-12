import argparse
from email_agent import run_agent


def main():
    parser = argparse.ArgumentParser(description="AI 外贸邮件 Agent")
    parser.add_argument("--no-save", action="store_true", help="不保存草稿到文件")
    parser.add_argument("--json", action="store_true", help="额外输出 run_result.json")
    parser.add_argument("--drafts-dir", default="drafts", help="草稿保存目录")
    args = parser.parse_args()

    run_agent(
        save_dir=None if args.no_save else args.drafts_dir,
        output_json=args.json,
    )


if __name__ == "__main__":
    main()