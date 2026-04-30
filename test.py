import re


def extract_table_headers(html: str) -> list:
    """
    从公募/私募排排网表格HTML中提取列名（自动过滤无用列）
    返回：干净的列名列表
    """
    # 匹配 <div class="cell"> 内容
    pattern = re.compile(r'<div class="cell">([^<]+)<!', re.S)
    headers = []

    for match in pattern.finditer(html):
        title = match.group(1).strip()

        # 过滤空格、换行、空白
        if not title:
            continue

        # 过滤你不要的列
        if title in ["PK", "操作", "走势图"]:
            continue

        # 清理多余空格（比如“净值变动 ”这种）
        title = title.strip()
        headers.append(title)

    return headers


