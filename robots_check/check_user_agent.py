"""
User-Agent の robots.txt チェックスクリプト
アプリで使用しているUser-Agentが各サイトのrobots.txtでDisallowされていないか確認
"""

import requests
from urllib.parse import urljoin
import re

# アプリで使用しているUser-Agent
APP_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# 対象サイトのベースURL
TARGET_SITES = {
    "岐阜市立図書館": "https://www1.gifu-lib.jp/",
    "可児市立図書館": "https://www.kani-lib.jp/",
    "三省堂書店（岐阜駅本屋）": "https://www.books-sanseido.jp/",
    "TSUTAYA（草叢BOOKS）": "https://store-tsutaya.tsite.jp/",
}

HEADERS = {
    "User-Agent": APP_USER_AGENT
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


def parse_robots_txt(robots_content: str) -> dict:
    """
    robots.txtの内容を解析し、User-AgentごとのDisallow/Allowルールを抽出
    
    Returns:
        解析結果の辞書
        {
            "user_agents": {
                "User-Agent名": {
                    "disallow": [...],
                    "allow": [...],
                    "crawl_delay": ...
                }
            },
            "default": {
                "disallow": [...],
                "allow": [...],
                "crawl_delay": ...
            }
        }
    """
    result = {
        "user_agents": {},
        "default": {
            "disallow": [],
            "allow": [],
            "crawl_delay": None
        }
    }
    
    current_user_agent = None
    current_rules = None
    
    for line in robots_content.split("\n"):
        line = line.strip()
        
        # コメント行をスキップ
        if line.startswith("#") or not line:
            continue
        
        # User-agent
        if line.lower().startswith("user-agent:"):
            ua_name = line.split(":", 1)[1].strip()
            current_user_agent = ua_name
            if ua_name not in result["user_agents"]:
                result["user_agents"][ua_name] = {
                    "disallow": [],
                    "allow": [],
                    "crawl_delay": None
                }
            current_rules = result["user_agents"][ua_name]
        
        # Disallow
        elif line.lower().startswith("disallow:"):
            path = line.split(":", 1)[1].strip()
            if path and current_rules is not None:
                current_rules["disallow"].append(path)
            elif path:
                result["default"]["disallow"].append(path)
        
        # Allow
        elif line.lower().startswith("allow:"):
            path = line.split(":", 1)[1].strip()
            if path and current_rules is not None:
                current_rules["allow"].append(path)
            elif path:
                result["default"]["allow"].append(path)
        
        # Crawl-delay
        elif line.lower().startswith("crawl-delay:"):
            delay = line.split(":", 1)[1].strip()
            if current_rules is not None:
                current_rules["crawl_delay"] = delay
            else:
                result["default"]["crawl_delay"] = delay
    
    return result


def check_user_agent_disallowed(robots_parsed: dict, user_agent: str) -> dict:
    """
    指定されたUser-AgentがDisallowされているかチェック
    
    Returns:
        {
            "is_disallowed": bool,
            "matched_rules": list,
            "details": str
        }
    """
    result = {
        "is_disallowed": False,
        "matched_rules": [],
        "details": ""
    }
    
    # User-Agentのマッチング
    # 1. 完全一致
    # 2. ワイルドカード "*"
    # 3. 部分一致（User-Agent文字列に含まれるか）
    
    matched_ua = None
    
    # "*" をチェック（すべてのUser-Agentに適用）
    if "*" in robots_parsed["user_agents"]:
        matched_ua = "*"
    
    # 完全一致をチェック
    if user_agent in robots_parsed["user_agents"]:
        matched_ua = user_agent
    
    # 部分一致をチェック（User-Agent名が含まれるか）
    if matched_ua is None:
        for ua_name in robots_parsed["user_agents"].keys():
            if ua_name.lower() in user_agent.lower() or user_agent.lower() in ua_name.lower():
                matched_ua = ua_name
                break
    
    # マッチしたUser-Agentのルールを取得
    if matched_ua:
        rules = robots_parsed["user_agents"][matched_ua]
        result["matched_rules"] = rules["disallow"]
        result["details"] = f"User-Agent '{matched_ua}' のルールに一致"
        
        # Disallowが "/" の場合は全て禁止
        if "/" in rules["disallow"]:
            result["is_disallowed"] = True
            result["details"] += " - すべてのパスがDisallowされています"
    else:
        # マッチしない場合はデフォルトルール（通常は "*" のルール）を適用
        if "*" in robots_parsed["user_agents"]:
            rules = robots_parsed["user_agents"]["*"]
            result["matched_rules"] = rules["disallow"]
            result["details"] = "User-Agent '*' のルールに一致（デフォルト）"
        else:
            result["details"] = "該当するUser-Agentルールが見つかりませんでした"
    
    return result


def main():
    """メイン処理"""
    print("=" * 80)
    print("User-Agent の robots.txt チェック")
    print("=" * 80)
    print()
    print(f"アプリで使用しているUser-Agent:")
    print(f"  {APP_USER_AGENT}")
    print()
    
    all_sites_ok = True
    
    for site_name, base_url in TARGET_SITES.items():
        print(f"\n{'=' * 80}")
        print(f"【{site_name}】")
        print(f"ベースURL: {base_url}")
        print(f"{'=' * 80}\n")
        
        # robots.txtの取得
        robots_content, status_code = get_robots_txt(base_url)
        
        if status_code == 200:
            print("✅ robots.txt が見つかりました")
            print(f"\nrobots.txt の内容:\n{robots_content}\n")
            
            # robots.txtの解析
            robots_parsed = parse_robots_txt(robots_content)
            
            print("解析結果:")
            print(f"  定義されているUser-Agent: {list(robots_parsed['user_agents'].keys())}")
            print()
            
            # User-Agentのチェック
            print("User-Agent チェック:")
            print("-" * 80)
            ua_check = check_user_agent_disallowed(robots_parsed, APP_USER_AGENT)
            
            print(f"  マッチしたルール: {ua_check['details']}")
            print(f"  Disallowパス: {ua_check['matched_rules']}")
            
            if ua_check["is_disallowed"]:
                print(f"  ❌ このUser-AgentはすべてのパスでDisallowされています")
                print(f"  ⚠️ このサイトへのアクセスはrobots.txtで禁止されています")
                all_sites_ok = False
            elif ua_check["matched_rules"]:
                print(f"  ⚠️ このUser-Agentには一部のパスでDisallowルールが適用されています")
                print(f"  → 具体的なパスのチェックが必要です")
            else:
                print(f"  ✅ このUser-AgentにはDisallowルールが適用されていません")
                print(f"  → このUser-Agentでのアクセスは許可されています")
            
        elif status_code == 404:
            print("⚠️ robots.txt が見つかりませんでした (404)")
            print("  → robots.txtが存在しない場合、User-Agentによる制限はありません")
            print("  → ただし、利用規約の確認が必要です")
        else:
            print(f"❌ robots.txt の取得に失敗しました (ステータス: {status_code})")
            print(f"   エラー内容: {robots_content}")
            all_sites_ok = False
    
    # 最終判定
    print("\n" + "=" * 80)
    print("【最終判定】")
    print("=" * 80)
    if all_sites_ok:
        print("✅ すべてのサイトで、使用しているUser-AgentはDisallowされていません")
        print("\n⚠️ ただし、以下の点に注意してください：")
        print("   1. User-AgentがDisallowされていなくても、特定のパスがDisallowされている可能性があります")
        print("   2. 利用規約でスクレイピングが禁止されている可能性があります")
        print("   3. サーバーに過度な負荷をかけないよう、適切な間隔でアクセスしてください")
    else:
        print("❌ 一部またはすべてのサイトで、使用しているUser-AgentがDisallowされています")
        print("\n⚠️ 以下の対応を検討してください：")
        print("   1. 別のUser-Agentを使用する（ただし、利用規約に違反しない範囲で）")
        print("   2. サイト運営者に連絡して、スクレイピングの許可を得る")
        print("   3. 公式APIが提供されている場合は、APIを利用する")
    print("=" * 80)


if __name__ == "__main__":
    main()

