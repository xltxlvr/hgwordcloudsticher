#!/usr/bin/env python3
# version 2.1.0: --keep-startpar 플래그 추가로 특정 정규식 패턴으로 시작하는 문단의 병합 억제 기능 지원
# version 2.0.9: --keep-endpar 플래그 추가로 문단 강제 분리 기호 커스텀 기능 지원
# version 2.0.8: 문단 끝 \t\t와 빈 줄이 함께 쓰인 경우 -p 옵션 병합 우회 및 탭 문자 제거 기능 추가
# version 2.0.7: YAML Frontmatter 인식 강화 (BOM 문제 및 선행 빈 줄 허용 등으로 인한 빈 줄 삽입 버그 수정)
# version 2.0.6: 큰따옴표(", “)로 시작하는 행은 이전 행과의 단어 병합(kiwi 검수)을 무시하도록 수정
# version 2.0.5: -m 옵션 사용 시 마크다운 YAML 헤더(Frontmatter) 보존 기능 추가
# version 2.0.4: -p 옵션이 빈 줄로 나뉜 문단에도 종지부호 기반 재검토를 적용하도록 수정
# version 2.0.3: -l 옵션 줄 길이 지정 무시되는 삼항 연산자 버그 수정
# version 2.0.2: kiwi 중복 연산 제거, 단어 병합 논리 일관성 확보, 인용구 빈 줄 보존 버그 수정
# version 2.0.1: -p bug fix
# version 2.0.0: -m 옵션으로 마크다운 구조 보존 기능 추가
"""
hgwordstitcher
텍스트 개행 오류와 단어 잘림(한국어/영어 혼용)을 복원하고,
들여쓰기 및 줄 길이 분석을 통해 문단 경계를 지능적으로 추론.

-m/--markdown 옵션 사용 시, 마크다운 문서의 구조적 요소
(헤더, 코드블록, 리스트, 블록인용, YAML Frontmatter)를 인식하여 그 형태를 보존하면서
문단 텍스트에만 단어잘림 복원 및 문단 경계 추론을 적용한다.
"""

import re
import sys
import argparse
import string
import textwrap
from kiwipiepy import Kiwi

__version__ = "2.1.1"

TERMINAL_PUNCT = '.?!:;。？！”’」』】)"\''

# ---------------------------------------------------------------------------
# 마크다운 구조 인식용 정규식
# ---------------------------------------------------------------------------
FENCE_RE = re.compile(r'^(\s{0,3})(`{3,}|~{3,})')
HEADER_RE = re.compile(r'^#{1,6}(\s|$)')
BULLET_RE = re.compile(r'^(\s*)([-*+])\s+()')
ORDERED_RE = re.compile(r'^(\s*)(\d{1,9}[.)])\s+()')
BLOCKQUOTE_RE = re.compile(r'^(\s{0,3})>[ \t]?')


def _is_list_marker(line: str):
    return BULLET_RE.match(line) or ORDERED_RE.match(line)


def _would_merge_as_one_word(kiwi: Kiwi, w1: str, w2: str) -> bool:
    combined = w1 + w2
    try:
        spaced = kiwi.space(combined)
    except Exception:
        return False

    char_count = 0
    boundary_idx = len(w1)

    for i, char in enumerate(spaced):
        if char != ' ':
            char_count += 1
            if char_count == boundary_idx:
                return not (i + 1 < len(spaced) and spaced[i + 1] == ' ')

    return False


def _check_merge(kiwi: Kiwi, prev_line: str, stripped: str, keep_endpar: str = '\t\t'):
    if stripped.startswith('"') or stripped.startswith('“'):
        return False, prev_line, False

    w1 = prev_line.split()[-1] if prev_line.split() else ""
    w2 = stripped.split()[0] if stripped.split() else ""

    if not w1 or not w2:
        return False, prev_line, False

    if (w1.endswith('-') and len(w1) > 1 and
            w1[-2] in string.ascii_letters and w2[0] in string.ascii_letters):
        # prev_line 끝에 keep_endpar가 보존되어 있을 경우 '-' 문자만 정확히 제거
        if prev_line.endswith(keep_endpar):
            idx = prev_line.rfind('-')
            if idx != -1:
                return True, prev_line[:idx] + prev_line[idx+1:], False
        return True, prev_line[:-1], False

    kiwi_merge = _would_merge_as_one_word(kiwi, w1, w2)
    if kiwi_merge:
        return True, prev_line, True

    return False, prev_line, False


def _parse_user_words(raw: str) -> list:
    words = []
    for line in raw.splitlines():
        for token in line.split(','):
            token = token.strip()
            if token:
                words.append(token)
    return words


def restore_pdf_text(
    text: str,
    precise_paragraph: bool = False,
    line_length: int = 0,
    user_words: list = None,
    keep_endpar: str = '\t\t',
    keep_startpar: re.Pattern = None,
) -> str:
    kiwi = Kiwi()

    if user_words:
        for word in user_words:
            try:
                kiwi.add_user_word(word, tag='NNP')
            except Exception:
                pass

    # 잠재적인 BOM(Byte Order Mark) 제거
    text = text.lstrip('\ufeff').replace('\x0c', '\n')
    lines = text.splitlines()

    valid_lengths = [len(l.strip()) for l in lines if len(l.strip()) > 10]
    if valid_lengths:
        valid_lengths.sort()
        top_10 = valid_lengths[int(len(valid_lengths) * 0.9):] or valid_lengths
        full_width = sum(top_10) / len(top_10)
        short_line_threshold = full_width * 0.85
    else:
        full_width = 0
        short_line_threshold = 0

    result_lines = []
    buffer_empty_lines = 0
    prev_raw_len = 0

    for line in lines:
        stripped = line.strip()

        if not stripped:
            if result_lines:
                buffer_empty_lines += 1
            continue

        # 실제 텍스트가 있으면서 우측 끝이 keep_endpar로 끝나는 경우 기호 보존
        if line.rstrip(' \r\n').endswith(keep_endpar):
            stripped += keep_endpar

        if not result_lines:
            result_lines.append(stripped)
            prev_raw_len = len(stripped)
            continue

        prev_line = result_lines[-1]
        can_merge_no_space, new_prev_line, kiwi_merge = _check_merge(kiwi, prev_line, stripped, keep_endpar)
        
        w1 = prev_line.split()[-1] if prev_line.split() else ""
        ends_with_terminal = bool(w1) and w1[-1] in TERMINAL_PUNCT

        is_indented = line.startswith(' ') or line.startswith('\t')
        is_short_line = prev_raw_len > 0 and (prev_raw_len < short_line_threshold)
        has_blank_line = buffer_empty_lines > 0

        prev_ends_with_dt = prev_line.endswith(keep_endpar)
        is_start_break = bool(keep_startpar and keep_startpar.match(line))
        
        force_break = is_start_break
        if prev_ends_with_dt and has_blank_line:
            force_break = True

        is_paragraph_break = has_blank_line or is_indented or is_short_line or is_start_break

        if is_paragraph_break and precise_paragraph and not force_break:
            if (not ends_with_terminal) or kiwi_merge:
                is_paragraph_break = False

        if is_paragraph_break:
            if prev_ends_with_dt:
                result_lines[-1] = prev_line[:-len(keep_endpar)]  # 문단 끝이면 기호 삭제
            
            # 원래 텍스트에 빈 줄이 있었거나, 
            # 정규식 패턴(--keep-startpar) 강제 분리가 아닌 일반 문단 분리일 때만 빈 줄 추가
            if has_blank_line or not is_start_break:
                if result_lines[-1] != "":
                    result_lines.append("")
                    
            result_lines.append(stripped)
        elif can_merge_no_space:
            result_lines[-1] = new_prev_line + stripped
        else:
            result_lines[-1] = prev_line + " " + stripped

        buffer_empty_lines = 0
        prev_raw_len = len(stripped)

    if result_lines and result_lines[-1].endswith(keep_endpar):
        result_lines[-1] = result_lines[-1][:-len(keep_endpar)]

    if line_length == 0:
        return "\n".join(result_lines)

    if line_length == -1:
        wrap_width = int(round(full_width)) if full_width > 0 else 80
    else:
        wrap_width = line_length

    formatted_lines = []
    for paragraph in result_lines:
        if paragraph == "":
            formatted_lines.append("")
            continue
        wrapped = textwrap.fill(
            paragraph,
            width=wrap_width,
            break_long_words=False,
            break_on_hyphens=False,
        )
        formatted_lines.append(wrapped)

    return "\n".join(formatted_lines)


# ---------------------------------------------------------------------------
# 마크다운 모드(-m)
# ---------------------------------------------------------------------------

def _stitch_paragraph_lines(kiwi, stripped_lines, raw_lines, precise_paragraph,
                             full_width, short_line_threshold, keep_endpar='\t\t', keep_startpar=None):
    result_lines = [stripped_lines[0]]
    prev_raw_len = len(stripped_lines[0])

    for k in range(1, len(stripped_lines)):
        stripped = stripped_lines[k]
        raw = raw_lines[k]
        prev_line = result_lines[-1]

        prev_ends_with_dt = prev_line.endswith(keep_endpar)
        is_start_break = bool(keep_startpar and keep_startpar.match(raw))
        
        force_break = prev_ends_with_dt or is_start_break

        can_merge_no_space, new_prev_line, kiwi_merge = _check_merge(kiwi, prev_line, stripped, keep_endpar)

        w1 = prev_line.split()[-1] if prev_line.split() else ""
        ends_with_terminal = bool(w1) and w1[-1] in TERMINAL_PUNCT

        is_indented = raw.startswith(' ') or raw.startswith('\t')
        is_short_line = prev_raw_len > 0 and (prev_raw_len < short_line_threshold)
        is_paragraph_break = is_indented or is_short_line or is_start_break

        if is_paragraph_break and precise_paragraph and not force_break:
            if (not ends_with_terminal) or kiwi_merge:
                is_paragraph_break = False

        if is_paragraph_break:
            if prev_ends_with_dt:
                result_lines[-1] = prev_line[:-len(keep_endpar)]  # 문단 끝이면 기호 삭제
            result_lines.append(stripped)
        elif can_merge_no_space:
            result_lines[-1] = new_prev_line + stripped
        else:
            result_lines[-1] = prev_line + " " + stripped

        prev_raw_len = len(stripped)

    if result_lines and result_lines[-1].endswith(keep_endpar):
        result_lines[-1] = result_lines[-1][:-len(keep_endpar)]

    return result_lines


def _stitch_no_break(kiwi, lines):
    if not lines:
        return ''
    result = lines[0]
    for stripped in lines[1:]:
        if not result.split():
            result = (result + stripped) if result == '' else (result + ' ' + stripped)
            continue
        can_merge_no_space, new_result, _ = _check_merge(kiwi, result, stripped)
        if can_merge_no_space:
            result = new_result + stripped
        else:
            result = result + " " + stripped
    return result


def _split_markdown_blocks(lines):
    blocks = []
    i = 0
    n = len(lines)

    # --- YAML Frontmatter 인식 로직 강화 ---
    start_i = 0
    while start_i < n and not lines[start_i].strip():
        start_i += 1
    
    if start_i < n and lines[start_i].strip() == '---':
        frontmatter_lines = []
        for j in range(start_i + 1):
            frontmatter_lines.append(lines[j])
        
        temp_i = start_i + 1
        closed = False
        while temp_i < n:
            frontmatter_lines.append(lines[temp_i])
            line_stripped = lines[temp_i].strip()
            if line_stripped in ('---', '...'):
                closed = True
                temp_i += 1
                break
            temp_i += 1
        
        if closed:
            blocks.append(('yaml_frontmatter', frontmatter_lines))
            i = temp_i
        else:
            # 닫히지 않은 경우 YAML 헤더가 아니라고 간주
            i = 0
            blocks = []

    while i < n:
        line = lines[i]
        stripped = line.strip()

        if stripped == '':
            blocks.append(('blank', ['']))
            i += 1
            continue

        fm = FENCE_RE.match(line)
        if fm:
            fence_char = fm.group(2)[0]
            fence_len = len(fm.group(2))
            block_lines = [line]
            i += 1
            close_re = re.compile(r'^\s{0,3}' + re.escape(fence_char) + '{' + str(fence_len) + r',}\s*$')
            while i < n:
                block_lines.append(lines[i])
                closed = bool(close_re.match(lines[i]))
                i += 1
                if closed:
                    break
            blocks.append(('fence', block_lines))
            continue

        if HEADER_RE.match(stripped):
            blocks.append(('header', [line]))
            i += 1
            continue

        if BLOCKQUOTE_RE.match(line):
            block_lines = [line]
            i += 1
            while i < n and BLOCKQUOTE_RE.match(lines[i]):
                block_lines.append(lines[i])
                i += 1
            blocks.append(('blockquote', block_lines))
            continue

        indent = len(line) - len(line.lstrip(' '))
        is_list_start = bool(_is_list_marker(line))

        if indent >= 4 and not is_list_start:
            block_lines = [line]
            i += 1
            while i < n:
                l2 = lines[i]
                if l2.strip() == '':
                    j = i
                    while j < n and lines[j].strip() == '':
                        j += 1
                    if j < n and (len(lines[j]) - len(lines[j].lstrip(' '))) >= 4:
                        block_lines.extend(lines[i:j])
                        i = j
                        continue
                    break
                if (len(l2) - len(l2.lstrip(' '))) >= 4:
                    block_lines.append(l2)
                    i += 1
                else:
                    break
            blocks.append(('indent_code', block_lines))
            continue

        if is_list_start:
            block_lines = [line]
            i += 1
            base_indent = indent
            while i < n:
                l2 = lines[i]
                if l2.strip() == '':
                    j = i
                    while j < n and lines[j].strip() == '':
                        j += 1
                    if j < n:
                        nxt = lines[j]
                        nxt_indent = len(nxt) - len(nxt.lstrip(' '))
                        nxt_is_item = bool(_is_list_marker(nxt))
                        if nxt_indent > base_indent or (nxt_indent == base_indent and nxt_is_item):
                            block_lines.extend(lines[i:j])
                            i = j
                            continue
                    break
                l2_indent = len(l2) - len(l2.lstrip(' '))
                l2_is_item = bool(_is_list_marker(l2))
                if l2_indent < base_indent:
                    break
                if l2_indent == base_indent and not l2_is_item:
                    break
                block_lines.append(l2)
                i += 1
            blocks.append(('list', block_lines))
            continue

        block_lines = [line]
        i += 1
        while i < n:
            l2 = lines[i]
            if l2.strip() == '':
                break
            if (HEADER_RE.match(l2.strip()) or FENCE_RE.match(l2) or
                    BLOCKQUOTE_RE.match(l2) or _is_list_marker(l2)):
                break
            if (len(l2) - len(l2.lstrip(' '))) >= 4:
                break
            block_lines.append(l2)
            i += 1
        blocks.append(('paragraph', block_lines))

    return blocks


def _process_list_block(kiwi, blines, depth=0, max_depth=2):
    out = []
    i = 0
    n = len(blines)

    first_line = next((l for l in blines if l.strip() != ''), None)
    if first_line is None:
        return ['']
    fm = _is_list_marker(first_line)
    base_indent = len(fm.group(1))

    while i < n:
        line = blines[i]
        if line.strip() == '':
            out.append('')
            i += 1
            continue

        m = _is_list_marker(line)
        if not m or (len(m.group(1)) != base_indent):
            out.append(line.strip())
            i += 1
            continue

        marker_prefix = line[:m.end()]
        first_text = line[m.end():].strip()
        content_col = len(marker_prefix)

        child_raw = []
        i += 1
        while i < n:
            nxt = blines[i]
            if nxt.strip() == '':
                j = i
                while j < n and blines[j].strip() == '':
                    j += 1
                if j < n and (len(blines[j]) - len(blines[j].lstrip(' '))) >= content_col:
                    child_raw.append('')
                    i += 1
                    continue
                break
            indent2 = len(nxt) - len(nxt.lstrip(' '))
            if indent2 < content_col:
                break
            child_raw.append(nxt[content_col:] if len(nxt) >= content_col else nxt.strip())
            i += 1

        item_text_lines = []
        nested_lines = []
        in_nested = False
        for cl in child_raw:
            if cl.strip() == '':
                if in_nested:
                    nested_lines.append(cl)
                continue
            if _is_list_marker(cl):
                in_nested = True
            if in_nested:
                nested_lines.append(cl)
            else:
                item_text_lines.append(cl.strip())

        item_full = [first_text] + item_text_lines
        merged_item_text = _stitch_no_break(kiwi, item_full)

        out.append((marker_prefix + merged_item_text) if merged_item_text else marker_prefix.rstrip())

        if nested_lines:
            if depth < max_depth - 1:
                nested_out = _process_list_block(kiwi, nested_lines, depth=depth + 1, max_depth=max_depth)
            else:
                nested_out = [nl.strip() if nl.strip() else '' for nl in nested_lines]
            indent_str = ' ' * content_col
            for nl in nested_out:
                out.append(indent_str + nl if nl else '')

    return out


def restore_markdown_text(
    text: str,
    precise_paragraph: bool = False,
    line_length: int = 0,
    user_words: list = None,
    keep_endpar: str = '\t\t',
    keep_startpar: re.Pattern = None,
) -> str:
    kiwi = Kiwi()

    if user_words:
        for word in user_words:
            try:
                kiwi.add_user_word(word, tag='NNP')
            except Exception:
                pass

    # 잠재적인 BOM(Byte Order Mark) 제거
    text = text.lstrip('\ufeff').replace('\x0c', '\n')
    raw_lines = text.splitlines()

    valid_lengths = [len(l.strip()) for l in raw_lines if len(l.strip()) > 10]
    if valid_lengths:
        valid_lengths.sort()
        top_10 = valid_lengths[int(len(valid_lengths) * 0.9):] or valid_lengths
        full_width = sum(top_10) / len(top_10)
        short_line_threshold = full_width * 0.85
    else:
        full_width = 0
        short_line_threshold = 0

    blocks = _split_markdown_blocks(raw_lines)

    out_lines = []
    for btype, blines in blocks:
        if btype == 'blank':
            out_lines.append('')

        elif btype in ('fence', 'header', 'indent_code', 'yaml_frontmatter'):
            out_lines.extend(blines)

        elif btype == 'paragraph':
            stripped = []
            for l in blines:
                s = l.strip()
                if s and l.rstrip(' \r\n').endswith(keep_endpar):
                    s += keep_endpar
                stripped.append(s)
                
            merged = _stitch_paragraph_lines(kiwi, stripped, blines, precise_paragraph,
                                              full_width, short_line_threshold, keep_endpar, keep_startpar)
            out_lines.append(merged[0])
            for m in merged[1:]:
                out_lines.append('')
                out_lines.append(m)

        elif btype == 'blockquote':
            sub_paragraphs = []
            current_sub = []
            
            for l in blines:
                m = BLOCKQUOTE_RE.match(l)
                content = l[m.end():] if m else l
                if content.strip() == '':
                    if current_sub:
                        sub_paragraphs.append(current_sub)
                        current_sub = []
                    sub_paragraphs.append([])
                else:
                    current_sub.append((l, content))
                    
            if current_sub:
                sub_paragraphs.append(current_sub)
                
            for sp in sub_paragraphs:
                if not sp:
                    out_lines.append('>')
                else:
                    raws = [x[0] for x in sp]
                    stripped = []
                    for x in sp:
                        s = x[1].strip()
                        if s and x[1].rstrip(' \r\n').endswith(keep_endpar):
                            s += keep_endpar
                        stripped.append(s)
                        
                    merged = _stitch_paragraph_lines(kiwi, stripped, raws, precise_paragraph,
                                                      full_width, short_line_threshold, keep_endpar, keep_startpar)
                    out_lines.append('> ' + merged[0] if merged[0] else '>')
                    for m in merged[1:]:
                        out_lines.append('>')
                        out_lines.append('> ' + m if m else '>')

        elif btype == 'list':
            out_lines.extend(_process_list_block(kiwi, blines))

    if line_length == 0:
        return "\n".join(out_lines)

    if line_length == -1:
        wrap_width = int(round(full_width)) if full_width > 0 else 80
    else:
        wrap_width = line_length

    final_blocks = _split_markdown_blocks(out_lines)
    wrapped = []
    for btype, blines in final_blocks:
        if btype in ('fence', 'header', 'indent_code', 'blank', 'yaml_frontmatter'):
            wrapped.extend(blines)

        elif btype == 'blockquote':
            for l in blines:
                m = BLOCKQUOTE_RE.match(l)
                content = l[m.end():] if m else ''
                if not content.strip():
                    wrapped.append('>')
                    continue
                w = textwrap.fill(content, width=max(wrap_width - 2, 10),
                                   break_long_words=False, break_on_hyphens=False)
                wrapped.extend('> ' + wl for wl in w.splitlines())

        elif btype == 'list':
            for l in blines:
                if l.strip() == '':
                    wrapped.append('')
                    continue
                m = _is_list_marker(l)
                if m:
                    prefix = l[:m.end()]
                    body = l[m.end():]
                    w = textwrap.fill(
                        body, width=max(wrap_width - len(prefix), 10),
                        initial_indent='', subsequent_indent=' ' * len(prefix),
                        break_long_words=False, break_on_hyphens=False,
                    )
                    wl = w.splitlines()
                    wrapped.append((prefix + wl[0]) if wl else prefix.rstrip())
                    wrapped.extend(wl[1:])
                else:
                    wrapped.append(l)

        else:
            for l in blines:
                if l.strip() == '':
                    wrapped.append('')
                    continue
                w = textwrap.fill(l, width=wrap_width, break_long_words=False, break_on_hyphens=False)
                wrapped.extend(w.splitlines())

    return "\n".join(wrapped)


def main():
    parser = argparse.ArgumentParser(
        description=f"[hgwordstitcher v{__version__}] 텍스트의 페이지와 줄넘김 잘린 단어를 복원"
    )

    parser.add_argument(
        "-i", "--input",
        type=str,
        default=None,
        help="입력 파일 경로 (지정하지 않으면 표준 입력 사용)"
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        default=None,
        help="출력 파일 경로 (지정하지 않으면 표준 출력 사용)"
    )
    parser.add_argument(
        "-p", "--precise-paragraph",
        action="store_true",
        default=False,
        help=(
            "좀 더 섬세한 문단 구분: 나뉜 앞 문단의 마지막 문장이 종지부호(.?! 등)로 "
            "끝나지 않거나, 앞뒤 단어가 kiwi 판정상 하나의 단어로 이어질 수 있다면 "
            "문단을 나누지 않은 것으로 처리 (기본값: 끔)"
        )
    )
    parser.add_argument(
        "-l", "--line-length",
        nargs='?',
        type=int,
        const=-1,
        default=0,
        metavar="LENGTH",
        help=(
            "줄바꿈 포맷팅 길이. 값을 지정하면(예: -l 80) 해당 길이에 맞추며, "
            "숫자 없이 -l만 입력하면 내부 계산된 평균 길이에 맞춤 "
            "(지정하지 않으면 문단마다 한 줄 출력)"
        )
    )
    parser.add_argument(
        "-u", "--user-words",
        type=str,
        default=None,
        help=(
            "콤마(,)로 구분한 사용자 정의 단어 목록. kiwi가 단어 잘림/문단 경계를 "
            "잘못 판정하는 고유명사·전문용어 등을 보완할 때 사용"
        )
    )
    parser.add_argument(
        "-U", "--user-dict-file",
        type=str,
        default=None,
        help=(
            "사용자 사전 파일 경로. 파일 안의 단어는 개행 또는 콤마(,)로 구분"
        )
    )
    parser.add_argument(
        "-m", "--markdown",
        action="store_true",
        default=False,
        help=(
            "마크다운 구조 보존 모드. 헤더(#, ##...), 코드블록(``` 및 4칸 들여쓰기), "
            "리스트(불릿/순번, 중첩 2단계까지), 블록인용(>)의 형태는 건드리지 않고 "
            "일반 문단 텍스트에 대해서만 단어잘림 복원 및 문단 경계 추론을 적용한다."
        )
    )
    parser.add_argument(
        "--keep-endpar",
        type=str,
        default='\t\t',
        help=(
            "문단 강제 분리 기호 (기본값: 탭 두 개). "
            "터미널에서 따옴표로 감싸서 전달 가능 (예: --keep-endpar \"||\")"
        )
    )
    parser.add_argument(
        "--keep-startpar",
        type=str,
        default=None,
        help="문단 병합을 억제할 시작 정규식 패턴 (예: \"  [\\d]+\\.\")"
    )

    args = parser.parse_args()

    # CLI 환경에서 이스케이프 문자 그대로 입력될 경우를 처리
    keep_endpar = args.keep_endpar.replace('\\t', '\t').replace('\\n', '\n')
    
    keep_startpar = None
    if args.keep_startpar:
        try:
            # 세미콜론(;)으로 구분된 패턴들을 분리하고 양쪽 공백 제거
            patterns = [p.strip() for p in args.keep_startpar.split(';') if p.strip()]
            # 각 패턴을 괄호로 묶고 파이프(|)로 연결하여 OR 조건 생성
            if patterns:
                combined_pattern = "|".join(f"({p})" for p in patterns)
                keep_startpar = re.compile(combined_pattern)
        except re.error as e:
            print(f"Regex Error (--keep-startpar): {e}", file=sys.stderr)
            sys.exit(1)

    try:
        if args.input:
            with open(args.input, 'r', encoding='utf-8') as f:
                input_text = f.read()
        else:
            input_text = sys.stdin.read()

        if not input_text.strip():
            return

        user_words = []
        if args.user_words:
            user_words.extend(_parse_user_words(args.user_words))
        if args.user_dict_file:
            with open(args.user_dict_file, 'r', encoding='utf-8') as f:
                user_words.extend(_parse_user_words(f.read()))
        user_words = list(dict.fromkeys(user_words))

        restore_fn = restore_markdown_text if args.markdown else restore_pdf_text

        restored_text = restore_fn(
            input_text,
            precise_paragraph=args.precise_paragraph,
            line_length=args.line_length,
            user_words=user_words,
            keep_endpar=keep_endpar,
            keep_startpar=keep_startpar,
        )

        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(restored_text + "\n")
        else:
            sys.stdout.write(restored_text + "\n")

    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()