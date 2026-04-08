from bs4 import BeautifulSoup

from app.crawlers.utils.selector_parser import parse_list_items


def test_parse_list_items_supports_title_attr():
    html = """
    <div class="ListconC">
      <span>2026-01-05</span>
      <a href="/detail.html" title="深圳市工业和信息化局科技型企业孵化器管理办法">
        <em>1</em>深圳市工业和信息化局科技型企业孵化器管理办法
      </a>
    </div>
    """
    soup = BeautifulSoup(html, "html.parser")

    items = parse_list_items(
        soup,
        {
            "list_item": "div.ListconC",
            "title": "a",
            "title_attr": "title",
            "link": "a",
            "date": "span",
            "date_format": "%Y-%m-%d",
        },
        "http://gxj.sz.gov.cn",
    )

    assert len(items) == 1
    assert items[0].title == "深圳市工业和信息化局科技型企业孵化器管理办法"
    assert items[0].url == "http://gxj.sz.gov.cn/detail.html"


def test_parse_list_items_supports_link_rewrite():
    html = """
    <li>
      <span>2026-04-07</span>
      <a href="https://stic.sz.gov.cn/xxgk/tzgg/content/post_1.html">通知</a>
    </li>
    """
    soup = BeautifulSoup(html, "html.parser")

    items = parse_list_items(
        soup,
        {
            "list_item": "li",
            "title": "a",
            "link": "a",
            "link_replace_from": "https://stic.sz.gov.cn",
            "link_replace_to": "http://stic.sz.gov.cn",
            "date": "span",
            "date_format": "%Y-%m-%d",
        },
        "http://stic.sz.gov.cn",
    )

    assert len(items) == 1
    assert items[0].url == "http://stic.sz.gov.cn/xxgk/tzgg/content/post_1.html"
