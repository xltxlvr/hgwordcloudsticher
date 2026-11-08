# Korean Word Cloud & Stitcher

이 저장소는 한국어 텍스트 분석을 통한 워드클라우드 생성 툴과 행 단위로 잘린 단어를 하나로 병합(Stitching)하는 툴을 포함하고 있습니다. 이 둘은 성격이 상이하지만 한국어 형태소 분석기를 활용하는 명령행 도구라는 공통점을 지니고 있어 이곳에서 함께 관리합니다.

## 파일 구성 (Repository Structure)

- `koreanwordcloudnlp.py`: 한국어 자연어 처리(NLP)를 적용하여 텍스트에서 단어를 추출하고 워드클라우드를 생성하는 스크립트입니다.
- `hgwordstitcher.py`: 한국어 텍스트의 문단 내 행 사이에 잘린 단어를 복원하는 스크립트입니다.
- `korwordcloud.tex`: 생성된 워드클라우드 데이터를 컴파일하는 LaTeX 템플릿 파일입니다.
- `requirements.txt`: 프로젝트 실행에 필요한 파이썬 패키지 목록입니다.

## 설치 (Installation)

Python 3 환경이 필요합니다. 두 스크립트 모두 형태소 분석기 [Kiwi](https://github.com/bab2min/kiwipiepy)(`kiwipiepy`)를 사용합니다.

```bash
pip install -r requirements.txt
```

`requirements.txt`에는 다음 패키지가 들어 있습니다.

| 패키지 | 용도 |
| --- | --- |
| `kiwipiepy` | 한국어 형태소 분석 (두 스크립트 공통, 필수) |
| `janome` | 일본어 형태소 분석 (`koreanwordcloudnlp.py`의 다국어 모드에서만 사용, 없으면 일본어 분석만 건너뜀) |

워드클라우드 PDF를 만들려면 추가로 LaTeX 배포판(LuaLaTeX)과 `kotex`, `ninecolors`, `wordcloud`, `singlepageempty` 패키지가 필요합니다.

---

## 1. koreanwordcloudnlp.py — 워드클라우드용 단어 빈도 추출

입력 텍스트를 형태소 분석하여 단어별 빈도를 세고, LaTeX [`wordcloud`](https://ctan.org/pkg/wordcloud) 패키지가 읽을 수 있는 `(단어, 횟수);` 형식으로 출력합니다.

### 기본 사용법

입력은 세 가지 방법 중 하나로 줍니다. 우선순위는 `-i` 파일 > 위치 인자 텍스트 > 표준 입력(stdin) 순입니다.

```bash
# 1) 파일 입력
python koreanwordcloudnlp.py -i input.txt -o out.txt

# 2) 텍스트를 직접 입력
python koreanwordcloudnlp.py "분석할 텍스트를 여기에 씁니다"

# 3) 표준 입력 (파이프)
cat input.txt | python koreanwordcloudnlp.py > out.txt
```

`-o`를 생략하면 결과를 표준 출력으로 내보냅니다. 입력 없이 터미널에서 실행하면 도움말이 표시됩니다.

### 출력 형식

빈도 내림차순(빈도가 같으면 가나다순)으로 정렬되며, 항목은 세미콜론과 줄바꿈으로 구분됩니다. 공백이 들어간 단어는 중괄호로 감쌉니다.

```
(글꼴, 3);
({오픈 타입}, 2);
(조판, 1)
```

단어에 LaTeX 특수문자(`\ & % $ # _ { } ~ ^`)가 있으면 자동으로 이스케이프하고, 출력 형식을 깨뜨리는 쉼표·괄호·세미콜론은 전각 문자(`，` `（` `）` `；`)로 바꿉니다.

### 단어 집계 방식

한국어 단어는 어절이 아니라 형태소 분석 결과를 기준으로 셉니다.

- **체언(명사·대명사·수사)**: 조사를 뗀 어간만 셉니다. 예를 들어 `문서를`, `문서가`, `문서는`은 모두 `문서` 하나로 집계됩니다.
- **용언(동사·형용사)**: 어미를 떼고 사전형(기본형)으로 복원해 셉니다. 예를 들어 `만들었다`, `만든다`, `만들면`은 모두 `만들다`로, `좋았다`, `좋은`, `좋다`는 모두 `좋다`로 집계됩니다.

따라서 같은 단어가 조사나 어미 때문에 서로 다른 단어로 갈라져 집계되지 않습니다. 다만 형태소 분석기가 문맥에 따라 단어를 다르게 쪼개는 경우가 드물게 있으며, 이때는 `-u`로 단어를 등록해 보완할 수 있습니다. 한국어 모드(`-k`)와 기본(다국어) 모드 모두 동일하게 적용됩니다. 또한 `-x`(제외어)와 `-s`(치환)는 조사·어미를 제거한 **뒤의 형태**를 기준으로 비교하므로 `-x 좋다`처럼 기본형으로 지정해야 합니다.

### 옵션

| 옵션 | 설명 |
| --- | --- |
| `-i`, `--input FILE` | 분석할 입력 파일(UTF-8). |
| `-o`, `--output FILE` | 결과를 저장할 파일. 생략하면 표준 출력. |
| `-m`, `--max N` | 출력할 최대 단어 수(상위 N개). `0`이면 0개를 출력하고, 음수이면 경고 후 전체를 출력합니다. |
| `-x`, `--exclude WORDS` | 제외할 단어 목록(콤마 구분). 예: `-x "것,수,등"` |
| `-X`, `--exclude-file FILE` | 제외할 단어 목록 파일(줄바꿈 또는 콤마 구분). |
| `-u`, `--user-word WORDS` | 하나의 단어로 인식시킬 단어(콤마 구분, 띄어쓰기 포함 가능). 예: `-u "오픈 타입"`을 주면 원문의 `오픈타입`과 `오픈 타입`을 모두 `오픈 타입` 하나로 집계합니다. |
| `-U`, `--user-dict FILE` | 사용자 단어 목록 파일(줄바꿈 또는 콤마 구분). |
| `-s`, `--substitute RULES` | 단어 교체·분해(`원본->교체본`, 콤마로 여러 개). 정확히 일치하는 단어에만 적용되며, 교체본에 공백이 있으면 공백 기준으로 분해되어 각각 집계됩니다. |
| `-k`, `--korean` | 한국어만 분석합니다. 지정하지 않으면 다국어 모드로 동작합니다. |
| `-t`, `--pos-tags TAGS` | 추출할 품사 태그(콤마 구분). 지정하면 기본값을 **대체**합니다. |

#### 분석 모드 (`-k`)

- **기본(다국어) 모드**: 한국어와 함께 영어 단어(2글자 이상, 소문자로 통일)를 추출합니다. `janome`이 설치되어 있으면 일본어 명사·동사·형용사도 추출합니다.
- **한국어 모드 (`-k`)**: 한국어 형태소 분석 결과만 사용합니다.

두 모드 모두 `\명령어`와 `{중괄호 안 텍스트}`(중첩 포함)는 형태소 분석을 거치지 않고 하나의 단어로 그대로 집계합니다. TeX 문서를 분석할 때 유용합니다.

#### 품사 태그 (`-t`)

기본값은 `NNG,NNP,NP,NR,VV,VA`이며, 동사·형용사는 기본형(`~다`)으로 복원됩니다.

| 태그 | 품사 | 태그 | 품사 |
| --- | --- | --- | --- |
| `NNG` | 일반명사 | `MAG` | 일반부사 |
| `NNP` | 고유명사 | `MAJ` | 접속부사 |
| `NP` | 대명사 | `MM` | 관형사 |
| `NR` | 수사 | `IC` | 감탄사 |
| `VV` | 동사 | `XR` | 어근 |
| `VA` | 형용사 | | |

명사만 뽑거나 부사를 더하려면 원하는 전체 목록을 직접 지정합니다.

```bash
python koreanwordcloudnlp.py -i input.txt -t NNG,NNP                 # 명사만
python koreanwordcloudnlp.py -i input.txt -t NNG,NNP,NP,NR,VV,VA,MAG # 기본값 + 일반부사
```

목록에 없는 태그를 주면 경고를 출력하지만 그대로 적용됩니다.

### 사용 예

```bash
# 상위 100개 단어만, 불용어 제외
python koreanwordcloudnlp.py -i book.txt -m 100 -x "것,수,등,때문" -o out.txt

# 제외어와 사용자 사전을 파일로 관리
python koreanwordcloudnlp.py -i book.txt -X stopwords.txt -U userdict.txt -o out.txt

# 복합어를 하나로 집계하고, 표기 변형을 통일
python koreanwordcloudnlp.py -i book.txt -u "오픈 타입,한글 조판" -s "TeX->텍스,LaTeX->라텍" -o out.txt

# 한국어만 분석 (영어·일본어 무시)
python koreanwordcloudnlp.py -k -i book.txt -o out.txt
```

### 참고 사항

- `-s`는 한글이 포함된 규칙의 경우 **완전히 일치하는 단어**에만 적용됩니다(부분 일치 아님). 영문·숫자로만 된 규칙은 대소문자를 구분하지 않고 단어 경계에서 적용됩니다.
- `-x`의 영문 제외어도 대소문자를 구분하지 않습니다.
- `-u`로 등록한 복합어는 `-s`를 별도로 지정할 필요가 없습니다. 둘이 겹치면 안내 메시지가 표시됩니다.
- `-X`, `-U` 파일을 찾을 수 없거나 읽지 못하면 조용히 무시됩니다. 경로를 확인하세요.

---

## 2. hgwordstitcher.py — 잘린 단어 복원(Stitching)

PDF 등에서 복사한 텍스트처럼 줄 끝에서 단어가 끊어진 텍스트를 복원하고, 들여쓰기·줄 길이·빈 줄을 분석하여 문단 경계를 추론합니다. 앞 줄의 마지막 어절과 뒷줄의 첫 어절이 Kiwi 판정상 한 단어이면 공백 없이 이어 붙이고, 영어 단어가 하이픈(`-`)으로 끊긴 경우에는 하이픈을 제거하여 합칩니다.

### 기본 사용법

```bash
# 파일 입력 → 파일 출력
python hgwordstitcher.py -i input.txt -o output.txt

# 표준 입력 → 표준 출력
cat input.txt | python hgwordstitcher.py > output.txt
```

기본적으로 문단마다 한 줄로 출력하며, 문단 사이에는 빈 줄을 넣습니다.

### 옵션

| 옵션 | 설명 |
| --- | --- |
| `-i`, `--input FILE` | 입력 파일(UTF-8). 생략하면 표준 입력. |
| `-o`, `--output FILE` | 출력 파일. 생략하면 표준 출력. |
| `-p`, `--precise-paragraph` | 더 섬세한 문단 구분. 문단이 나뉜 지점이라도 앞 문단이 종지부호(`.?!` 등)로 끝나지 않거나, 앞뒤 단어가 하나의 단어로 이어질 수 있으면 문단을 나누지 않습니다. 빈 줄로 나뉜 곳에도 적용됩니다. |
| `-l`, `--line-length [LENGTH]` | 출력 줄 길이 지정. `-l 80`처럼 값을 주면 그 길이로 줄바꿈하고, 숫자 없이 `-l`만 쓰면 입력에서 계산한 평균 줄 길이에 맞춥니다. 생략하면 문단당 한 줄입니다. |
| `-u`, `--user-words WORDS` | 사용자 정의 단어(콤마 구분). Kiwi가 잘못 판정하는 고유명사·전문용어를 보완합니다. |
| `-U`, `--user-dict-file FILE` | 사용자 사전 파일(줄바꿈 또는 콤마 구분). |
| `-m`, `--markdown` | 마크다운 구조 보존 모드(아래 참조). |
| `--keep-endpar STR` | 문단 강제 분리 기호. 기본값은 탭 두 개(`\t\t`). `\t`, `\n` 표기도 쓸 수 있습니다. |
| `--keep-startpar REGEX` | 이 정규식과 일치하는 줄로 **시작**하는 행은 이전 행과 병합하지 않고 새 문단으로 시작합니다. 세미콜론(`;`)으로 여러 패턴을 OR로 지정할 수 있습니다. |

### 문단 경계를 판단하는 기준

다음 중 하나에 해당하면 새 문단으로 봅니다(`-p`를 쓰면 위 설명대로 일부가 다시 병합됩니다).

1. 두 줄 사이에 빈 줄이 있다.
2. 줄이 들여쓰기(공백 또는 탭)로 시작한다.
3. 앞 줄이 짧다(상위 10% 줄 길이 평균의 85% 미만).
4. `--keep-startpar` 패턴과 일치한다.

큰따옴표(`"`, `“`)로 시작하는 줄은 단어 병합 판정에서 제외되어 이전 줄과 공백 없이 붙지 않습니다.

### 문단 강제 분리 기호 (`--keep-endpar`)

문단 끝에 이 기호를 직접 적어 두면 다음 줄이 이어지는 것처럼 보여도 문단을 나눕니다(빈 줄까지 함께 있는 경우 `-p`의 병합도 우회). 기호 자체는 출력에서 제거됩니다.

```bash
# 기본값(탭 2개) 대신 || 를 사용
python hgwordstitcher.py -p --keep-endpar "||" -i input.txt
```

### 시작 패턴으로 문단 분리 (`--keep-startpar`)

번호 목록처럼 특정 모양으로 시작하는 줄을 항상 새 문단으로 만들 때 사용합니다.

```bash
# "1. ", "2. " 로 시작하는 줄과 "제1장" 으로 시작하는 줄
python hgwordstitcher.py -p --keep-startpar "[0-9]+\.\s;제[0-9]+장" -i input.txt
```

### 마크다운 모드 (`-m`)

마크다운 문서의 구조는 그대로 두고 일반 문단 텍스트에만 복원을 적용합니다.

| 요소 | 처리 |
| --- | --- |
| YAML Frontmatter (`---` … `---`) | 그대로 보존 |
| 헤더 (`#`, `##` …) | 그대로 보존 |
| 코드 블록 (` ``` `, `~~~`, 4칸 들여쓰기) | 그대로 보존 |
| 리스트 (불릿·순번, 중첩 2단계까지) | 항목 내부의 잘린 줄만 병합 |
| 블록인용 (`>`) | `>`를 유지한 채 내부 문단에 복원 적용 |
| 일반 문단 | 단어 복원 및 문단 경계 추론 |

```bash
python hgwordstitcher.py -m -p -l 80 -i draft.md -o draft_fixed.md
```

### 사용 예

```bash
# 기본 복원
python hgwordstitcher.py -i pdf_copy.txt -o fixed.txt

# 문단 구분을 섬세하게 + 전문용어 보완
python hgwordstitcher.py -p -u "오픈타입,조판" -i pdf_copy.txt -o fixed.txt

# 80자 폭으로 재정렬
python hgwordstitcher.py -p -l 80 -i pdf_copy.txt -o fixed.txt

# 사용자 사전 파일 사용
python hgwordstitcher.py -p -U userdict.txt -i pdf_copy.txt -o fixed.txt
```

---

## 3. korwordcloud.tex — 워드클라우드 PDF 만들기

`koreanwordcloudnlp.py`의 출력을 `out.txt`로 저장한 뒤, 같은 폴더에서 `korwordcloud.tex`를 LuaLaTeX으로 컴파일하면 워드클라우드가 담긴 PDF가 만들어집니다. `standalone` 클래스를 사용하므로 결과물은 워드클라우드 크기에 딱 맞는 한 페이지입니다.

```bash
python koreanwordcloudnlp.py -i input.txt -m 150 -o out.txt
lualatex korwordcloud.tex
```

`lualatex` 또는 `latexmk -lualatex`로 컴파일하세요.

### 모양 바꾸기

기본 옵션은 템플릿 안의 `\mycmd` 정의 안에 있습니다. 필요에 따라 이 부분을 수정하세요.

| 옵션 | 설명 |
| --- | --- |
| `scale=2` | 전체 크기 배율 |
| `rotate=45` | 단어 회전 각도(템플릿에서 주석 처리되어 있음) |
| `margin=0.5pt` | 단어 사이 간격 |
| `usecolor` | 색상 사용 |
| `colors={...}` | `ninecolors`의 색상 이름 목록 |

글꼴은 `\sffamily\bfseries`로 지정되어 있습니다. 다른 입력 파일을 쓰려면 문서 본문의 `\mycmd{out.txt}`에서 파일 이름을 바꾸세요.

---

## 함께 쓰는 방법 (Workflow)

PDF에서 복사한 텍스트로 워드클라우드를 만드는 전체 흐름입니다.

```bash
# 1) 줄 끝에서 잘린 단어와 문단을 복원
python hgwordstitcher.py -p -i pdf_copy.txt -o fixed.txt

# 2) 복원된 텍스트에서 단어 빈도 추출
python koreanwordcloudnlp.py -i fixed.txt -m 150 -x "것,수,등" -o out.txt

# 3) 워드클라우드 PDF 생성
lualatex korwordcloud.tex
```

파이프로 1)과 2)를 이어서 실행할 수도 있습니다.

```bash
python hgwordstitcher.py -p -i pdf_copy.txt | python koreanwordcloudnlp.py -m 150 -o out.txt
```

## 문제 해결 (Troubleshooting)

- **`ModuleNotFoundError: No module named 'kiwipiepy'`**: `pip install -r requirements.txt`를 실행하세요.
- **일본어 단어가 추출되지 않음**: `janome`이 설치되어 있는지, `-k` 옵션을 쓰지 않았는지 확인하세요.
- **원하는 복합어가 쪼개져 나옴**: `-u` 또는 `-U`로 단어를 등록하세요.
- **문단이 너무 잘게 나뉘거나 너무 합쳐짐**: `-p`를 켜거나, `--keep-endpar`/`--keep-startpar`로 경계를 직접 지정하세요.
- **LaTeX 컴파일 오류**: `out.txt`가 UTF-8인지, 단어에 특수문자가 남아 있지 않은지 확인하세요. 특수문자는 기본적으로 자동 이스케이프됩니다.

## 라이선스 (License)

이 프로젝트는 [MIT 라이선스](LICENSE)로 배포됩니다.

이 프로젝트가 사용하는 `kiwipiepy`와 `janome`(둘 다 Apache-2.0)은 각자의 라이선스를 따르며, 이 저장소에 포함되어 있지 않고 `pip`로 별도 설치됩니다.
