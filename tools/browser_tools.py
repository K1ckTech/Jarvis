import asyncio
from typing import Optional
from langchain_core.tools import tool
from playwright.async_api import async_playwright, Page, BrowserContext

_playwright = None
_browser = None
_context = None
_page = None

async def get_page():
    global _playwright, _browser, _context, _page
    if _page is None:
        try:
            _playwright = await async_playwright().start()
            _browser = await _playwright.chromium.launch(headless=True)
            _context = await _browser.new_context(
                viewport={'width': 1280, 'height': 800},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            _page = await _context.new_page()
        except Exception as e:
            raise Exception(f"Playwrightの初期化に失敗しました: {e}")
    return _page

@tool
async def browser_navigate(url: str) -> str:
    """指定したURLにブラウザで移動します。最初にページを開くときや別のURLに移動するときに使用します。"""
    try:
        page = await get_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        return f"URL [{url}] へ移動しました。現在のページタイトル: {await page.title()}"
    except Exception as e:
        return f"エラー: {e}"

@tool
async def browser_get_content() -> str:
    """現在のページのテキスト内容（HTMLから抽出された文章）を取得します。ページ内の情報や次の操作対象を探すときに使用します。"""
    try:
        page = await get_page()
        from bs4 import BeautifulSoup
        html = await page.content()
        soup = BeautifulSoup(html, "lxml")
        text = soup.get_text(separator="\n", strip=True)
        # LLMのコンテキスト制限を考慮し、最初の10000文字程度に制限
        return text[:10000] if len(text) > 10000 else text
    except Exception as e:
        return f"エラー: {e}"

@tool
async def browser_click(selector: str) -> str:
    """現在のページ内で、指定したCSSセレクタに一致する要素をクリックします。"""
    try:
        page = await get_page()
        await page.click(selector, timeout=5000)
        # クリック後、画面の遷移や読み込みが落ち着くまで少し待機
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=5000)
        except:
            pass
        return f"セレクタ [{selector}] をクリックしました。現在のタイトル: {await page.title()}"
    except Exception as e:
        return f"エラー: {e}"

@tool
async def browser_fill(selector: str, text: str) -> str:
    """指定したCSSセレクタの入力フォーム（input, textareaなど）に指定したテキストを入力します。"""
    try:
        page = await get_page()
        await page.fill(selector, text, timeout=5000)
        return f"セレクタ [{selector}] にテキスト [{text}] を入力しました。"
    except Exception as e:
        return f"エラー: {e}"

@tool
async def browser_evaluate(script: str) -> str:
    """現在のページ内で任意のJavaScriptを実行し、結果を文字列で返します。スクロールや複雑なDOM操作が必要な場合に使用します。"""
    try:
        page = await get_page()
        result = await page.evaluate(script)
        return f"実行結果: {result}"
    except Exception as e:
        return f"エラー: {e}"

browser_tools = [
    browser_navigate,
    browser_get_content,
    browser_click,
    browser_fill,
    browser_evaluate
]
