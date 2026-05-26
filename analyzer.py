import os
import anthropic

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4000


def build_prompt(data: dict) -> str:
    company = data.get("company_name", "不明")
    code = data.get("code", "不明")
    stock_price = data.get("stock_price", "不明")
    dividend_yield = data.get("dividend_yield", "不明")
    per = data.get("per", "不明")
    pbr = data.get("pbr", "不明")
    roe = data.get("roe", "不明")
    market_cap = data.get("market_cap", "不明")

    results_text = ""
    for r in data.get("results", []):
        results_text += (
            f"  {r['year']}: 収益={r['revenue']}, 営業利益={r['op_profit']}, "
            f"当期純利益={r['net_profit']}, EPS={r['eps']}, ROE={r['roe']}\n"
        )
    if not results_text:
        results_text = "  データなし\n"

    dividends_text = ""
    for d in data.get("dividends", []):
        dividends_text += (
            f"  {d['year']}（{d['type']}）: 中間={d['interim']}円, "
            f"期末={d['yearend']}円, 合計={d['total']}円, 利回り={d['yield']}\n"
        )
    if not dividends_text:
        dividends_text = "  データなし\n"

    prompt = f"""あなたは日本株（高配当株）の銘柄分析アシスタントです。
以下のIRBANKから取得したデータをもとに、指定フォーマットで分析レポートを作成してください。

【取得データ】
会社名: {company}（{code}）
株価: {stock_price}
配当利回り（予）: {dividend_yield}
PER（予）: {per}
PBR: {pbr}
ROE（予）: {roe}
時価総額: {market_cap}

【業績推移】
{results_text}
【配当推移】
{dividends_text}

【出力ルール】
- 必ずファクトチェックをして真実を伝えること
- 取得データの範囲で回答し、情報が不足する項目は「不明」と明記すること
- 根拠のない推測はしないこと
- 忖度せず事実に基づくアドバイスをすること

【出力フォーマット】
以下のフォーマットを厳守してください。前後の挨拶や解説は不要です。

---

会社名：{company}（{code}）

購入アドバイス（100文字程度で忖度なしに高配当株として魅力があるかを評価）

**1. 最新の株価と配当利回り**
（取得データをそのまま記載）

**2. セクター／業種、アクティブorディフェンシブ**
（業種・セクターを記載。景気敏感株かディフェンシブ株かを明記すること）

**3. 事業内容**
（主要事業を簡潔に3〜5行で）

**4. 売上高は右肩上がりか**
（業績推移データをもとに傾向を評価）

**5. 営業利益は右肩上がりか**
（業績推移データをもとに傾向を評価）

**6. EPSは右肩上がりか**
（業績推移データをもとに傾向を評価）

**7. 過去10年間の配当金推移**
（以下のルールを厳守すること）
- 直近の2025年度（予想含む）から遡って、過去10年分を1年ずつ漏れなく記載
- 1年1行の形式を厳守
- 「右肩上がり」「成長傾向」などの分析・要約文は一切含めないこと
- データが見つからない年は「調査中」と記載
（出力例）
2016年：〇〇円
2017年：〇〇円
...
2025年（予）：〇〇円

**8. 累進配当か**
（累進配当に該当しない場合は、どんな状況だったか補足すること）

**9. 連続増配年数**

**10. DOEは何％か**

**11. 配当性向は何％か**

**12. 海外売上比率は何％か**

**13. 今後の見通し**

**14. 今後投資する上での不安材料**

**15. その他特記事項**

---
"""
    return prompt


def generate_report(data: dict) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return "エラー：APIキーが設定されていません。環境変数 ANTHROPIC_API_KEY を設定してください。"

    try:
        client = anthropic.Anthropic(api_key=api_key)
        prompt = build_prompt(data)
        message = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text
    except anthropic.AuthenticationError:
        return "エラー：APIキーが正しくありません。ANTHROPIC_API_KEY を確認してください。"
    except anthropic.APIError as e:
        return f"エラー：Claude APIでエラーが発生しました。（{e}）"
    except Exception as e:
        return f"エラー：レポート生成中に予期しないエラーが発生しました。（{e}）"
