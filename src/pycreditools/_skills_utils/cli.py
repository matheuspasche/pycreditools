from __future__ import annotations

import argparse
from pathlib import Path

from pycreditools._skills_utils import installer


def main() -> None:
    parser = argparse.ArgumentParser(prog="pasche-utils")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list-packs", help="list bundled skill packs")

    p_list = sub.add_parser("list-skills", help="list skills in a pack")
    p_list.add_argument("pack")

    p_install = sub.add_parser("install-skills", help="copy a skill pack into a target dir")
    p_install.add_argument("pack")
    p_install.add_argument(
        "--target",
        default=".claude/skills",
        help="destination dir (default: ./.claude/skills, relative to cwd)",
    )
    p_install.add_argument("--global", dest="use_global", action="store_true",
                            help="install to ~/.claude/skills instead of --target")
    p_install.add_argument("--overwrite", action="store_true")

    args = parser.parse_args()

    if args.command == "list-packs":
        for pack in installer.list_packs():
            print(pack)
    elif args.command == "list-skills":
        for skill in installer.list_skills(args.pack):
            print(skill)
    elif args.command == "install-skills":
        target = Path.home() / ".claude" / "skills" if args.use_global else Path(args.target)
        installed = installer.install(args.pack, target, overwrite=args.overwrite)
        for name in installed:
            print(f"{target}/{name}")


if __name__ == "__main__":
    main()
