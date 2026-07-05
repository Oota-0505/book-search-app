"""
robots.txt および meta robots タグの確認スクリプト
対象サイトのクローリング制限をチェックします
"""

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import time

# 対象サイトのベースURL
TARGET_SITES = {
    "岐阜市立図書館": "https://www1.gifu-lib.jp/",
    "可児市立図書館": "https://www.kani-lib.jp/",
    "三省堂書店（岐阜駅本屋）": "https://www.books-sanseido.jp/",
    "TSUTAYA（草叢BOOKS）": "https://store-tsutaya.tsite.jp/",
}

# 実際にスクレイピングしているURL
SCRAPING_URLS = {
    "岐阜市立図書館": [
        "https://www1.gifu-lib.jp/winj/opac/top.do",
        "https://www1.gifu-lib.jp/winj/opac/search-standard.do",
    ],
    "可児市立図書館": [
        "https://www.kani-lib.jp/csp/opw/OPW/OPWSRCH1.CSP",
        "https://www.kani-lib.jp/csp/opw/OPW/OPWSRCHLIST.CSP",
    ],
    "三省堂書店（岐阜駅本屋）": [
        "https://www.books-sanseido.jp/booksearch/BookSearchExec.action",
    ],
    "TSUTAYA（草叢BOOKS）": [
        "https://store-tsutaya.tsite.jp/search/result/select",
        "https://store-tsutaya.tsite.jp/search/result/",
        "https://store-tsutaya.tsite.jp/search/result/stock/result",
    ],
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def get_robots_txt(base_url: str) -> tuple:
    """
    robots.txtを取得
    
    Returns:
        (robots.txtの内容, ステータスコード)
    """
    try:
        robots_url = urljoin(base_url, "/robots.txt")
        response = requests.get(robots_url, headers=HEADERS, timeout=10)
        return response.text, response.status_code
    except Exception as e:
        return f"エラー: {str(e)}", 0


def check_meta_robots(url: str) -> dict:
    """
    指定URLのmeta robotsタグを確認
    
    Returns:
        meta robotsタグの情報
    """
    result = {
        "url": url,
        "has_meta_robots": False,
        "content": None,
        "error": None,
    }
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, "html.parser")
        meta_robots = soup.find("meta", attrs={"name": "robots"})
        
        if meta_robots:
            result["has_meta_robots"] = True
            result["content"] = meta_robots.get("content", "")
        
        return result
    except Exception as e:
        result["error"] = str(e)
        return result


def parse_robots_txt(robots_content: str) -> dict:
    """
    robots.txtの内容を解析
    
    Returns:
        解析結果の辞書
    """
    result = {
        "user_agents": [],
        "disallow_paths": [],
        "allow_paths": [],
        "crawl_delay": None,
        "sitemap": None,
    }
    
    current_user_agent = None
    
    for line in robots_content.split("\n"):
        line = line.strip()
        
        # コメント行をスキップ
        if line.startswith("#") or not line:
            continue
        
        # User-agent
        if line.lower().startswith("user-agent:"):
            current_user_agent = line.split(":", 1)[1].strip()
            if current_user_agent not in result["user_agents"]:
                result["user_agents"].append(current_user_agent)
        
        # Disallow
        elif line.lower().startswith("disallow:"):
            path = line.split(":", 1)[1].strip()
            if path:
                result["disallow_paths"].append(path)
        
        # Allow
        elif line.lower().startswith("allow:"):
            path = line.split(":", 1)[1].strip()
            if path:
                result["allow_paths"].append(path)
        
        # Crawl-delay
        elif line.lower().startswith("crawl-delay:"):
            delay = line.split(":", 1)[1].strip()
            result["crawl_delay"] = delay
        
        # Sitemap
        elif line.lower().startswith("sitemap:"):
            sitemap = line.split(":", 1)[1].strip()
            result["sitemap"] = sitemap
    
    return result


def check_path_allowed(robots_parsed: dict, path: str) -> bool:
    """
    指定パスがrobots.txtで許可されているかチェック
    
    Returns:
        True: 許可されている, False: 禁止されている
    """
    # Disallowが空の場合は全て許可
    if not robots_parsed["disallow_paths"]:
        return True
    
    # 各disallowパターンと照合
    for disallow_path in robots_parsed["disallow_paths"]:
        if disallow_path == "/":
            # "/" は全て禁止
            return False
        elif path.startswith(disallow_path):
            # パスがdisallowパターンに一致する場合
            # allowパターンで上書きされているかチェック
            for allow_path in robots_parsed["allow_paths"]:
                if path.startswith(allow_path):
                    return True
            return False
    
    return True


def main():
    """メイン処理"""
    print("=" * 80)
    print("robots.txt および meta robots タグの確認")
    print("=" * 80)
    print()
    
    all_sites_legal = True
    
    for site_name, base_url in TARGET_SITES.items():
        print(f"\n{'=' * 80}")
        print(f"【{site_name}】")
        print(f"ベースURL: {base_url}")
        print(f"{'=' * 80}\n")
        
        site_legal = True
        
        # 1. robots.txtの取得
        print("1. robots.txt の確認")
        print("-" * 80)
        robots_content, status_code = get_robots_txt(base_url)
        
        if status_code == 200:
            print(f"✅ robots.txt が見つかりました (ステータス: {status_code})")
            print(f"\nrobots.txt の内容:\n{robots_content}")
            
            # robots.txtの解析
            robots_parsed = parse_robots_txt(robots_content)
            print(f"\n解析結果:")
            print(f"  - User-Agent: {robots_parsed['user_agents']}")
            print(f"  - Disallow: {robots_parsed['disallow_paths']}")
            print(f"  - Allow: {robots_parsed['allow_paths']}")
            print(f"  - Crawl-delay: {robots_parsed['crawl_delay']}")
            print(f"  - Sitemap: {robots_parsed['sitemap']}")
            
            # スクレイピング対象URLのチェック
            print(f"\n2. スクレイピング対象URLの許可状況")
            print("-" * 80)
            scraping_urls = SCRAPING_URLS.get(site_name, [])
            
            for url in scraping_urls:
                parsed = urlparse(url)
                path = parsed.path
                
                is_allowed = check_path_allowed(robots_parsed, path)
                status_icon = "✅" if is_allowed else "❌"
                status_text = "許可" if is_allowed else "禁止"
                
                print(f"{status_icon} {url}")
                print(f"   パス: {path}")
                print(f"   ステータス: {status_text}")
                
                if not is_allowed:
                    site_legal = False
                    all_sites_legal = False
                print()
        elif status_code == 404:
            print(f"⚠️ robots.txt が見つかりませんでした (404)")
            print("   → robots.txtが存在しない場合、クローリングは制限されていません")
            print("   → この場合、スクレイピングは技術的には可能ですが、")
            print("     利用規約や法的な制約を確認する必要があります")
        else:
            print(f"❌ robots.txt の取得に失敗しました (ステータス: {status_code})")
            print(f"   エラー内容: {robots_content}")
        
        # 2. meta robotsタグの確認
        print(f"\n3. meta robots タグの確認")
        print("-" * 80)
        scraping_urls = SCRAPING_URLS.get(site_name, [])
        
        for url in scraping_urls[:2]:  # 最初の2つのURLのみ確認（負荷軽減）
            print(f"\nURL: {url}")
            meta_result = check_meta_robots(url)
            
            if meta_result["error"]:
                print(f"  ❌ エラー: {meta_result['error']}")
            elif meta_result["has_meta_robots"]:
                content = meta_result["content"]
                print(f"  ⚠️ meta robots タグが見つかりました")
                print(f"  content: {content}")
                
                # noindex, nofollow などのチェック
                if "noindex" in content.lower():
                    print(f"  ❌ noindex が設定されています（インデックス禁止）")
                    print(f"  ⚠️ 注意: このページはスクレイピングを推奨しません")
                    site_legal = False
                    all_sites_legal = False
                if "nofollow" in content.lower():
                    print(f"  ⚠️ nofollow が設定されています（リンク追跡禁止）")
                    print(f"  → スクレイピング自体は可能ですが、リンクを追跡しないでください")
            else:
                print(f"  ✅ meta robots タグは見つかりませんでした（制限なし）")
            
            time.sleep(1)  # サーバー負荷を考慮して1秒待機
        
        # サイトごとの判定
        print(f"\n{'=' * 80}")
        if site_legal:
            print(f"✅ 【{site_name}】: robots.txtとmeta robotsタグの確認結果、スクレイピングは許可されています")
        else:
            print(f"❌ 【{site_name}】: robots.txtまたはmeta robotsタグでスクレイピングが制限されています")
        print(f"{'=' * 80}")
        
        print()
        time.sleep(2)  # サイト間で2秒待機
    
    # 最終判定
    print("\n" + "=" * 80)
    print("【最終判定】")
    print("=" * 80)
    if all_sites_legal:
        print("✅ すべてのサイトで、robots.txtとmeta robotsタグの確認結果、")
        print("   スクレイピングは許可されています。")
        print("\n⚠️ ただし、以下の点に注意してください：")
        print("   1. robots.txtは技術的なガイドラインであり、法的な許可ではありません")
        print("   2. 各サイトの利用規約を確認してください")
        print("   3. サーバーに過度な負荷をかけないよう、適切な間隔でアクセスしてください")
        print("   4. 取得したデータの利用目的が各サイトの利用規約に準拠しているか確認してください")
    else:
        print("❌ 一部またはすべてのサイトで、スクレイピングが制限されています。")
        print("\n⚠️ 以下の対応を検討してください：")
        print("   1. 制限されているサイトへのスクレイピングを停止する")
        print("   2. 各サイトの運営者に連絡して、スクレイピングの許可を得る")
        print("   3. 公式APIが提供されている場合は、APIを利用する")
    print("=" * 80)


if __name__ == "__main__":
    main()

