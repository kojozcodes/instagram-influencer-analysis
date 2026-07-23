"""Excel (.xlsx) report generation with Japanese headers.

Column set follows the client's エーストリーム reference (spec section 10 + the
返答.pptx additions): identity, estimated demographics, engagement, 30-post
averages, feed/reel split, top-5 posts (last ~6 months), profile, status.
The demographic reliability columns (分析対象数/判定可能数/不明数) are omitted to
match the reference layout; re-enable via INCLUDE_RELIABILITY if requested.
"""
from __future__ import annotations

import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .models import AGE_BUCKETS, AnalysisRow

INCLUDE_RELIABILITY = False  # 分析対象数/判定可能数/不明数 — off to match エーストリーム

_BASE_HEADERS: list[str] = [
    "アカウント名",
    "表示名",
    "アカウントURL",
    "フォロワー数",
    "いいねエンゲージメント率（推定/％）",
    "エンゲージメント率（％）",
    "男性割合（推定）",
    "女性割合（推定）",
    "13-17歳男性割合（推定）",
    "18-24歳男性割合（推定）",
    "25-34歳男性割合（推定）",
    "35-44歳男性割合（推定）",
    "45-64歳男性割合（推定）",
    "13-17歳女性割合（推定）",
    "18-24歳女性割合（推定）",
    "25-34歳女性割合（推定）",
    "35-44歳女性割合（推定）",
    "45-64歳女性割合（推定）",
    "直近30投稿の平均いいね数",
    "直近30投稿の平均コメント数",
    "平均リール再生数",
    "直近12投稿のフィード平均いいね数",
    "直近12投稿のフィード平均コメント数",
    "直近12投稿のフィードエンゲージメント率（％）",
    "直近12投稿のリール平均いいね数",
    "直近12投稿のリール平均コメント数",
    "直近12投稿のリールエンゲージメント率（％）",
    "直近12投稿のリール平均再生数",
    "人気投稿1（直近6ヶ月）",
    "人気投稿2",
    "人気投稿3",
    "人気投稿4",
    "人気投稿5",
    "プロフィール",
    "ステータス",
    "エラー理由",
]

_RELIABILITY_HEADERS = ["分析対象数", "判定可能数", "不明数"]


def _headers() -> list[str]:
    if INCLUDE_RELIABILITY:
        # insert reliability columns right before エラー-related tail (after profile)
        idx = _BASE_HEADERS.index("プロフィール")
        return _BASE_HEADERS[:idx] + _RELIABILITY_HEADERS + _BASE_HEADERS[idx:]
    return list(_BASE_HEADERS)


HEADERS = _headers()

_HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
_HEADER_FONT = Font(color="FFFFFF", bold=True)
_ERROR_FILL = PatternFill("solid", fgColor="FCE4E4")
_NOTE_FONT = Font(italic=True, color="666666", size=9)


def _cell(v):
    return "" if v is None else v


def _row_values(r: AnalysisRow) -> list:
    d = r.demographics
    m = r.metrics
    g = d.grid
    top = list(m.top_posts) + [""] * 5

    values = [
        r.username,
        r.display_name,
        r.account_url,
        _cell(r.followers_count),
        _cell(m.like_engagement_rate),
        _cell(m.engagement_rate),
        _cell(d.male_ratio),
        _cell(d.female_ratio),
        *[_cell(g.get(f"male_{b}")) for b in AGE_BUCKETS],
        *[_cell(g.get(f"female_{b}")) for b in AGE_BUCKETS],
        _cell(m.avg_likes_30),
        _cell(m.avg_comments_30),
        _cell(m.avg_reels_views),
        _cell(m.feed_avg_likes),
        _cell(m.feed_avg_comments),
        _cell(m.feed_engagement_rate),
        _cell(m.reel_avg_likes),
        _cell(m.reel_avg_comments),
        _cell(m.reel_engagement_rate),
        _cell(m.reel_avg_views),
        *top[:5],
    ]
    if INCLUDE_RELIABILITY:
        values += [d.analysis_target_count, d.classifiable_count, d.unknown_count]
    values += [r.profile_text, r.status, r.error_reason]
    return values


def build_workbook(rows: list[AnalysisRow]) -> Workbook:
    wb = Workbook()
    ws = wb.active
    ws.title = "分析結果"

    note = "※男女比率・年代比率は公開情報に基づく推定値です（Instagram公式インサイト値ではありません）。リール再生数は取得可能な範囲で出力します。"
    ws.append([note])
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(HEADERS))
    ws.cell(row=1, column=1).font = _NOTE_FONT

    ws.append(HEADERS)
    for col in range(1, len(HEADERS) + 1):
        c = ws.cell(row=2, column=col)
        c.fill = _HEADER_FILL
        c.font = _HEADER_FONT
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for r in rows:
        ws.append(_row_values(r))
        if r.status == "エラー":
            excel_row = ws.max_row
            for col in range(1, len(HEADERS) + 1):
                ws.cell(row=excel_row, column=col).fill = _ERROR_FILL

    ws.freeze_panes = "D3"  # freeze header rows + first 3 identity columns
    for col in range(1, len(HEADERS) + 1):
        letter = get_column_letter(col)
        header = HEADERS[col - 1]
        width = min(max(len(header) * 1.4, 12), 34)
        ws.column_dimensions[letter].width = width

    return wb


def build_excel_bytes(rows: list[AnalysisRow]) -> bytes:
    wb = build_workbook(rows)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
