# -*- mode: python ; coding: utf-8 -*-
#
# koreanwordcloudnlp.py + hgwordstitcher.py 를 하나의 폴더(onedir)로 묶는 PyInstaller spec
#
# 사용법 (저장소 루트에서):
#     pip install -r requirements.txt pyinstaller
#     pyinstaller --noconfirm koreanwordcloud_stitcher.spec
#
# 결과: dist/korwordcloud/ 폴더 안에
#     koreanwordcloudnlp(.exe), hgwordstitcher(.exe)  — 두 실행 파일
#     _internal/                                       — 공유 라이브러리와 Kiwi 모델
#
# 두 실행 파일이 Kiwi 모델(약 100MB)을 공유하도록 하나의 COLLECT로 묶었습니다.
# onefile은 실행할 때마다 임시 폴더에 모델을 풀어서 시작이 느리므로 쓰지 않았습니다.

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
)

# ---------------------------------------------------------------------------
# Kiwi 수집
#  - kiwipiepy_model: 형태소 분석 모델(.dict/.mdl/.morph/.txt)이 들어 있는 별도 패키지.
#    .py가 아닌 데이터 파일이라 자동으로 수집되지 않으므로 반드시 collect_data_files로 가져옵니다.
#  - _kiwipiepy: 최상위 C 확장 모듈(_kiwipiepy.abi3.so / .pyd). kiwipiepy/_c_api.py가
#    `from _kiwipiepy import Token` 으로 불러오므로 hiddenimports에 명시합니다.
#  - kiwipiepy 자체의 데이터(corpus/stopwords.txt 등)와 동적 라이브러리도 함께 수집합니다.
# ---------------------------------------------------------------------------
kiwi_datas = (
    collect_data_files('kiwipiepy_model')
    + collect_data_files('kiwipiepy')
)
kiwi_binaries = (
    collect_dynamic_libs('kiwipiepy')
    + collect_dynamic_libs('kiwipiepy_model')
)
kiwi_hidden = (
    ['_kiwipiepy']
    + collect_submodules('kiwipiepy')
    + collect_submodules('kiwipiepy_model')
    + ['numpy', 'tqdm']
)

# ---------------------------------------------------------------------------
# Janome (선택): koreanwordcloudnlp.py의 다국어 모드에서 일본어 분석에만 사용합니다.
#  janome은 사전(sysdic)을 entries_*.py, connections*.py 등 .py 파일로 가지고 있고,
#  실행 시 이 파일들을 import가 아니라 "파일로 직접 열어서(mmap)" 읽습니다.
#  따라서 .py 파일을 코드가 아닌 데이터 파일로 그대로 복사해야 합니다
#  (collect_data_files의 include_py_files=True). 이렇게 하지 않으면
#  FileNotFoundError: .../janome/sysdic/entries_compact0.py 가 발생합니다.
#  설치되어 있지 않으면 건너뜁니다.
#  (일본어 분석이 필요 없다면 아래 USE_JANOME = False 로 바꾸면 용량이 크게 줄어듭니다.)
# ---------------------------------------------------------------------------
USE_JANOME = True
try:
    import janome  # noqa: F401
    HAVE_JANOME = USE_JANOME
except ImportError:
    HAVE_JANOME = False

if HAVE_JANOME:
    janome_datas = collect_data_files('janome', include_py_files=True)
    # sysdic 모듈은 위에서 데이터로 복사하므로, 코드 쪽에는 sysdic을 제외한 모듈만 넣습니다.
    janome_hidden = [m for m in collect_submodules('janome')
                     if not m.startswith('janome.sysdic.')]
else:
    janome_datas, janome_hidden = [], []

# 쓰이지 않는데 용량만 키우는 패키지 제외
# (kiwipiepy의 transformers_addon이 torch/transformers를 선택적으로 import 합니다.)
COMMON_EXCLUDES = [
    'torch', 'transformers', 'tensorflow', 'sklearn', 'scipy', 'pandas',
    'matplotlib', 'PIL', 'IPython', 'jupyter', 'notebook', 'pytest',
    'tkinter', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6',
]


def make_analysis(script, datas, binaries, hiddenimports, extra_excludes=()):
    return Analysis(
        [script],
        pathex=[SPECPATH],
        binaries=binaries,
        datas=datas,
        hiddenimports=hiddenimports,
        hookspath=[],
        hooksconfig={},
        runtime_hooks=[],
        excludes=COMMON_EXCLUDES + list(extra_excludes),
        noarchive=False,
        optimize=0,
    )


# 단어 빈도 추출기: Kiwi + (선택) Janome
a_cloud = make_analysis(
    'koreanwordcloudnlp.py',
    datas=kiwi_datas + janome_datas,
    binaries=kiwi_binaries,
    hiddenimports=kiwi_hidden + janome_hidden,
)

# 단어 병합기: Kiwi만 사용 (Janome 불필요)
a_stitch = make_analysis(
    'hgwordstitcher.py',
    datas=kiwi_datas,
    binaries=kiwi_binaries,
    hiddenimports=kiwi_hidden,
    extra_excludes=['janome'],
)

pyz_cloud = PYZ(a_cloud.pure)
pyz_stitch = PYZ(a_stitch.pure)

# 둘 다 명령행 도구이므로 콘솔 창을 유지합니다(console=True).
exe_cloud = EXE(
    pyz_cloud,
    a_cloud.scripts,
    [],
    exclude_binaries=True,
    name='koreanwordcloudnlp',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)

exe_stitch = EXE(
    pyz_stitch,
    a_stitch.scripts,
    [],
    exclude_binaries=True,
    name='hgwordstitcher',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)

# 두 실행 파일을 한 폴더에 모읍니다. 같은 이름의 라이브러리/데이터는 한 번만 복사됩니다.
coll = COLLECT(
    exe_cloud,
    a_cloud.binaries,
    a_cloud.datas,
    exe_stitch,
    a_stitch.binaries,
    a_stitch.datas,
    strip=False,
    upx=False,
    name='korwordcloud',
)
