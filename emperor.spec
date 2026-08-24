# PyInstaller spec · Emperor Agent（任务 D2）
# 打包：pyinstaller emperor.spec
# 产物：dist/EmperorAgent.exe（单文件）——旁边放 .env 即可运行
# 红线：.env / memory / .team / mcp_servers.json 一律不打进 exe（密钥与用户数据）
from PyInstaller.utils.hooks import collect_data_files

datas = [
    ("web/static", "web/static"),                  # 前端
    ("templates", "templates"),                    # 压缩提示词 / persona / USER 模板
    ("examples", "examples"),                      # demo MCP server（供 mcp_servers.json 引用）
]
# mcp 包自带少量数据文件（如 cli 模板），收集以免运行时 ImportError
datas += collect_data_files("mcp")

a = Analysis(
    ["run_app.py"],
    pathex=["."],
    datas=datas,
    hiddenimports=[
        "web.server",
        "uvicorn.logging", "uvicorn.loops", "uvicorn.loops.auto",
        "uvicorn.protocols", "uvicorn.protocols.http", "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets", "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan", "uvicorn.lifespan.on",
        "engineio.async_drivers", "webview.platforms.edgechromium",
    ],
    excludes=["tkinter.test"],
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name="EmperorAgent",
    icon="assets/emperor.ico",
    console=False,               # 桌面软件：不弹黑框（首启引导用 tkinter 消息框）
    onefile=True,
)
