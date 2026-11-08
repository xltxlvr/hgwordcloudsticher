#!/usr/bin/env python3
# Version 13
# v13 변경 사항:
#   - argparse 도움말 문자열이 주석 처리로 잘려 보이던 문제 수정
#   - 다국어 모드에서 라틴 문자 단어가 이중 집계되던 버그 수정 (Kiwi의 SL 태그 활용)
#   - -s/-x 옵션의 라틴 단어 매칭을 대소문자 무관하게 처리
#   - -u/-U 로 등록한 복합어 처리 순서를 결정적(deterministic)으로 개선 (긴 단어 우선)
#   - LaTeX 특수문자 이스케이프 및 출력 포맷 파괴 문자 처리 추가
#   - 중괄호 {} 중첩 처리 개선
#   - -m 0 옵션이 무시되던 버그 수정
#   - 위치 인자 텍스트가 파이프된 stdin보다 우선하도록 우선순위 조정
import sys
import os
import argparse
import re
from collections import Counter
from kiwipiepy import Kiwi

_LATIN_ONLY_RE = re.compile(r'[A-Za-z0-9]+')
_LATIN_CHAR = r'[A-Za-z0-9]'

# 기본으로 추출할 품사 태그 (Kiwi 태그 체계 기준)
# NNG:일반명사 NNP:고유명사 NP:대명사 NR:수사 VV:동사 VA:형용사
DEFAULT_TARGET_TAGS = {'NNG', 'NNP', 'NP', 'NR', 'VV', 'VA'}

# 참고용: Kiwi에서 자주 쓰이는 품사 태그 설명 (-t 옵션 도움말에도 사용)
KNOWN_POS_TAGS = {
    'NNG': '일반명사', 'NNP': '고유명사', 'NP': '대명사', 'NR': '수사',
    'VV': '동사', 'VA': '형용사', 'MAG': '일반부사', 'MAJ': '접속부사',
    'MM': '관형사', 'IC': '감탄사', 'XR': '어근',
}


def _is_latin_only(s):
    """치환 대상 문자열이 라틴 알파벳/숫자로만 구성되어 있는지 확인합니다."""
    return bool(s) and _LATIN_ONLY_RE.fullmatch(s) is not None


# LaTeX 특수문자 -> 이스케이프 시퀀스
_LATEX_SPECIAL_RE = re.compile(r'([\\&%$#_{}~^])')


def _latex_escape_repl(m):
    c = m.group(1)
    if c == '\\':
        return r'\textbackslash{}'
    if c == '~':
        return r'\textasciitilde{}'
    if c == '^':
        return r'\textasciicircum{}'
    return '\\' + c


def escape_latex(word):
    """LaTeX 컴파일을 깨뜨릴 수 있는 특수문자(%, &, #, $, _, ~, ^, \\, {, })를 이스케이프합니다."""
    return _LATEX_SPECIAL_RE.sub(_latex_escape_repl, word)


def sanitize_for_wordcloud_format(word):
    """
    wordcloud 패키지가 읽는 "(word, count);" 포맷 자체를 깨뜨릴 수 있는 문자
    (쉼표, 소/괄호)를 전각(fullwidth) 문자로 치환합니다.
    이스케이프가 아니라 치환인 이유: 이스케이프 처리(\\, 등)는 이 포맷의 파서가
    아니라 LaTeX 컴파일러가 해석하는 것이므로, 포맷 구분자 자체를 보호하려면
    시각적으로 유사한 다른 문자로 바꿔주는 편이 안전합니다.
    """
    return (
        word.replace(',', '，')
            .replace('(', '（')
            .replace(')', '）')
            .replace(';', '；')
    )


def _substitute_one(current_word, old, new):
    """
    old를 current_word 안에서 치환합니다.

    - old가 라틴 문자/숫자로만 구성된 경우: 라틴 문자 기준 경계에서만 매치합니다.
      (한글 조사가 바로 붙은 "AI가" 같은 어절은 정상적으로 치환하되,
       "AIDS"처럼 다른 라틴 문자에 이어 붙은 경우는 오매치하지 않습니다.)
    - old에 한글 등이 포함된 경우: 형태소 분석기가 이미 조사/어미를 제거한
      정제된 토큰을 넘겨주므로, old와 current_word가 완전히 일치할 때만 치환합니다.
      (부분 문자열 매치를 쓰면 "이->그" 같은 규칙이 "고양이"의 "이"에도 걸려
       "고양그"가 되는 등의 오매치가 발생하므로, 정확히 같은 단어일 때만 적용합니다.)

    반환값: (치환된 문자열, 치환 발생 여부)
    """
    if _is_latin_only(old):
        # 다국어 모드에서는 영어 토큰이 소문자로 정규화되어 저장되므로,
        # 사용자가 -s/-x에 대문자를 섞어 입력해도 매치되도록 대소문자를 구분하지 않는다.
        pattern = re.compile(
            r'(?<!' + _LATIN_CHAR + r')' + re.escape(old) + r'(?!' + _LATIN_CHAR + r')',
            re.IGNORECASE,
        )
        if pattern.search(current_word):
            return pattern.sub(new, current_word), True
        return current_word, False
    else:
        if current_word == old:
            return new, True
        return current_word, False


def make_exclude_checker(exclude_set):
    """
    exclude_set 멤버십을 확인하는 함수를 반환합니다.
    라틴 문자로만 구성된 제외어는 대소문자를 구분하지 않고,
    그 외(한글 등)는 기존처럼 완전히 일치할 때만 제외합니다.
    """
    latin_lower = {w.lower() for w in exclude_set if _is_latin_only(w)}
    other_words = {w for w in exclude_set if not _is_latin_only(w)}

    def is_excluded(word):
        if _is_latin_only(word):
            return word.lower() in latin_lower
        return word in other_words

    return is_excluded


def apply_substitutions_to_words(words, substitutions, exclude_set, protected_words):
    """
    형태소 분석이 완료되어 기본형으로 복원된 단어 목록에 치환 및 분해 규칙을 적용합니다.
    단, -u로 지정된 띄어쓰기 포함 단어(protected_words)는 강제로 쪼개지 않습니다.
    """
    is_excluded = make_exclude_checker(exclude_set)
    final_words = []
    for w in words:
        current_word = w
        modified = False
        
        for old, new in substitutions:
            current_word, did_match = _substitute_one(current_word, old, new)
            if did_match:
                modified = True
        
        # -u로 지정되어 띄어쓰기가 포함된 원본 단어이고, 이번에 치환을 거치지 않았다면 쪼개지 않음
        if not modified and current_word in protected_words:
            if not is_excluded(current_word):
                final_words.append(current_word)
        else:
            # 그 외의 경우 (치환 후 띄어쓰기가 생겼거나 일반 단어인 경우) 공백 기준으로 분해
            for split_word in current_word.split():
                if split_word and not is_excluded(split_word):
                    final_words.append(split_word)
                
    return final_words

def _sorted_custom_words(custom_words):
    """
    custom_words(set)는 순회 순서가 실행마다 달라질 수 있으므로,
    "스크립트"/"타입 스크립트"처럼 서로 겹치는 복합어가 있을 때도
    항상 같은 결과가 나오도록 긴 단어(엄밀히는 공백 제거 기준 긴 단어)부터
    처리되도록 정렬한 리스트로 변환한다.
    """
    cleaned = [w.strip() for w in custom_words if w.strip()]
    return sorted(cleaned, key=lambda w: len(w.replace(' ', '')), reverse=True)


def apply_custom_words_to_kiwi(kiwi, custom_words):
    space_mapping = {}
    for w_clean in _sorted_custom_words(custom_words):
        if ' ' in w_clean:
            w_no_space = w_clean.replace(' ', '')
            space_mapping[w_no_space] = w_clean
            kiwi.add_user_word(w_no_space, 'NNP', 10.0)
        else:
            kiwi.add_user_word(w_clean, 'NNP', 10.0)
            
    return space_mapping

def preprocess_text(text, custom_words):
    for w_clean in _sorted_custom_words(custom_words):
        if ' ' in w_clean:
            w_no_space = w_clean.replace(' ', '')
            text = text.replace(w_clean, w_no_space)
    return text

def _extract_balanced_braces(text):
    r"""
    최상위(outermost) 중괄호 쌍 내부 텍스트를 균형을 고려해 추출한다.
    기존의 r'\{([^{}]+)\}' 정규식은 \textbf{안녕 \textit{하세요}}처럼
    중첩된 중괄호가 있으면 바깥쪽 중괄호를 매치하지 못해 '{', '}' 문자가
    본문에 그대로 남는 문제가 있었다. 이 함수는 중첩이 있어도 바깥쪽
    괄호 전체(중첩 내용 포함)를 하나의 블록으로 추출하고, 해당 구간
    전체를 원문에서 제거한 텍스트도 함께 돌려준다.
    (참고: 중첩된 안쪽 명령어까지 개별적으로 분리해내지는 않으며,
     바깥쪽 블록 하나로 뭉쳐서 취급한다.)
    """
    contents = []
    depth = 0
    start = None
    spans = []
    for i, ch in enumerate(text):
        if ch == '{':
            if depth == 0:
                start = i
            depth += 1
        elif ch == '}':
            if depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    contents.append(text[start + 1:i])
                    spans.append((start, i + 1))
                    start = None
            # depth가 이미 0인데 '}'가 나오는 경우(짝이 맞지 않는 경우)는 무시한다.

    if not spans:
        return contents, text

    pieces = []
    last_end = 0
    for s, e in spans:
        pieces.append(text[last_end:s])
        pieces.append(' ')
        last_end = e
    pieces.append(text[last_end:])
    clean_text = ''.join(pieces)

    return contents, clean_text


def extract_special_tokens(text):
    special_words = []
    
    # 1. 백슬래시로 시작하는 TeX Command 추출 (\문자열)
    tex_commands = re.findall(r'\\[a-zA-Z]+', text)
    for cmd in tex_commands:
        special_words.append(cmd)
            
    # 2. 중괄호 {} 내부 텍스트 추출 (중첩 중괄호도 안전하게 처리)
    text_wo_commands = re.sub(r'\\[a-zA-Z]+', ' ', text)
    brace_contents, clean_text = _extract_balanced_braces(text_wo_commands)
    for content in brace_contents:
        cleaned = content.strip()
        if cleaned:
            special_words.append(cleaned)
    
    return special_words, clean_text

def extract_keywords_korean(text, exclude_set, custom_words, substitutions, target_tags=None):
    if not text or not text.strip():
        return Counter()

    if target_tags is None:
        target_tags = DEFAULT_TARGET_TAGS

    special_words, text = extract_special_tokens(text)

    kiwi = Kiwi()
    space_mapping = apply_custom_words_to_kiwi(kiwi, custom_words)
    text = preprocess_text(text, custom_words)

    raw_words = list(special_words)
    tokens = kiwi.tokenize(text)
    
    for token in tokens:
        if token.tag in target_tags:
            word = token.form + "다" if token.tag.startswith('V') else token.form
            
            if word in space_mapping:
                word = space_mapping[word]
                
            raw_words.append(word)
                
    protected_words = set(space_mapping.values())
    
    final_words = apply_substitutions_to_words(raw_words, substitutions, exclude_set, protected_words)
    return Counter(final_words)

def extract_keywords_multilingual(text, exclude_set, custom_words, substitutions, target_tags=None):
    if not text or not text.strip():
        return Counter()

    if target_tags is None:
        target_tags = DEFAULT_TARGET_TAGS

    special_words, text = extract_special_tokens(text)
    raw_words = list(special_words)

    kiwi = Kiwi()
    space_mapping = apply_custom_words_to_kiwi(kiwi, custom_words)
    text = preprocess_text(text, custom_words)

    # 1. 한국어 + 영어 분석
    # 주의: 예전 버전은 Kiwi 토큰화 결과와 별개로 원문 전체에 정규식
    # r'[a-zA-Z]+' 를 다시 돌려 영어 단어를 추출했다. 그런데 -u로 등록한
    # 영어 사용자 단어(예: "AI")는 Kiwi가 이미 NNP로 토큰화하므로,
    # 정규식 재추출 시 같은 구간이 "AI"(NNP 결과)와 "ai"(정규식 소문자화
    # 결과) 두 개로 이중 집계되는 문제가 있었다.
    # Kiwi는 한 글자 구간에 하나의 태그만 부여하므로, 같은 tokenize() 결과
    # 안에서 라틴 문자 토큰(태그 'SL')도 함께 처리하면 구간이 절대
    # 겹치지 않아 이중 집계가 발생하지 않는다.
    for token in kiwi.tokenize(text):
        if token.tag in target_tags:
            word = token.form + "다" if token.tag.startswith('V') else token.form
            if word in space_mapping:
                word = space_mapping[word]
            raw_words.append(word)
        elif token.tag == 'SL' and _is_latin_only(token.form) and len(token.form) > 1:
            word = token.form.lower()
            if word in space_mapping:
                word = space_mapping[word]
            raw_words.append(word)

    # 2. 일본어 분석
    try:
        from janome.tokenizer import Tokenizer
        t = Tokenizer()
        jp_text_blocks = re.findall(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]+', text)
        jp_text = " ".join(jp_text_blocks)
        
        if jp_text:
            for token in t.tokenize(jp_text):
                pos = token.part_of_speech.split(',')[0]
                if pos in ['名詞', '動詞', '形容詞']:
                    base_form = token.base_form
                    if base_form == '*':
                        base_form = token.surface
                    raw_words.append(base_form)
    except ImportError:
        pass 

    protected_words = set(space_mapping.values())
    
    final_words = apply_substitutions_to_words(raw_words, substitutions, exclude_set, protected_words)
    return Counter(final_words)

def main():
    parser = argparse.ArgumentParser(description="한국어 빈도 분석 도구 (v12)")
    parser.add_argument('-i', '--input', type=str, help="분석할 입력 파일 경로")
    parser.add_argument('-o', '--output', type=str, help="결과를 저장할 출력 파일 경로")
    parser.add_argument('-m', '--max', type=int, help="출력할 최대 단어 수")
    parser.add_argument('-x', '--exclude', type=str, help="제외할 단어 목록 (콤마 구분)")
    parser.add_argument('-X', '--exclude-file', type=str, help="제외할 단어 목록 파일 경로")
    parser.add_argument('-u', '--user-word', type=str,
                         help="강제로 하나의 단어로 인식할 목록 (콤마 구분, 띄어쓰기 포함 가능). "
                              "예: '오픈 타입'을 주면 원문의 '오픈타입'(또는 '오픈 타입')을 "
                              "하나의 단어로 인식해 '오픈 타입'으로 집계합니다. 이 경우 -s는 필요 없습니다.")
    parser.add_argument('-U', '--user-dict', type=str, help="강제로 하나의 단어로 인식할 목록 파일 경로")
    parser.add_argument('-s', '--substitute', type=str,
                         help="단어 교체 또는 분해 (형식: '원본->교체본', 콤마로 다수 지정 가능). "
                              "정확히 일치하는 단어에만 적용됩니다. "
                              "복합어를 공백 포함 형태로 그대로 집계하고 싶다면 -u만으로 충분합니다.")
    parser.add_argument('-k', '--korean', action='store_true', help="분석 시 한국어만 분석 강제")
    parser.add_argument('-t', '--pos-tags', type=str,
                         help="추출할 품사 Kiwi 태그 목록. 지정 시 기본값을 대체합니다(추가가 아님). "
                         f"기본값: {','.join(sorted(DEFAULT_TARGET_TAGS))}. "
                         "예: 부사를 포함하려면 'NNG,NNP,NP,NR,VV,VA,MAG,MAJ'처럼 "
                         "기본값에 원하는 태그를 더해서 지정하세요.")
    parser.add_argument('text', nargs='?', type=str, help="직접 입력할 분석 텍스트")

    args = parser.parse_args()
    text = ""
    is_file_input = False

    if args.input:
        if not os.path.isfile(args.input):
            print(f"오류: 입력 파일 '{args.input}'을(를) 찾을 수 없습니다.", file=sys.stderr)
            sys.exit(1)
        try:
            with open(args.input, 'r', encoding='utf-8') as f:
                text = f.read()
            is_file_input = True  
        except Exception as e:
            print(f"오류: 파일을 읽는 중 문제가 발생했습니다. ({e})", file=sys.stderr)
            sys.exit(1)
    elif args.text:
        # stdin이 파이프로 연결되어 있어도(not isatty), 위치 인자로 텍스트를
        # 명시적으로 준 경우에는 그쪽을 우선한다. 예전 순서는 stdin 검사가
        # 먼저라, CI나 특정 터미널처럼 stdin이 tty가 아닌 환경에서 위치
        # 인자를 줘도 조용히 무시되고 빈 stdin을 읽는 문제가 있었다.
        text = args.text
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
    else:
        parser.print_help()
        sys.exit(1)

    # 단어 교체/분해 목록 구성
    substitutions = []
    if args.substitute:
        for rule in args.substitute.split(','):
            if '->' in rule:
                old_word, new_word = rule.split('->', 1)
                substitutions.append((old_word.strip(), new_word.strip()))

    # 제외 목록 구성
    exclude_set = set()
    if args.exclude:
        exclude_set.update([w.strip() for w in args.exclude.split(',') if w.strip()])
    if args.exclude_file:
        if os.path.isfile(args.exclude_file):
            try:
                with open(args.exclude_file, 'r', encoding='utf-8') as f:
                    content = f.read().replace(',', '\n')
                    exclude_set.update([w.strip() for w in content.split('\n') if w.strip()])
            except Exception:
                pass

    # 사용자 지정 단어 (사전) 구성
    custom_words = set()
    if args.user_word:
        custom_words.update([w.strip() for w in args.user_word.split(',') if w.strip()])
    if args.user_dict:
        if os.path.isfile(args.user_dict):
            try:
                with open(args.user_dict, 'r', encoding='utf-8') as f:
                    content = f.read().replace(',', '\n')
                    custom_words.update([w.strip() for w in content.split('\n') if w.strip()])
            except Exception:
                pass

    # -u로 등록한 복합어와 -s 치환 규칙이 중복되는 경우 안내
    # (예: -u "오픈 타입" -s "오픈타입->오픈 타입" 처럼 같은 단어를 이중으로 지정한 경우)
    custom_no_space_forms = {w.strip().replace(' ', '') for w in custom_words if w.strip()}
    for old_word, _ in substitutions:
        if old_word in custom_no_space_forms:
            print(
                f"안내: 치환 규칙 '{old_word}->...'는 -u로 이미 등록된 단어와 겹칩니다. "
                f"이런 경우 -u 지정만으로 공백 포함 형태로 집계되므로 이 -s 규칙은 불필요합니다.",
                file=sys.stderr
            )

    # 추출할 품사 태그 구성
    if args.pos_tags:
        target_tags = {t.strip().upper() for t in args.pos_tags.split(',') if t.strip()}
        unknown_tags = target_tags - set(KNOWN_POS_TAGS.keys())
        if unknown_tags:
            print(
                f"안내: 알려지지 않은 품사 태그가 포함되어 있습니다: {', '.join(sorted(unknown_tags))}. "
                f"Kiwi 태그 표기가 맞는지 확인해주세요. (예: {', '.join(sorted(KNOWN_POS_TAGS.keys()))})",
                file=sys.stderr
            )
    else:
        target_tags = DEFAULT_TARGET_TAGS

    # 분석
    if not args.korean:
        word_counts = extract_keywords_multilingual(text, exclude_set, custom_words, substitutions, target_tags)
    else:
        word_counts = extract_keywords_korean(text, exclude_set, custom_words, substitutions, target_tags)

    # 정렬 및 개수 자르기
    sorted_items = sorted(word_counts.items(), key=lambda item: (-item[1], item[0]))
    if args.max is not None:
        if args.max < 0:
            print(
                f"안내: -m 값은 0 이상이어야 합니다 (입력값: {args.max}). 전체 결과를 출력합니다.",
                file=sys.stderr
            )
        else:
            # 0을 포함해 그대로 적용한다. (예전 코드는 `> 0` 조건이라 -m 0이
            # "0개 출력"이 아니라 "제한 없음"으로 조용히 무시되었다.)
            sorted_items = sorted_items[:args.max]

    # 출력 포맷팅
    # word에 LaTeX 특수문자(%, &, # 등)나 이 출력 포맷의 구분자로 쓰이는
    # 쉼표/괄호가 섞여 있으면 그대로 내보낼 경우 wordcloud 파싱 또는 LaTeX
    # 컴파일이 깨질 수 있으므로, 포맷 보호 -> LaTeX 이스케이프 순서로 처리한다.
    output_lines = []
    for word, count in sorted_items:
        safe_word = escape_latex(sanitize_for_wordcloud_format(word))
        formatted_word = f'{{{safe_word}}}' if ' ' in safe_word else safe_word
        output_lines.append(f"({formatted_word}, {count})")

    output_content = ";\n".join(output_lines)
    if output_content:
        output_content += "\n"

    # 결과 출력
    if args.output:
        try:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(output_content)
        except Exception as e:
            print(f"오류: 출력 파일을 저장하는 중 문제가 발생했습니다. ({e})", file=sys.stderr)
            sys.exit(1)
    else:
        sys.stdout.write(output_content)

if __name__ == "__main__":
    main()