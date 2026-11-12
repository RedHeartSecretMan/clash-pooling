"""命令行入口。"""

import argparse
import sys

from . import __version__, commands, platform, scheduler, setup_console


def build_parser():
    parser = argparse.ArgumentParser(
        prog="clashctl",
        description="Clash Verge 控制台工具：查看链路、切换服务组、核验节点出口、同步配置",
    )
    parser.add_argument("--version", action="version", version="clashctl %s" % __version__)
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("status", help="服务组链路与各地区池当前节点")
    sub.add_parser("regions", help="所有组及其成员数")
    sub.add_parser("audit", help="检查本地规则是否遮蔽机场规则")
    sub.add_parser("doctor", help="体检：内核、分组、规则、DNS")
    sub.add_parser("backup", help="备份 Clash 配置")
    sub.add_parser("sync", help="把仓库 clash/ 下的配置同步到 Clash")

    nodes = sub.add_parser("nodes", help="某组的节点清单")
    nodes.add_argument("group", nargs="?", default="")

    test = sub.add_parser("test", help="实测延迟（默认测全部服务组）")
    test.add_argument("services", nargs="*")

    use = sub.add_parser("use", help="切换服务组到地区池 / 节点 / DIRECT")
    use.add_argument("service")
    use.add_argument("target")

    check = sub.add_parser("exit-check", help="核验节点出口")
    check.add_argument("pool", nargs="?", default=None, help="只核验某个地区池")
    check.add_argument("--refresh", action="store_true", help="重新测量并写回清单")
    check.add_argument("--full", action="store_true", help="全量重测（配合 --refresh）")
    check.add_argument("--recheck", metavar="子串", default=None, help="只重测名字匹配的节点")

    auto = sub.add_parser("auto", help="定时核验：安装、停用、查看、执行")
    auto.add_argument("action", choices=["enable", "disable", "status", "run"])
    auto.add_argument("--full", action="store_true", help="run 时强制全量")

    return parser


def main(argv=None):
    setup_console()
    platform.migrate_state_dir()      # 兼容 0.1.1 及更早的 ~/.dsh-clashctl
    args = build_parser().parse_args(argv)
    if not args.command:
        build_parser().print_help()
        return 0

    if args.command == "status":
        commands.status()
    elif args.command == "regions":
        commands.regions()
    elif args.command == "nodes":
        commands.nodes(args.group)
    elif args.command == "test":
        commands.test(args.services)
    elif args.command == "use":
        commands.use(args.service, args.target)
    elif args.command == "exit-check":
        if args.refresh or args.recheck:
            commands._refresh(full=args.full, recheck=args.recheck)
        else:
            commands.exit_check(args.pool)
    elif args.command == "audit":
        commands.audit()
    elif args.command == "doctor":
        commands.doctor()
    elif args.command == "backup":
        commands.backup()
    elif args.command == "sync":
        commands.sync()
    elif args.command == "auto":
        if args.action == "enable":
            return 0 if scheduler.enable() else 1
        elif args.action == "disable":
            return 0 if scheduler.disable() else 1
        elif args.action == "status":
            scheduler.status()
        else:
            scheduler.run("full" if args.full else "watch")
    return 0


if __name__ == "__main__":
    sys.exit(main())
