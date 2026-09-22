# -*- coding: utf-8 -*-
"""把便携版 Python + 依赖装进 jijin/runtime/ ，使整个文件夹可随拷随用。

用法：python _setup_runtime.py
幂等：已装好则跳过（加 --force 强制重装）
"""
import os
import subprocess
import sys
import shutil
import ssl
import urllib.request
import zipfile

BASE = os.path.dirname(os.path.abspath(__file__))
RUNTIME = os.path.join(BASE, "runtime")
PYDIR = os.path.join(RUNTIME, "python")
CACHE = os.path.join(RUNTIME, "_cache")

PY_VER = "3.13.12"
EMBED_NAME = f"python-{PY_VER}-embed-amd64"
EMBED_URL = f"https://www.python.org/ftp/python/{PY_VER}/{EMBED_NAME}.zip"
GETPIP_URL = "https://bootstrap.pypa.io/get-pip.py"

PKGS = ["flask", "requests"]

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


def log(msg):
    print(msg, flush=True)


def download(url, dest):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.exists(dest) and os.path.getsize(dest) > 1000:
        log(f"  [缓存] {os.path.basename(dest)} ({os.path.getsize(dest):,} B)")
        return dest
    log(f"  下载 {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120, context=ctx) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)
    log(f"  完成 {os.path.getsize(dest):,} B")
    return dest


def py_exe():
    return os.path.join(PYDIR, "python.exe")


def run(args, **kw):
    log("  $ " + " ".join(str(a) for a in args))
    p = subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", **kw)
    if p.stdout and p.stdout.strip():
        log("    " + p.stdout.strip().replace("\n", "\n    ")[:1500])
    if p.returncode != 0:
        if p.stderr and p.stderr.strip():
            log("    [stderr] " + p.stderr.strip().replace("\n", "\n    ")[:1500])
        raise SystemExit(f"命令失败，返回码 {p.returncode}")
    return p


def already_ok():
    if not os.path.exists(py_exe()):
        return False
    p = subprocess.run([py_exe(), "-c", "import flask, requests; print('ok')"],
                       capture_output=True, text=True)
    return p.returncode == 0 and "ok" in p.stdout


def main():
    force = "--force" in sys.argv
    log("=" * 64)
    log(f"  装配便携运行环境 -> {RUNTIME}")
    log("=" * 64)

    if already_ok() and not force:
        log("环境已就绪，无需重装。")
        run([py_exe(), "-c", "import flask,requests,sys;print(sys.version);print('flask',flask.__version__);print('requests',requests.__version__)"])
        return 0

    if force and os.path.isdir(PYDIR):
        log("--force：清除旧 runtime\\python")
        shutil.rmtree(PYDIR, ignore_errors=True)

    # 1) 下载并解压 Python embeddable
    log("\n[1/4] 便携版 Python")
    zp = download(EMBED_URL, os.path.join(CACHE, EMBED_NAME + ".zip"))
    os.makedirs(PYDIR, exist_ok=True)
    with zipfile.ZipFile(zp) as z:
        z.extractall(PYDIR)
    log(f"  解压到 {PYDIR}")

    # 2) 开启 site（embeddable 默认关闭，不开 pip 装不进去）
    log("\n[2/4] 启用 site-packages")
    pth = [f for f in os.listdir(PYDIR) if f.endswith("._pth")]
    if not pth:
        raise SystemExit("未找到 ._pth 文件，Python 包结构异常")
    pth_path = os.path.join(PYDIR, pth[0])
    with open(pth_path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    fixed = []
    for ln in lines:
        if ln.strip().startswith("#import site"):
            fixed.append("import site")
        elif ln.strip() == "import site":
            fixed.append("import site")
        else:
            fixed.append(ln)
    if "import site" not in [x.strip() for x in fixed]:
        fixed.append("import site")
    with open(pth_path, "w", encoding="utf-8") as f:
        f.write("\n".join(fixed) + "\n")
    log(f"  已修改 {pth[0]}：import site")

    # 3) 安装 pip
    log("\n[3/4] 安装 pip")
    gp = download(GETPIP_URL, os.path.join(CACHE, "get-pip.py"))
    run([py_exe(), gp, "--no-warn-script-location"])

    # 4) 安装依赖
    log("\n[4/4] 安装依赖 " + ", ".join(PKGS))
    pip = [py_exe(), "-m", "pip", "install", "--no-warn-script-location",
           "--disable-pip-version-check"]
    run(pip + ["-i", "https://pypi.tuna.tsinghua.edu.cn/simple"] + PKGS)

    log("\n验证：")
    run([py_exe(), "-c",
         "import sys,flask,requests;print(sys.version);"
         "print('flask',flask.__version__);print('requests',requests.__version__)"])

    # 清掉下载缓存（省空间，用户 C 盘紧张，这里在 D 盘也顺手清）
    shutil.rmtree(CACHE, ignore_errors=True)
    log("\n环境装配完成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
