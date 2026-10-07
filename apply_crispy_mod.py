#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
脆皮红警玩法 · 一键应用 / 撤销脚本

用法:
    python apply_crispy_mod.py "<游戏目录>"              # 应用
    python apply_crispy_mod.py "<游戏目录>" --undo       # 从备份还原
    python apply_crispy_mod.py "<游戏目录>" --all-five   # 连任务例外也改成 5
    python apply_crispy_mod.py "<游戏目录>" --no-exe     # 不打 exe 补丁（会崩，不推荐）

例:
    python apply_crispy_mod.py "D:\\RAY2\\红色警戒2 完整版"

做了什么:
    1. rules.ini                       -> 覆盖（全血量 5 + 崩溃修复）
    2. 11 个任务包/地图里的地图自带覆盖 -> Strength 全部改成 5（等长字节替换，不动数据包大小）
       默认跳过两个任务例外: [SAPC]=800（苏2关气垫船）、[CANEWY04]=10000（盟1关自由女神像）
    3. game.exe 偏移 0x2DAEDC          -> 6 字节补丁，修掉 5 血触发的整数除零崩溃

所有被修改的文件都会先备份到 <游戏目录>\\_crispy_backup\\
"""
import argparse
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# ---- exe 补丁：idiv dword ptr [ecx+0x1334]  ->  mov eax,5 ; nop ----
EXE_OFFSET = 0x2DAEDC
EXE_OLD = bytes.fromhex('f7b934130000')
EXE_NEW = bytes.fromhex('b80500000090')

# ---- 任务包 / 散装地图（地图自带规则覆盖就在这些文件里）----
MIX_FILES = [
    'maps01.mix', 'maps02.mix', 'mapsmd03.mix', 'MULTI.MIX', 'multimd.mix',
    'DeepFrze.yro', 'EB2.mmx', 'HighExpR.yro', 'Hills.mmx', 'MonsterM.yro', 'Transylv.yro',
]

# ---- 刻意保留的任务例外（按段落名跳过）----
KEEP_SECTIONS = {'SAPC', 'CANEWY04'}

STRENGTH_LINE = re.compile(rb'^([ \t]*Strength[ \t]*=[ \t]*)(\d+)([ \t]*)(\r?)$', re.M)
SECTION = re.compile(rb'^[ \t]*\[([^\]\r\n]+)\]', re.M)


def backup_of(path: Path, bak_dir: Path) -> Path:
    """把文件复制进备份目录（只备份一次），返回备份路径"""
    bak_dir.mkdir(exist_ok=True)
    dst = bak_dir / path.name
    if not dst.exists():
        shutil.copy2(path, dst)
    return dst


def patch_mix(path: Path, all_five: bool) -> tuple:
    """把文件里地图自带的 Strength 覆盖改成 5（等长，保持数据包结构）"""
    data = path.read_bytes()
    out = bytearray(data)
    changed = kept = 0
    kept_names = set()
    cur = b''

    for m in STRENGTH_LINE.finditer(data):
        head, digits, spaces, cr = m.group(1), m.group(2), m.group(3), m.group(4)
        # 找这一行属于哪个段落
        secs = SECTION.findall(data, 0, m.start())
        if secs:
            cur = secs[-1].strip().upper()
        if not all_five and cur in {s.encode() for s in KEEP_SECTIONS}:
            kept += 1
            kept_names.add(cur.decode('latin-1', 'ignore'))
            continue
        if digits == b'5':
            continue
        pad = len(digits) + len(spaces) - 1
        if pad < 0:
            continue
        new = head + b'5' + b' ' * pad + cr
        if len(new) != m.end() - m.start():
            continue
        out[m.start():m.end()] = new
        changed += 1

    if bytes(out) != data:
        path.write_bytes(bytes(out))
    return changed, kept, sorted(kept_names)


def patch_exe(path: Path) -> str:
    data = bytearray(path.read_bytes())
    old = bytes(data[EXE_OFFSET:EXE_OFFSET + len(EXE_OLD)])
    if old == EXE_NEW:
        return '已是补丁后状态'
    if old != EXE_OLD:
        return f'跳过（字节不符 {old.hex()}，可能是别的版本）'
    data[EXE_OFFSET:EXE_OFFSET + len(EXE_NEW)] = EXE_NEW
    path.write_bytes(bytes(data))
    return '已打补丁'


def main() -> int:
    ap = argparse.ArgumentParser(description='脆皮红警玩法 一键应用/撤销')
    ap.add_argument('gamedir', help='游戏安装目录')
    ap.add_argument('--undo', action='store_true', help='从 _crispy_backup 还原')
    ap.add_argument('--all-five', action='store_true', help='连任务例外也改成 5')
    ap.add_argument('--no-exe', action='store_true', help='不打 exe 补丁')
    args = ap.parse_args()

    game = Path(args.gamedir)
    if not game.is_dir():
        print(f'找不到目录: {game}')
        return 1
    bak = game / '_crispy_backup'

    # ---------------- 撤销 ----------------
    if args.undo:
        if not bak.is_dir():
            print(f'没有备份目录 {bak}，无法撤销')
            return 1
        n = 0
        for f in sorted(bak.iterdir()):
            if f.is_file():
                shutil.copy2(f, game / f.name)
                n += 1
                print(f'  还原 {f.name}')
        print(f'\n已还原 {n} 个文件。记得重启游戏。')
        return 0

    # ---------------- 应用 ----------------
    print(f'目标目录: {game}\n备份目录: {bak}\n')

    # 1) rules.ini
    src_ini = HERE / 'rules.ini'
    if src_ini.is_file():
        backup_of(game / 'rules.ini', bak)
        shutil.copy2(src_ini, game / 'rules.ini')
        print('  [1/3] rules.ini 已覆盖（血量 5 + 崩溃修复）')
    else:
        print('  [1/3] !! 仓库里没有 rules.ini，跳过')

    # 2) 任务包 / 地图
    print('  [2/3] 任务包 / 地图里的地图自带覆盖:')
    for name in MIX_FILES:
        p = game / name
        if not p.is_file():
            print(f'        {name:16s} 不存在，跳过')
            continue
        backup_of(p, bak)
        changed, kept, names = patch_mix(p, args.all_five)
        extra = f'（保留任务例外 {", ".join(names)}）' if kept else ''
        print(f'        {name:16s} 改 {changed:3d} 处{extra}')

    # 3) exe
    exe = game / 'game.exe'
    if args.no_exe:
        print('  [3/3] exe 补丁: 按参数要求跳过（会崩）')
    elif exe.is_file():
        backup_of(exe, bak)
        print(f'  [3/3] game.exe: {patch_exe(exe)}')
    else:
        print('  [3/3] !! 找不到 game.exe')

    print('\n完成。请完全退出游戏后重开（规则只在启动时读一次）。')
    print(f'想撤销: python {Path(__file__).name} "{game}" --undo')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
